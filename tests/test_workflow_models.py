# tests/test_workflow_models.py
import pytest
from astromesh.workflow.models import (
    WorkflowSpec,
    StepSpec,
    StepResult,
    RetryConfig,
    WorkflowRunResult,
    StepType,
    StepStatus,
)


class TestRetryConfig:
    def test_defaults(self):
        rc = RetryConfig()
        assert rc.max_attempts == 1
        assert rc.backoff == "fixed"
        assert rc.initial_delay_seconds == 1.0

    def test_exponential(self):
        rc = RetryConfig(max_attempts=3, backoff="exponential", initial_delay_seconds=2.0)
        assert rc.max_attempts == 3
        assert rc.backoff == "exponential"


class TestStepSpec:
    def test_agent_step(self):
        step = StepSpec(
            name="research",
            agent="web-researcher",
            input_template="{{ trigger.query }}",
        )
        assert step.step_type == StepType.AGENT
        assert step.agent == "web-researcher"

    def test_tool_step(self):
        step = StepSpec(
            name="store",
            tool="cache_store",
            arguments={"key": "k1", "value": "v1"},
        )
        assert step.step_type == StepType.TOOL

    def test_switch_step(self):
        step = StepSpec(
            name="decide",
            switch=[
                {"when": "{{ steps.qualify.output.data.score > 7 }}", "goto": "send-email"},
                {"default": True, "goto": "log-skip"},
            ],
        )
        assert step.step_type == StepType.SWITCH

    def test_invalid_step_raises(self):
        """A step with no agent, tool, or switch is invalid."""
        with pytest.raises(ValueError, match="must have exactly one"):
            StepSpec(name="broken")

    def test_retry_config_from_dict(self):
        step = StepSpec(
            name="s1",
            agent="a1",
            input_template="hi",
            retry={"max_attempts": 3, "backoff": "exponential", "initial_delay_seconds": 2.0},
        )
        assert step.retry.max_attempts == 3
        assert step.retry.backoff == "exponential"


class TestStepResult:
    def test_success(self):
        sr = StepResult(name="research", status=StepStatus.SUCCESS, output={"answer": "hello"})
        assert sr.status == StepStatus.SUCCESS
        assert sr.output["answer"] == "hello"
        assert sr.error is None

    def test_error(self):
        sr = StepResult(name="research", status=StepStatus.ERROR, error="timeout")
        assert sr.status == StepStatus.ERROR


class TestWorkflowSpec:
    def test_basic_workflow(self):
        wf = WorkflowSpec(
            name="test-wf",
            trigger="api",
            timeout_seconds=300,
            steps=[
                StepSpec(name="s1", agent="a1", input_template="{{ trigger.query }}"),
            ],
        )
        assert wf.name == "test-wf"
        assert wf.trigger == "api"
        assert len(wf.steps) == 1

    def test_step_lookup_by_name(self):
        wf = WorkflowSpec(
            name="test-wf",
            trigger="api",
            steps=[
                StepSpec(name="s1", agent="a1", input_template="hi"),
                StepSpec(name="s2", agent="a2", input_template="bye"),
            ],
        )
        assert wf.get_step("s1").agent == "a1"
        assert wf.get_step("s2").agent == "a2"
        assert wf.get_step("nonexistent") is None

    def test_duplicate_step_names_raises(self):
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            WorkflowSpec(
                name="test-wf",
                trigger="api",
                steps=[
                    StepSpec(name="s1", agent="a1", input_template="hi"),
                    StepSpec(name="s1", agent="a2", input_template="bye"),
                ],
            )


class TestWorkflowRunResult:
    def test_basic(self):
        result = WorkflowRunResult(
            workflow_name="test-wf",
            status="completed",
            steps={"s1": StepResult(name="s1", status=StepStatus.SUCCESS, output={"answer": "ok"})},
            output={"answer": "ok"},
        )
        assert result.workflow_name == "test-wf"
        assert result.status == "completed"
        assert "s1" in result.steps
