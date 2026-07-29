"""on_error: continue registra el fallo y sigue; el default sigue cortando."""

from astromesh.workflow import WorkflowEngine
from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec


class _RuntimeQueRompe:
    """Falla para los agentes en `rotos`, responde bien para el resto."""

    def __init__(self, rotos):
        self._rotos = rotos
        self.llamados = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.llamados.append(agent_name)
        if agent_name in self._rotos:
            raise RuntimeError(f"{agent_name} explotó")
        return {"answer": f"ok {agent_name}", "steps": []}


async def _correr(runtime, steps):
    engine = WorkflowEngine(workflows_dir="", runtime=runtime, tool_registry=None)
    await engine.bootstrap()
    engine.register_workflow(WorkflowSpec(name="wf", steps=steps))
    return await engine.run("wf", trigger={})


async def test_continue_sigue_con_el_resto():
    runtime = _RuntimeQueRompe({"malo"})
    result = await _correr(
        runtime,
        [
            StepSpec(name="uno", agent="malo", input_template="x", on_error="continue"),
            StepSpec(name="dos", agent="bueno", input_template="x"),
        ],
    )

    assert result.status == "completed"
    assert result.steps["uno"].status == StepStatus.ERROR
    assert result.steps["dos"].status == StepStatus.SUCCESS
    assert "bueno" in runtime.llamados


async def test_sin_on_error_corta_el_run():
    """Comportamiento histórico: el default sigue siendo cortar."""
    runtime = _RuntimeQueRompe({"malo"})
    result = await _correr(
        runtime,
        [
            StepSpec(name="uno", agent="malo", input_template="x"),
            StepSpec(name="dos", agent="bueno", input_template="x"),
        ],
    )

    assert result.status == "failed"
    assert "bueno" not in runtime.llamados


async def test_continue_deja_el_error_en_el_resultado():
    runtime = _RuntimeQueRompe({"malo"})
    result = await _correr(
        runtime,
        [
            StepSpec(name="uno", agent="malo", input_template="x", on_error="continue"),
            StepSpec(name="dos", agent="bueno", input_template="x"),
        ],
    )

    assert result.steps["uno"].error
    assert "explotó" in result.steps["uno"].error
