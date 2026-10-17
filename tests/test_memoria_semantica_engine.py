"""`memory.semantic` y `memory.episodic` del manifiesto llegan al MemoryManager.

Antes el engine construía sólo la conversacional: un agente que declaraba
memoria semántica corría sin ella, sin un error en ningún lado.
"""

import asyncio
import logging

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.memory import SemanticBackend
from astromesh.providers.base import CompletionResponse
from astromesh.runtime import engine as engine_mod
from astromesh.runtime.engine import AgentRuntime
from tests.test_client_tools import _agent_spec

SEMANTIC = {"backend": "faiss", "dimension": 3, "embeddings": {"provider": "ollama"}}


class FakeSemantic(SemanticBackend):
    def __init__(self, falla_en=None):
        self.stored = []
        self.inits = 0
        self._falla_en = falla_en

    async def initialize(self):
        self.inits += 1

    async def store(self, agent_id, content, embedding, metadata):
        if self._falla_en == "store":
            raise RuntimeError("store caído")
        self.stored.append(content)

    async def search(self, agent_id, query_embedding, top_k=10, threshold=0.7, session_id=None):
        if self._falla_en == "search":
            raise RuntimeError("search caído")
        return []

    async def delete(self, agent_id, memory_id):
        pass


async def _embed(text):
    return [0.1, 0.2, 0.3]


@pytest.fixture(autouse=True)
def _sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _agente(monkeypatch, fake):
    monkeypatch.setattr(engine_mod, "build_semantic_memory", lambda cfg: (fake, _embed))
    spec = _agent_spec([])
    spec["spec"]["memory"] = {"semantic": SEMANTIC}
    return AgentRuntime(config_dir="/nonexistent")._build_agent(spec)


def _con_respuesta(agente, content):
    async def route(messages, tools=None, **kwargs):
        return CompletionResponse(
            content=content,
            model="m",
            provider="p",
            usage={"input_tokens": 1, "output_tokens": 1},
            latency_ms=1.0,
            cost=0.0,
            tool_calls=[],
        )

    agente._routers["default"].route = route


async def test_el_manifiesto_construye_la_semantica(monkeypatch):
    fake = FakeSemantic()
    agente = _agente(monkeypatch, fake)
    assert agente._memory._semantic is fake
    assert agente._memory._embed is _embed


async def test_semantic_sin_embeddings_deja_el_agente_en_draft(tmp_path):
    spec = _agent_spec([])
    spec["metadata"]["name"] = "g-agent"
    spec["spec"]["memory"] = {"semantic": {"backend": "faiss", "dimension": 3}}
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "g.agent.yaml").write_text(yaml.safe_dump(spec))
    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()
    assert runtime._agent_status["g-agent"] == "draft"
    assert "embeddings" in runtime.agent_error("g-agent")


async def test_backend_que_falla_en_search_no_rompe_la_corrida(monkeypatch, caplog):
    agente = _agente(monkeypatch, FakeSemantic(falla_en="search"))
    _con_respuesta(agente, "respuesta")
    with caplog.at_level(logging.WARNING):
        result = await agente.run("hola", "s1")
    assert result["answer"] == "respuesta"
    assert "search caído" in caplog.text


async def test_backend_que_falla_en_store_no_rompe_la_corrida(monkeypatch, caplog):
    agente = _agente(monkeypatch, FakeSemantic(falla_en="store"))
    _con_respuesta(agente, "palabra " * 200)
    with caplog.at_level(logging.WARNING):
        result = await agente.run("hola", "s1")
    assert result["answer"].startswith("palabra")
    assert "store caído" in caplog.text


async def test_semantica_se_escribe_sin_memoria_conversacional(monkeypatch):
    fake = FakeSemantic()
    agente = _agente(monkeypatch, fake)
    assert agente._memory._conversation is None
    _con_respuesta(agente, "palabra " * 200)
    await agente.run("hola", "s1")
    assert len(fake.stored) == 1


async def test_initialize_se_llama_una_vez(monkeypatch):
    fake = FakeSemantic()
    agente = _agente(monkeypatch, fake)
    _con_respuesta(agente, "ok")
    await agente.run("hola", "s1")
    await agente.run("otra", "s1")
    assert fake.inits == 1


async def test_initialize_que_falla_se_reintenta(monkeypatch, caplog):
    fake = FakeSemantic()
    llamadas = []

    async def init_que_falla_una_vez():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("db caída")

    fake.initialize = init_que_falla_una_vez
    agente = _agente(monkeypatch, fake)
    _con_respuesta(agente, "ok")
    with caplog.at_level(logging.WARNING):
        await agente.run("hola", "s1")
    assert "db caída" in caplog.text
    # build_context falló al preparar; persist_turn, en la misma corrida, reintenta.
    assert len(llamadas) == 2
    await agente.run("otra", "s1")
    assert len(llamadas) == 2


async def test_dos_primeras_llamadas_concurrentes_inicializan_una_vez():
    from astromesh.core.memory import MemoryManager

    fake = FakeSemantic()
    orig = fake.initialize

    async def init_lento():
        await asyncio.sleep(0.01)  # cede el loop: la otra llamada entra mientras tanto
        await orig()

    fake.initialize = init_lento
    memoria = MemoryManager("a", {}, semantic=fake, embedding_fn=_embed)
    await asyncio.gather(memoria.build_context("s1", "q"), memoria.build_context("s2", "q"))
    assert fake.inits == 1
