"""El contexto del llamador llega a una integración pasando por el ENGINE.

Los tests de los handlers del catálogo arman `IntegrationContext` a mano y
nunca pasan por `AgentRuntime`: por eso nadie vio que `caller_context` llegaba
como `{agent, session, connections, secrets}` — sin `sender_phone`, y con las
credenciales de la corrida. Acá la corrida es real (runtime armado desde YAML,
catálogo en disco); lo único falso es el patrón, que llama la tool de una.
"""

import httpx
import respx
import yaml

from astromesh.integrations.executor import HttpActionExecutor
from astromesh.runtime.engine import AgentRuntime

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: quien
      description: "Quién escribe"
      handler: "python:tests.test_caller_context_engine:espia"
      parameters: {}
    - name: ping
      description: "Lee algo"
      request: {method: GET, path: "/ping"}
"""

CONTEXTO = {
    "channel": "whatsapp",
    "sender": "+5491100000000",
    "sender_phone": "+5491100000000",
    "contact_name": "Ana",
    # Del runtime: un handler no las ve nunca.
    "_provider_override": {"name": "openai", "key": "sk-no-se-ve"},
    "_nexus_run_token": "run-token-no-se-ve",
}

ESPERADO = {
    "channel": "whatsapp",
    "sender": "+5491100000000",
    "sender_phone": "+5491100000000",
    "contact_name": "Ana",
}

VISTO: list[dict] = []


async def espia(args, ctx):
    VISTO.append(dict(ctx.caller_context))
    return {"ok": True}


def _agente(prefetch=None):
    spec = {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["quien", "ping"],
            }
        ],
    }
    if prefetch:
        spec["prefetch"] = prefetch
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "demo-agent", "version": "0.1.0"},
        "spec": spec,
    }


async def _runtime(tmp_path, monkeypatch, agent_config):
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
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(agent_config))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "demo-agent" in runtime._agents, runtime._agent_errors
    return runtime


async def _correr(runtime, tool=None):
    agente = runtime._agents["demo-agent"]

    async def fake_execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        if tool:
            await tool_fn(tool, {})
        return {"answer": "listo", "steps": []}

    agente._pattern.execute = fake_execute
    return await agente.run(
        "hola",
        session_id="s1",
        context=dict(CONTEXTO),
        connections={"demo_conn": {"access_token": "TOKEN-DE-LA-CORRIDA"}},
    )


async def test_el_handler_ve_quien_escribe_por_el_camino_del_modelo(tmp_path, monkeypatch):
    VISTO.clear()
    rt = await _runtime(tmp_path, monkeypatch, _agente())

    await _correr(rt, tool="demo_quien")

    assert VISTO == [ESPERADO]
    visto = VISTO[0]
    assert "connections" not in visto
    assert "secrets" not in visto
    assert not [k for k in visto if k.startswith("_")]


@respx.mock
async def test_el_prefetch_le_pasa_quien_escribe_a_la_integracion(tmp_path, monkeypatch):
    # El prefetch sólo corre acciones `request: GET` (validar_prefetch), que no
    # tienen handler: se mira lo que recibe el executor, que es lo que un
    # handler recibiría.
    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    recibido: list[dict] = []
    original = HttpActionExecutor.execute

    async def espia_executor(self, *a, caller_context=None, **kw):
        recibido.append(dict(caller_context or {}))
        return await original(self, *a, caller_context=caller_context, **kw)

    monkeypatch.setattr(HttpActionExecutor, "execute", espia_executor)
    rt = await _runtime(tmp_path, monkeypatch, _agente([{"name": "x", "tool": "demo_ping"}]))

    await _correr(rt)

    assert recibido == [ESPERADO]
