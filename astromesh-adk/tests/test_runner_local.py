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
