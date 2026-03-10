# tests/test_workflow_executor.py
import asyncio

import pytest
from unittest.mock import AsyncMock

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec, StepStatus, RetryConfig


@pytest.fixture
def mock_runtime():
    runtime = AsyncMock()
    runtime.run = AsyncMock(return_value={"answer": "researched data", "steps": []})
    return runtime


@pytest.fixture
def mock_tool_registry():
    registry = AsyncMock()
    registry.execute = AsyncMock(return_value={"result": "stored"})
    return registry


@pytest.fixture
def executor(mock_runtime, mock_tool_registry):
    return StepExecutor(runtime=mock_runtime, tool_registry=mock_tool_registry)


class TestAgentStep:
    async def test_basic_agent_step(self, executor, mock_runtime):
        step = StepSpec(name="research", agent="web-researcher", input_template="{{ trigger.query }}")
        ctx = {"trigger": {"query": "Tell me about Acme Corp"}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"answer": "researched data", "steps": []}

    async def test_agent_step_with_step_reference(self, executor, mock_runtime):
        step = StepSpec(name="qualify", agent="qualifier", input_template="{{ steps.research.output }}")
        ctx = {
            "trigger": {},
            "steps": {"research": {"output": {"answer": "data about Acme"}}},
        }
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS

    async def test_agent_step_error(self, executor, mock_runtime):
        mock_runtime.run.side_effect = Exception("agent crashed")
        step = StepSpec(name="broken", agent="bad-agent", input_template="go")
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.ERROR
        assert "agent crashed" in result.error


class TestToolStep:
    async def test_basic_tool_step(self, executor, mock_tool_registry):
        step = StepSpec(name="store", tool="cache_store", arguments={"key": "k", "value": "v"})
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"result": "stored"}

    async def test_tool_step_with_template_args(self, executor, mock_tool_registry):
        step = StepSpec(
            name="store",
            tool="cache_store",
            arguments={"key": "lead_{{ trigger.id }}", "value": "{{ steps.prev.output }}"},
        )
        ctx = {"trigger": {"id": "123"}, "steps": {"prev": {"output": "some data"}}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        # Verify arguments were template-rendered
        call_args = mock_tool_registry.execute.call_args
        assert call_args[0][1]["key"] == "lead_123"


class TestSwitchStep:
    async def test_switch_when_true(self, executor):
        step = StepSpec(
            name="decide",
            switch=[
                {"when": "{{ steps.score.output.value > 7 }}", "goto": "high"},
                {"default": True, "goto": "low"},
            ],
        )
        ctx = {"trigger": {}, "steps": {"score": {"output": {"value": 9}}}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"goto": "high"}

    async def test_switch_default(self, executor):
        step = StepSpec(
            name="decide",
            switch=[
                {"when": "{{ steps.score.output.value > 7 }}", "goto": "high"},
                {"default": True, "goto": "low"},
            ],
        )
        ctx = {"trigger": {}, "steps": {"score": {"output": {"value": 3}}}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"goto": "low"}

    async def test_switch_no_match_no_default(self, executor):
        step = StepSpec(
            name="decide",
            switch=[{"when": "{{ False }}", "goto": "never"}],
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert result.output == {"goto": None}


class TestRetry:
    async def test_retry_on_failure(self, executor, mock_runtime):
        call_count = 0

        async def flaky_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("transient error")
            return {"answer": "success", "steps": []}

        mock_runtime.run = flaky_run
        step = StepSpec(
            name="flaky",
            agent="flaky-agent",
            input_template="go",
            retry=RetryConfig(max_attempts=3, backoff="fixed", initial_delay_seconds=0.01),
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.SUCCESS
        assert call_count == 3

    async def test_retry_exhausted(self, executor, mock_runtime):
        mock_runtime.run = AsyncMock(side_effect=Exception("always fails"))
        step = StepSpec(
            name="doomed",
            agent="bad-agent",
            input_template="go",
            retry=RetryConfig(max_attempts=2, backoff="fixed", initial_delay_seconds=0.01),
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.ERROR
        assert mock_runtime.run.call_count == 2


class TestTimeout:
    async def test_step_timeout(self, executor, mock_runtime):
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return {"answer": "too late"}

        mock_runtime.run = slow_run
        step = StepSpec(
            name="slow",
            agent="slow-agent",
            input_template="go",
            timeout_seconds=1,
        )
        ctx = {"trigger": {}, "steps": {}}
        result = await executor.execute_step(step, ctx)
        assert result.status == StepStatus.ERROR
        assert "timeout" in result.error.lower() or "timed out" in result.error.lower()
