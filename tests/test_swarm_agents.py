"""Swarm: el handoff es una tool `type: agent` y la respuesta del destino es la final."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from astromesh.orchestration.swarm import CLAVE_HANDOFFS, SwarmPattern


@dataclass
class Resp:
    content: str
    tool_calls: list | None = None
    reasoning_content: str | None = None


def _schema(name):
    return {"type": "function", "function": {"name": name, "parameters": {}}}


TOOLS = [_schema("especialista"), _schema("leer")]
HANDOFF = {"id": "t1", "name": "especialista", "arguments": {"query": "revisá esto"}}


def _fns(*respuestas, obs=None):
    model_fn = AsyncMock(side_effect=list(respuestas))
    tool_fn = AsyncMock(return_value=obs if obs is not None else {"answer": "listo"})
    return model_fn, tool_fn


async def test_handoff_devuelve_la_respuesta_del_destino_como_final():
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]))
    r = await SwarmPattern(workers=["especialista"]).execute("q", {}, model_fn, tool_fn, TOOLS)
    assert r["answer"] == "listo"
    assert r["final_agent"] == "especialista"
    assert model_fn.await_count == 1


async def test_el_destino_recibe_la_historia():
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]))
    ctx = {
        "_history_messages": [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "¿qué necesitás?"},
        ]
    }
    await SwarmPattern(workers=["especialista"]).execute("q", ctx, model_fn, tool_fn, TOOLS)
    assert tool_fn.await_args.args[0] == "especialista"
    args = tool_fn.await_args.args[1]
    assert "hola" in args["query"]
    assert "¿qué necesitás?" in args["query"]
    assert "revisá esto" in args["query"]


async def test_handoff_incrementa_el_contador():
    for previo, esperado in ((None, 1), (2, 3)):
        model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]))
        ctx = {} if previo is None else {CLAVE_HANDOFFS: previo}
        await SwarmPattern(workers=["especialista"], max_handoffs=5).execute(
            "q", ctx, model_fn, tool_fn, TOOLS
        )
        assert tool_fn.await_args.args[1][CLAVE_HANDOFFS] == esperado


async def test_tope_de_handoffs_no_ofrece_agentes_ni_los_ejecuta():
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]), Resp("sin pasar"), obs="x")
    r = await SwarmPattern(workers=["especialista"], max_handoffs=3).execute(
        "q", {CLAVE_HANDOFFS: 3}, model_fn, tool_fn, TOOLS
    )
    ofrecidas = [t["function"]["name"] for t in model_fn.await_args_list[0].args[1]]
    assert "especialista" not in ofrecidas
    assert "leer" in ofrecidas
    assert all(c.args[0] != "especialista" for c in tool_fn.await_args_list)
    assert r["answer"] == "sin pasar"


async def test_tool_comun_es_observacion_no_final():
    leer = {"id": "t1", "name": "leer", "arguments": {"p": 1}}
    model_fn, tool_fn = _fns(Resp("", tool_calls=[leer]), Resp("segunda"), obs="dato")
    r = await SwarmPattern(workers=["especialista"]).execute("q", {}, model_fn, tool_fn, TOOLS)
    tool_fn.assert_awaited_once_with("leer", {"p": 1})
    assert model_fn.await_count == 2
    assert r["answer"] == "segunda"


async def test_sin_handoff_contesta_directo():
    model_fn, tool_fn = _fns(Resp("directo"))
    r = await SwarmPattern(workers=["especialista"]).execute("q", {}, model_fn, tool_fn, TOOLS)
    assert r["answer"] == "directo"
    tool_fn.assert_not_called()


async def test_no_agrega_un_system_propio():
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]))
    ctx = {"_history_messages": [{"role": "user", "content": "hola"}]}
    await SwarmPattern(workers=["especialista"]).execute("q", ctx, model_fn, tool_fn, TOOLS)
    mensajes = model_fn.await_args_list[0].args[0]
    assert all(m["role"] != "system" for m in mensajes)
    assert model_fn.await_args_list[0].kwargs["role"] == "reasoner"


async def test_ciclo_de_tools_final_no_ejecuta_las_demas_tool_calls():
    from astromesh.orchestration.patterns import ciclo_de_tools

    leer = {"id": "t2", "name": "leer", "arguments": {}}
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF, leer]))
    r = await ciclo_de_tools(
        [{"role": "user", "content": "q"}],
        model_fn,
        tool_fn,
        TOOLS,
        5,
        role="reasoner",
        finales={"especialista"},
    )
    assert r["answer"] == "listo"
    assert r["final_agent"] == "especialista"
    assert tool_fn.await_count == 1


@pytest.mark.parametrize(
    ("obs", "marca"),
    [
        ({"error": "Rate limit exceeded for 'especialista'"}, "Rate limit"),
        ({"error": "confirmacion_requerida", "tool": "especialista"}, "confirmacion_requerida"),
        ({"data_error": "schema"}, "data_error"),
        ("La tool «especialista» no está disponible para este agente.", "no está disponible"),
    ],
)
async def test_handoff_fallido_vuelve_al_modelo_y_su_respuesta_es_la_final(obs, marca):
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]), Resp("contesto yo"), obs=obs)
    r = await SwarmPattern(workers=["especialista"]).execute("q", {}, model_fn, tool_fn, TOOLS)
    assert model_fn.await_count == 2
    visto = model_fn.await_args_list[1].args[0][-1]
    assert visto["role"] == "tool"
    assert marca in visto["content"]
    assert r["answer"] == "contesto yo"
    assert "final_agent" not in r


@pytest.mark.parametrize("valor", ["x", None, -1, True, 1.5])
async def test_contador_invalido_en_el_context_cuenta_como_cero(valor):
    model_fn, tool_fn = _fns(Resp("", tool_calls=[HANDOFF]))
    await SwarmPattern(workers=["especialista"], max_handoffs=1).execute(
        "q", {CLAVE_HANDOFFS: valor}, model_fn, tool_fn, TOOLS
    )
    assert tool_fn.await_args.args[1][CLAVE_HANDOFFS] == 1


def test_handoffs_de():
    from astromesh.orchestration.swarm import handoffs_de

    assert [handoffs_de(v) for v in (0, 2, -3, "2", None, True, False, 2.0)] == [
        0,
        2,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
