import pytest

from astromesh.api.routes import workflows as wf_route
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
        return StepResult(name=step.name, status=StepStatus.SUCCESS, output={"ok": step.name})


@pytest.fixture
def wired(monkeypatch):
    from astromesh.workflow import WorkflowEngine

    store = InMemoryRunStore()
    eng = WorkflowEngine(workflows_dir="", runtime=None, tool_registry=None, store=store)
    eng._workflows = {
        "wf": WorkflowSpec(
            name="wf",
            steps=[StepSpec(name="w", wait={"resume_key": "k"}), StepSpec(name="b", tool="t")],
        )
    }
    eng._executor = _StubExecutor()
    wf_route.set_workflow_engine(eng)
    return eng


async def test_run_suspends_then_get_then_resume(client, wired):
    r = await client.post("/v1/workflows/wf/run", json={"trigger": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "suspended" and body["run_id"]
    run_id = body["run_id"]

    g = await client.get(f"/v1/workflows/runs/{run_id}")
    assert g.status_code == 200 and g.json()["status"] == "suspended"

    res = await client.post(f"/v1/workflows/runs/{run_id}/resume", json={"payload": {"amount": 9}})
    assert res.status_code == 200 and res.json()["status"] == "completed"


async def test_resume_non_suspended_409(client, wired):
    r = await client.post("/v1/workflows/wf/run", json={"trigger": {}})
    run_id = r.json()["run_id"]
    await client.post(f"/v1/workflows/runs/{run_id}/resume", json={"payload": {}})  # completa
    again = await client.post(f"/v1/workflows/runs/{run_id}/resume", json={"payload": {}})
    assert again.status_code == 409


async def test_get_unknown_run_404(client, wired):
    g = await client.get("/v1/workflows/runs/nope")
    assert g.status_code == 404
