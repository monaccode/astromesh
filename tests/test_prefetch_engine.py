"""`spec.prefetch`: búsquedas de solo lectura antes del LLM.

Los helpers son los de tests/test_confirmacion_engine.py: un catálogo en disco
con una integración `demo`, HTTP falso con respx y un runtime armado desde YAML.
"""

import copy

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
      description: "Lee algo"
      request: {method: GET, path: "/ping", query: {q: "{q}"}}
    - name: write_thing
      description: "Escribe algo"
      writes: true
      request: {method: POST, path: "/thing"}
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
                "actions": ["ping", "write_thing"],
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


def _agente(prefetch, **spec_extra):
    agente = copy.deepcopy(AGENT)
    agente["spec"]["prefetch"] = prefetch
    agente["spec"].update(spec_extra)
    return agente


async def _runtime(tmp_path, monkeypatch, agent_config):
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(agent_config))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


def _no_carga(runtime, texto):
    assert "demo-agent" not in runtime._agents
    error = str(runtime._agent_errors["demo-agent"])
    assert "prefetch" in error, error
    assert texto in error, error


async def test_una_tool_que_el_agente_no_tiene_no_carga(tmp_path, monkeypatch):
    rt = await _runtime(tmp_path, monkeypatch, _agente([{"name": "x", "tool": "demo_nada"}]))
    _no_carga(rt, "demo_nada")


async def test_una_escritura_no_carga(tmp_path, monkeypatch):
    rt = await _runtime(tmp_path, monkeypatch, _agente([{"name": "x", "tool": "demo_write_thing"}]))
    _no_carga(rt, "GET")


async def test_un_name_repetido_no_carga(tmp_path, monkeypatch):
    pf = [{"name": "x", "tool": "demo_ping"}, {"name": "x", "tool": "demo_ping"}]
    rt = await _runtime(tmp_path, monkeypatch, _agente(pf))
    _no_carga(rt, "'x'")


async def test_una_accion_en_confirm_no_carga(tmp_path, monkeypatch):
    agente = _agente([{"name": "x", "tool": "demo_ping"}])
    agente["spec"]["tools"][0]["confirm"] = ["ping"]
    rt = await _runtime(tmp_path, monkeypatch, agente)
    _no_carga(rt, "confirm")


async def test_un_prefetch_valido_carga(tmp_path, monkeypatch):
    pf = [{"name": "x", "tool": "demo_ping", "when": "sender_phone", "arguments": {"q": "1"}}]
    rt = await _runtime(tmp_path, monkeypatch, _agente(pf))
    assert rt._agents["demo-agent"]._prefetch == [
        {"name": "x", "tool": "demo_ping", "arguments": {"q": "1"}, "when": "sender_phone"}
    ]


async def test_un_agente_sin_prefetch_carga_igual(tmp_path, monkeypatch):
    rt = await _runtime(tmp_path, monkeypatch, copy.deepcopy(AGENT))
    assert rt._agents["demo-agent"]._prefetch == []
