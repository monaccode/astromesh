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
    await agente._memory.persist_turn("s1", _t("user", "otro"))
    assert len(pedidos) == 1
    assert "m0" in pedidos[0][-1]["content"]
    assert agente._memory._conversation.summary == "RESUMEN"


async def test_sin_strategy_summary_no_se_cablea_resumidor(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    assert agente._memory._summarize is None
