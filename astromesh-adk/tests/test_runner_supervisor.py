"""Tests for ADKRuntime._run_supervisor."""
from __future__ import annotations

import pytest

from astromesh_adk import agent
from astromesh_adk.team import AgentTeam
from astromesh_adk.runner import ADKRuntime
from astromesh_adk._internal.llm_dispatch import LlmResult


@pytest.fixture
def fake_caller(monkeypatch):
    queue = []

    async def _caller(model, payload):
        if not queue:
            raise AssertionError(f"unexpected LLM call to {model}")
        return queue.pop(0)

    monkeypatch.setattr("astromesh_adk.runner._llm_caller", _caller)
    return queue


@pytest.mark.asyncio
async def test_supervisor_delegates_then_returns_final(fake_caller):
    @agent(name="worker", model="claude-haiku-4-5")
    async def worker(ctx):
        """worker"""
        return None

    @agent(name="supervisor", model="claude-haiku-4-5")
    async def supervisor(ctx):
        """supervisor"""
        return None

    # Supervisor turn 1: delegate to worker
    fake_caller.append(LlmResult(
        text="", input_tokens=10, output_tokens=5, model="claude-haiku-4-5", cost_usd=0.001,
        tool_calls=[{"id": "d1", "name": "delegate_to", "arguments": {"worker": "worker", "task": "do thing"}}],
    ))
    # Worker turn (called by _run_local)
    fake_caller.append(LlmResult(
        text="worker result", input_tokens=15, output_tokens=10, model="claude-haiku-4-5", cost_usd=0.002,
    ))
    # Supervisor turn 2: final answer
    fake_caller.append(LlmResult(
        text="", input_tokens=20, output_tokens=5, model="claude-haiku-4-5", cost_usd=0.001,
        tool_calls=[{"id": "f1", "name": "final_answer", "arguments": {"answer": "all done"}}],
    ))

    team = AgentTeam(name="sup", pattern="supervisor", supervisor=supervisor, workers=[worker])
    runtime = ADKRuntime()
    result = await runtime.run_team(team, "go", "s", None, None)

    assert result.answer == "all done"
    assert result.metadata["worker_results"]["worker"] == "worker result"
