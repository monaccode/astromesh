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


async def _agente_sin_memoria(tmp_path, manifest):
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "mem-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "mem-agent" in runtime._agents, runtime._agent_errors
    return runtime._agents["mem-agent"]


class FakeRAG:
    async def build_context(self, query_text):
        return f"DOC sobre {query_text}"


def _con_context(manifest, context="{% if knowledge %}DOCS: {{ knowledge }}{% endif %}", **kw):
    manifest["spec"]["prompts"]["context"] = context
    manifest["spec"].setdefault("orchestration", {}).update(kw)
    return manifest


def _span(result, name):
    return next(s for s in result["trace"]["spans"] if s["name"] == name)


async def test_contexto_va_en_el_ultimo_mensaje_y_el_system_queda_estable(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest()))
    agente._rag = FakeRAG()
    llamadas = _capturar(agente)
    r1 = await agente.run("frenos", session_id="s1")
    await agente.run("embrague", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "DOCS: DOC sobre frenos\n\nfrenos"}
    assert llamadas[1][-1] == {"role": "user", "content": "DOCS: DOC sobre embrague\n\nembrague"}
    assert llamadas[0][0] == llamadas[1][0]
    assert _span(r1, "context_fit")["attributes"]["turn_context.delivery"] == "message"
    assert _span(r1, "context_fit")["attributes"]["turn_context.tokens"] > 0


async def test_el_turno_persistido_es_la_query_original(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest()))
    agente._rag = FakeRAG()
    _capturar(agente)
    await agente.run("frenos", session_id="s1")
    persistidos = agente._memory._conversation.turns
    assert persistidos[0].role == "user"
    assert persistidos[0].content == "frenos"


async def test_contexto_sin_memoria_conversacional(tmp_path):
    manifest = _con_context(_manifest())
    del manifest["spec"]["memory"]
    agente = await _agente_sin_memoria(tmp_path, manifest)
    agente._rag = FakeRAG()
    llamadas = _capturar(agente)
    await agente.run("frenos", session_id="s1")
    assert llamadas[0][1:] == [{"role": "user", "content": "DOCS: DOC sobre frenos\n\nfrenos"}]


async def test_contexto_vacio_no_agrega_nada(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest()))  # sin RAG → knowledge vacío
    llamadas = _capturar(agente)
    r = await agente.run("frenos", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "frenos"}
    assert _span(r, "context_fit")["attributes"]["turn_context.delivery"] == "none"
    assert _span(r, "context_fit")["attributes"]["turn_context.tokens"] == 0


async def test_contexto_no_lleva_el_bloque_de_output_schema(tmp_path):
    manifest = _con_context(_manifest(), context="DOCS FIJOS")
    manifest["spec"]["output_schema"] = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
    }
    agente = await _agente(tmp_path, manifest)
    llamadas = _capturar(agente)
    await agente.run("frenos", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "DOCS FIJOS\n\nfrenos"}


async def test_patron_desconocido_cae_a_react_y_recibe_el_mensaje(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest(), context="CTX", pattern="raro"))
    llamadas = _capturar(agente)
    await agente.run("frenos", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "CTX\n\nfrenos"}


async def test_patron_sin_soporte_recibe_el_contexto_en_el_system(tmp_path, caplog):
    import logging

    from astromesh.orchestration.patterns import OrchestrationPattern

    with caplog.at_level(logging.WARNING):
        agente = await _agente(
            tmp_path, _con_context(_manifest(), context="CTX", pattern="plan_and_execute")
        )
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("mem-agent" in m and "prompts.context" in m for m in avisos), avisos

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            await model_fn([{"role": "user", "content": query}], [])
            return {"answer": "ok", "steps": []}

    agente._pattern = Espia()
    llamadas = _capturar(agente)
    r = await agente.run("frenos", session_id="s1")
    assert llamadas[0][0]["content"].endswith("\n\nCTX")
    assert "_turn_context" not in visto["context"]
    assert _span(r, "context_fit")["attributes"]["turn_context.delivery"] == "system"


async def test_tokens_del_contexto_achican_el_historial(tmp_path):
    model = {
        "primary": {
            "provider": "ollama",
            "model": "llama3",
            "context_window": 3000,
            "max_tokens": 100,
        }
    }
    turns = [_t("user" if i % 2 == 0 else "assistant", f"t{i:02d} " + "x" * 396) for i in range(40)]

    async def historial(context):
        agente = await _agente(
            tmp_path / context[:3],
            _con_context(_manifest(model=model, max_turns=40), context=context),
            turns=list(turns),
        )
        llamadas = _capturar(agente)
        await agente.run("q", session_id="s1")
        return len(llamadas[0]) - 2

    corto = await historial("CTX")
    largo = await historial("BIG" + "y" * 4000)
    assert largo < corto


async def test_contexto_con_memory_conversation_no_activa_el_camino_legado(tmp_path):
    ctx = "{% for t in memory.conversation %}{{ t.content }}{% endfor %}"
    agente = await _agente(
        tmp_path,
        _con_context(_manifest(), context=ctx),
        turns=[_t("user", "u1"), _t("assistant", "a1")],
    )
    llamadas = _capturar(agente)
    r = await agente.run("q", session_id="s1")
    assert _span(r, "context_fit")["attributes"]["history.delivery"] == "messages"
    assert llamadas[0][1] == {"role": "user", "content": "u1"}


async def test_warning_por_variables_de_query_en_el_system(tmp_path, caplog):
    import logging

    sistemas = {
        "rag": "Docs: {{ knowledge }}",
        "pref": "{{ prefetch.stock }}",
        "sem": "{{ memory.semantic }}",
        "kbid": "base {{ knowledge_base_id }}",
        "summ": "{{ memory.conversation_summary }}",
    }
    avisados = {}
    for clave, system in sistemas.items():
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            await _agente(tmp_path / clave, _manifest(system=system))
        avisados[clave] = any(
            "cambia en cada query" in r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        )
    assert avisados == {"rag": True, "pref": True, "sem": True, "kbid": False, "summ": False}


async def test_ssti_en_el_contexto_hace_fallar_la_corrida(tmp_path):
    from jinja2.exceptions import SecurityError

    agente = await _agente(
        tmp_path, _con_context(_manifest(), context="{{ ''.__class__.__mro__ }}")
    )
    _capturar(agente)
    with pytest.raises(SecurityError):
        await agente.run("q", session_id="s1")


async def test_cache_hit_ratio_en_el_span(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    usos = [
        {"input_tokens": 1000, "output_tokens": 5, "cache_read_input_tokens": 880},
        {"input_tokens": 0, "output_tokens": 5},
    ]

    async def route(messages, requirements=None, **kwargs):
        return CompletionResponse(
            content="ok", model="m", provider="p", usage=usos.pop(0), latency_ms=1.0, cost=0.0
        )

    agente._routers["default"].route = route
    r1 = await agente.run("q1", session_id="s1")
    r2 = await agente.run("q2", session_id="s1")
    assert _span(r1, "llm.complete")["attributes"]["cache.hit_ratio"] == 0.88
    assert _span(r2, "llm.complete")["attributes"]["cache.hit_ratio"] == 0
