"""Un sub-agente (tool `type: agent`) cuelga del trace del padre y su costo se
suma al run raíz, a cualquier profundidad.

Antes: el `context` de `tool_fn` no llevaba `trace_id` (el hijo arrancaba otro
trace) y el uso del hijo no entraba en el `usage` del padre — Nexus factura del
`usage.by_model` del run, así que nunca cobraba a los sub-agentes, y el
`cost_limit` del padre no los veía.
"""

import pytest
import yaml

from astromesh.api.routes import traces as traces_module
from astromesh.api.usage import usage_from_trace
from astromesh.observability.collector import InternalCollector
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime


def _manifest(nombre: str, hijo: str | None = None, guardrails: dict | None = None) -> dict:
    spec = {
        "identity": {"description": nombre},
        "model": {"primary": {"provider": "ollama", "model": "llama3"}},
        "prompts": {"system": f"sos {nombre}"},
    }
    if hijo:
        spec["tools"] = [{"name": hijo, "type": "agent", "agent": hijo}]
    if guardrails:
        spec["guardrails"] = guardrails
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": nombre, "version": "0.1.0"},
        "spec": spec,
    }


class _Patron:
    """Una llamada al modelo, después (opcional) la tool del sub-agente.

    `tool_primero`: llama la tool antes que al modelo (para el `cost_limit`).
    `falla`: después de gastar, revienta (un sub-agente que falla a mitad).
    """

    def __init__(self, tool=None, tool_primero=False, falla=False):
        self.tool = tool
        self.tool_primero = tool_primero
        self.falla = falla

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        if self.tool and self.tool_primero:
            await tool_fn(self.tool, {"query": "hacelo"})
        await model_fn([{"role": "user", "content": "hola"}], tools)
        if self.falla:
            raise RuntimeError("el hijo se rompió después de gastar")
        if self.tool and not self.tool_primero:
            await tool_fn(self.tool, {"query": "hacelo"})
        return {"answer": "listo", "steps": []}


def _modelo(agente, modelo: str, tin: int, tout: int, costo: float):
    async def route(messages, tools=None, **kwargs):
        return CompletionResponse(
            content="ok",
            model=modelo,
            provider="fake",
            usage={"input_tokens": tin, "output_tokens": tout},
            latency_ms=1.0,
            cost=costo,
        )

    agente._routers["default"].route = route


async def _runtime(tmp_path, *manifiestos: dict) -> AgentRuntime:
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    for m in manifiestos:
        nombre = m["metadata"]["name"]
        (config_dir / "agents" / f"{nombre}.agent.yaml").write_text(yaml.safe_dump(m))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    for m in manifiestos:
        assert m["metadata"]["name"] in runtime._agents, runtime._agent_errors
    return runtime


@pytest.fixture
def collector(monkeypatch):
    c = InternalCollector()
    monkeypatch.setattr(traces_module, "_collector", c, raising=False)
    monkeypatch.setattr(traces_module, "get_collector", lambda: c)
    return c


async def _padre_hijo(tmp_path, *, falla_hijo=False):
    runtime = await _runtime(tmp_path, _manifest("padre", hijo="hijo"), _manifest("hijo"))
    padre, hijo = runtime._agents["padre"], runtime._agents["hijo"]
    padre._pattern = _Patron(tool="hijo")
    hijo._pattern = _Patron(falla=falla_hijo)
    _modelo(padre, "modelo-padre", 100, 50, 0.01)
    _modelo(hijo, "modelo-hijo", 200, 80, 0.02)
    return runtime


async def test_hijo_comparte_trace_id(tmp_path, collector):
    runtime = await _padre_hijo(tmp_path)

    result = await runtime.run("padre", "hola", "s1")

    emitidas = list(collector._traces)
    por_agente = {t["agent"]: t for t in emitidas}
    assert set(por_agente) == {"padre", "hijo"}
    assert por_agente["hijo"]["trace_id"] == result["trace"]["trace_id"]
    assert por_agente["padre"]["trace_id"] == result["trace"]["trace_id"]


async def test_costo_hijo_sumado_al_padre(tmp_path, client, monkeypatch, collector):
    from astromesh.api.routes import agents as agents_module

    runtime = await _padre_hijo(tmp_path)
    monkeypatch.setattr(agents_module, "_runtime", runtime)

    resp = await client.post("/v1/agents/padre/run", json={"query": "hola"})

    assert resp.status_code == 200, resp.text
    usage = resp.json()["usage"]
    assert (usage["tokens_in"], usage["tokens_out"]) == (300, 130)
    filas = {f["model"]: f for f in usage["by_model"]}
    assert set(filas) == {"modelo-padre", "modelo-hijo"}
    assert filas["modelo-hijo"]["tokens_in"] == 200
    assert filas["modelo-hijo"]["tokens_out"] == 80
    assert filas["modelo-hijo"]["cost"] == pytest.approx(0.02)
    assert filas["modelo-padre"]["cost"] == pytest.approx(0.01)


async def test_costo_nieto_llega_a_la_raiz(tmp_path, collector):
    runtime = await _runtime(
        tmp_path,
        _manifest("padre", hijo="hijo"),
        _manifest("hijo", hijo="nieto"),
        _manifest("nieto"),
    )
    for nombre, tool, modelo, tin, tout in (
        ("padre", "hijo", "m-padre", 100, 50),
        ("hijo", "nieto", "m-hijo", 200, 80),
        ("nieto", None, "m-nieto", 400, 160),
    ):
        runtime._agents[nombre]._pattern = _Patron(tool=tool)
        _modelo(runtime._agents[nombre], modelo, tin, tout, 0.0)

    result = await runtime.run("padre", "hola", "s1")

    usage = usage_from_trace(result["trace"])
    assert (usage["tokens_in"], usage["tokens_out"]) == (700, 290)
    assert {f["model"] for f in usage["by_model"]} == {"m-padre", "m-hijo", "m-nieto"}
    # Los tres corrieron en el mismo trace.
    assert {t["trace_id"] for t in collector._traces} == {result["trace"]["trace_id"]}


async def test_costo_hijo_fallido_se_suma(tmp_path, collector):
    """El hijo gasta y revienta; la excepción sube y el padre falla.

    Un run fallido no tiene resultado (REST responde 500 sin `usage`), así que
    el uso parcial queda en el trace del run raíz que recibe el collector: es el
    que indexa `/v1/traces/{trace_id}` (el raíz se emite último y pisa al hijo).
    """
    runtime = await _padre_hijo(tmp_path, falla_hijo=True)

    with pytest.raises(RuntimeError, match="se rompió"):
        await runtime.run("padre", "hola", "s1")

    raiz = [t for t in collector._traces if t["agent"] == "padre"]
    assert len(raiz) == 1
    assert await collector.get_trace(raiz[0]["trace_id"]) is raiz[0]
    usage = usage_from_trace(raiz[0])
    assert (usage["tokens_in"], usage["tokens_out"]) == (300, 130)
    assert {f["model"] for f in usage["by_model"]} == {"modelo-padre", "modelo-hijo"}


async def test_cost_limit_del_padre_cuenta_al_hijo(tmp_path, collector):
    limite = {"output": [{"type": "cost_limit", "max_tokens_per_turn": 100}]}
    runtime = await _runtime(
        tmp_path, _manifest("padre", hijo="hijo", guardrails=limite), _manifest("hijo")
    )
    padre, hijo = runtime._agents["padre"], runtime._agents["hijo"]
    padre._pattern = _Patron(tool="hijo", tool_primero=True)
    hijo._pattern = _Patron()
    llamadas_padre = []

    async def route_padre(messages, tools=None, **kwargs):
        llamadas_padre.append(messages)
        raise AssertionError("el padre no debía gastar: el hijo ya pasó el límite")

    padre._routers["default"].route = route_padre
    _modelo(hijo, "modelo-hijo", 10, 150, 0.0)

    result = await runtime.run("padre", "hola", "s1")

    assert result["blocked"] is True
    assert result["guardrail"]["rule"] == "cost_limit"
    assert llamadas_padre == []
