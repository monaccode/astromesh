"""Contención de credenciales, extremo a extremo.

Lo que se verifica acá no es una convención sino el contrato de §5.4 del
spec: el material de credencial entra por `connections`, firma un request y
muere ahí.
"""

import logging

import httpx
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

SECRET = "SUPER-SECRETO-9Z"

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: "demo de seguridad"}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Hace ping al servicio de demostración"
      request: {method: GET, path: "/ping"}
    - name: fetch
      description: "Trae un recurso por su identificador de path"
      parameters:
        resource: {type: string, description: "Identificador del recurso", required: true}
      request: {method: GET, path: "/r/{resource}"}
"""

AGENT = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "sec-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "conn_a",
                "actions": ["ping", "fetch"],
            }
        ],
    },
}


async def _runtime(tmp_path, monkeypatch, agent_config=AGENT):
    import astromesh.runtime.engine as engine_module
    from astromesh.integrations import IntegrationCatalog

    root = tmp_path / "catalog"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "integration.yaml").write_text(MANIFEST)
    catalog = IntegrationCatalog()
    catalog.discover(root)
    monkeypatch.setattr(engine_module, "default_catalog", lambda: catalog)

    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "sec-agent.agent.yaml").write_text(yaml.safe_dump(agent_config))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


@respx.mock
async def test_credential_reaches_the_wire_but_not_the_result(tmp_path, monkeypatch):
    route = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"conn_a": {"access_token": SECRET}}}
    )
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in str(result)


@respx.mock
async def test_credential_never_appears_in_the_trace(tmp_path, monkeypatch):
    from astromesh.observability.tracing import TracingContext

    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    tracing = TracingContext(agent_name="sec-agent", session_id="s1")
    span = tracing.start_span("tool.call", {"tool": "demo_ping"})
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"conn_a": {"access_token": SECRET}}}
    )
    span.set_attribute("tool_args", {})
    span.set_attribute("tool_result", str(result))
    tracing.finish_span(span)
    assert SECRET not in str(getattr(span, "attributes", {}))


@respx.mock
async def test_credential_is_not_in_debug_logs(tmp_path, monkeypatch, caplog):
    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    with caplog.at_level(logging.DEBUG):
        await tools.execute("demo_ping", {}, {"connections": {"conn_a": {"access_token": SECRET}}})
    assert SECRET not in caplog.text


async def test_agent_cannot_reach_a_connection_it_did_not_declare(tmp_path, monkeypatch):
    """El bundle puede traer varias conexiones; el agente sólo usa la suya."""
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"conn_b": {"access_token": SECRET}}}
    )
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == "credential_missing"


@respx.mock
async def test_traversal_argument_cannot_escape_the_base_path(tmp_path, monkeypatch):
    route = respx.get(url__startswith="https://api.demo.test/").mock(
        return_value=httpx.Response(200, json={})
    )
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_fetch",
        {"resource": "../../admin/keys"},
        {"connections": {"conn_a": {"access_token": SECRET}}},
    )
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == "bad_request"
    assert not route.called


@respx.mock
async def test_slash_in_path_argument_is_rejected_by_default(tmp_path, monkeypatch):
    route = respx.get(url__startswith="https://api.demo.test/").mock(
        return_value=httpx.Response(200, json={})
    )
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_fetch",
        {"resource": "a/b"},
        {"connections": {"conn_a": {"access_token": SECRET}}},
    )
    assert result["success"] is False
    assert not route.called


async def test_run_without_connections_does_not_crash(tmp_path, monkeypatch):
    """Retrocompatibilidad: `connections` ausente es `{}`, no un error."""
    runtime = await _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute("demo_ping", {}, {"agent": "sec-agent", "session": "s"})
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == "credential_missing"
