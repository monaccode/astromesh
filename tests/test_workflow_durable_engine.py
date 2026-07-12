from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _StubExecutor:
    """Resuelve agent/tool a un output fijo; delega wait a un StepResult SUSPENDED."""

    def __init__(self):
        from astromesh.workflow.executor import StepExecutor

        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult

        if step.step_type.value == "wait":
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


def _engine(steps, store):
    from astromesh.workflow import WorkflowEngine

    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=steps)}
    eng._executor = _StubExecutor()
    return eng


async def test_run_without_wait_returns_full_result():
    store = InMemoryRunStore()
    eng = _engine([StepSpec(name="a", tool="t"), StepSpec(name="b", tool="t")], store)
    result = await eng.run("wf", trigger={"x": 1})
    assert result.status == "completed"
    assert result.run_id is not None
    assert result.steps["a"].output == {"ok": "a"}
    assert (await store.load(result.run_id)).status == "completed"


async def test_run_with_wait_suspends_and_persists():
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(name="a", tool="t"),
            StepSpec(name="w", wait={"resume_key": "k"}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    result = await eng.run("wf", trigger={})
    assert result.status == "suspended"
    saved = await store.load(result.run_id)
    assert saved.status == "suspended"
    assert saved.current_index == 2  # posterior al wait (índice de "b")
    assert saved.context["steps"]["a"]["output"] == {"ok": "a"}


async def test_switch_goto_to_wait_suspends():
    """A switch step whose branch goto's a wait step must suspend the run,
    not silently complete it (the wait's output would otherwise be stored
    as an ordinary step output and the run marked COMPLETED)."""

    class _SwitchStubExecutor(_StubExecutor):
        """Como _StubExecutor pero también delega switch al StepExecutor real,
        para que el goto se resuelva de verdad y apunte al step wait."""

        async def execute_step(self, step, context):
            if step.step_type.value in ("wait", "switch"):
                return await self._real.execute_step(step, context)
            return await super().execute_step(step, context)

    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(name="s", switch=[{"default": True, "goto": "w"}]),
            StepSpec(name="w", wait={"resume_key": "k"}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    eng._executor = _SwitchStubExecutor()

    result = await eng.run("wf", trigger={})

    assert result.status == "suspended"
    assert result.run_id is not None
    saved = await store.load(result.run_id)
    assert saved.status == "suspended"


async def test_bootstrap_runs_orphan_sweep(tmp_path, monkeypatch):
    from astromesh.workflow import WorkflowEngine
    from astromesh.workflow.models import WorkflowRun
    from astromesh.workflow.store import InMemoryRunStore

    store = InMemoryRunStore()
    await store.create(
        WorkflowRun(
            run_id="orphan", workflow_name="w", status="running", current_index=0, context={}
        )
    )
    eng = WorkflowEngine(workflows_dir=str(tmp_path), runtime=None, tool_registry=None, store=store)
    await eng.bootstrap()
    assert (await store.load("orphan")).status == "failed"
