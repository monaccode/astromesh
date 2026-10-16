"""Un episodio por corrida y la memoria proyectada al prompt (sin vectores)."""

import dataclasses
import json

import pytest

from astromesh.core.memory import EpisodicBackend, SemanticBackend, SemanticMemory
from tests.test_guardrails_run import _agente, _manifest, _resp, sin_litellm  # noqa: F401


class FakeEpisodic(EpisodicBackend):
    def __init__(self, falla=False):
        self.grabados = []
        self.falla = falla

    async def record(self, agent_id, episode):
        if self.falla:
            raise RuntimeError("db caída")
        self.grabados.append(episode)

    async def recall(self, agent_id, event_type=None, since=None, limit=20):
        return list(reversed(self.grabados))[:limit]


class FakeSemantic(SemanticBackend):
    async def store(self, agent_id, memory):
        pass

    async def search(self, agent_id, query_embedding, top_k=10, threshold=0.7):
        return [
            SemanticMemory(
                content="dato", embedding=[0.1] * 3, metadata={}, similarity=0.9, source="doc"
            )
        ]

    async def delete(self, agent_id, memory_id):
        pass


async def _con_episodios(tmp_path, manifest, respuestas=("ok",), falla=False):
    agente, llamadas = await _agente(tmp_path, manifest, respuestas)
    fake = FakeEpisodic(falla)
    agente._memory._episodic = fake
    return agente, llamadas, fake


async def test_una_corrida_ok_deja_un_episodio(tmp_path):
    agente, _, fake = await _con_episodios(tmp_path, _manifest())

    async def execute(query, context, model_fn, tool_fn, tools, max_iterations=10):
        await model_fn([{"role": "user", "content": "1"}], [])
        await tool_fn("leer", {})
        await model_fn([{"role": "user", "content": "2"}], [])
        return {"answer": "listo", "steps": []}

    async def ejecutar(*a, **k):
        return "x"

    agente._pattern.execute = execute
    agente._tools.execute = ejecutar
    # la primera respuesta lleva output_tokens=7, la segunda 0
    cola = [_resp("a", 7), _resp("b", 0)]

    async def route(messages, requirements=None, **kwargs):
        return cola.pop(0)

    agente._routers["default"].route = route
    await agente.run("hola", "s1")
    ep = fake.grabados[0]
    assert len(fake.grabados) == 1
    assert (ep.event_type, ep.outcome["result"]) == ("run", "ok")
    assert (ep.context["tools"], ep.outcome["tokens"]) == (["leer"], {"input": 6, "output": 7})
    assert ep.summary == "hola"


async def test_query_larga_se_trunca_a_500(tmp_path):
    agente, _, fake = await _con_episodios(tmp_path, _manifest())
    await agente.run("x" * 900, "s1")
    assert len(fake.grabados[0].summary) == 500


async def test_bloqueo_de_entrada_deja_episodio_sin_query(tmp_path):
    reglas = {"input": [{"type": "topic_filter", "blocked_topics": ["secreto"], "action": "block"}]}
    agente, _, fake = await _con_episodios(tmp_path, _manifest(reglas))
    await agente.run("contame el secreto", "s1")
    ep = fake.grabados[0]
    assert (ep.outcome["result"], ep.outcome["guardrail"]) == ("blocked", "topic_filter")
    assert ep.summary == ""
    assert "secreto" not in json.dumps(dataclasses.asdict(ep), default=str)


async def test_bloqueo_de_salida_guarda_la_query(tmp_path):
    reglas = {
        "output": [
            {"type": "content_filter", "forbidden_keywords": ["prohibido"], "action": "block"}
        ]
    }
    agente, _, fake = await _con_episodios(
        tmp_path, _manifest(reglas), respuestas=["esto es prohibido"]
    )
    await agente.run("<query filtrada>", "s1")
    ep = fake.grabados[0]
    assert ep.outcome["result"] == "blocked"
    assert ep.summary == "<query filtrada>"


async def test_error_deja_episodio_error(tmp_path):
    agente, _, fake = await _con_episodios(tmp_path, _manifest())

    async def route(messages, requirements=None, **kwargs):
        raise RuntimeError("proveedor caído")

    agente._routers["default"].route = route
    with pytest.raises(RuntimeError):
        await agente.run("hola", "s1")
    assert fake.grabados[0].outcome["result"] == "error"


async def test_fallo_al_grabar_el_episodio_no_rompe_la_corrida(tmp_path):
    agente, _, _ = await _con_episodios(tmp_path, _manifest(), falla=True)
    result = await agente.run("hola", "s1")
    assert result["answer"] == "ok"


async def test_proyeccion_semantica_sin_vector(tmp_path):
    manifest = _manifest()
    manifest["spec"]["prompts"]["context"] = "{{ memory.semantic | tojson }}"
    agente, llamadas, _ = await _con_episodios(tmp_path, manifest)
    agente._memory._semantic = FakeSemantic()
    agente._memory._embed = lambda texto: _vec()
    await agente.run("hola", "s1")
    enviado = json.dumps(llamadas)
    assert '\\"content\\"' in enviado
    assert "0.1" not in enviado
    ctx = await agente._memory.build_context("s1", "hola")
    assert ctx["semantic"][0].keys() == {"content", "similarity", "source"}


async def _vec():
    return [0.1] * 3


async def test_episodios_de_otra_sesion_no_llegan_al_prompt(tmp_path):
    manifest = _manifest()
    manifest["spec"]["prompts"]["context"] = "{{ memory.episodic | tojson }}"
    agente, llamadas, _ = await _con_episodios(tmp_path, manifest)
    agente._memory._conversation = None  # el historial del fake no distingue sesiones
    await agente.run("dato-de-s1", "s1")
    llamadas.clear()
    await agente.run("otra cosa", "s2")
    assert "dato-de-s1" not in json.dumps(llamadas)
