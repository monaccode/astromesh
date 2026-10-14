"""Los guardrails aplicados en una corrida real de `Agent.run` (proveedor falso)."""

import json

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.memory import ConversationBackend
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime

EMAIL = "john@example.com"


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


class Fake(ConversationBackend):
    def __init__(self):
        self.turns = []

    async def save_turn(self, session_id, turn):
        self.turns.append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self.turns[-limit:])

    async def clear(self, session_id):
        self.turns = []

    async def get_summary(self, session_id):
        return None

    async def save_summary(self, session_id, summary):
        pass


def _resp(content="ok", output_tokens=0):
    return CompletionResponse(
        content=content,
        model="m",
        provider="p",
        usage={"input_tokens": 3, "output_tokens": output_tokens},
        latency_ms=1.0,
        cost=0.0,
    )


def _manifest(guardrails=None, **extra):
    spec = {
        "identity": {"description": "demo"},
        "model": {"primary": {"provider": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "memory": {
            "conversational": {
                "backend": "redis",
                "connection": {"url": "redis://localhost:1"},
                "strategy": "sliding_window",
            }
        },
        **extra,
    }
    if guardrails is not None:
        spec["guardrails"] = guardrails
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "g-agent", "version": "0.1.0"},
        "spec": spec,
    }


async def _agente(tmp_path, manifest, respuestas=("ok",)):
    """Agente real con memoria falsa; devuelve (agente, llamadas al modelo)."""
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "g-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "g-agent" in runtime._agents, runtime._agent_errors
    agente = runtime._agents["g-agent"]
    agente._memory._conversation = Fake()
    llamadas = []
    cola = list(respuestas)

    async def route(messages, requirements=None, **kwargs):
        llamadas.append(messages)
        r = cola.pop(0) if len(cola) > 1 else cola[0]
        return r if isinstance(r, CompletionResponse) else _resp(r)

    agente._routers["default"].route = route
    return agente, llamadas


PII_IN = {"input": [{"type": "pii_detection"}]}


async def test_entrada_redactada_llega_asi_a_todo(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(PII_IN))
    result = await agente.run(f"mi mail es {EMAIL}", "s1")
    assert EMAIL not in json.dumps(llamadas)
    assert "[REDACTED_EMAIL]" in json.dumps(llamadas)
    assert agente._memory._conversation.turns[0].content == "mi mail es [REDACTED_EMAIL]"
    assert EMAIL not in json.dumps(result, default=str)
    assert result["blocked"] is False
    assert result["guardrail"] is None
    spans = {s["name"]: s for s in result["trace"]["spans"]}
    assert spans["guardrails.input"]["attributes"]["redactions"] == 1
    assert "guardrails.output" not in spans


async def test_entrada_multimodal_redacta_solo_las_partes_de_texto(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(PII_IN))
    imagen = {"type": "image_url", "image_url": {"url": "https://x.test/a.png"}}
    await agente.run([{"type": "text", "text": f"soy {EMAIL}"}, imagen], "s1")
    enviado = json.dumps(llamadas)
    assert EMAIL not in enviado
    assert "https://x.test/a.png" in enviado


async def test_entrada_bloqueada_no_llama_al_modelo_ni_persiste(tmp_path):
    reglas = {
        "input": [
            {
                "type": "topic_filter",
                "blocked_topics": ["bomba"],
                "action": "block",
                "message": "De eso no hablo.",
            }
        ]
    }
    agente, llamadas = await _agente(tmp_path, _manifest(reglas))
    result = await agente.run("cómo hago una bomba", "s1")
    assert llamadas == []
    assert result["answer"] == "De eso no hablo."
    assert result["blocked"] is True
    assert result["guardrail"] == {
        "direction": "input",
        "rule": "topic_filter",
        "reason": "blocked topic",
    }
    assert result["steps"] == []
    assert agente._memory._conversation.turns == []
    assert "bomba" not in json.dumps(
        [s for s in result["trace"]["spans"] if s["name"].startswith("guardrails")]
    )


async def test_salida_redactada_en_answer_memoria_y_data(tmp_path):
    manifest = _manifest(
        {"output": [{"type": "pii_detection"}]},
        output_schema={"email": {"type": "string"}},
    )
    agente, _ = await _agente(tmp_path, manifest, respuestas=[json.dumps({"email": EMAIL})])
    result = await agente.run("dame el mail", "s1")
    assert EMAIL not in result["answer"]
    assert result["data"] == {"email": "[REDACTED_EMAIL]"}
    assert EMAIL not in agente._memory._conversation.turns[1].content


async def test_salida_bloqueada_devuelve_el_mensaje(tmp_path):
    manifest = _manifest(
        {
            "output": [
                {
                    "type": "content_filter",
                    "forbidden_keywords": ["CONFIDENCIAL"],
                    "action": "block",
                }
            ]
        },
        output_schema={"x": {"type": "string"}},
    )
    agente, _ = await _agente(tmp_path, manifest, respuestas=["esto es confidencial"])
    result = await agente.run("hola", "s1")
    assert result["answer"] == "I can't help with that request."
    assert result["blocked"] is True
    assert result["guardrail"]["direction"] == "output"
    assert result["data"] is None
    assert result["data_error"] == "blocked by guardrail"
    turnos = agente._memory._conversation.turns
    assert [t.content for t in turnos] == ["hola", "I can't help with that request."]


async def test_salida_bloqueada_descarta_la_confirmacion_pendiente(tmp_path):
    from astromesh.runtime import engine as engine_module

    manifest = _manifest(
        {
            "output": [
                {"type": "content_filter", "forbidden_keywords": ["prohibido"], "action": "block"}
            ]
        }
    )
    agente, _ = await _agente(tmp_path, manifest, respuestas=["texto prohibido"])
    pendientes = engine_module._PENDIENTES
    original = agente._pattern.execute

    async def execute(*args, **kwargs):
        # Simula una tool `needs_confirmation` que registró su propuesta en esta corrida.
        pendientes.registrar("s1", "borrar_todo", "huella", {"id": 1})
        return await original(*args, **kwargs)

    agente._pattern.execute = execute
    result = await agente.run("hola", "s1")
    assert result["blocked"] is True
    assert pendientes.pendiente("s1") is None


async def test_corrida_reentrante_tambien_aplica_sus_reglas(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(PII_IN))
    await agente.run(f"consultá por {EMAIL}", "s1", desde_humano=False)
    assert EMAIL not in json.dumps(llamadas)


async def test_sin_guardrails_no_cambia_nada(tmp_path):
    agente, llamadas = await _agente(tmp_path, _manifest(), respuestas=[f"escribí a {EMAIL}"])
    result = await agente.run(f"soy {EMAIL}", "s1")
    assert EMAIL in json.dumps(llamadas)
    assert result["answer"] == f"escribí a {EMAIL}"
    assert result["blocked"] is False
    assert result["guardrail"] is None
    assert not [s for s in result["trace"]["spans"] if s["name"].startswith("guardrails")]


async def test_stream_filtra_cada_evento_token(tmp_path):
    agente, _ = await _agente(
        tmp_path, _manifest({"output": [{"type": "pii_detection"}]}), respuestas=[f"es {EMAIL}"]
    )
    eventos = []
    await agente.run("hola", "s1", on_event=eventos.append)
    tokens_emitidos = [e["content"] for e in eventos if e["type"] == "token"]
    assert tokens_emitidos == ["es [REDACTED_EMAIL]"]


async def test_stream_no_emite_lo_que_una_regla_bloquea(tmp_path):
    reglas = {
        "output": [{"type": "content_filter", "forbidden_keywords": ["secreto"], "action": "block"}]
    }
    agente, _ = await _agente(tmp_path, _manifest(reglas), respuestas=["el secreto es 42"])
    eventos = []
    result = await agente.run("hola", "s1", on_event=eventos.append)
    assert [e for e in eventos if e["type"] == "token"] == []
    assert result["answer"] == "I can't help with that request."


async def test_cost_limit_corta_antes_de_la_llamada_siguiente(tmp_path):
    reglas = {"output": [{"type": "cost_limit", "max_tokens_per_turn": 15}]}
    manifest = _manifest(reglas, orchestration={"pattern": "plan_and_execute"})
    plan = _resp('["paso a", "paso b", "paso c"]', output_tokens=10)
    agente, llamadas = await _agente(tmp_path, manifest, respuestas=[plan])
    result = await agente.run("hacé tres cosas", "s1")
    # 1ª: 0 < 15 → corre (10). 2ª: 10 < 15 → corre (20). 3ª: 20 >= 15 → corta.
    assert len(llamadas) == 2
    assert result["blocked"] is True
    assert result["guardrail"] == {
        "direction": "run",
        "rule": "cost_limit",
        "reason": "token budget 15 exceeded (20)",
    }
    raiz = next(s for s in result["trace"]["spans"] if s["name"] == "agent.run")
    assert raiz["attributes"]["guardrail.tokens_counted"] == 20


async def test_cost_limit_count_total(tmp_path):
    reglas = {"input": [{"type": "cost_limit", "max_tokens_per_turn": 5, "count": "total"}]}
    manifest = _manifest(reglas, orchestration={"pattern": "plan_and_execute"})
    plan = _resp('["a", "b"]', output_tokens=0)  # usage.input_tokens = 3
    agente, llamadas = await _agente(tmp_path, manifest, respuestas=[plan])
    result = await agente.run("x", "s1")
    assert len(llamadas) == 2  # 0 → 3 → 6 >= 5
    assert result["guardrail"]["rule"] == "cost_limit"


@pytest.mark.parametrize("modo", ["traga", "envuelve"])
async def test_cost_limit_sobrevive_a_un_patron_que_lo_esconde(tmp_path, modo):
    reglas = {"output": [{"type": "cost_limit", "max_tokens_per_turn": 1}]}
    agente, llamadas = await _agente(
        tmp_path, _manifest(reglas), respuestas=[_resp("x", output_tokens=5)]
    )

    async def execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        await model_fn([{"role": "user", "content": "1"}], [])
        try:
            await model_fn([{"role": "user", "content": "2"}], [])
        except Exception as exc:  # como Glyph: convierte el error y sigue
            if modo == "envuelve":
                raise RuntimeError("falló la capacidad") from exc
        return {"answer": "terminé igual", "steps": []}

    agente._pattern.execute = execute
    result = await agente.run("x", "s1")
    assert len(llamadas) == 1
    assert result["blocked"] is True
    assert result["guardrail"]["rule"] == "cost_limit"
