import logging

import httpx
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Ping"
      request: {method: GET, path: "/ping"}
    - name: pong
      description: "Pong"
      request: {method: GET, path: "/pong"}
"""

AGENT = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "demo-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["ping"],
            }
        ],
    },
}


def _catalog(tmp_path):
    from astromesh.integrations import IntegrationCatalog

    root = tmp_path / "catalog"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "integration.yaml").write_text(MANIFEST)
    catalog = IntegrationCatalog()
    catalog.discover(root)
    return catalog


async def _runtime(tmp_path, agent_config, monkeypatch):
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(agent_config))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


async def test_allowlisted_action_is_registered_with_underscore_name(tmp_path, monkeypatch):
    runtime = await _runtime(tmp_path, AGENT, monkeypatch)
    tools = runtime._agents["demo-agent"]._tools
    assert "demo_ping" in tools._tools
    assert "demo_pong" not in tools._tools


async def test_action_outside_allowlist_is_not_exposed_to_the_model(tmp_path, monkeypatch):
    runtime = await _runtime(tmp_path, AGENT, monkeypatch)
    names = {s["function"]["name"] for s in runtime._agents["demo-agent"]._tools.get_tool_schemas()}
    assert names == {"demo_ping"}


async def test_unknown_integration_warns_and_skips(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0]["name"] = "no_existe"
    with caplog.at_level(logging.WARNING):
        runtime = await _runtime(tmp_path, config, monkeypatch)
    assert runtime._agents["demo-agent"]._tools._tools == {}
    assert "no_existe" in caplog.text


async def test_unknown_action_skips_only_that_action(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0]["actions"] = ["ping", "no_existe"]
    with caplog.at_level(logging.WARNING):
        runtime = await _runtime(tmp_path, config, monkeypatch)
    tools = runtime._agents["demo-agent"]._tools._tools
    assert "demo_ping" in tools
    assert "no_existe" in caplog.text


async def test_missing_actions_key_warns_and_skips_integration(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0].pop("actions")
    with caplog.at_level(logging.WARNING):
        runtime = await _runtime(tmp_path, config, monkeypatch)
    assert runtime._agents["demo-agent"]._tools._tools == {}
    assert "actions" in caplog.text


async def test_missing_connection_key_warns_and_skips_integration(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0].pop("connection")
    with caplog.at_level(logging.WARNING):
        runtime = await _runtime(tmp_path, config, monkeypatch)
    assert runtime._agents["demo-agent"]._tools._tools == {}
    assert "connection" in caplog.text


@respx.mock
async def test_connections_bundle_reaches_the_tool(tmp_path, monkeypatch):
    route = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"pong": True})
    )
    runtime = await _runtime(tmp_path, AGENT, monkeypatch)
    tools = runtime._agents["demo-agent"]._tools
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"demo_conn": {"access_token": "T"}}}
    )
    assert result["success"] is True
    assert route.calls[0].request.headers["Authorization"] == "Bearer T"


async def test_run_accepts_connections_and_defaults_to_empty(tmp_path, monkeypatch):
    import inspect

    from astromesh.runtime.engine import Agent

    assert "connections" in inspect.signature(AgentRuntime.run).parameters
    assert "connections" in inspect.signature(Agent.run).parameters
    assert inspect.signature(AgentRuntime.run).parameters["connections"].default is None
