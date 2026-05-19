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
