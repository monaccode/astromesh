# tests/test_workflow_approval_executor.py
from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec, StepStatus


async def test_approval_step_suspends_with_metadata():
    ex = StepExecutor(runtime=None, tool_registry=None)
    step = StepSpec(
        name="aprobar",
        approval={
            "approver": "role:finance_manager",
            "prompt": "Aprobar orden?",
            "on_reject": "avisar",
            "timeout_seconds": 3600,
        },
    )
    result = await ex.execute_step(step, context={})
    assert result.status == StepStatus.SUSPENDED
    out = result.output
    assert out["approver"] == "role:finance_manager"
    assert out["prompt"] == "Aprobar orden?"
    assert out["on_reject"] == "avisar"
    assert out["timeout_seconds"] == 3600
    assert out["pending_approval"] == {
        "step_name": "aprobar",
        "approver": "role:finance_manager",
        "prompt": "Aprobar orden?",
    }


async def test_approval_without_optional_fields():
    ex = StepExecutor(runtime=None, tool_registry=None)
    step = StepSpec(name="ap", approval={"approver": "u:jc"})
    result = await ex.execute_step(step, context={})
    assert result.status == StepStatus.SUSPENDED
    assert result.output["timeout_seconds"] is None
    assert result.output["on_reject"] is None
    assert result.output["pending_approval"]["approver"] == "u:jc"
