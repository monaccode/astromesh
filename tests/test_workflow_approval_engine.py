import pytest

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


async def _suspend_at_approval(store, extra_steps=None, approval=None):
    approval = approval or {"approver": "role:mgr", "prompt": "ok?"}
    steps = [
        StepSpec(name="a", tool="t"),
        StepSpec(name="aprobar", approval=approval),
    ] + (extra_steps or [StepSpec(name="b", tool="t")])
    eng = _engine(steps, store)
    r = await eng.run("wf", trigger={})
    return eng, r.run_id


async def test_approve_continues_and_records_decision():
    store = InMemoryRunStore()
    eng, run_id = await _suspend_at_approval(store)
    result = await eng.approve(
        run_id, approver="u:jc", comment="ok", decided_at="2026-07-11T10:00:00"
    )
    assert result.status == "completed"
    saved = await store.load(run_id)
    decision = saved.context["steps"]["aprobar"]["output"]
    assert decision == {
        "approved": True,
        "approver": "u:jc",
        "comment": "ok",
        "decided_at": "2026-07-11T10:00:00",
    }
    assert saved.pending_approval is None


async def test_reject_with_on_reject_jumps():
    store = InMemoryRunStore()
    eng, run_id = await _suspend_at_approval(
        store,
        extra_steps=[StepSpec(name="avisar", tool="t"), StepSpec(name="b", tool="t")],
        approval={"approver": "role:mgr", "prompt": "ok?", "on_reject": "avisar"},
    )
    result = await eng.reject(
        run_id, approver="u:jc", comment="no", decided_at="2026-07-11T10:00:00"
    )
    assert result.status == "completed"  # ran avisar → b
    saved = await store.load(run_id)
    assert saved.context["steps"]["aprobar"]["output"]["approved"] is False
    assert "avisar" in saved.context["steps"]  # the reject branch executed


async def test_reject_without_on_reject_terminates_rejected():
    store = InMemoryRunStore()
    eng, run_id = await _suspend_at_approval(store)
    result = await eng.reject(
        run_id, approver="u:jc", comment=None, decided_at="2026-07-11T10:00:00"
    )
    assert result.status == "rejected"
    saved = await store.load(run_id)
    assert saved.status == "rejected"
    assert saved.pending_approval is None


async def test_switch_routes_on_decision():
    # approval → switch that goes to "aprobado" when approved, else default "rechazado"
    store = InMemoryRunStore()
    steps = [
        StepSpec(name="aprobar", approval={"approver": "role:mgr", "prompt": "ok?"}),
        StepSpec(
            name="ruta",
            switch=[
                {"when": "{{ steps['aprobar'].output.approved }}", "goto": "aprobado"},
                {"default": True, "goto": "rechazado"},
            ],
        ),
        StepSpec(name="aprobado", tool="t"),
        StepSpec(name="rechazado", tool="t"),
    ]
    eng = _engine(steps, store)
    run_id = (await eng.run("wf", trigger={})).run_id
    await eng.approve(run_id, approver="u:jc", comment=None, decided_at="2026-07-11T10:00:00")
    saved = await store.load(run_id)
    assert "aprobado" in saved.context["steps"]
    assert "rechazado" not in saved.context["steps"]


async def test_approve_unknown_run_raises_not_found():
    eng = _engine([StepSpec(name="a", tool="t")], InMemoryRunStore())
    with pytest.raises(ValueError, match="not found"):
        await eng.approve("nope", approver="u:jc", comment=None, decided_at="t")


async def test_approve_non_approval_run_raises():
    # a run that completed (not awaiting approval) → ValueError without "not found"
    store = InMemoryRunStore()
    eng = _engine([StepSpec(name="a", tool="t")], store)
    run_id = (await eng.run("wf", trigger={})).run_id
    with pytest.raises(ValueError) as exc:
        await eng.approve(run_id, approver="u:jc", comment=None, decided_at="t")
    assert "not found" not in str(exc.value)


async def test_approve_plain_wait_run_raises_without_not_found():
    # suspended at a plain WAIT step (not an approval) → pending_approval is None,
    # so approve() must still 409 (ValueError without "not found"), not 404.
    store = InMemoryRunStore()
    eng = _engine(
        [
            StepSpec(name="w", wait={"resume_key": "k"}),
            StepSpec(name="b", tool="t"),
        ],
        store,
    )
    run_id = (await eng.run("wf", trigger={})).run_id
    saved = await store.load(run_id)
    assert saved.status == "suspended"
    assert saved.pending_approval is None

    with pytest.raises(ValueError) as exc:
        await eng.approve(run_id, approver="u:jc", comment=None, decided_at="t")
    assert "not found" not in str(exc.value)
