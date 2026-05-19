"""Tests for ADKRuntime (local in-process execution)."""
import pytest

from astromesh_adk.runner import _provider_and_model


def test_provider_and_model_explicit_slash():
    assert _provider_and_model("anthropic/claude-x") == ("anthropic", "claude-x")


def test_provider_and_model_claude_bare():
    assert _provider_and_model("claude-haiku-4-5") == ("anthropic", "claude-haiku-4-5")


def test_provider_and_model_gpt_bare():
    assert _provider_and_model("gpt-4o-mini") == ("openai", "gpt-4o-mini")


def test_provider_and_model_unknown_defaults_openai():
    assert _provider_and_model("mistral-large") == ("openai", "mistral-large")


from astromesh.observability.tracing import TracingContext
from astromesh.providers.base import CompletionResponse
from astromesh_adk.runner import ADKRuntime


class FakeProvider:
    """Stand-in ProviderProtocol; records calls, returns canned responses."""

    def __init__(self, model_name, *, fail_times=0, content="ok", tool_calls=None):
        self._model = model_name
        self._fail_times = fail_times
        self._content = content
        self._tool_calls = tool_calls or []
        self.calls = []

    async def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("boom")
        return CompletionResponse(
            content=self._content, model=self._model, provider="fake",
            usage={"input_tokens": 11, "output_tokens": 7}, latency_ms=5.0,
            cost=0.002, tool_calls=list(self._tool_calls),
        )

    async def stream(self, messages, **kwargs):  # pragma: no cover - not used here
        yield

    async def health_check(self):
        return True

    def supports_tools(self):
        return True

    def supports_vision(self):
        return False

    def estimated_cost(self, model, input_tokens, output_tokens):
        return 0.001


def _agent(name="a", model="claude-x", fallback=None, routing="quality_first"):
    from astromesh_adk.agent import agent

    @agent(name=name, model=model, fallback_model=fallback, routing=routing)
    async def _h(ctx):
        """SYSTEM-PROMPT-MARK"""
        return None

    return _h


@pytest.mark.asyncio
async def test_model_fn_injects_system_prompt_and_records_span():
    prov = FakeProvider("claude-x")
    rt = ADKRuntime(provider_factory=lambda p, m, c: prov)
    tctx = TracingContext("a", "s1")
    fn = rt._make_model_fn(_agent(), tctx)

    resp = await fn([{"role": "user", "content": "hi"}], None)

    assert resp.content == "ok"
    sent_messages = prov.calls[0][0]
    assert sent_messages[0] == {"role": "system", "content": "SYSTEM-PROMPT-MARK"}
    llm_spans = [s for s in tctx.spans if s.name == "llm.complete"]
    assert len(llm_spans) == 1
    assert llm_spans[0].attributes["cost"] == 0.002
    assert llm_spans[0].attributes["input_tokens"] == 11
    assert llm_spans[0].attributes["model"] == "claude-x"


@pytest.mark.asyncio
async def test_model_fn_falls_back_on_primary_failure():
    primary = FakeProvider("claude-x", fail_times=3)  # exhaust circuit
    fallback = FakeProvider("gpt-x", content="fallback-answer")

    def factory(provider_name, model_name, cfg):
        return primary if model_name == "claude-x" else fallback

    rt = ADKRuntime(provider_factory=factory)
    tctx = TracingContext("a", "s1")
    fn = rt._make_model_fn(_agent(model="claude-x", fallback="gpt-x"), tctx)

    resp = await fn([{"role": "user", "content": "hi"}], None)
    assert resp.content == "fallback-answer"


@pytest.mark.asyncio
async def test_tool_fn_invokes_tool_and_records_span():
    from astromesh_adk.tools import tool

    @tool(description="adds")
    async def add(a: int, b: int) -> int:
        return a + b

    rt = ADKRuntime(provider_factory=lambda p, m, c: FakeProvider(m))
    tctx = TracingContext("a", "s1")
    fn = rt._make_tool_fn([add], tctx)

    result = await fn("add", {"a": 2, "b": 3})
    assert result == 5
    tool_spans = [s for s in tctx.spans if s.name == "tool.call"]
    assert len(tool_spans) == 1
    assert tool_spans[0].attributes["tool"] == "add"


@pytest.mark.asyncio
async def test_tool_fn_unknown_tool_raises():
    rt = ADKRuntime(provider_factory=lambda p, m, c: FakeProvider(m))
    fn = rt._make_tool_fn([])
    with pytest.raises(KeyError):
        await fn("nope", {})


def test_build_context_wires_callables():
    rt = ADKRuntime(provider_factory=lambda p, m, c: FakeProvider(m))
    ctx = rt._build_context(_agent(name="z"), "the-query", "sess-1")
    assert ctx.agent_name == "z"
    assert ctx.query == "the-query"
    assert ctx.session_id == "sess-1"
    assert ctx._call_tool_fn is not None
    assert ctx._complete_fn is not None


@pytest.mark.asyncio
async def test_run_agent_returns_runresult_with_trace_accounting():
    prov = FakeProvider("claude-x", content="final answer")
    rt = ADKRuntime(provider_factory=lambda p, m, c: prov)

    result = await rt.run_agent(_agent(model="claude-x"), "what is 2+2?", "sess-1")

    assert result.answer == "final answer"
    assert isinstance(result.steps, list)
    assert result.cost == pytest.approx(0.002)
    assert result.tokens == {"input": 11, "output": 7}
    assert result.latency_ms >= 0
    assert result.model == "claude-x"


@pytest.mark.asyncio
async def test_run_agent_runs_tool_then_finishes():
    from astromesh_adk.tools import tool

    @tool(description="echo")
    async def echo(text: str) -> str:
        return f"echoed:{text}"

    from astromesh_adk.agent import agent

    @agent(name="t", model="claude-x", tools=[echo])
    async def _h(ctx):
        """sys"""
        return None

    class TwoStep(FakeProvider):
        def __init__(self):
            super().__init__("claude-x")
            self._n = 0

        async def complete(self, messages, **kwargs):
            self._n += 1
            if self._n == 1:
                return CompletionResponse(
                    content="thinking", model="claude-x", provider="fake",
                    usage={"input_tokens": 1, "output_tokens": 1}, latency_ms=1.0,
                    cost=0.0,
                    tool_calls=[{"id": "1", "name": "echo", "arguments": {"text": "hi"}}],
                )
            return CompletionResponse(
                content="done", model="claude-x", provider="fake",
                usage={"input_tokens": 1, "output_tokens": 1}, latency_ms=1.0, cost=0.0,
                tool_calls=[],
            )

    rt = ADKRuntime(provider_factory=lambda p, m, c: TwoStep())
    result = await rt.run_agent(_h, "go", "s")
    assert result.answer == "done"
    assert any(s.get("action") == "echo" for s in result.steps)


from astromesh_adk.team import AgentTeam


@pytest.mark.asyncio
async def test_run_team_parallel_aggregates_and_sums():
    rt = ADKRuntime(provider_factory=lambda p, m, c: FakeProvider(m, content=m))
    team = AgentTeam(
        name="par", pattern="parallel",
        agents=[_agent(name="x", model="claude-x"), _agent(name="y", model="gpt-y")],
    )
    result = await rt.run_team(team, "q", "s")

    assert {s["agent"] for s in result.steps} == {"x", "y"}
    assert result.tokens["input"] == 22  # 11 + 11
    assert result.cost == pytest.approx(0.004)


@pytest.mark.asyncio
async def test_run_team_pipeline_threads_output_and_nests():
    seen = []

    class RecordingProvider(FakeProvider):
        async def complete(self, messages, **kwargs):
            seen.append(messages[-1]["content"])
            return await super().complete(messages, **kwargs)

    rt = ADKRuntime(provider_factory=lambda p, m, c: RecordingProvider(m, content=f"out-{m}"))
    inner = AgentTeam(name="inner", pattern="parallel", agents=[_agent(name="a", model="claude-a")])
    team = AgentTeam(
        name="pipe", pattern="pipeline",
        agents=[inner, _agent(name="b", model="claude-b")],
    )
    result = await rt.run_team(team, "start", "s")

    assert result.answer == "out-claude-b"
    assert any("out-claude-a" in c for c in seen)


@pytest.mark.asyncio
async def test_run_team_supervisor_delegates_to_worker():
    import json
    from astromesh_adk.agent import agent

    @agent(name="sup", model="claude-sup")
    async def _sup(ctx):
        """supervisor"""
        return None

    @agent(name="worker", model="claude-w", description="does the work")
    async def _w(ctx):
        """worker"""
        return None

    class SupProvider(FakeProvider):
        def __init__(self):
            super().__init__("claude-sup")
            self._n = 0

        async def complete(self, messages, **kwargs):
            self._n += 1
            if self._n == 1:
                # SupervisorPattern expects JSON with "delegate" key in content
                return CompletionResponse(
                    content=json.dumps({"delegate": "worker", "task": "do it"}),
                    model="claude-sup", provider="fake",
                    usage={"input_tokens": 1, "output_tokens": 1}, latency_ms=1.0, cost=0.0,
                    tool_calls=[],
                )
            return CompletionResponse(
                content=json.dumps({"final_answer": "final from sup"}),
                model="claude-sup", provider="fake",
                usage={"input_tokens": 1, "output_tokens": 1}, latency_ms=1.0, cost=0.0,
                tool_calls=[],
            )

    def factory(p, m, c):
        return SupProvider() if m == "claude-sup" else FakeProvider(m, content="worker-did-it")

    rt = ADKRuntime(provider_factory=factory)
    team = AgentTeam(name="t", pattern="supervisor", supervisor=_sup, workers=[_w])
    result = await rt.run_team(team, "please do work", "s")
    assert "final from sup" in result.answer
    # Prove the worker was actually delegated to (not a no-op tool_fn):
    serialized_steps = str(result.steps)
    assert "worker-did-it" in serialized_steps, (
        f"worker delegation not observable in steps: {result.steps!r}"
    )


@pytest.mark.asyncio
async def test_stream_agent_emits_done_with_runresult():
    rt = ADKRuntime(provider_factory=lambda p, m, c: FakeProvider(m, content="streamed"))
    events = [e async for e in rt.stream_agent(_agent(model="claude-x"), "q", "s")]
    assert events[-1].type == "done"
    assert events[-1].result.answer == "streamed"


@pytest.mark.asyncio
async def test_run_class_agent_runs_hooks():
    from astromesh_adk.agent import Agent

    calls = []

    class MyAgent(Agent):
        name = "cls"
        model = "claude-x"

        async def on_before_run(self, ctx):
            calls.append("before")

        async def on_after_run(self, ctx, result):
            calls.append("after")

    rt = ADKRuntime(provider_factory=lambda p, m, c: FakeProvider(m, content="cls-out"))
    result = await rt.run_class_agent(MyAgent(), "q", "s")
    assert result.answer == "cls-out"
    assert calls == ["before", "after"]
