"""Tests for provider base types used by the model router."""

from astromech.providers.base import (
    CompletionChunk,
    CompletionResponse,
    ProviderHealth,
    RoutingStrategy,
)


class TestRoutingStrategy:
    """RoutingStrategy enum contains the expected members."""

    def test_has_cost_optimized(self):
        assert RoutingStrategy.COST_OPTIMIZED == "cost_optimized"

    def test_has_latency_optimized(self):
        assert RoutingStrategy.LATENCY_OPTIMIZED == "latency_optimized"

    def test_has_quality_first(self):
        assert RoutingStrategy.QUALITY_FIRST == "quality_first"

    def test_has_round_robin(self):
        assert RoutingStrategy.ROUND_ROBIN == "round_robin"

    def test_has_capability_match(self):
        assert RoutingStrategy.CAPABILITY_MATCH == "capability_match"

    def test_member_count(self):
        assert len(RoutingStrategy) == 5

    def test_is_str_subclass(self):
        assert isinstance(RoutingStrategy.COST_OPTIMIZED, str)


class TestCompletionResponse:
    """CompletionResponse dataclass has correct fields and defaults."""

    def test_required_fields(self):
        resp = CompletionResponse(
            content="hello",
            model="gpt-4",
            provider="openai",
            usage={"prompt_tokens": 5, "completion_tokens": 3},
            latency_ms=120.0,
            cost=0.001,
        )
        assert resp.content == "hello"
        assert resp.model == "gpt-4"
        assert resp.provider == "openai"
        assert resp.usage == {"prompt_tokens": 5, "completion_tokens": 3}
        assert resp.latency_ms == 120.0
        assert resp.cost == 0.001

    def test_default_tool_calls(self):
        resp = CompletionResponse(
            content="hi", model="m", provider="p", usage={}, latency_ms=0, cost=0
        )
        assert resp.tool_calls == []

    def test_default_metadata(self):
        resp = CompletionResponse(
            content="hi", model="m", provider="p", usage={}, latency_ms=0, cost=0
        )
        assert resp.metadata == {}

    def test_default_lists_are_independent(self):
        a = CompletionResponse(content="a", model="m", provider="p", usage={}, latency_ms=0, cost=0)
        b = CompletionResponse(content="b", model="m", provider="p", usage={}, latency_ms=0, cost=0)
        a.tool_calls.append("x")
        assert b.tool_calls == []


class TestCompletionChunk:
    """CompletionChunk dataclass has correct fields and defaults."""

    def test_defaults(self):
        chunk = CompletionChunk(content="tok", model="m", provider="p")
        assert chunk.done is False
        assert chunk.usage is None

    def test_done_flag(self):
        chunk = CompletionChunk(content="", model="m", provider="p", done=True, usage={"total": 10})
        assert chunk.done is True
        assert chunk.usage == {"total": 10}


class TestProviderHealth:
    """ProviderHealth dataclass has correct defaults."""

    def test_defaults(self):
        health = ProviderHealth()
        assert health.is_healthy is True
        assert health.last_check == 0.0
        assert health.consecutive_failures == 0
        assert health.avg_latency_ms == 0.0
        assert health.circuit_open is False
        assert health.circuit_open_until == 0.0

    def test_custom_values(self):
        health = ProviderHealth(
            is_healthy=False,
            last_check=1000.0,
            consecutive_failures=3,
            avg_latency_ms=250.0,
            circuit_open=True,
            circuit_open_until=2000.0,
        )
        assert health.is_healthy is False
        assert health.consecutive_failures == 3
        assert health.circuit_open is True
