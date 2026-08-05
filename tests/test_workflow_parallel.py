"""Paso PARALLEL: los sub-pasos corren a la vez y sus outputs se mergean al contexto."""

import asyncio

import pytest

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec


class _RuntimeLento:
    """Duerme `demora` por agente para que el paralelismo sea observable."""

    def __init__(self, demora=0.05, rotos=()):
        self._demora = demora
        self._rotos = set(rotos)
        self.llamados = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        await asyncio.sleep(self._demora)
        self.llamados.append(agent_name)
        if agent_name in self._rotos:
            raise RuntimeError(f"{agent_name} explotó")
        return {"answer": f"ok {agent_name}", "steps": []}


async def _correr(runtime, steps, trigger=None):
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(WorkflowSpec(name="wf", steps=steps))
    return await engine.run("wf", trigger=trigger or {})


def _paralelo(*subs):
    return StepSpec(name="fanout", parallel=list(subs))


async def test_los_subpasos_corren_concurrentemente():
    runtime = _RuntimeLento(demora=0.1)
    inicio = asyncio.get_event_loop().time()

    await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x"),
                StepSpec(name="b", agent="dos", input_template="x"),
                StepSpec(name="c", agent="tres", input_template="x"),
            )
        ],
    )

    transcurrido = asyncio.get_event_loop().time() - inicio
    assert transcurrido < 0.25, f"parecen secuenciales: tardó {transcurrido:.2f}s para 3x0.1s"
    assert set(runtime.llamados) == {"uno", "dos", "tres"}


async def test_cada_subresultado_queda_direccionable_por_nombre():
    runtime = _RuntimeLento(demora=0)
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x"),
                StepSpec(name="b", agent="dos", input_template="x"),
            )
        ],
    )

    assert result.steps["a"].status == StepStatus.SUCCESS
    assert result.steps["b"].status == StepStatus.SUCCESS
    assert result.steps["a"].output["answer"] == "ok uno"


async def test_una_rama_que_falla_no_tumba_a_las_hermanas():
    runtime = _RuntimeLento(demora=0, rotos={"malo"})
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="malo", input_template="x", on_error="continue"),
                StepSpec(name="b", agent="bueno", input_template="x"),
            )
        ],
    )

    assert result.steps["a"].status == StepStatus.ERROR
    assert result.steps["b"].status == StepStatus.SUCCESS


async def test_guardas_de_subpasos_se_respetan():
    runtime = _RuntimeLento(demora=0)
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x", when="{{ trigger.n > 7 }}"),
                StepSpec(name="b", agent="dos", input_template="x", when="{{ trigger.n < 7 }}"),
            )
        ],
        trigger={"n": 9},
    )

    assert result.steps["a"].status == StepStatus.SUCCESS
    assert result.steps["b"].status == StepStatus.SKIPPED
    assert runtime.llamados == ["uno"]


async def test_las_guardas_quedan_en_el_slot_when():
    """El paso siguiente puede leer `when.<sub>` para decidir."""
    runtime = _RuntimeLento(demora=0)
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(name="a", agent="uno", input_template="x", when="{{ trigger.n > 7 }}"),
            ),
            StepSpec(name="tardio", agent="tres", input_template="x", when="{{ not when.a }}"),
        ],
        trigger={"n": 2},
    )

    assert result.steps["a"].status == StepStatus.SKIPPED
    assert result.steps["tardio"].status == StepStatus.SUCCESS


async def test_retry_por_rama():
    class _RuntimeIntermitente:
        def __init__(self):
            self.intentos = 0

        async def run(self, agent_name, query, session_id, context=None, **kw):
            self.intentos += 1
            if self.intentos < 3:
                raise RuntimeError("todavía no")
            return {"answer": "ok", "steps": []}

    runtime = _RuntimeIntermitente()
    result = await _correr(
        runtime,
        [
            _paralelo(
                StepSpec(
                    name="a",
                    agent="uno",
                    input_template="x",
                    retry={"max_attempts": 3, "initial_delay_seconds": 0},
                )
            )
        ],
    )

    assert result.steps["a"].status == StepStatus.SUCCESS
    assert runtime.intentos == 3


def test_step_spec_rechaza_parallel_junto_a_agent():
    with pytest.raises(ValueError, match="exactly one"):
        StepSpec(name="x", agent="a", parallel=[StepSpec(name="s", agent="b")])
