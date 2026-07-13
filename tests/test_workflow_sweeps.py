from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore


def _engine(store):
    from astromesh.workflow import WorkflowEngine

    return WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)


async def test_sweep_expired_marks_expired():
    store = InMemoryRunStore()
    await store.create(
        WorkflowRun(
            run_id="r1",
            workflow_name="w",
            status="suspended",
            current_index=1,
            context={},
            expires_at="2026-01-01T00:00:00+00:00",
        )
    )
    await store.create(
        WorkflowRun(
            run_id="r2",
            workflow_name="w",
            status="suspended",
            current_index=1,
            context={},
            expires_at="2999-01-01T00:00:00+00:00",
        )
    )
    n = await _engine(store).sweep_expired(now="2026-06-01T00:00:00+00:00")
    assert n == 1
    assert (await store.load("r1")).status == "expired"
    assert (await store.load("r2")).status == "suspended"


async def test_mark_orphaned_failed():
    store = InMemoryRunStore()
    await store.create(
        WorkflowRun(run_id="a", workflow_name="w", status="running", current_index=0, context={})
    )
    await store.create(
        WorkflowRun(run_id="b", workflow_name="w", status="suspended", current_index=1, context={})
    )
    n = await _engine(store).mark_orphaned_failed()
    assert n == 1
    assert (await store.load("a")).status == "failed"
    assert (await store.load("b")).status == "suspended"


async def test_mark_orphaned_failed_staleness_guard_spares_active_runs():
    """Con orphan_after_seconds>0, solo se marcan runs sin progreso reciente:
    un run activo (updated_at fresco) queda intacto; uno viejo o sin timestamp
    se marca huérfano. Esto lo hace seguro de llamar periódicamente."""
    from datetime import UTC, datetime, timedelta

    store = InMemoryRunStore()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    # activo: checkpointeó updated_at hace 10s
    await store.create(
        WorkflowRun(
            run_id="active",
            workflow_name="w",
            status="running",
            current_index=0,
            context={},
            updated_at=(now - timedelta(seconds=10)).isoformat(),
        )
    )
    # huérfano: sin progreso hace 1h
    await store.create(
        WorkflowRun(
            run_id="stale",
            workflow_name="w",
            status="running",
            current_index=0,
            context={},
            updated_at=(now - timedelta(seconds=3600)).isoformat(),
        )
    )
    # sin timestamp: no se puede probar liveness → huérfano
    await store.create(
        WorkflowRun(
            run_id="notime",
            workflow_name="w",
            status="running",
            current_index=0,
            context={},
            updated_at=None,
        )
    )
    n = await _engine(store).mark_orphaned_failed(now=now.isoformat(), orphan_after_seconds=300)
    assert n == 2
    assert (await store.load("active")).status == "running"  # vivo → intacto
    assert (await store.load("stale")).status == "failed"
    assert (await store.load("notime")).status == "failed"
