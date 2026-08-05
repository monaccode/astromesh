"""Guarda `when` por paso: si no matchea, el paso queda SKIPPED y el run sigue."""

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec


class _RuntimeSpy:
    def __init__(self):
        self.llamados = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.llamados.append(agent_name)
        return {"answer": f"ok {agent_name}", "steps": []}


def _executor(runtime):
    return StepExecutor(runtime=runtime, tool_registry=None)


async def _correr(runtime, steps, trigger=None):
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(WorkflowSpec(name="wf", steps=steps))
    return await engine.run("wf", trigger=trigger or {})


async def test_guarda_verdadera_ejecuta_el_paso():
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x", when="{{ score > 7 }}")

    result = await _executor(runtime).execute_step(step, {"score": 9})

    assert result.status == StepStatus.SUCCESS
    assert result.condition_matched is True
    assert runtime.llamados == ["a"]


async def test_guarda_falsa_saltea_el_paso():
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x", when="{{ score > 7 }}")

    result = await _executor(runtime).execute_step(step, {"score": 2})

    assert result.status == StepStatus.SKIPPED
    assert result.condition_matched is False
    assert runtime.llamados == [], "el agente no debía ejecutarse"


async def test_sin_guarda_se_ejecuta_siempre():
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x")

    result = await _executor(runtime).execute_step(step, {})

    assert result.status == StepStatus.SUCCESS
    assert result.condition_matched is None
    assert runtime.llamados == ["a"]


async def test_guarda_acepta_yes_y_1():
    runtime = _RuntimeSpy()
    for expr in ("{{ 'yes' }}", "{{ 1 }}", "{{ true }}"):
        result = await _executor(runtime).execute_step(
            StepSpec(name="n", agent="a", input_template="x", when=expr), {}
        )
        assert result.status == StepStatus.SUCCESS, f"{expr} debía matchear"


async def test_guarda_no_estricta_con_campo_inexistente_da_falso():
    """Comportamiento histórico para workflows escritos a mano: rinde vacío y saltea.

    Es exactamente el modo de fallo que motivó `strict_conditions`: un `when` con
    un typo se comporta igual que uno que da falso, sin dejar rastro.
    """
    runtime = _RuntimeSpy()
    step = StepSpec(name="uno", agent="a", input_template="x", when="{{ output.data.ok }}")

    # `output.data` existe pero no trae `ok`: la búsqueda falla y rinde vacío.
    result = await _executor(runtime).execute_step(step, {"output": {"data": {}}})

    assert result.status == StepStatus.SKIPPED
    assert runtime.llamados == []


async def test_guarda_estricta_con_campo_inexistente_da_error():
    """Con la guarda estricta el mismo `when` grita en vez de saltear en silencio."""
    runtime = _RuntimeSpy()
    step = StepSpec(
        name="uno",
        agent="a",
        input_template="x",
        when="{{ output.data.ok }}",
        strict_conditions=True,
    )

    result = await _executor(runtime).execute_step(step, {"output": {"data": {}}})

    assert result.status == StepStatus.ERROR
    assert "uno" in result.error
    assert runtime.llamados == []


async def test_comparacion_sobre_campo_inexistente_es_error_en_ambos_modos():
    """Una comparación contra un Undefined revienta en Jinja con o sin modo estricto;
    eso ya era así antes de la guarda y se reporta como error del paso."""
    runtime = _RuntimeSpy()
    for estricto in (False, True):
        step = StepSpec(
            name="uno",
            agent="a",
            input_template="x",
            when="{{ output.data.score > 7 }}",
            strict_conditions=estricto,
        )
        result = await _executor(runtime).execute_step(step, {})
        assert result.status == StepStatus.ERROR, f"strict={estricto}"
    assert runtime.llamados == []


async def test_drive_publica_el_resultado_de_la_guarda_en_contexto():
    result = await _correr(
        _RuntimeSpy(),
        [
            StepSpec(name="alto", agent="a", input_template="x", when="{{ trigger.n > 7 }}"),
            StepSpec(name="bajo", agent="b", input_template="x", when="{{ trigger.n <= 7 }}"),
        ],
        trigger={"n": 9},
    )

    assert result.status == "completed"
    assert result.steps["alto"].status == StepStatus.SUCCESS
    assert result.steps["bajo"].status == StepStatus.SKIPPED


async def test_un_paso_salteado_no_corta_el_run():
    runtime = _RuntimeSpy()
    result = await _correr(
        runtime,
        [
            StepSpec(name="salteado", agent="a", input_template="x", when="{{ false }}"),
            StepSpec(name="corre", agent="b", input_template="x"),
        ],
    )

    assert result.status == "completed"
    assert "b" in runtime.llamados, "el paso siguiente al salteado tenía que correr"


async def test_el_slot_when_es_legible_por_pasos_posteriores():
    runtime = _RuntimeSpy()
    result = await _correr(
        runtime,
        [
            StepSpec(name="alto", agent="a", input_template="x", when="{{ trigger.n > 7 }}"),
            StepSpec(name="fallback", agent="b", input_template="x", when="{{ not when.alto }}"),
        ],
        trigger={"n": 2},
    )

    assert result.steps["alto"].status == StepStatus.SKIPPED
    assert result.steps["fallback"].status == StepStatus.SUCCESS
