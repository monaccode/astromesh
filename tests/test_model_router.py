"""Tests for provider base types used by the model router."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astromesh.core.model_router import ModelRouter
from astromesh.errors import ModelProviderError
from astromesh.providers.base import (
    CompletionChunk,
    CompletionResponse,
    CompletionResponse as CR,
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


# ---------------------------------------------------------------------------
# ModelRouter tests
# ---------------------------------------------------------------------------


def _make_mock_provider(
    name: str = "mock",
    cost: float = 0.01,
    supports_tools: bool = True,
    supports_vision: bool = False,
    complete_response: CR | None = None,
    complete_side_effect=None,
):
    """Return an AsyncMock that satisfies ProviderProtocol."""
    provider = AsyncMock()
    provider.supports_tools = MagicMock(return_value=supports_tools)
    provider.supports_vision = MagicMock(return_value=supports_vision)
    provider.estimated_cost = MagicMock(return_value=cost)

    if complete_response is None:
        complete_response = CR(
            content="ok",
            model="test-model",
            provider=name,
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            latency_ms=0.0,
            cost=cost,
        )

    if complete_side_effect is not None:
        provider.complete.side_effect = complete_side_effect
    else:
        provider.complete.return_value = complete_response

    return provider


class TestModelRouterRegistersProvider:
    """register_provider stores the provider and initialises health."""

    def test_router_registers_provider(self):
        router = ModelRouter({"strategy": "cost_optimized"})
        provider = _make_mock_provider("alpha")
        router.register_provider("alpha", provider)

        assert "alpha" in router._providers
        assert "alpha" in router._health
        assert router._health["alpha"].is_healthy is True
        assert router._health["alpha"].circuit_open is False


class TestModelRouterRoutesToProvider:
    """route() calls the provider and returns a response with latency."""

    @pytest.mark.asyncio
    async def test_router_routes_to_provider(self):
        router = ModelRouter({"strategy": "cost_optimized"})
        provider = _make_mock_provider("primary")
        router.register_provider("primary", provider)

        response = await router.route([{"role": "user", "content": "hi"}])

        provider.complete.assert_awaited_once()
        assert response.content == "ok"
        assert response.latency_ms > 0


class TestModelRouterFallbackOnFailure:
    """route() falls back to the next provider when the first fails."""

    @pytest.mark.asyncio
    async def test_router_fallback_on_failure(self):
        router = ModelRouter({"strategy": "cost_optimized"})

        failing = _make_mock_provider("failing", cost=0.001)
        failing.complete.side_effect = RuntimeError("provider down")

        backup = _make_mock_provider("backup", cost=0.01)
        router.register_provider("failing", failing)
        router.register_provider("backup", backup)

        response = await router.route([{"role": "user", "content": "hi"}])

        assert response.provider == "backup"
        failing.complete.assert_awaited_once()
        backup.complete.assert_awaited_once()


class TestModelRouterCircuitBreaker:
    """Three consecutive failures open the circuit breaker."""

    @pytest.mark.asyncio
    async def test_router_circuit_breaker(self):
        router = ModelRouter({"strategy": "cost_optimized"})

        failing = _make_mock_provider("flaky", cost=0.001)
        failing.complete.side_effect = RuntimeError("boom")

        backup = _make_mock_provider("backup", cost=0.01)

        router.register_provider("flaky", failing)
        router.register_provider("backup", backup)

        # Drive three failures on 'flaky' (backup succeeds each time).
        for _ in range(3):
            resp = await router.route([{"role": "user", "content": "hi"}])
            assert resp.provider == "backup"

        assert router._health["flaky"].circuit_open is True
        assert router._health["flaky"].consecutive_failures >= 3


class TestModelRouterNoProviders:
    """Declarative error when the router has no registered providers."""

    @pytest.mark.asyncio
    async def test_empty_router_raises(self):
        router = ModelRouter({"strategy": "cost_optimized"})
        with pytest.raises(ModelProviderError, match="No LLM providers are configured"):
            await router.route([{"role": "user", "content": "hi"}])


class TestModelRouterAllExhaustedRaises:
    """ModelProviderError when every provider fails."""

    @pytest.mark.asyncio
    async def test_router_all_exhausted_raises(self):
        router = ModelRouter({"strategy": "cost_optimized"})

        bad = _make_mock_provider("bad")
        bad.complete.side_effect = RuntimeError("nope")
        router.register_provider("bad", bad)

        with pytest.raises(ModelProviderError, match="All model providers failed"):
            await router.route([{"role": "user", "content": "hi"}])


class TestModelRouterProviderOverride:
    """provider_override kwarg bypasses registered providers."""

    @pytest.mark.asyncio
    async def test_route_with_provider_override(self):
        """When a provider_override is passed, ModelRouter uses it instead of registered providers."""
        router = ModelRouter({"strategy": "cost_optimized"})

        default_provider = _make_mock_provider(cost=0.01)
        router.register_provider("openai", default_provider)

        override_provider = _make_mock_provider(cost=0.0)
        override_provider.complete.return_value = MagicMock(
            content="override response",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            latency_ms=50.0,
        )

        messages = [{"role": "user", "content": "test"}]
        await router.route(messages, provider_override=("openai", override_provider))

        override_provider.complete.assert_called_once()
        default_provider.complete.assert_not_called()
