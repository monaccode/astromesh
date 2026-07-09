import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromesh.orchestration.patterns import ReActPattern


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
    model_fn = AsyncMock(return_value=make_response("Thinking...", tool_calls=[tool_call]))
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
    from astromesh.orchestration.patterns import PlanAndExecutePattern

    plan_response = make_response(
        '{"steps": [{"step": 1, "description": "Search", "tool": null, "depends_on": []}]}'
    )
    step_response = make_response("Step 1 result")
    final_response = make_response("Final synthesized answer")
    model_fn = AsyncMock(side_effect=[plan_response, step_response, final_response])
    tool_fn = AsyncMock()
    pattern = PlanAndExecutePattern()
    result = await pattern.execute("Do research", {}, model_fn, tool_fn, [])
    assert result["answer"] == "Final synthesized answer"


@pytest.mark.asyncio
async def test_parallel_fan_out():
    from astromesh.orchestration.patterns import ParallelFanOutPattern

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
    from astromesh.orchestration.patterns import PipelinePattern

    r1 = make_response("analyzed")
    r2 = make_response("processed")
    r3 = make_response("synthesized")
    model_fn = AsyncMock(side_effect=[r1, r2, r3])
    pattern = PipelinePattern()
    result = await pattern.execute("input", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "synthesized"


@pytest.mark.asyncio
async def test_supervisor_pattern():
    from astromesh.orchestration.supervisor import SupervisorPattern

    resp = make_response('{"final_answer": "done"}')
    model_fn = AsyncMock(return_value=resp)
    pattern = SupervisorPattern()
    result = await pattern.execute("task", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "done"


@pytest.mark.asyncio
async def test_swarm_pattern():
    from astromesh.orchestration.swarm import SwarmPattern

    resp = make_response("The answer is 42")
    model_fn = AsyncMock(return_value=resp)
    pattern = SwarmPattern()
    result = await pattern.execute("question", {}, model_fn, AsyncMock(), [])
    assert result["answer"] == "The answer is 42"


@pytest.mark.asyncio
async def test_react_echoes_tool_call_in_openai_format():
    """When a tool call iteration happens, ReAct echoes the assistant
    tool_calls back into the next request. After 0.28.4, tc["arguments"]
    is a parsed dict (internal shape); but the assistant.tool_calls field
    sent to OpenAI-compatible APIs MUST be the nested OpenAI shape:
    {id, type:"function", function:{name, arguments:<JSON string>}}.
    Otherwise the API rejects the next request with 400 Bad Request."""
    import json as _json

    captured = []

    async def capturing_model_fn(messages, tools, role=None):
        captured.append([dict(m) for m in messages])
        if len(captured) == 1:
            return make_response(
                "I'll call calc_roi",
                tool_calls=[
                    {
                        "id": "tc_1",
                        "name": "calc_roi",
                        "arguments": {"monthly_volume": 100, "minutes_saved_per_unit": 5},
                    }
                ],
            )
        return make_response("ROI is positive")

    tool_fn = AsyncMock(return_value={"monthly_savings_usd": 416.67})

    pattern = ReActPattern()
    await pattern.execute(
        query="What's the ROI?",
        context={},
        model_fn=capturing_model_fn,
        tool_fn=tool_fn,
        tools=[],
    )

    # Second model call: the assistant message echoing the tool call must
    # use the nested OpenAI format, not the normalized internal shape.
    second_call_messages = captured[1]
    assistant_msg = next(
        m for m in second_call_messages if m.get("role") == "assistant" and m.get("tool_calls")
    )
    tc = assistant_msg["tool_calls"][0]
    assert tc.get("type") == "function", f"tool_call missing type:function — got {tc}"
    assert "function" in tc, f"tool_call missing nested 'function' key — got {tc}"
    assert tc["function"]["name"] == "calc_roi"
    # arguments MUST be a JSON string per the OpenAI schema
    assert isinstance(tc["function"]["arguments"], str), (
        f"arguments must be a JSON string, got {type(tc['function']['arguments']).__name__}"
    )
    assert _json.loads(tc["function"]["arguments"]) == {
        "monthly_volume": 100,
        "minutes_saved_per_unit": 5,
    }
    # The matching tool-result message follows with the same tool_call_id
    tool_msg = next(m for m in second_call_messages if m.get("role") == "tool")
    assert tool_msg["tool_call_id"] == "tc_1"


@dataclass
class ThinkingResponse:
    content: str
    tool_calls: list | None = None
    reasoning_content: str | None = None


@pytest.mark.asyncio
async def test_react_echoes_reasoning_content_for_thinking_models():
    """Thinking models (Kimi k2.5/k2.6 on Moonshot) require the assistant's
    reasoning_content to be echoed back on the tool-call message, or the next
    request 400s with 'reasoning_content is missing in assistant tool call
    message'. ReAct must carry response.reasoning_content through."""
    captured = []

    async def capturing_model_fn(messages, tools, role=None):
        captured.append([dict(m) for m in messages])
        if len(captured) == 1:
            return ThinkingResponse(
                content="",
                tool_calls=[{"id": "tc_1", "name": "calc_roi", "arguments": {"inversion": 1000}}],
                reasoning_content="The user wants ROI; I'll call calc_roi.",
            )
        return ThinkingResponse(content="ROI is 30%")

    tool_fn = AsyncMock(return_value={"roi": 30})
    pattern = ReActPattern()
    await pattern.execute(
        query="ROI?",
        context={},
        model_fn=capturing_model_fn,
        tool_fn=tool_fn,
        tools=[],
    )

    assistant_msg = next(
        m for m in captured[1] if m.get("role") == "assistant" and m.get("tool_calls")
    )
    assert assistant_msg.get("reasoning_content") == "The user wants ROI; I'll call calc_roi."


@pytest.mark.asyncio
async def test_react_omits_reasoning_content_when_absent():
    """Non-thinking models don't emit reasoning_content; the echoed assistant
    message must not carry the key (sending it empty/null can itself be rejected)."""
    captured = []

    async def capturing_model_fn(messages, tools, role=None):
        captured.append([dict(m) for m in messages])
        if len(captured) == 1:
            return make_response(
                "I'll call calc_roi",
                tool_calls=[{"id": "tc_1", "name": "calc_roi", "arguments": {"inversion": 1000}}],
            )
        return make_response("ROI is 30%")

    tool_fn = AsyncMock(return_value={"roi": 30})
    pattern = ReActPattern()
    await pattern.execute(
        query="ROI?",
        context={},
        model_fn=capturing_model_fn,
        tool_fn=tool_fn,
        tools=[],
    )

    assistant_msg = next(
        m for m in captured[1] if m.get("role") == "assistant" and m.get("tool_calls")
    )
    assert "reasoning_content" not in assistant_msg
