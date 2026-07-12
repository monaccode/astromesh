# tests/test_workflow_wait_models.py
import pytest

from astromesh.workflow.models import (
    StepSpec,
    StepStatus,
    StepType,
    WorkflowRun,
    WorkflowRunResult,
)


def test_wait_step_type():
    s = StepSpec(name="w", wait={"resume_key": "k", "timeout_seconds": 60})
    assert s.step_type == StepType.WAIT


def test_exactly_one_step_type_still_enforced():
    with pytest.raises(ValueError):
        StepSpec(name="bad", agent="a", wait={"resume_key": "k"})
    with pytest.raises(ValueError):
        StepSpec(name="none")


def test_suspended_status_exists():
    assert StepStatus.SUSPENDED.value == "suspended"


def test_run_result_has_run_id():
    r = WorkflowRunResult(workflow_name="w", status="suspended", run_id="r1")
    assert r.run_id == "r1"


def test_workflow_run_dataclass():
    run = WorkflowRun(
        run_id="r1",
        workflow_name="w",
        status="running",
        current_index=0,
        context={"trigger": {}, "steps": {}},
    )
    assert run.status == "running" and run.resume_key is None and run.error is None
