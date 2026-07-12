import tempfile
from pathlib import Path

import aiosqlite

from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore, SqliteRunStore


def _run(run_id, status="running"):
    return WorkflowRun(
        run_id=run_id, workflow_name="w", status=status, current_index=0, context={"steps": {}}
    )


async def test_create_load_roundtrip():
    store = InMemoryRunStore()
    await store.create(_run("r1"))
    loaded = await store.load("r1")
    assert loaded is not None and loaded.run_id == "r1"
    assert await store.load("nope") is None


async def test_save_updates():
    store = InMemoryRunStore()
    await store.create(_run("r1"))
    run = await store.load("r1")
    run.status = "suspended"
    run.current_index = 3
    await store.save(run)
    again = await store.load("r1")
    assert again.status == "suspended" and again.current_index == 3


async def test_list_by_status():
    store = InMemoryRunStore()
    await store.create(_run("r1", "running"))
    await store.create(_run("r2", "suspended"))
    await store.create(_run("r3", "running"))
    running = await store.list_by_status("running")
    assert {r.run_id for r in running} == {"r1", "r3"}


async def test_sqlite_store_roundtrip(tmp_path):
    from astromesh.workflow.store import SqliteRunStore

    store = SqliteRunStore(str(tmp_path / "runs.db"))
    await store.initialize()
    await store.create(
        WorkflowRun(
            run_id="r1",
            workflow_name="w",
            status="running",
            current_index=0,
            context={"steps": {"a": {"output": 1}}},
        )
    )
    loaded = await store.load("r1")
    assert loaded.context["steps"]["a"]["output"] == 1
    loaded.status = "suspended"
    loaded.current_index = 2
    await store.save(loaded)
    assert (await store.load("r1")).current_index == 2
    await store.create(
        WorkflowRun(run_id="r2", workflow_name="w", status="suspended", current_index=0, context={})
    )
    assert {r.run_id for r in await store.list_by_status("suspended")} == {"r1", "r2"}


def _run_with_approval():
    return WorkflowRun(
        run_id="rap",
        workflow_name="wf",
        status="suspended",
        current_index=2,
        pending_approval={"step_name": "aprobar", "approver": "role:mgr", "prompt": "ok?"},
    )


async def test_inmemory_roundtrips_pending_approval():
    store = InMemoryRunStore()
    await store.create(_run_with_approval())
    loaded = await store.load("rap")
    assert loaded.pending_approval == {
        "step_name": "aprobar",
        "approver": "role:mgr",
        "prompt": "ok?",
    }


async def test_sqlite_roundtrips_pending_approval():
    with tempfile.TemporaryDirectory() as d:
        store = SqliteRunStore(str(Path(d) / "runs.db"))
        await store.initialize()
        await store.create(_run_with_approval())
        loaded = await store.load("rap")
        assert loaded.pending_approval == {
            "step_name": "aprobar",
            "approver": "role:mgr",
            "prompt": "ok?",
        }
        # None round-trips too
        await store.save(
            WorkflowRun(run_id="r2", workflow_name="wf", status="running", current_index=0)
        )
        r2 = await store.load("r2")
        assert r2.pending_approval is None


async def test_sqlite_migrates_pre_slice2_schema_missing_pending_approval():
    with tempfile.TemporaryDirectory() as d:
        db_path = str(Path(d) / "runs.db")
        old_db = await aiosqlite.connect(db_path)
        await old_db.execute(
            "CREATE TABLE workflow_runs ("
            "run_id TEXT PRIMARY KEY, workflow_name TEXT, status TEXT, "
            "current_index INTEGER, context TEXT, resume_key TEXT, "
            "created_at TEXT, updated_at TEXT, expires_at TEXT, error TEXT)"
        )
        await old_db.commit()
        await old_db.close()

        store = SqliteRunStore(db_path)
        await store.initialize()
        await store.create(_run_with_approval())
        loaded = await store.load("rap")
        assert loaded.pending_approval == {
            "step_name": "aprobar",
            "approver": "role:mgr",
            "prompt": "ok?",
        }
