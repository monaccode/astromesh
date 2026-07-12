import os

import pytest

from astromesh.workflow.models import WorkflowRun

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="requiere TEST_DATABASE_URL (Postgres) para PgRunStore",
)

DSN = os.environ.get("TEST_DATABASE_URL", "")


def _run(run_id: str, status: str = "suspended") -> WorkflowRun:
    return WorkflowRun(
        run_id=run_id,
        workflow_name="wf",
        status=status,
        current_index=1,
        context={"steps": {"aprobar": {"output": {"approved": True}}}},
        resume_key="k",
        created_at="t0",
        updated_at="t1",
        expires_at=None,
        error=None,
        pending_approval={"step_name": "aprobar", "approver": "role:mgr", "prompt": "ok?"},
    )


async def _fresh_store():
    from astromesh.workflow.store_pg import PgRunStore

    store = PgRunStore(DSN)
    await store.initialize()
    # tabla limpia entre tests (usa el pool asyncpg que expone la impl del Step 3)
    async with store._pool.acquire() as conn:
        await conn.execute("DELETE FROM workflow_runs")
    return store


async def test_create_load_roundtrip_incluye_pending_approval():
    store = await _fresh_store()
    await store.create(_run("r1"))
    loaded = await store.load("r1")
    assert loaded is not None
    assert loaded.run_id == "r1"
    assert loaded.status == "suspended"
    assert loaded.context == {"steps": {"aprobar": {"output": {"approved": True}}}}
    assert loaded.pending_approval == {
        "step_name": "aprobar",
        "approver": "role:mgr",
        "prompt": "ok?",
    }


async def test_load_inexistente_devuelve_none():
    store = await _fresh_store()
    assert await store.load("nope") is None


async def test_save_hace_upsert():
    store = await _fresh_store()
    await store.create(_run("r1", status="suspended"))
    r = _run("r1", status="completed")
    r.pending_approval = None
    await store.save(r)
    loaded = await store.load("r1")
    assert loaded.status == "completed"
    assert loaded.pending_approval is None


async def test_list_by_status_filtra():
    store = await _fresh_store()
    await store.create(_run("r1", status="suspended"))
    await store.create(_run("r2", status="completed"))
    suspended = await store.list_by_status("suspended")
    assert [r.run_id for r in suspended] == ["r1"]


async def test_durabilidad_entre_instancias():
    from astromesh.workflow.store_pg import PgRunStore

    store = await _fresh_store()
    await store.create(_run("r1"))
    # una segunda instancia sobre la misma DB ve el dato persistido
    store2 = PgRunStore(DSN)
    await store2.initialize()
    loaded = await store2.load("r1")
    assert loaded is not None and loaded.run_id == "r1"
