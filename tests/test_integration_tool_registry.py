import httpx
import respx

from astromesh.core.tools import ToolRegistry, ToolType
from astromesh.integrations import errors
from astromesh.integrations.credentials import CredentialResolver
from astromesh.integrations.manifest import load_manifest

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Ping al servicio"
      request: {method: GET, path: "/ping"}
    - name: write_thing
      description: "Escribe"
      writes: true
      request: {method: POST, path: "/thing"}
"""


def _registry(tmp_path):
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    manifest = load_manifest(path)
    registry = ToolRegistry()
    registry.register_integration_tool(
        name="demo_ping",
        manifest=manifest,
        action=manifest.action("ping"),
        connection="demo_conn",
        resolver=CredentialResolver(None),
    )
    return registry, manifest


def test_registers_with_integration_type(tmp_path):
    registry, _ = _registry(tmp_path)
    assert registry._tools["demo_ping"].tool_type == ToolType.INTEGRATION
    assert registry._tools["demo_ping"].integration_config["action"] == "ping"
    assert registry._tools["demo_ping"].integration_config["connection"] == "demo_conn"


def test_schema_uses_action_description_and_parameters(tmp_path):
    registry, _ = _registry(tmp_path)
    schema = next(s for s in registry.get_tool_schemas() if s["function"]["name"] == "demo_ping")
    assert schema["function"]["description"] == "Ping al servicio"
    assert schema["function"]["parameters"]["type"] == "object"


def test_writes_action_sets_requires_approval(tmp_path):
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    manifest = load_manifest(path)
    registry = ToolRegistry()
    registry.register_integration_tool(
        name="demo_write_thing",
        manifest=manifest,
        action=manifest.action("write_thing"),
        connection="c",
        resolver=CredentialResolver(None),
    )
    assert registry._tools["demo_write_thing"].requires_approval is True


@respx.mock
async def test_execute_uses_connections_from_context(tmp_path):
    route = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"pong": True})
    )
    registry, _ = _registry(tmp_path)
    result = await registry.execute(
        "demo_ping",
        {},
        {"agent": "a", "session": "s", "connections": {"demo_conn": {"access_token": "T"}}},
    )
    assert result["success"] is True
    assert result["data"] == {"pong": True}
    assert route.calls[0].request.headers["Authorization"] == "Bearer T"


async def test_execute_without_connection_returns_credential_missing(tmp_path):
    registry, _ = _registry(tmp_path)
    result = await registry.execute("demo_ping", {}, {"agent": "a", "session": "s"})
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == errors.CREDENTIAL_MISSING


async def test_execute_never_raises_on_unknown_connection(tmp_path):
    registry, _ = _registry(tmp_path)
    result = await registry.execute(
        "demo_ping", {}, {"connections": {"otra": {"access_token": "T"}}}
    )
    assert result["success"] is False


@respx.mock
async def test_rate_limit_still_applies_to_integration_tools(tmp_path):
    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    manifest = load_manifest(path)
    registry = ToolRegistry()
    registry.register_integration_tool(
        name="demo_ping",
        manifest=manifest,
        action=manifest.action("ping"),
        connection="c",
        resolver=CredentialResolver(None),
        rate_limit={"window_seconds": 60, "max_calls": 1},
    )
    ctx = {"connections": {"c": {"access_token": "T"}}}
    first = await registry.execute("demo_ping", {}, ctx)
    second = await registry.execute("demo_ping", {}, ctx)
    assert first["success"] is True
    assert "error" in second and "Rate limit" in second["error"]
