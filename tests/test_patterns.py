import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromech.orchestration.patterns import ReActPattern


@dataclass
class CompletionResponse:
    content: str
    tool_calls: list | None = None


def make_response(content, tool_calls=None):
    return CompletionResponse(content=content, tool_calls=tool_calls)


@pytest.mark.asyncio
async def test_react_direct_answer():
    """No tool calls -> final answer returned immediately."""
    model_fn = AsyncMock(return_value=make_response("The answer is 42."))
    tool_fn = AsyncMock()

    pattern = ReActPattern()
    result = await pattern.execute(
        query="What is the answer?",
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[],
    )

    assert result["answer"] == "The answer is 42."
    assert len(result["steps"]) == 1
    assert result["steps"][0].result == "The answer is 42."
    tool_fn.assert_not_called()


@pytest.mark.asyncio
async def test_react_with_tool_call():
    """One tool call followed by a final answer."""
    tool_call = {"id": "tc_1", "name": "lookup", "arguments": {"query": "weather"}}

    # First call returns a tool call; second call returns the final answer
    model_fn = AsyncMock(
        side_effect=[
            make_response("Let me look that up.", tool_calls=[tool_call]),
            make_response("It is sunny today."),
        ]
    )
    tool_fn = AsyncMock(return_value={"weather": "sunny"})

    pattern = ReActPattern()
    result = await pattern.execute(
        query="What is the weather?",
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[],
    )

    assert result["answer"] == "It is sunny today."
    assert len(result["steps"]) == 2
    # First step is the tool call
    assert result["steps"][0].action == "lookup"
    assert result["steps"][0].observation == str({"weather": "sunny"})
    # Second step is the final answer
    assert result["steps"][1].result == "It is sunny today."
    tool_fn.assert_called_once_with("lookup", {"query": "weather"})


@pytest.mark.asyncio
async def test_react_max_iterations():
    """Always returns tool_calls -> hits max iterations."""
    tool_call = {"id": "tc_loop", "name": "search", "arguments": {"q": "info"}}
    model_fn = AsyncMock(
        return_value=make_response("Thinking...", tool_calls=[tool_call])
    )
    tool_fn = AsyncMock(return_value={"result": "partial"})

    pattern = ReActPattern()
    result = await pattern.execute(
        query="Find info",
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[],
        max_iterations=3,
    )

    assert result["answer"] == "Max iterations reached"
    assert len(result["steps"]) == 3
    assert all(step.action == "search" for step in result["steps"])


@pytest.mark.asyncio
async def test_plan_execute_pattern():
    from astromech.orchestration.patterns import PlanAndExecutePattern
    plan_response = make_response('{"steps": [{"step": 1, "description": "Search", "tool": null, "depends_on": []}]}')
    step_response = make_response("Step 1 result")
    final_response = make_response("Final synthesized answer")
    model_fn = AsyncMock(side_effect=[plan_response, step_response, final_response])
    tool_fn = AsyncMock()
    pattern = PlanAndExecutePattern()
    result = await pattern.execute("Do research", {}, model_fn, tool_fn, [])
    assert result["answer"] == "Final synthesized answer"


@pytest.mark.asyncio
async def test_parallel_fan_out():
    from astromech.orchestration.patterns import ParallelFanOutPattern
    decompose = make_response('["subtask 1", "subtask 2"]')
    sub1 = make_response("result 1")
    sub2 = make_response("result 2")
    final = make_response("Aggregated answer")
    model_fn = AsyncMock(side_effect=[decompose, sub1, sub2, final])
    pattern = ParallelFanOutPattern()
    result = await pattern.execute("Do things", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "Aggregated answer"


@pytest.mark.asyncio
async def test_pipeline_pattern():
    from astromech.orchestration.patterns import PipelinePattern
    r1 = make_response("analyzed")
    r2 = make_response("processed")
    r3 = make_response("synthesized")
    model_fn = AsyncMock(side_effect=[r1, r2, r3])
    pattern = PipelinePattern()
    result = await pattern.execute("input", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "synthesized"


@pytest.mark.asyncio
async def test_supervisor_pattern():
    from astromech.orchestration.supervisor import SupervisorPattern
    resp = make_response('{"final_answer": "done"}')
    model_fn = AsyncMock(return_value=resp)
    pattern = SupervisorPattern()
    result = await pattern.execute("task", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "done"


@pytest.mark.asyncio
async def test_swarm_pattern():
    from astromech.orchestration.swarm import SwarmPattern
    resp = make_response("The answer is 42")
    model_fn = AsyncMock(return_value=resp)
    pattern = SwarmPattern()
    result = await pattern.execute("question", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "The answer is 42"
