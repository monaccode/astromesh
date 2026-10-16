"""Local runs with core 0.70 semantics: guardrails, patterns, roles, tool budgets, kb tools."""

from pathlib import Path

import pytest
from astromesh.errors import AgentConfigError
from astromesh.providers.base import CompletionResponse

from astromesh_adk import agent, kb_tools, tool
from astromesh_adk.runner import ADKRuntime

OKF = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "okf"


class Provider:
    def __init__(self, model, replies):
        self.model, self.replies, self.calls = model, list(replies), []

    async def complete(self, messages, **kwargs):
        self.calls.append(messages)
        content, tool_calls = self.replies.pop(0) if self.replies else ("done", [])
        return CompletionResponse(
            content=content,
            model=self.model,
            provider="fake",
            usage={"input_tokens": 5, "output_tokens": 50},
            latency_ms=1.0,
            cost=0.0,
            tool_calls=tool_calls,
        )

    async def stream(self, messages, **kwargs):  # pragma: no cover
        yield

    async def health_check(self):
        return True

    def supports_tools(self):
        return True

    def supports_vision(self):
        return False

    def estimated_cost(self, model, i, o):
        return 0.0


def _rt(provider):
    return ADKRuntime(provider_factory=lambda p, m, c: provider)


async def test_input_block_returns_refusal_without_calling_the_model():
    @agent(
        name="g",
        model="claude-x",
        guardrails={"input": [{"type": "pii_detection", "action": "block", "message": "no"}]},
    )
    async def g(ctx):
        """sys"""

    prov = Provider("claude-x", [("leaked", [])])
    result = await g.run("mail a@b.co", runtime=_rt(prov))
    assert result.blocked is True and result.answer == "no"
    assert result.guardrail == {
        "direction": "input",
        "rule": "pii_detection",
        "reason": "pii detected",
    }
    assert prov.calls == []


async def test_input_redact_and_output_filter():
    @agent(
        name="g2",
        model="claude-x",
        guardrails={
            "input": ["pii_detection"],
            "output": [{"type": "content_filter", "forbidden_keywords": ["secret"]}],
        },
    )
    async def g2(ctx):
        """sys"""

    prov = Provider("claude-x", [("the secret is out", [])])
    result = await g2.run("mail a@b.co", runtime=_rt(prov))
    assert result.blocked is False and result.guardrail is None
    assert result.answer == "the [FILTERED] is out"
    assert "[REDACTED_EMAIL]" in prov.calls[0][-1]["content"]


async def test_cost_limit_blocks_the_next_model_call():
    @tool(description="noop")
    async def noop() -> str:
        return "ok"

    @agent(
        name="c",
        model="claude-x",
        tools=[noop],
        guardrails={"output": [{"type": "cost_limit", "max_tokens_per_turn": 40}]},
    )
    async def c(ctx):
        """sys"""

    call = {"id": "1", "name": "noop", "arguments": {}}
    prov = Provider("claude-x", [("", [call]), ("never", [])])
    result = await c.run("go", runtime=_rt(prov))
    assert result.blocked is True and result.guardrail["rule"] == "cost_limit"
    assert len(prov.calls) == 1


def test_unknown_pattern_raises_at_definition():
    with pytest.raises(AgentConfigError):

        @agent(name="x", model="claude-x", pattern="swarmy")
        async def x(ctx):
            """sys"""


async def test_supervisor_needs_agent_tools():
    @agent(name="s", model="claude-x", pattern="supervisor")
    async def s(ctx):
        """sys"""

    with pytest.raises(AgentConfigError):
        await s.run("go", runtime=_rt(Provider("claude-x", [])))


async def test_roles_route_to_their_own_model():
    used = []

    def factory(p, m, c):
        used.append(m)
        return Provider(m, [("plan", [])] * 5)

    @agent(
        name="r", model="claude-main", roles={"planner": "claude-plan"}, pattern="plan_and_execute"
    )
    async def r(ctx):
        """sys"""

    result = await r.run("go", runtime=ADKRuntime(provider_factory=factory))
    models = [
        s["attributes"]["model"] for s in result.trace["spans"] if s["name"] == "llm.complete"
    ]
    assert models[0] == "claude-plan" and "claude-main" in models
    assert {m["role"] for m in result.by_model} >= {"planner"}


async def test_tool_result_is_capped_by_max_result_tokens():
    @tool(description="big", max_result_tokens=20)
    async def big() -> str:
        return "word " * 2000

    @agent(name="b", model="claude-x", tools=[big])
    async def b(ctx):
        """sys"""

    prov = Provider("claude-x", [("", [{"id": "1", "name": "big", "arguments": {}}])])
    await b.run("go", runtime=_rt(prov))
    tool_msg = next(m for m in prov.calls[1] if m.get("role") == "tool")
    assert "resultado recortado" in tool_msg["content"]
    assert len(tool_msg["content"]) < 400


async def test_kb_tools_are_core_bundle_tools():
    tools = kb_tools(str(OKF))
    assert sorted(t.tool_name for t in tools) == ["kb_find", "kb_index", "kb_read"]
    read = next(t for t in tools if t.tool_name == "kb_read")
    out = await read.execute({"concept_id": "metrics/revenue"})
    assert out["success"] is True and out["data"]["title"] == "Revenue"
    with pytest.raises(ValueError):
        kb_tools("/nonexistent/bundle")


def test_history_budget_uses_declared_context_window():
    @agent(name="w", model="claude-x", context_window=10_000)
    async def w(ctx):
        """sys"""

    budget = ADKRuntime()._history_budget(w, [])
    assert 0 < budget < 9_000


def _team_members():
    @agent(
        name="sup",
        model="claude-sup",
        guardrails={
            "input": [{"type": "pii_detection", "action": "block"}],
            "output": [{"type": "cost_limit", "max_tokens_per_turn": 40}],
        },
    )
    async def sup(ctx):
        """sys"""

    @agent(name="worker", model="claude-w")
    async def worker(ctx):
        """sys"""

    return sup, worker


async def test_supervisor_team_applies_the_supervisor_input_rules():
    from astromesh_adk.team import AgentTeam

    sup, worker = _team_members()
    prov = Provider("claude-sup", [])
    team = AgentTeam(name="t", pattern="supervisor", supervisor=sup, workers=[worker])
    result = await team.run("mail a@b.co", runtime=_rt(prov))
    assert result.blocked is True and result.guardrail["rule"] == "pii_detection"
    assert prov.calls == []


async def test_supervisor_team_applies_the_supervisor_cost_limit():
    from astromesh_adk.team import AgentTeam

    sup, worker = _team_members()
    call = {"id": "1", "name": "worker", "arguments": {"query": "x"}}
    provs = {"claude-sup": Provider("claude-sup", [("", [call]), ("never", [])])}

    def factory(p, m, c):
        return provs.get(m) or Provider(m, [("work", [])])

    team = AgentTeam(name="t", pattern="supervisor", supervisor=sup, workers=[worker])
    result = await team.run("go", runtime=ADKRuntime(provider_factory=factory))
    assert result.blocked is True and result.guardrail["rule"] == "cost_limit"
    assert len(provs["claude-sup"].calls) == 1


async def test_pipeline_stops_at_a_blocked_stage_and_reports_it():
    from astromesh_adk.team import AgentTeam

    @agent(
        name="first",
        model="claude-x",
        guardrails={"input": [{"type": "pii_detection", "action": "block", "message": "no"}]},
    )
    async def first(ctx):
        """sys"""

    @agent(name="second", model="claude-x")
    async def second(ctx):
        """sys"""

    prov = Provider("claude-x", [("second ran", [])])
    team = AgentTeam(name="p", pattern="pipeline", agents=[first, second])
    result = await team.run("mail a@b.co", runtime=_rt(prov))
    assert result.blocked is True and result.answer == "no"
    assert result.guardrail["rule"] == "pii_detection"
    assert prov.calls == []


def test_history_budget_reserves_the_model_max_tokens():
    @agent(name="w2", model="claude-x", context_window=10_000, model_config={"max_tokens": 4000})
    async def w2(ctx):
        """sys"""

    @agent(name="w3", model="claude-x", context_window=10_000)
    async def w3(ctx):
        """sys"""

    rt = ADKRuntime()
    assert rt._history_budget(w3, []) - rt._history_budget(w2, []) == 4000 - 1024


async def test_local_by_model_carries_provider_and_cached_tokens():
    class Cached(Provider):
        async def complete(self, messages, **kwargs):
            resp = await super().complete(messages, **kwargs)
            resp.usage = {**resp.usage, "cache_read_input_tokens": 3}
            return resp

    @agent(name="k", model="claude-x")
    async def k(ctx):
        """sys"""

    result = await k.run("hi", runtime=_rt(Cached("claude-x", [("ok", [])])))
    assert result.by_model[0]["provider"] == "fake"
    assert result.by_model[0]["tokens_cached"] == 3
