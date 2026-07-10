# tests/test_workflow_resume.py
import pytest

from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _StubExecutor:
    def __init__(self):
        from astromesh.workflow.executor import StepExecutor
        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult
        if step.step_type.value == "wait":
            return await self._real.execute_step(step, context)
        # 'b' expone el payload del resume para poder asertarlo
        return StepResult(name=step.name, status=StepStatus.SUCCESS,
                          output={"seen_resume": context.get("resume")})


def _engine(store):
    from astromesh.workflow import WorkflowEngine
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=[
        StepSpec(name="a", tool="t"),
        StepSpec(name="w", wait={"resume_key": "k"}),
        StepSpec(name="b", tool="t")])}
    eng._executor = _StubExecutor()
    return eng


async def test_resume_continues_to_completion():
    store = InMemoryRunStore()
    eng = _engine(store)
    r1 = await eng.run("wf", trigger={})
    assert r1.status == "suspended"
    r2 = await eng.resume(r1.run_id, payload={"amount": 100})
    assert r2.status == "completed"
    assert r2.steps["b"].output == {"seen_resume": {"amount": 100}}
    assert (await store.load(r1.run_id)).status == "completed"


async def test_resume_from_fresh_store_instance_is_durable():
    store = InMemoryRunStore()
    r1 = await _engine(store).run("wf", trigger={})
    # nuevo engine, MISMO store (simula otro proceso)
    eng2 = _engine(store)
    r2 = await eng2.resume(r1.run_id, payload={"amount": 5})
    assert r2.status == "completed"


async def test_resume_non_suspended_raises():
    store = InMemoryRunStore()
    eng = _engine(store)
    r1 = await eng.run("wf", trigger={})
    await eng.resume(r1.run_id, payload={})           # completa
    with pytest.raises(ValueError):
        await eng.resume(r1.run_id, payload={})       # ya no está suspended
