# tests/test_workflow_approval_api.py
import pytest

from astromesh.api.routes import workflows as wf_route
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


@pytest.fixture
def wired():
    from astromesh.workflow import WorkflowEngine

    eng = WorkflowEngine(
        workflows_dir="", runtime=None, tool_registry=None, store=InMemoryRunStore()
    )
    eng._workflows = {
        "wf": WorkflowSpec(
            name="wf",
            steps=[
                StepSpec(
                    name="aprobar",
                    approval={"approver": "role:finance_manager", "prompt": "Aprobar?"},
                ),
                StepSpec(name="b", tool="t"),
            ],
        )
    }
    eng._executor = _ApprovalStubExecutor()
    wf_route.set_workflow_engine(eng)
    return eng


async def test_queue_lists_pending_approval(client, wired):
    r = await client.post("/v1/workflows/wf/run", json={"trigger": {}})
    run_id = r.json()["run_id"]
    q = await client.get("/v1/workflows/approvals")
    assert q.status_code == 200
    items = q.json()["approvals"]
    assert len(items) == 1
    assert items[0]["run_id"] == run_id
    assert items[0]["step_name"] == "aprobar"
    assert items[0]["approver"] == "role:finance_manager"
    assert items[0]["prompt"] == "Aprobar?"


async def test_queue_filters_by_approver(client, wired):
    await client.post("/v1/workflows/wf/run", json={"trigger": {}})
    hit = await client.get("/v1/workflows/approvals", params={"approver": "role:finance_manager"})
    miss = await client.get("/v1/workflows/approvals", params={"approver": "role:other"})
    assert len(hit.json()["approvals"]) == 1
    assert len(miss.json()["approvals"]) == 0


async def test_approve_endpoint(client, wired):
    run_id = (await client.post("/v1/workflows/wf/run", json={"trigger": {}})).json()["run_id"]
    a = await client.post(
        f"/v1/workflows/runs/{run_id}/approve", json={"approver": "u:jc", "comment": "ok"}
    )
    assert a.status_code == 200 and a.json()["status"] == "completed"


async def test_reject_endpoint(client, wired):
    run_id = (await client.post("/v1/workflows/wf/run", json={"trigger": {}})).json()["run_id"]
    a = await client.post(f"/v1/workflows/runs/{run_id}/reject", json={"approver": "u:jc"})
    assert a.status_code == 200 and a.json()["status"] == "rejected"


async def test_approve_unknown_run_404(client, wired):
    a = await client.post("/v1/workflows/runs/nope/approve", json={"approver": "u:jc"})
    assert a.status_code == 404


async def test_double_approve_409(client, wired):
    run_id = (await client.post("/v1/workflows/wf/run", json={"trigger": {}})).json()["run_id"]
    await client.post(f"/v1/workflows/runs/{run_id}/approve", json={"approver": "u:jc"})
    again = await client.post(f"/v1/workflows/runs/{run_id}/approve", json={"approver": "u:jc"})
    assert again.status_code == 409
