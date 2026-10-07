"""correr_eval: estados por caso, memoria entre turnos, umbrales y uso."""

import pytest
import yaml

from astromesh.core import tokens
from astromesh.evals import fixtures
from astromesh.evals.formato import Caso, Eval
from astromesh.evals.runner import correr_eval
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime
from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

EJECUCIONES = []


class _Stock(BuiltinTool):
    name = "stock"
    description = "stock de un sku"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        EJECUCIONES.append(arguments)
        return ToolResult(success=True, data={"stock": 99}, metadata={})


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)
    monkeypatch.setattr(ToolLoader, "auto_discover", lambda self: self.register_class(_Stock))
    EJECUCIONES.clear()


def _resp(content="", tool_calls=None, usage=None, cost=0.0):
    return CompletionResponse(
        content=content,
        model="m",
        provider="p",
        usage=usage or {},
        latency_ms=1.0,
        cost=cost,
        tool_calls=tool_calls or [],
    )


async def _runtime(tmp_path):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    (d / "agents" / "lucia.agent.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "lucia", "version": "0.1.0"},
                "spec": {
                    "identity": {"description": "demo"},
                    "model": {"primary": {"provider": "ollama", "model": "llama3"}},
                    "prompts": {"system": "sos un agente"},
                    "orchestration": {"pattern": "react"},
                    "tools": [{"name": "stock", "type": "builtin"}],
                    "memory": {
                        "conversational": {
                            "backend": "redis",
                            "connection": {"url": "redis://localhost:1"},
                            "strategy": "sliding_window",
                        }
                    },
                },
            }
        )
    )
    rt = AgentRuntime(config_dir=str(d))
    await rt.bootstrap()
    assert "lucia" in rt._agents, rt._agent_errors
    fixtures.preparar(rt)
    return rt


def _modelo(rt, fn):
    rt._agents["lucia"]._routers["default"].route = fn


def _eval(casos, **kw):
    return Eval(name="e", agent="lucia", pass_rate=kw.pop("pass_rate", 1.0), casos=casos, **kw)


async def test_fixture_tool_called_y_uso(tmp_path):
    rt = await _runtime(tmp_path)
    vistos = []

    async def route(messages, requirements=None, **kw):
        vistos.append(list(messages))
        if len(vistos) == 1:
            return _resp(
                tool_calls=[{"id": "t1", "name": "stock", "arguments": {}}],
                usage={"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 40},
                cost=0.01,
            )
        return _resp("hay 12", usage={"input_tokens": 120, "output_tokens": 5}, cost=0.02)

    _modelo(rt, route)
    caso = Caso(
        id="c1",
        turns=["¿stock?"],
        tools={"stock": {"stock": 12}},
        expect=[{"contains": "12"}, {"tool_called": "stock"}],
    )
    r = await correr_eval(rt, _eval([caso]), "run1")
    c = r["cases"][0]
    assert c["status"] == "pass", c["motivos"]
    assert EJECUCIONES == []  # la fixture no ejecutó la tool real
    assert any("12" in str(m.get("content")) for m in vistos[1] if m.get("role") == "tool")
    assert (c["tokens_in"], c["tokens_out"], c["cached_tokens"]) == (220, 15, 40)
    assert c["cost"] == pytest.approx(0.03)
    assert c["tools_llamadas"] == ["stock"]
    assert c["answer"] == "hay 12"
    assert r["passed"] is True
    assert r["pass_rate"] == 1.0
    assert r["avg_tokens"] == 235


async def test_turnos_comparten_memoria_y_casos_no(tmp_path):
    rt = await _runtime(tmp_path)
    vistos = []

    async def route(messages, requirements=None, **kw):
        vistos.append([m.get("content") for m in messages])
        return _resp("ok")

    _modelo(rt, route)
    casos = [
        Caso(id="a", turns=["me llamo Ana", "¿cómo me llamo?"], expect=[{"contains": "ok"}]),
        Caso(id="b", turns=["¿cómo me llamo?"], expect=[{"contains": "ok"}]),
    ]
    await correr_eval(rt, _eval(casos), "run2")
    assert any("me llamo Ana" in str(c) for c in vistos[1])  # turno 2 de `a` ve el turno 1
    assert not any("me llamo Ana" in str(c) for c in vistos[2])  # `b` no ve a `a`


async def test_context_se_copia_por_turno(tmp_path):
    rt = await _runtime(tmp_path)
    recibidos = []
    original = rt.run

    async def run(agent_name, query, session_id, context=None, **kw):
        recibidos.append(dict(context))
        context["mutado"] = True
        return await original(agent_name, query, session_id, context=context, **kw)

    rt.run = run
    _modelo(rt, lambda *a, **k: _async(_resp("ok")))
    caso = Caso(id="c", turns=["1", "2"], context={"k": 1}, expect=[{"contains": "ok"}])
    await correr_eval(rt, _eval([caso]), "run3")
    assert recibidos[1] == {"k": 1}


async def _async(valor):
    return valor


async def test_caso_que_levanta_queda_en_error_y_sigue(tmp_path):
    rt = await _runtime(tmp_path)
    llamadas = []

    async def route(messages, requirements=None, **kw):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("proveedor caído")
        return _resp("ok")

    _modelo(rt, route)
    casos = [
        Caso(id="a", turns=["x"], expect=[{"contains": "ok"}]),
        Caso(id="b", turns=["y"], expect=[{"contains": "ok"}]),
    ]
    r = await correr_eval(rt, _eval(casos, pass_rate=0.5), "run4")
    estados = [c["status"] for c in r["cases"]]
    assert estados[1] == "pass"
    assert estados[0] in ("error", "fail")
    assert r["pass_rate"] == 0.5
    assert r["passed"] is True


async def test_umbrales_deciden_passed(tmp_path):
    rt = await _runtime(tmp_path)

    async def route(messages, requirements=None, **kw):
        return _resp("ok", usage={"input_tokens": 500, "output_tokens": 0})

    _modelo(rt, route)
    casos = [
        Caso(id="a", turns=["x"], expect=[{"contains": "ok"}]),
        Caso(id="b", turns=["y"], expect=[{"contains": "nunca"}]),
    ]
    r = await correr_eval(rt, _eval(casos, pass_rate=0.9), "run5")
    assert r["pass_rate"] == 0.5
    assert r["passed"] is False
    assert r["cases"][1]["status"] == "fail"
    assert r["cases"][1]["motivos"]
    r = await correr_eval(rt, _eval(casos[:1], max_avg_tokens=100), "run6")
    assert r["passed"] is False  # pasa el caso, pero 500 tokens > 100


async def test_juez_decide_y_sus_tokens_van_aparte(tmp_path):
    rt = await _runtime(tmp_path)

    async def route(messages, requirements=None, **kw):
        return _resp("hay 12", usage={"input_tokens": 10, "output_tokens": 2})

    _modelo(rt, route)

    class Juez:
        def __init__(self, score):
            self.score = score

        async def complete(self, messages, **kw):
            return _resp(
                f'{{"score": {self.score}, "reason": "r"}}',
                usage={"input_tokens": 50, "output_tokens": 5},
            )

    caso = Caso(id="c", turns=["q"], rubric="dice 12")
    ev = _eval([caso], judge_model={"provider": "ollama"}, judge_pass_score=0.7)
    r = await correr_eval(rt, ev, "run7", juez=Juez(0.9))
    c = r["cases"][0]
    assert c["status"] == "pass"
    assert c["judge"] == {"score": 0.9, "reason": "r"}
    assert c["judge_tokens"] == 55
    assert c["tokens_in"] + c["tokens_out"] == 12
    r = await correr_eval(rt, ev, "run8", juez=Juez(0.2))
    assert r["cases"][0]["status"] == "fail"


async def test_block_sin_fixture_no_ejecuta(tmp_path):
    rt = await _runtime(tmp_path)
    n = []

    async def route(messages, requirements=None, **kw):
        n.append(1)
        if len(n) == 1:
            return _resp(tool_calls=[{"id": "t1", "name": "stock", "arguments": {}}])
        return _resp("ok")

    _modelo(rt, route)
    caso = Caso(id="c", turns=["q"], expect=[{"tool_called": "stock"}])
    r = await correr_eval(rt, _eval([caso], tools_default="block"), "run9")
    assert r["cases"][0]["status"] == "pass"
    assert EJECUCIONES == []


async def test_run_que_levanta_deja_error_con_el_mensaje(tmp_path, monkeypatch):
    rt = await _runtime(tmp_path)

    async def run(*a, **kw):
        raise RuntimeError("se cayó")

    monkeypatch.setattr(rt, "run", run)
    r = await correr_eval(rt, _eval([Caso(id="a", turns=["x"], expect=[{"contains": "ok"}])]), "r")
    (c,) = r["cases"]
    assert c["status"] == "error"
    assert c["motivos"] == ["RuntimeError: se cayó"]
