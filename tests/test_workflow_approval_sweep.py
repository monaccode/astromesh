from astromesh.workflow.models import StepSpec, StepStatus, WorkflowSpec
from astromesh.workflow.store import InMemoryRunStore


class _ApprovalStubExecutor:
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


async def test_expired_approval_without_on_reject_becomes_rejected():
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(
                name="aprobar",
                approval={"approver": "role:mgr", "prompt": "ok?", "timeout_seconds": 1},
            ),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    run_id = (await eng.run("wf", trigger={})).run_id
    # expires_at was set 1s out; sweep with a far-future "now"
    n = await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert n == 1
    saved = await store.load(run_id)
    assert saved.status == "rejected"
    assert saved.context["steps"]["aprobar"]["output"]["approver"] == "system:timeout"
    assert saved.context["steps"]["aprobar"]["output"]["approved"] is False


async def test_expired_approval_with_on_reject_jumps():
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(
                name="aprobar",
                approval={
                    "approver": "role:mgr",
                    "prompt": "ok?",
                    "on_reject": "avisar",
                    "timeout_seconds": 1,
                },
            ),
            StepSpec(name="avisar", tool="t"),
        ],
        store,
    )
    run_id = (await eng.run("wf", trigger={})).run_id
    await eng.sweep_expired(now="2999-01-01T00:00:00")
    saved = await store.load(run_id)
    assert saved.status == "completed"  # ran avisar
    assert "avisar" in saved.context["steps"]


async def test_approval_without_timeout_not_swept():
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(name="aprobar", approval={"approver": "role:mgr", "prompt": "ok?"}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    run_id = (await eng.run("wf", trigger={})).run_id
    n = await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert n == 0
    assert (await store.load(run_id)).status == "suspended"


async def test_expired_plain_wait_still_expires():
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(name="w", wait={"resume_key": "k", "timeout_seconds": 1}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    run_id = (await eng.run("wf", trigger={})).run_id
    await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert (await store.load(run_id)).status == "expired"


async def test_second_suspend_without_timeout_clears_stale_expires_at():
    # First approval has a timeout; second does not. Approving #1 must not
    # leave #1's expires_at deadline hanging over #2's no-timeout suspend.
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(
                name="aprobar1",
                approval={"approver": "role:mgr", "prompt": "ok?", "timeout_seconds": 1},
            ),
            StepSpec(name="aprobar2", approval={"approver": "role:mgr", "prompt": "ok2?"}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    run_id = (await eng.run("wf", trigger={})).run_id

    await eng.approve(run_id, approver="u:jc", comment=None, decided_at="2026-07-11T10:00:00")
    saved = await store.load(run_id)
    assert saved.status == "suspended"
    assert saved.expires_at is None

    n = await eng.sweep_expired(now="2999-01-01T00:00:00")
    assert n == 0
    saved = await store.load(run_id)
    assert saved.status == "suspended"
