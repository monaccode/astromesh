"""Los patrones que CLARUS ofrece se portan como agentes conversacionales."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from astromesh.orchestration.patterns import ciclo_de_tools, mensajes_de_conversacion


@dataclass
class Resp:
    content: str
    tool_calls: list | None = None
    reasoning_content: str | None = None


HISTORIA = [
    {"role": "user", "content": "me llamo Ana"},
    {"role": "assistant", "content": "hola Ana"},
]


def test_mensajes_de_conversacion_lleva_historia_y_contexto_del_turno():
    msgs = mensajes_de_conversacion(
        "¿cómo me llamo?", {"_history_messages": HISTORIA, "_turn_context": "CTX"}
    )
    assert msgs[:2] == HISTORIA
    assert msgs[2] == {"role": "user", "content": "CTX\n\n¿cómo me llamo?"}


def test_mensajes_de_conversacion_sin_contexto():
    assert mensajes_de_conversacion("hola", None) == [{"role": "user", "content": "hola"}]


@pytest.mark.asyncio
async def test_ciclo_de_tools_devuelve_el_resultado_al_modelo():
    tc = {"id": "t1", "name": "buscar", "arguments": {"q": "x"}}
    model_fn = AsyncMock(side_effect=[Resp("", tool_calls=[tc]), Resp("listo")])
    tool_fn = AsyncMock(return_value="dato")
    r = await ciclo_de_tools(
        [{"role": "user", "content": "q"}], model_fn, tool_fn, [], 5, role="worker"
    )
    assert r["answer"] == "listo"
    segunda = model_fn.await_args_list[1].args[0]
    assert segunda[-1] == {"role": "tool", "content": "dato", "tool_call_id": "t1"}
    assert model_fn.await_args_list[0].kwargs["role"] == "worker"


@pytest.mark.asyncio
async def test_ciclo_de_tools_no_ejecuta_una_tool_fuera_de_permitidas():
    tc = {"id": "t1", "name": "borrar_todo", "arguments": {}}
    model_fn = AsyncMock(side_effect=[Resp("", tool_calls=[tc]), Resp("ok")])
    tool_fn = AsyncMock()
    await ciclo_de_tools(
        [{"role": "user", "content": "q"}],
        model_fn,
        tool_fn,
        [],
        5,
        role="supervisor",
        permitidas={"consultar_ventas"},
    )
    tool_fn.assert_not_called()
    obs = model_fn.await_args_list[1].args[0][-1]
    assert obs["content"] == "La tool «borrar_todo» no está disponible para este agente."
