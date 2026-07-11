from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _ApprovalStubExecutor:
    """Delegates wait/approval/switch to the real executor; fixed output otherwise."""

    def __init__(self):
        from astromesh.workflow.executor import StepExecutor

        self._real = StepExecutor(runtime=None, tool_registry=None)

    async def execute_step(self, step, context):
        from astromesh.workflow.models import StepResult

        if step.step_type.value in ("wait", "approval", "switch"):
            return await self._real.execute_step(step, context)
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


def _engine(steps, store):
    from astromesh.workflow import WorkflowEngine

    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {"wf": WorkflowSpec(name="wf", steps=steps)}
    eng._executor = _ApprovalStubExecutor()
    return eng


async def test_run_suspends_at_approval_with_pending_approval():
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(name="a", tool="t"),
            StepSpec(name="aprobar", approval={"approver": "role:mgr", "prompt": "ok?"}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    result = await eng.run("wf", trigger={})
    assert result.status == "suspended"
    saved = await store.load(result.run_id)
    assert saved.status == "suspended"
    assert saved.current_index == 2  # past the approval (index of "b")
    assert saved.pending_approval == {
        "step_name": "aprobar",
        "approver": "role:mgr",
        "prompt": "ok?",
    }
