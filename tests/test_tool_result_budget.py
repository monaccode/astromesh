import json

import pytest

from astromesh.core import tokens
from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ReActPattern,
    ciclo_de_tools,
)
from astromesh.orchestration.supervisor import SupervisorPattern


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


class Resp:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = {}


def modelo_que_llama(nombre):
    """Primera vuelta: pide `nombre`; segunda: contesta."""
    llamadas = []

    async def model_fn(messages, tools, role=None):
        llamadas.append(list(messages))
        if len(llamadas) == 1:
            return Resp(tool_calls=[{"id": "t1", "name": nombre, "arguments": {}}])
        return Resp(content="listo")

    return model_fn, llamadas


GRANDE = [{"id": i, "v": "x" * 40} for i in range(2000)]


async def _correr(presupuesto, nombre="buscar", resultado=GRANDE):
    model_fn, llamadas = modelo_que_llama(nombre)

    async def tool_fn(name, args):
        return resultado

    r = await ciclo_de_tools(
        [{"role": "user", "content": "q"}],
        model_fn,
        tool_fn,
        [],
        5,
        "reasoner",
        presupuesto=presupuesto,
    )
    tool_msg = next(m for m in llamadas[1] if m["role"] == "tool")
    return r, tool_msg


async def test_sin_presupuesto_usa_el_default():
    _, msg = await _correr(None)
    assert tokens.estimate_tokens(msg["content"]) <= 8000
    assert json.loads(msg["content"])[-1]["_omitidos"] > 0


async def test_por_tool_gana_sobre_default():
    _, msg = await _correr({"default": 8000, "por_tool": {"buscar": 200}})
    assert tokens.estimate_tokens(msg["content"]) <= 200


async def test_default_del_agente_si_la_tool_no_tiene_propio():
    _, msg = await _correr({"default": 300, "por_tool": {"otra": 50}})
    assert 50 < tokens.estimate_tokens(msg["content"]) <= 300


async def test_dict_llega_como_json():
    _, msg = await _correr(None, resultado={"ok": True, "v": None})
    assert msg["content"] == '{"ok":true,"v":null}'


async def test_el_step_lleva_el_recorte_solo_si_hubo():
    r, _ = await _correr({"default": 200, "por_tool": {}})
    paso = next(s for s in r["steps"] if s.action == "buscar")
    assert paso.recorte["truncated"] is True
    assert paso.recorte["omitted"] > 0
    r2, _ = await _correr(None, resultado="corto")
    paso2 = next(s for s in r2["steps"] if s.action == "buscar")
    assert paso2.recorte is None


def _modelo_por_patron():
    """Modelo guionado por rol: planifica con JSON, UNA vez pide la tool, el resto contesta."""
    vistos = []
    pidio = []

    async def model_fn(messages, tools, role=None):
        vistos.append(list(messages))
        if role == "planner":
            return Resp('["a"]')
        if role == "synthesizer":
            return Resp("final")
        if not pidio:
            pidio.append(1)
            return Resp(tool_calls=[{"id": "t1", "name": "buscar", "arguments": {}}])
        return Resp("listo")

    return model_fn, vistos


@pytest.mark.parametrize(
    "patron",
    [
        ReActPattern(),
        PlanAndExecutePattern(),
        ParallelFanOutPattern(),
        PipelinePattern(stages=["a"]),
        SupervisorPattern(workers=["buscar"]),
    ],
    ids=lambda p: type(p).__name__,
)
async def test_cada_patron_pasa_el_presupuesto_del_context(patron):
    model_fn, vistos = _modelo_por_patron()
    # El planner devuelve una lista: fan_out la usa, plan_and_execute cae al paso por defecto.

    async def tool_fn(name, args):
        return GRANDE

    tools = [{"type": "function", "function": {"name": "buscar"}}]
    await patron.execute(
        query="q",
        context={"_presupuesto_tools": {"default": 150, "por_tool": {}}},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=tools,
    )
    msgs = [m for conv in vistos for m in conv if m["role"] == "tool"]
    assert msgs, "el patrón nunca llamó a la tool"
    assert all(tokens.estimate_tokens(m["content"]) <= 150 for m in msgs)


async def test_el_aviso_de_confirmacion_nunca_se_recorta():
    aviso = {
        "error": "confirmacion_requerida",
        "pendiente": {
            "tool": "crear_pedido",
            "argumentos": {f"campo_{i}": "valor " * 20 for i in range(50)},
        },
        "mensaje": "repetí EXACTAMENTE estos argumentos",
    }
    r, msg = await _correr({"default": 8000, "por_tool": {"buscar": 20}}, resultado=aviso)
    assert json.loads(msg["content"]) == aviso
    assert r["steps"][0].recorte is None
