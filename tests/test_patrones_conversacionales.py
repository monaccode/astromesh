"""Los patrones que CLARUS ofrece se portan como agentes conversacionales."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from astromesh.errors import AgentConfigError
from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ciclo_de_tools,
    mensajes_de_conversacion,
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.runtime.engine import AgentRuntime


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


CTX = {"_history_messages": HISTORIA, "_turn_context": "CTX"}


def _primera(model_fn):
    return model_fn.await_args_list[0].args[0]


@pytest.mark.asyncio
async def test_plan_and_execute_planifica_y_sintetiza_con_la_conversacion():
    model_fn = AsyncMock(
        side_effect=[
            Resp('{"steps": [{"step": 1, "description": "buscar"}]}'),
            Resp("paso hecho"),
            Resp("final"),
        ]
    )
    r = await PlanAndExecutePattern().execute("¿cómo me llamo?", CTX, model_fn, AsyncMock(), [])
    assert r["answer"] == "final"
    assert _primera(model_fn)[:2] == HISTORIA
    assert _primera(model_fn)[2]["content"] == "CTX\n\n¿cómo me llamo?"
    assert model_fn.await_args_list[2].args[0][:2] == HISTORIA  # sintetizador


@pytest.mark.asyncio
async def test_plan_and_execute_un_paso_ve_el_resultado_de_su_tool():
    tc = {"id": "t1", "name": "buscar", "arguments": {}}
    model_fn = AsyncMock(
        side_effect=[
            Resp('{"steps": [{"step": 1, "description": "buscar"}]}'),
            Resp("", tool_calls=[tc]),
            Resp("con el dato"),
            Resp("final"),
        ]
    )
    tool_fn = AsyncMock(return_value="dato")
    await PlanAndExecutePattern().execute("q", {}, model_fn, tool_fn, [])
    assert model_fn.await_args_list[2].args[0][-1]["content"] == "dato"
    assert "con el dato" in model_fn.await_args_list[3].args[0][-1]["content"]


@pytest.mark.asyncio
async def test_plan_que_no_es_json_igual_sintetiza_con_la_historia():
    model_fn = AsyncMock(side_effect=[Resp("no es json"), Resp("paso"), Resp("final")])
    r = await PlanAndExecutePattern().execute("q", CTX, model_fn, AsyncMock(), [])
    assert r["answer"] == "final"
    assert model_fn.await_args_list[2].args[0][:2] == HISTORIA


@pytest.mark.asyncio
async def test_pipeline_usa_las_etapas_declaradas_y_la_primera_ve_la_conversacion():
    model_fn = AsyncMock(side_effect=[Resp("uno"), Resp("dos")])
    r = await PipelinePattern(stages=["leer", "contestar"]).execute(
        "q", CTX, model_fn, AsyncMock(), []
    )
    assert r["answer"] == "dos"
    roles = [c.kwargs["role"] for c in model_fn.await_args_list]
    assert roles == ["stage:leer", "stage:contestar"]
    assert _primera(model_fn)[:2] == HISTORIA
    assert "uno" in model_fn.await_args_list[1].args[0][-1]["content"]


@pytest.mark.asyncio
async def test_pipeline_la_salida_de_una_etapa_es_su_respuesta_no_la_tool():
    tc = {"id": "t1", "name": "buscar", "arguments": {}}
    model_fn = AsyncMock(side_effect=[Resp("", tool_calls=[tc]), Resp("resumen"), Resp("fin")])
    await PipelinePattern(stages=["a", "b"]).execute(
        "q", {}, model_fn, AsyncMock(return_value="CRUDO"), []
    )
    entrada_b = model_fn.await_args_list[2].args[0][-1]["content"]
    assert "resumen" in entrada_b
    assert "CRUDO" not in entrada_b


@pytest.mark.asyncio
async def test_fan_out_descompone_y_junta_con_la_conversacion_y_las_subtareas_usan_tools():
    tc = {"id": "t1", "name": "buscar", "arguments": {}}
    model_fn = AsyncMock(
        side_effect=[
            Resp('["sub"]'),
            Resp("", tool_calls=[tc]),
            Resp("sub hecha"),
            Resp("junto"),
        ]
    )
    tool_fn = AsyncMock(return_value="dato")
    r = await ParallelFanOutPattern().execute("q", CTX, model_fn, tool_fn, [])
    assert r["answer"] == "junto"
    tool_fn.assert_awaited_once()
    assert _primera(model_fn)[:2] == HISTORIA
    assert model_fn.await_args_list[3].args[0][:2] == HISTORIA


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patron", [PlanAndExecutePattern(), PipelinePattern(stages=["a", "b"]), ParallelFanOutPattern()]
)
async def test_una_consulta_multimodal_no_se_pierde(patron):
    partes = [{"type": "text", "text": "mirá"}, {"type": "image_url", "image_url": {"url": "x"}}]
    model_fn = AsyncMock(return_value=Resp('["s"]'))
    await patron.execute(partes, {}, model_fn, AsyncMock(), [])
    assert _primera(model_fn)[0]["content"] == partes


@pytest.mark.parametrize("cls", [PlanAndExecutePattern, PipelinePattern, ParallelFanOutPattern])
def test_reciben_el_contexto_del_turno_como_mensaje(cls):
    assert cls.consumes_turn_context is True


@pytest.mark.asyncio
async def test_plan_con_pasos_como_strings_ejecuta_uno_por_string():
    model_fn = AsyncMock(
        side_effect=[
            Resp('{"steps": ["buscar", "resumir"]}'),
            Resp("a"),
            Resp("b"),
            Resp("final"),
        ]
    )
    r = await PlanAndExecutePattern().execute("q", {}, model_fn, AsyncMock(), [])
    assert r["answer"] == "final"
    assert "buscar" in model_fn.await_args_list[1].args[0][-1]["content"]
    assert "resumir" in model_fn.await_args_list[2].args[0][-1]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("plan", ['{"steps": "texto"}', '{"steps": []}'])
async def test_plan_sin_lista_de_pasos_cae_a_un_solo_paso(plan):
    model_fn = AsyncMock(side_effect=[Resp(plan), Resp("paso"), Resp("final")])
    r = await PlanAndExecutePattern().execute("q", {}, model_fn, AsyncMock(), [])
    assert r["answer"] == "final"
    assert model_fn.await_count == 3


def _schema(nombre):
    return {"type": "function", "function": {"name": nombre, "description": "", "parameters": {}}}


@pytest.mark.asyncio
async def test_supervisor_solo_ofrece_sus_trabajadores_y_ve_la_conversacion():
    tc = {"id": "t1", "name": "consultar_ventas", "arguments": {"query": "x"}}
    model_fn = AsyncMock(side_effect=[Resp("", tool_calls=[tc]), Resp("listo")])
    tool_fn = AsyncMock(return_value="ventas ok")
    r = await SupervisorPattern(workers=["consultar_ventas", "consultar_stock"]).execute(
        "q",
        CTX,
        model_fn,
        tool_fn,
        [_schema("consultar_ventas"), _schema("consultar_stock"), _schema("praxis_buscar")],
    )
    assert r["answer"] == "listo"
    ofrecidas = [t["function"]["name"] for t in model_fn.await_args_list[0].args[1]]
    assert ofrecidas == ["consultar_ventas", "consultar_stock"]
    assert model_fn.await_args_list[0].kwargs["role"] == "supervisor"
    assert _primera(model_fn)[:2] == HISTORIA
    tool_fn.assert_awaited_once_with("consultar_ventas", {"query": "x"})


@pytest.mark.asyncio
async def test_supervisor_no_ejecuta_una_tool_que_no_es_trabajador():
    tc = {"id": "t1", "name": "praxis_buscar", "arguments": {}}
    model_fn = AsyncMock(side_effect=[Resp("", tool_calls=[tc]), Resp("ok")])
    tool_fn = AsyncMock()
    await SupervisorPattern(workers=["consultar_ventas"]).execute(
        "q", {}, model_fn, tool_fn, [_schema("consultar_ventas"), _schema("praxis_buscar")]
    )
    tool_fn.assert_not_called()


def _runtime():
    return AgentRuntime.__new__(AgentRuntime)


def test_supervisor_sin_tools_agent_no_construye():
    with pytest.raises(AgentConfigError, match="supervisor"):
        _runtime()._build_pattern(
            {
                "orchestration": {"pattern": "supervisor"},
                "tools": [{"name": "x", "type": "builtin"}],
            }
        )


def test_supervisor_toma_sus_trabajadores_de_las_tools_agent():
    p = _runtime()._build_pattern(
        {
            "orchestration": {"pattern": "supervisor"},
            "tools": [
                {"name": "consultar_a", "type": "agent", "agent": "a"},
                {"name": "datetime_now", "type": "builtin"},
                {"name": "consultar_b", "type": "agent", "agent": "b"},
            ],
        }
    )
    assert isinstance(p, SupervisorPattern)
    assert p._workers == ["consultar_a", "consultar_b"]


def test_pipeline_lee_stages_del_yaml():
    p = _runtime()._build_pattern({"orchestration": {"pattern": "pipeline", "stages": ["a", "b"]}})
    assert p._stages == ["a", "b"]


@pytest.mark.parametrize("stages", [["solo"], ["a"] * 7, ["a", ""], ["a", "x" * 41], "ab", [1, 2]])
def test_pipeline_con_stages_invalidas_no_construye(stages):
    with pytest.raises(AgentConfigError, match="stages"):
        _runtime()._build_pattern({"orchestration": {"pattern": "pipeline", "stages": stages}})
