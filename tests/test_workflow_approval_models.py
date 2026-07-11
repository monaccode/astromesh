# tests/test_workflow_approval_models.py
import pytest

from astromesh.workflow.models import StepSpec, StepType, WorkflowRun


def test_approval_step_type():
    step = StepSpec(name="ap", approval={"approver": "role:mgr", "prompt": "ok?"})
    assert step.step_type == StepType.APPROVAL
    assert StepType.APPROVAL.value == "approval"


def test_approval_counts_in_mutual_exclusion():
    # two step types → error that mentions approval
    with pytest.raises(ValueError, match="approval"):
        StepSpec(name="bad", tool="t", approval={"approver": "x"})
    # zero step types → error
    with pytest.raises(ValueError):
        StepSpec(name="empty")


def test_workflow_run_pending_approval_defaults_none():
    run = WorkflowRun(run_id="r1", workflow_name="wf", status="running", current_index=0)
    assert run.pending_approval is None


def test_loader_parses_approval_step():
    from pathlib import Path
    import tempfile
    from astromesh.workflow.loader import WorkflowLoader

    yaml_text = (
        "kind: Workflow\n"
        "metadata:\n  name: wf\n"
        "spec:\n  steps:\n"
        "    - name: aprobar\n"
        "      approval:\n        approver: role:finance_manager\n        prompt: Aprobar?\n"
        "        on_reject: avisar\n"
        "    - name: avisar\n      tool: notify\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.workflow.yaml"
        p.write_text(yaml_text)
        wf = WorkflowLoader(d).load_file(p)
    step = wf.get_step("aprobar")
    assert step.approval == {
        "approver": "role:finance_manager",
        "prompt": "Aprobar?",
        "on_reject": "avisar",
    }
    assert step.step_type == StepType.APPROVAL
