"""Model router with strategy-based provider selection and circuit breaker."""

from __future__ import annotations

import os
import time

from astromesh.errors import (
    ModelProviderError,
    explain_model_provider_failure,
    explain_no_eligible_providers,
)
from astromesh.providers.base import (
    CompletionResponse,
    ProviderHealth,
    ProviderProtocol,
    RoutingStrategy,
)

try:
    from astromesh._native import rust_detect_vision, rust_ema_update

    _HAS_NATIVE_ROUTING = True
except ImportError:
    _HAS_NATIVE_ROUTING = False


class ModelRouter:
    """Routes completion requests across registered providers.

    Supports multiple routing strategies (cost, latency, round-robin,
    capability match) and implements a circuit breaker that opens after
    three consecutive failures with a 60-second cooldown.
    """

    CIRCUIT_BREAKER_THRESHOLD = 3
    CIRCUIT_BREAKER_COOLDOWN_S = 60.0
    EMA_ALPHA = 0.8  # weight for existing average
    EMA_BETA = 0.2  # weight for new observation

    def __init__(self, config: dict):
        self._providers: dict[str, ProviderProtocol] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._strategy = RoutingStrategy(config.get("strategy", "cost_optimized"))
        self._config = config
        self._request_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider: ProviderProtocol) -> None:
        """Register a provider and initialise its health record."""
        self._providers[name] = provider
        self._health[name] = ProviderHealth()

    async def route(
        self,
        messages: list[dict],
        requirements: dict | None = None,
        **kwargs,
    ) -> CompletionResponse:
        """Route a completion request to the best available provider.

        Tries candidates in ranked order.  On failure the next candidate
        is attempted.  After *CIRCUIT_BREAKER_THRESHOLD* consecutive
        failures a provider's circuit is opened for *CIRCUIT_BREAKER_COOLDOWN_S*
        seconds.

        Raises ``ModelProviderError`` when every candidate has been exhausted
        or no providers are configured.
        """
        # Check for request-scoped provider override (BYOK)
        provider_override = kwargs.pop("provider_override", None)
        if provider_override:
            override_name, override_provider = provider_override
            try:
                response = await override_provider.complete(messages, **kwargs)
                response.latency_ms = 0.0
                return response
            except Exception as e:
                raise ModelProviderError(
                    f"Request-scoped provider '{override_name}' could not complete the request.",
                    hint=(
                        "Check X-Astromesh-Provider-Name / X-Astromesh-Provider-Key headers, "
                        "network access, and that the provider accepts the chosen model."
                    ),
                    code="model_provider_override_failed",
                    cause=e,
                ) from e

        if requirements is None:
            requirements = {}

        if not requirements.get("vision") and self._detect_vision_requirement(messages):
            requirements["vision"] = True

        registered = list(self._providers.keys())
        if not registered:
            raise explain_model_provider_failure(
                None,
                candidate_names=[],
                registered_provider_names=[],
            )

        candidates = self._rank_candidates(requirements)
        if not candidates:
            raise explain_no_eligible_providers(registered)

        last_error: Exception | None = None

        for name in candidates:
            provider = self._providers[name]
            health = self._health[name]

            start = time.perf_counter()
            try:
                response = await provider.complete(messages, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000.0

                # Update health metrics with exponential moving average.
                if health.avg_latency_ms == 0.0:
                    health.avg_latency_ms = elapsed_ms
                else:
                    if _HAS_NATIVE_ROUTING and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
                        health.avg_latency_ms = rust_ema_update(
                            health.avg_latency_ms, elapsed_ms, self.EMA_ALPHA, self.EMA_BETA
                        )
                    else:
                        health.avg_latency_ms = (
                            self.EMA_ALPHA * health.avg_latency_ms + self.EMA_BETA * elapsed_ms
                        )
                health.consecutive_failures = 0
                health.is_healthy = True
                health.last_check = time.time()

                # Ensure latency_ms is set on the response.
                response.latency_ms = elapsed_ms

                self._request_count += 1
                return response

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                health.consecutive_failures += 1
                health.last_check = time.time()

                if health.consecutive_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
                    health.circuit_open = True
                    health.circuit_open_until = time.time() + self.CIRCUIT_BREAKER_COOLDOWN_S
                    health.is_healthy = False

        raise explain_model_provider_failure(
            last_error,
            candidate_names=candidates,
            registered_provider_names=registered,
        )

    @staticmethod
    def _detect_vision_requirement(messages: list[dict]) -> bool:
        """Return True if any message contains image_url content."""
        if _HAS_NATIVE_ROUTING and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            return rust_detect_vision(messages)
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "image_url":
                        return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rank_candidates(self, requirements: dict) -> list[str]:
        """Return provider names ordered by the active routing strategy.

        Circuit-broken providers whose cooldown has not yet elapsed are
        excluded from the candidate list.
        """
        now = time.time()
        available: list[str] = []

        for name, health in self._health.items():
            if health.circuit_open:
                if now >= health.circuit_open_until:
                    # Cooldown elapsed – allow a retry (half-open).
                    health.circuit_open = False
                    health.consecutive_failures = 0
                    available.append(name)
                # else: still within cooldown, skip
            else:
                available.append(name)

        strategy = self._strategy

        if strategy == RoutingStrategy.COST_OPTIMIZED:
            available.sort(
                key=lambda n: self._providers[n].estimated_cost("default", 1000, 1000),
            )

        elif strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            available.sort(key=lambda n: self._health[n].avg_latency_ms)

        elif strategy == RoutingStrategy.ROUND_ROBIN:
            if available:
                offset = self._request_count % len(available)
                available = available[offset:] + available[:offset]

        elif strategy == RoutingStrategy.CAPABILITY_MATCH:
            required_tools = requirements.get("tools", False)
            required_vision = requirements.get("vision", False)
            available = [
                n
                for n in available
                if (not required_tools or self._providers[n].supports_tools())
                and (not required_vision or self._providers[n].supports_vision())
            ]

        return available
