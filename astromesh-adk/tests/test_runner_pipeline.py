"""Tests for ADKRuntime._run_pipeline."""
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
            raise AssertionError(f"unexpected LLM call to {model} with system={payload.get('system','')[:60]}")
        return queue.pop(0)

    monkeypatch.setattr("astromesh_adk.runner._llm_caller", _caller)
    return queue


@pytest.mark.asyncio
async def test_pipeline_passes_output_to_next_agent(fake_caller):
    @agent(name="step1", model="claude-haiku-4-5")
    async def step1(ctx):
        """First step."""
        return None

    @agent(name="step2", model="claude-haiku-4-5")
    async def step2(ctx):
        """Second step."""
        return None

    fake_caller.append(LlmResult(text="output-of-step-1", input_tokens=5, output_tokens=10, model="claude-haiku-4-5", cost_usd=0.001))
    fake_caller.append(LlmResult(text="final-after-step2", input_tokens=20, output_tokens=5, model="claude-haiku-4-5", cost_usd=0.001))

    team = AgentTeam(name="pipe", pattern="pipeline", agents=[step1, step2])
    runtime = ADKRuntime()
    result = await runtime.run_team(team, "input-original", "s", None, None)

    assert result.answer == "final-after-step2"
    assert "step1" in result.metadata.get("previous_outputs", {})
    assert result.metadata["previous_outputs"]["step1"] == "output-of-step-1"
    assert result.cost == pytest.approx(0.002)
    assert result.tokens["input"] == 25
    assert result.tokens["output"] == 15
