"""Tests for ADKRuntime local execution paths."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from astromesh_adk import agent
from astromesh_adk.runner import ADKRuntime
from astromesh_adk._internal.llm_dispatch import LlmResult


@pytest.fixture
def fake_caller(monkeypatch):
    """Patch the LLM caller used by the runner to return canned responses."""
    queue: list[LlmResult] = []

    async def _caller(model: str, payload: dict) -> LlmResult:
        if not queue:
            raise AssertionError(f"unexpected LLM call to {model}")
        return queue.pop(0)

    monkeypatch.setattr("astromesh_adk.runner._llm_caller", _caller)
    return queue


@pytest.mark.asyncio
async def test_run_agent_no_tools_returns_final_answer(fake_caller):
    fake_caller.append(LlmResult(text="42", input_tokens=10, output_tokens=2, model="claude-haiku-4-5", cost_usd=0.001))

    @agent(name="echo", model="claude-haiku-4-5")
    async def echo(ctx):
        """You answer questions briefly."""
        return None

    runtime = ADKRuntime()
    result = await runtime.run_agent(echo, "what is 6*7?", "session-1", None, None)

    assert result.answer == "42"
    assert result.tokens["input"] == 10
    assert result.tokens["output"] == 2
    assert result.model == "claude-haiku-4-5"


from astromesh_adk import tool


@pytest.mark.asyncio
async def test_run_agent_executes_tool_call_and_loops(fake_caller):
    @tool(description="Add two integers")
    async def add(a: int, b: int) -> int:
        return a + b

    @agent(name="math", model="claude-sonnet-4-6", tools=[add], max_iterations=5)
    async def math(ctx):
        """Use the add tool to do arithmetic."""
        return None

    # First LLM turn: requests tool call
    fake_caller.append(LlmResult(
        text="",
        input_tokens=20, output_tokens=10, model="claude-sonnet-4-6", cost_usd=0.002,
        tool_calls=[{"id": "tc1", "name": "add", "arguments": {"a": 6, "b": 7}}],
    ))
    # Second LLM turn: final answer
    fake_caller.append(LlmResult(
        text="13", input_tokens=30, output_tokens=2, model="claude-sonnet-4-6", cost_usd=0.003,
    ))

    runtime = ADKRuntime()
    result = await runtime.run_agent(math, "what is 6+7?", "s", None, None)

    assert result.answer == "13"
    assert len(result.steps) == 2  # tool_call + final
    assert result.steps[0]["kind"] == "tool_call"
    assert result.steps[0]["tool"] == "add"
    assert result.steps[0]["result"] == 13


@pytest.mark.asyncio
async def test_run_agent_respects_max_iterations(fake_caller):
    @tool(description="loops")
    async def noop() -> str:
        return "ok"

    @agent(name="looper", model="claude-haiku-4-5", tools=[noop], max_iterations=2)
    async def looper(ctx):
        """Loop forever via tool calls."""
        return None

    # Always request a tool call — should stop after max_iterations
    for _ in range(5):
        fake_caller.append(LlmResult(
            text="", input_tokens=5, output_tokens=2, model="claude-haiku-4-5", cost_usd=0.0001,
            tool_calls=[{"id": "tc", "name": "noop", "arguments": {}}],
        ))

    runtime = ADKRuntime()
    with pytest.raises(RuntimeError, match="max_iterations"):
        await runtime.run_agent(looper, "loop", "s", None, None)


@pytest.mark.asyncio
async def test_stream_agent_emits_events_per_step(fake_caller):
    @tool(description="echo")
    async def echo(text: str) -> str:
        return text

    @agent(name="streamer", model="claude-haiku-4-5", tools=[echo], max_iterations=3)
    async def streamer(ctx):
        """stream test"""
        return None

    fake_caller.append(LlmResult(
        text="", input_tokens=5, output_tokens=2, model="claude-haiku-4-5", cost_usd=0.0001,
        tool_calls=[{"id": "x", "name": "echo", "arguments": {"text": "hi"}}],
    ))
    fake_caller.append(LlmResult(
        text="hi back", input_tokens=10, output_tokens=3, model="claude-haiku-4-5", cost_usd=0.0001,
    ))

    runtime = ADKRuntime()
    events = []
    async for ev in runtime.stream_agent(streamer, "go", "s", None, True, None):
        events.append(ev)

    types = [e.type for e in events]
    assert "step" in types
    assert types[-1] == "done"
    step_kinds = [e.step.get("kind") for e in events if e.type == "step"]
    assert "tool_call" in step_kinds
