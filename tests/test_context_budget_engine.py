from datetime import UTC, datetime

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.memory import ConversationBackend, ConversationTurn
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


class Fake(ConversationBackend):
    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.summary = None

    async def save_turn(self, session_id, turn):
        self.turns.append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self.turns[-limit:])

    async def clear(self, session_id):
        self.turns = []

    async def get_summary(self, session_id):
        return self.summary

    async def save_summary(self, session_id, summary):
        self.summary = summary


def _t(role, content):
    return ConversationTurn(role=role, content=content, timestamp=datetime.now(UTC))


def _resp(content="ok"):
    return CompletionResponse(
        content=content, model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0
    )


def _manifest(system="sos un agente", strategy="sliding_window", model=None, **conv):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "mem-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": model or {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": system},
            "memory": {
                "conversational": {
                    "backend": "redis",
                    "connection": {"url": "redis://localhost:1"},
                    "strategy": strategy,
                    **conv,
                }
            },
        },
    }


async def _agente(tmp_path, manifest, turns=None):
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "mem-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "mem-agent" in runtime._agents, runtime._agent_errors
    agente = runtime._agents["mem-agent"]
    agente._memory._conversation = Fake(turns)
    return agente


def _capturar(agente):
    """Reemplaza el router default; devuelve la lista de `messages` de cada llamada."""
    llamadas = []

    async def route(messages, requirements=None, **kwargs):
        llamadas.append(messages)
        return _resp()

    agente._routers["default"].route = route
    return llamadas


async def test_ventana_desde_yaml_y_minima_entre_candidatos(tmp_path):
    model = {
        "default": {
            "candidates": [
                {"provider": "ollama", "model": "a", "context_window": 200_000},
                {"provider": "ollama", "model": "b", "context_window": 8_000},
            ]
        }
    }
    agente = await _agente(tmp_path, _manifest(model=model))
    assert agente._context_window == 8_000
    assert agente._context_window_source == "yaml"


async def test_ventana_default_y_respuesta_desde_max_tokens(tmp_path):
    model = {"primary": {"provider": "ollama", "model": "llama3", "max_tokens": 777}}
    agente = await _agente(tmp_path, _manifest(model=model))
    assert agente._context_window == tokens.DEFAULT_CONTEXT_WINDOW
    assert agente._context_window_source == "default"
    assert agente._response_tokens == 777


async def test_summary_usa_el_rol_summarizer(tmp_path):
    model = {
        "default": {"candidates": [{"provider": "ollama", "model": "grande"}]},
        "roles": {"summarizer": {"candidates": [{"provider": "ollama", "model": "chico"}]}},
    }
    agente = await _agente(
        tmp_path,
        _manifest(model=model, strategy="summary", max_turns=4),
        turns=[_t("user", f"m{i}") for i in range(12)],
    )
    pedidos = []

    async def route(messages, requirements=None, **kwargs):
        pedidos.append(messages)
        return _resp("RESUMEN")

    agente._routers["summarizer"].route = route
    await agente._memory.persist_turn("s1", _t("assistant", "otro"))
    assert len(pedidos) == 1
    # 13 turnos, ventana de 4: salen de la ventana m7 y m8 (los anteriores ya se resumieron).
    assert pedidos[0][-1]["content"] == "[user] m7\n[user] m8"
    assert agente._memory._conversation.summary == "RESUMEN"


async def test_summarizer_integra_el_resumen_anterior(tmp_path):
    agente = await _agente(
        tmp_path,
        _manifest(strategy="summary", max_turns=4),
        turns=[_t("user", f"m{i}") for i in range(12)],
    )
    agente._memory._conversation.summary = "VIEJO"
    pedidos = []

    async def route(messages, requirements=None, **kwargs):
        pedidos.append(messages)
        return _resp("NUEVO")

    agente._routers["default"].route = route
    await agente._memory.persist_turn("s1", _t("assistant", "otro"))
    assert pedidos[0][-1]["content"] == (
        "Resumen anterior:\nVIEJO\n\nTurnos nuevos:\n[user] m7\n[user] m8"
    )
    assert agente._memory._conversation.summary == "NUEVO"


async def test_sin_strategy_summary_no_se_cablea_resumidor(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    assert agente._memory._summarize is None


async def test_historial_llega_como_mensajes(tmp_path):
    agente = await _agente(
        tmp_path, _manifest(), turns=[_t("user", "me llamo Ana"), _t("assistant", "hola Ana")]
    )
    llamadas = _capturar(agente)
    await agente.run("¿cómo me llamo?", session_id="s1")
    assert llamadas[0][1:] == [
        {"role": "user", "content": "me llamo Ana"},
        {"role": "assistant", "content": "hola Ana"},
        {"role": "user", "content": "¿cómo me llamo?"},
    ]


async def test_template_legado_no_duplica_historial(tmp_path):
    system = "sos un agente\n{% for t in memory.conversation %}[{{ t.role }}] {{ t.content }}\n{% endfor %}"
    agente = await _agente(
        tmp_path,
        _manifest(system=system),
        turns=[_t("user", "me llamo Ana"), _t("assistant", "hola Ana")],
    )
    llamadas = _capturar(agente)
    await agente.run("¿cómo me llamo?", session_id="s1")
    assert len(llamadas[0]) == 2
    assert "[user] me llamo Ana" in llamadas[0][0]["content"]
    assert llamadas[0][1] == {"role": "user", "content": "¿cómo me llamo?"}


async def test_template_legado_avisa_al_cargar(tmp_path, caplog):
    import logging

    system = "{% for t in memory.conversation %}{{ t.content }}{% endfor %}"
    with caplog.at_level(logging.WARNING):
        await _agente(tmp_path, _manifest(system=system))
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("mem-agent" in m and "rompe el caché de prompts" in m for m in avisos), avisos


async def test_presupuesto_recorta_y_conserva_lo_ultimo(tmp_path):
    model = {
        "primary": {
            "provider": "ollama",
            "model": "llama3",
            "context_window": 2000,
            "max_tokens": 100,
        }
    }
    turns = [_t("user" if i % 2 == 0 else "assistant", f"t{i:02d} " + "x" * 396) for i in range(40)]
    agente = await _agente(tmp_path, _manifest(model=model, max_turns=40), turns=turns)
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    historial = llamadas[0][1:-1]
    assert 0 < len(historial) < 40
    assert historial[-1]["content"].startswith("t39")


async def test_base_mayor_que_la_ventana_no_lanza(tmp_path):
    model = {"primary": {"provider": "ollama", "model": "llama3", "context_window": 50}}
    agente = await _agente(
        tmp_path, _manifest(system="x" * 4000, model=model), turns=[_t("user", "viejo")]
    )
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1:] == [{"role": "user", "content": "q"}]


async def test_historial_recortado_no_empieza_con_assistant(tmp_path):
    agente = await _agente(
        tmp_path,
        _manifest(),
        turns=[_t("assistant", "a0"), _t("user", "u1"), _t("assistant", "a1")],
    )
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1]["role"] == "user"
    assert llamadas[0][1]["content"] == "u1"


async def test_resumen_es_el_primer_mensaje(tmp_path):
    agente = await _agente(
        tmp_path, _manifest(strategy="summary"), turns=[_t("assistant", "a0"), _t("user", "u1")]
    )
    agente._memory._conversation.summary = "Ana pidió un turno"
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1] == {
        "role": "user",
        "content": "[Resumen de la conversación anterior]\nAna pidió un turno",
    }
    assert llamadas[0][2] == {"role": "assistant", "content": "a0"}


async def test_resumen_se_fusiona_con_el_primer_turno_user(tmp_path):
    agente = await _agente(
        tmp_path, _manifest(strategy="summary"), turns=[_t("user", "u1"), _t("assistant", "a1")]
    )
    agente._memory._conversation.summary = "Ana pidió un turno"
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1:] == [
        {
            "role": "user",
            "content": "[Resumen de la conversación anterior]\nAna pidió un turno\n\nu1",
        },
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q"},
    ]


async def test_turnos_vacios_no_se_mandan(tmp_path):
    agente = await _agente(
        tmp_path,
        _manifest(),
        turns=[_t("user", "u1"), _t("assistant", "  "), _t("user", ""), _t("assistant", "a1")],
    )
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1:] == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q"},
    ]


async def test_ventana_desconocida_no_recorta(tmp_path):
    turns = [
        _t("user" if i % 2 == 0 else "assistant", f"t{i:02d} " + "x" * 4000) for i in range(40)
    ]
    agente = await _agente(tmp_path, _manifest(max_turns=40), turns=turns)
    assert agente._context_window_source == "default"
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert len(llamadas[0][1:-1]) == 40


async def test_ventana_desconocida_avisa_que_no_recorta(tmp_path, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        await _agente(tmp_path, _manifest())
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("mem-agent" in m and "NO se recorta" in m for m in avisos), avisos


async def test_solo_conversation_summary_en_template_manda_mensajes(tmp_path):
    system = "sos un agente\n{{ memory.conversation_summary }}"
    agente = await _agente(
        tmp_path,
        _manifest(system=system),
        turns=[_t("user", "me llamo Ana"), _t("assistant", "hola Ana")],
    )
    llamadas = _capturar(agente)
    await agente.run("¿cómo me llamo?", session_id="s1")
    assert llamadas[0][1:] == [
        {"role": "user", "content": "me llamo Ana"},
        {"role": "assistant", "content": "hola Ana"},
        {"role": "user", "content": "¿cómo me llamo?"},
    ]


async def test_system_null_carga(tmp_path):
    await _agente(tmp_path, _manifest(system=None))  # _agente asierta que cargó


async def test_system_prompt_estable_entre_turnos(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    llamadas = _capturar(agente)
    await agente.run("primero", session_id="s1")
    await agente.run("segundo", session_id="s1")
    assert llamadas[0][0] == llamadas[1][0]
    assert {"role": "user", "content": "primero"} in llamadas[1]
