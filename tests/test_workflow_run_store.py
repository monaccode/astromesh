from astromesh.workflow.models import WorkflowRun
from astromesh.workflow.store import InMemoryRunStore


def _run(run_id, status="running"):
    return WorkflowRun(run_id=run_id, workflow_name="w", status=status,
                       current_index=0, context={"steps": {}})


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
    await store.create(WorkflowRun(run_id="r1", workflow_name="w", status="running",
                                   current_index=0, context={"steps": {"a": {"output": 1}}}))
    loaded = await store.load("r1")
    assert loaded.context["steps"]["a"]["output"] == 1
    loaded.status = "suspended"
    loaded.current_index = 2
    await store.save(loaded)
    assert (await store.load("r1")).current_index == 2
    await store.create(WorkflowRun(run_id="r2", workflow_name="w", status="suspended",
                                   current_index=0, context={}))
    assert {r.run_id for r in await store.list_by_status("suspended")} == {"r1", "r2"}
