"""`spec.prefetch`: búsquedas de solo lectura antes del LLM.

Los helpers son los de tests/test_confirmacion_engine.py: un catálogo en disco
con una integración `demo`, HTTP falso con respx y un runtime armado desde YAML.
"""

import copy

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


class _Respuesta:
    content = "listo"
    tool_calls = None
    model = "test"
    provider = "test"
    latency_ms = 1
    cost = 0.0
    usage = None


async def _correr_capturando(runtime, context, connections=None):
    """Una corrida que llama al modelo una vez y captura el system prompt."""
    agente = runtime._agents["demo-agent"]
    capturado = {}

    async def fake_execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        resp = await model_fn([{"role": "user", "content": "x"}], [])
        return {"answer": resp.content, "steps": []}

    async def spy_route(messages, tools=None, **kw):
        capturado["system"] = messages[0]["content"]
        return _Respuesta()

    agente._pattern.execute = fake_execute
    agente._routers["default"].route = spy_route
    resultado = await agente.run(
        "hola",
        session_id="s1",
        context=context,
        connections=connections or {"demo_conn": {"access_token": "t"}},
    )
    return capturado["system"], resultado


PREFETCH_ENCADENADO = [
    {
        "name": "uno",
        "tool": "demo_ping",
        "when": "sender_phone",
        "arguments": {"q": "{{ sender_phone }}"},
    },
    {
        "name": "dos",
        "tool": "demo_ping",
        "when": "prefetch.uno and prefetch.uno.success and prefetch.uno.data.rows",
        "arguments": {"q": "{{ prefetch.uno.data.rows[0] }}"},
    },
]


@respx.mock
async def test_corre_en_orden_encadenado_y_llega_al_prompt(tmp_path, monkeypatch):
    ruta = respx.get("https://api.demo.test/ping").mock(
        side_effect=[
            httpx.Response(200, json={"rows": ["A"]}),
            httpx.Response(200, json={"rows": ["B"]}),
        ]
    )
    sistema = "UNO={{ prefetch.uno.data.rows[0] }} DOS={{ prefetch.dos.data.rows[0] }}"
    rt = await _runtime(
        tmp_path, monkeypatch, _agente(PREFETCH_ENCADENADO, prompts={"system": sistema})
    )

    system, resultado = await _correr_capturando(rt, {"sender_phone": "+54"})

    assert system == "UNO=A DOS=B"
    assert [c.request.url.params["q"] for c in ruta.calls] == ["+54", "A"]
    spans = [s for s in resultado["trace"]["spans"] if s["name"] == "tool.prefetch"]
    assert [s["attributes"]["tool"] for s in spans] == ["demo_ping", "demo_ping"]


@respx.mock
async def test_when_falso_no_corre_y_no_crea_la_clave(tmp_path, monkeypatch):
    ruta = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"rows": []})
    )
    sistema = "{% if prefetch.dos is defined %}HAY DOS{% else %}SIN DOS{% endif %}"
    rt = await _runtime(
        tmp_path, monkeypatch, _agente(PREFETCH_ENCADENADO, prompts={"system": sistema})
    )

    # `uno` corre y vuelve con rows vacío: `dos` NO corre. Evaluado como string,
    # "[]" no es vacío y habría corrido.
    system, _ = await _correr_capturando(rt, {"sender_phone": "+54"})

    assert system == "SIN DOS"
    assert len(ruta.calls) == 1


@respx.mock
async def test_sin_la_variable_del_when_no_corre_nada(tmp_path, monkeypatch):
    ruta = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"rows": ["A"]})
    )
    rt = await _runtime(tmp_path, monkeypatch, _agente(PREFETCH_ENCADENADO))

    await _correr_capturando(rt, {})

    assert len(ruta.calls) == 0


@respx.mock
async def test_una_busqueda_que_falla_no_tumba_la_corrida(tmp_path, monkeypatch):
    respx.get("https://api.demo.test/ping").mock(side_effect=httpx.ConnectError("caído"))
    sistema = "OK={{ prefetch.uno.success }}"
    pf = [PREFETCH_ENCADENADO[0]]
    rt = await _runtime(tmp_path, monkeypatch, _agente(pf, prompts={"system": sistema}))

    system, resultado = await _correr_capturando(rt, {"sender_phone": "+54"})

    assert system == "OK=False"
    assert resultado["answer"] == "listo"


@respx.mock
async def test_usa_las_credenciales_de_la_corrida(tmp_path, monkeypatch):
    ruta = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"rows": []})
    )
    rt = await _runtime(tmp_path, monkeypatch, _agente([PREFETCH_ENCADENADO[0]]))

    await _correr_capturando(
        rt, {"sender_phone": "+54"}, {"demo_conn": {"access_token": "TOKEN-DE-LA-CORRIDA"}}
    )

    assert ruta.calls[0].request.headers["authorization"] == "Bearer TOKEN-DE-LA-CORRIDA"


async def test_un_agente_sin_prefetch_renderiza_igual(tmp_path, monkeypatch):
    agente = copy.deepcopy(AGENT)
    agente["spec"]["prompts"] = {"system": "fijo"}
    rt = await _runtime(tmp_path, monkeypatch, agente)

    system, resultado = await _correr_capturando(rt, {"sender_phone": "+54"})

    assert system == "fijo"
    assert not [s for s in resultado["trace"]["spans"] if s["name"] == "tool.prefetch"]
