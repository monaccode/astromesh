# tests/test_workflow_wait_loader_exec.py

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import StepSpec, StepStatus, StepType

WF = """
apiVersion: astromesh/v1
kind: Workflow
metadata: {name: pago}
spec:
  steps:
    - name: esperar-pago
      wait: {resume_key: payment.confirmed, timeout_seconds: 60}
"""


def test_loader_parses_wait(tmp_path):
    p = tmp_path / "pago.workflow.yaml"
    p.write_text(WF)
    wf = WorkflowLoader(str(tmp_path)).load_file(p)
    step = wf.steps[0]
    assert step.step_type == StepType.WAIT
    assert step.wait["resume_key"] == "payment.confirmed"


async def test_executor_wait_suspends():
    execu = StepExecutor(runtime=None, tool_registry=None)
    step = StepSpec(name="w", wait={"resume_key": "k", "timeout_seconds": 30})
    result = await execu.execute_step(step, context={})
    assert result.status == StepStatus.SUSPENDED
    assert result.output == {"resume_key": "k", "timeout_seconds": 30}
