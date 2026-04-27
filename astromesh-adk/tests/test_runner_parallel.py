"""Tests for ADKRuntime._run_parallel."""
from __future__ import annotations

import asyncio
import pytest

from astromesh_adk import agent
from astromesh_adk.team import AgentTeam
from astromesh_adk.runner import ADKRuntime
from astromesh_adk._internal.llm_dispatch import LlmResult


@pytest.fixture
def fake_caller(monkeypatch):
    """Caller that returns one canned response per agent name."""
    by_system: dict[str, LlmResult] = {}

    async def _caller(model, payload):
        sys_prompt = payload.get("system", "")
        for sig, res in by_system.items():
            if sig in sys_prompt:
                return res
        raise AssertionError(f"no canned response matches system={sys_prompt[:80]}")

    monkeypatch.setattr("astromesh_adk.runner._llm_caller", _caller)
    return by_system


@pytest.mark.asyncio
async def test_parallel_runs_all_agents_and_aggregates(fake_caller):
    @agent(name="a1", model="claude-haiku-4-5")
    async def a1(ctx):
        """sig-a1 — agent one"""
        return None

    @agent(name="a2", model="claude-haiku-4-5")
    async def a2(ctx):
        """sig-a2 — agent two"""
        return None

    @agent(name="a3", model="claude-haiku-4-5")
    async def a3(ctx):
        """sig-a3 — agent three"""
        return None

    fake_caller["sig-a1"] = LlmResult(text="r1", input_tokens=5, output_tokens=3, model="claude-haiku-4-5", cost_usd=0.001)
    fake_caller["sig-a2"] = LlmResult(text="r2", input_tokens=6, output_tokens=4, model="claude-haiku-4-5", cost_usd=0.002)
    fake_caller["sig-a3"] = LlmResult(text="r3", input_tokens=7, output_tokens=5, model="claude-haiku-4-5", cost_usd=0.003)

    team = AgentTeam(name="par", pattern="parallel", agents=[a1, a2, a3])
    runtime = ADKRuntime()
    result = await runtime.run_team(team, "go", "s", None, None)

    outs = result.metadata["previous_outputs"]
    assert outs == {"a1": "r1", "a2": "r2", "a3": "r3"}
    assert result.cost == pytest.approx(0.006)
    assert result.tokens["input"] == 18
    assert result.tokens["output"] == 12


@pytest.mark.asyncio
async def test_parallel_propagates_first_exception(fake_caller, monkeypatch):
    async def failing_caller(model, payload):
        raise RuntimeError("provider down")

    monkeypatch.setattr("astromesh_adk.runner._llm_caller", failing_caller)

    @agent(name="a", model="claude-haiku-4-5")
    async def a(ctx):
        """a"""
        return None

    @agent(name="b", model="claude-haiku-4-5")
    async def b(ctx):
        """b"""
        return None

    team = AgentTeam(name="par", pattern="parallel", agents=[a, b])
    runtime = ADKRuntime()
    with pytest.raises(ExceptionGroup):
        await runtime.run_team(team, "go", "s", None, None)
