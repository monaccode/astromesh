from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore


def _engine(store):
    from astromesh.workflow import WorkflowEngine
    return WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)


async def test_sweep_expired_marks_expired():
    store = InMemoryRunStore()
    await store.create(WorkflowRun(run_id="r1", workflow_name="w", status="suspended",
                                   current_index=1, context={}, expires_at="2026-01-01T00:00:00+00:00"))
    await store.create(WorkflowRun(run_id="r2", workflow_name="w", status="suspended",
                                   current_index=1, context={}, expires_at="2999-01-01T00:00:00+00:00"))
    n = await _engine(store).sweep_expired(now="2026-06-01T00:00:00+00:00")
    assert n == 1
    assert (await store.load("r1")).status == "expired"
    assert (await store.load("r2")).status == "suspended"


async def test_mark_orphaned_failed():
    store = InMemoryRunStore()
    await store.create(WorkflowRun(run_id="a", workflow_name="w", status="running",
                                   current_index=0, context={}))
    await store.create(WorkflowRun(run_id="b", workflow_name="w", status="suspended",
                                   current_index=1, context={}))
    n = await _engine(store).mark_orphaned_failed()
    assert n == 1
    assert (await store.load("a")).status == "failed"
    assert (await store.load("b")).status == "suspended"
