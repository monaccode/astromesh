"""Un agente con spec.output_schema devuelve `data` validada junto a `answer`."""

import pytest

from astromesh.runtime.engine import AgentRuntime

AGENTE_CON_SCHEMA = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: calificador
spec:
  identity:
    description: "califica leads"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "Sos un calificador."
  output_schema:
    score:  {type: integer}
    urgent: {type: boolean}
  orchestration:
    pattern: react
    max_iterations: 1
"""

AGENTE_SIN_SCHEMA = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: simple
spec:
  identity:
    description: "sin schema"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "Sos simple."
  orchestration:
    pattern: react
    max_iterations: 1
"""


@pytest.fixture
def config_dir(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "calificador.agent.yaml").write_text(AGENTE_CON_SCHEMA, encoding="utf-8")
    (agents / "simple.agent.yaml").write_text(AGENTE_SIN_SCHEMA, encoding="utf-8")
    return tmp_path


async def _run_con_respuesta(runtime, agente, respuesta, monkeypatch):
    """Fuerza al patrón de orquestación a devolver `respuesta` como answer."""

    async def fake_execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        return {"answer": respuesta, "steps": []}

    monkeypatch.setattr(runtime._agents[agente]._pattern, "execute", fake_execute)
    return await runtime.run(agente, "un lead", session_id="s1")


async def test_data_poblada_y_validada(config_dir, monkeypatch):
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(
        runtime,
        "calificador",
        'Buen lead.\n```json\n{"score": 8, "urgent": true}\n```',
        monkeypatch,
    )

    assert result["data"] == {"score": 8, "urgent": True}
    assert result["data_error"] is None
    assert result["answer"].startswith("Buen lead."), "answer debe quedar intacta, con prosa"


async def test_json_faltante_no_rompe_la_corrida(config_dir, monkeypatch):
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(runtime, "calificador", "No pude calificarlo.", monkeypatch)

    assert result["data"] is None
    assert "no se encontró" in result["data_error"]
    assert result["answer"] == "No pude calificarlo."


async def test_validacion_fallida_no_rompe_la_corrida(config_dir, monkeypatch):
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(
        runtime, "calificador", '```json\n{"score": "ocho"}\n```', monkeypatch
    )

    assert result["data"] is None
    assert "score" in result["data_error"]


async def test_agente_sin_schema_no_gana_claves(config_dir, monkeypatch):
    """Guarda de regresión: la forma del resultado no cambia para quien no opta."""
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    result = await _run_con_respuesta(runtime, "simple", '```json\n{"score": 8}\n```', monkeypatch)

    assert "data" not in result
    assert "data_error" not in result


async def test_el_schema_llega_al_system_prompt(config_dir, monkeypatch):
    """El modelo tiene que enterarse de la forma pedida: ningún provider soporta
    response_format, así que la instrucción va por prompt."""
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    capturado = {}

    class _Respuesta:
        content = '```json\n{"score": 5}\n```'
        tool_calls = None
        model = "test"
        provider = "test"
        latency_ms = 1
        cost = 0.0
        usage = None

    async def fake_execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        # model_fn antepone el system prompt ya renderizado a los mensajes.
        resp = await model_fn([{"role": "user", "content": "x"}], [])
        return {"answer": resp.content, "steps": []}

    agente = runtime._agents["calificador"]

    async def spy_route(messages, tools=None, **kw):
        capturado["system"] = messages[0]["content"]
        return _Respuesta()

    monkeypatch.setattr(agente._pattern, "execute", fake_execute)
    monkeypatch.setattr(agente._routers["default"], "route", spy_route)

    await runtime.run("calificador", "un lead", session_id="s1")

    assert "score" in capturado["system"]
    assert "json" in capturado["system"].lower()
