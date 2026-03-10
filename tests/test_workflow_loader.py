# tests/test_workflow_loader.py
import pytest
from astromesh.workflow.loader import WorkflowLoader
from astromesh.workflow.models import WorkflowSpec, StepType


@pytest.fixture
def workflows_dir(tmp_path):
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    return wf_dir


def _write_workflow(wf_dir, name, content):
    (wf_dir / f"{name}.workflow.yaml").write_text(content)


class TestWorkflowLoader:
    def test_load_empty_dir(self, workflows_dir):
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        assert workflows == {}

    def test_load_basic_workflow(self, workflows_dir):
        _write_workflow(workflows_dir, "test", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: test-wf
  version: "0.1.0"
spec:
  trigger: api
  timeout_seconds: 120
  steps:
    - name: greet
      agent: greeter
      input: "{{ trigger.query }}"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        assert "test-wf" in workflows
        wf = workflows["test-wf"]
        assert isinstance(wf, WorkflowSpec)
        assert wf.trigger == "api"
        assert wf.timeout_seconds == 120
        assert len(wf.steps) == 1
        assert wf.steps[0].step_type == StepType.AGENT

    def test_load_workflow_with_tool_step(self, workflows_dir):
        _write_workflow(workflows_dir, "tool-wf", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: tool-wf
spec:
  steps:
    - name: store
      tool: cache_store
      arguments:
        key: "test-key"
        value: "test-value"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        wf = workflows["tool-wf"]
        assert wf.steps[0].step_type == StepType.TOOL
        assert wf.steps[0].arguments["key"] == "test-key"

    def test_load_workflow_with_switch_step(self, workflows_dir):
        _write_workflow(workflows_dir, "switch-wf", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: switch-wf
spec:
  steps:
    - name: check
      agent: checker
      input: "{{ trigger.query }}"
    - name: decide
      switch:
        - when: "{{ steps.check.output.score > 5 }}"
          goto: high
        - default: true
          goto: low
    - name: high
      agent: high-handler
      input: "high path"
    - name: low
      agent: low-handler
      input: "low path"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        wf = workflows["switch-wf"]
        assert wf.steps[1].step_type == StepType.SWITCH
        assert len(wf.steps[1].switch) == 2

    def test_load_workflow_with_retry(self, workflows_dir):
        _write_workflow(workflows_dir, "retry-wf", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: retry-wf
spec:
  steps:
    - name: flaky
      agent: flaky-agent
      input: "{{ trigger.query }}"
      retry:
        max_attempts: 3
        backoff: exponential
        initial_delay_seconds: 2
      timeout_seconds: 30
      on_error: fallback
    - name: fallback
      agent: fallback-agent
      input: "error occurred"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        wf = workflows["retry-wf"]
        step = wf.steps[0]
        assert step.retry.max_attempts == 3
        assert step.retry.backoff == "exponential"
        assert step.timeout_seconds == 30
        assert step.on_error == "fallback"

    def test_invalid_kind_skipped(self, workflows_dir):
        _write_workflow(workflows_dir, "agent", """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: not-a-workflow
spec:
  identity:
    description: "This is an agent, not a workflow"
""")
        loader = WorkflowLoader(str(workflows_dir))
        workflows = loader.load_all()
        assert workflows == {}

    def test_missing_dir_returns_empty(self, tmp_path):
        loader = WorkflowLoader(str(tmp_path / "nonexistent"))
        workflows = loader.load_all()
        assert workflows == {}

    def test_load_single_workflow(self, workflows_dir):
        _write_workflow(workflows_dir, "single", """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: single-wf
spec:
  steps:
    - name: do-thing
      agent: doer
      input: "{{ trigger.query }}"
""")
        loader = WorkflowLoader(str(workflows_dir))
        wf = loader.load_file(workflows_dir / "single.workflow.yaml")
        assert wf.name == "single-wf"
