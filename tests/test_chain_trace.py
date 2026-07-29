"""Toda la cadena tiene que colgar de un solo árbol de trazas."""

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import StepSpec, WorkflowSpec


class _RuntimeSpy:
    def __init__(self):
        self.trazas = []
        self.sesiones = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.trazas.append(parent_trace_id)
        self.sesiones.append(session_id)
        return {"answer": f"ok {agent_name}", "steps": []}


async def _correr(runtime, steps):
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(WorkflowSpec(name="__chain__a", steps=steps))
    return await engine.run("__chain__a", trigger={"query": "hola"})


async def test_todos_los_eslabones_comparten_trace_y_sesion():
    runtime = _RuntimeSpy()

    await _correr(
        runtime,
        [
            StepSpec(name="a", agent="a", input_template="{{ trigger.query }}"),
            StepSpec(name="a__b", agent="b", input_template="{{ steps.a.output.answer }}"),
            StepSpec(name="a__c", agent="c", input_template="{{ steps.a.output.answer }}"),
        ],
    )

    assert len(runtime.trazas) == 3
    assert len(set(runtime.trazas)) == 1, f"trazas distintas: {runtime.trazas}"
    assert runtime.trazas[0] is not None
    assert len(set(runtime.sesiones)) == 1, f"sesiones distintas: {runtime.sesiones}"


async def test_el_resultado_trae_los_spans_de_cada_eslabon():
    runtime = _RuntimeSpy()

    result = await _correr(
        runtime,
        [
            StepSpec(name="a", agent="a", input_template="{{ trigger.query }}"),
            StepSpec(name="a__b", agent="b", input_template="x"),
        ],
    )

    assert result.trace
    volcado = str(result.trace)
    assert "step.a" in volcado
    assert "step.a__b" in volcado


async def test_los_eslabones_de_un_paso_paralelo_tambien_comparten_trace():
    runtime = _RuntimeSpy()

    await _correr(
        runtime,
        [
            StepSpec(name="a", agent="a", input_template="{{ trigger.query }}"),
            StepSpec(
                name="a__fanout",
                parallel=[
                    StepSpec(name="a__b", agent="b", input_template="x"),
                    StepSpec(name="a__c", agent="c", input_template="x"),
                ],
            ),
        ],
    )

    assert len(runtime.trazas) == 3
    assert len(set(runtime.trazas)) == 1, f"trazas distintas: {runtime.trazas}"
