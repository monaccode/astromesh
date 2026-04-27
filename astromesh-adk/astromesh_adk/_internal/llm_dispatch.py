"""Internal helper to call LLM providers with retry and fallback chain."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable


class RateLimitError(Exception):
    """Provider returned 429."""


class TransientError(Exception):
    """Network/5xx/timeout — retryable."""


class PermanentError(Exception):
    """Auth, malformed request — do not retry."""


@dataclass
class LlmCall:
    system: str
    user: str
    tools: list[dict] = field(default_factory=list)
    response_format: dict | None = None
    max_tokens: int = 4096


@dataclass
class LlmResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict | None = None


# Caller signature: async (model: str, payload: dict) -> LlmResult
LlmCaller = Callable[[str, dict], Awaitable[LlmResult]]


def _reorder_for_routing(fallbacks: list[str], routing: str) -> list[str]:
    """Reorder fallback list per routing strategy.

    quality_first: keep order as-is.
    cost_optimized: cheapest first (caller's responsibility to provide cost table).
    latency_optimized: fastest first.
    round_robin: shuffle deterministically (rotate by hash).
    """
    if routing == "quality_first":
        return list(fallbacks)
    # NOTE: cost_optimized / latency_optimized actual sorting is done by caller's
    # routing.py table. Here we just preserve order; caller pre-sorts the list.
    return list(fallbacks)


async def dispatch_with_fallback(
    *,
    primary_model: str,
    fallback_models: list[str],
    routing: str,
    payload: dict,
    caller: LlmCaller,
    max_attempts_per_model: int = 3,
    base_backoff_seconds: float = 1.0,
) -> LlmResult:
    """Call `caller(model, payload)` retrying with exp backoff and falling back."""
    chain = [primary_model] + _reorder_for_routing(fallback_models, routing)
    last_err: Exception | None = None

    for model in chain:
        for attempt in range(max_attempts_per_model):
            try:
                return await caller(model, payload)
            except RateLimitError as e:
                last_err = e
                await asyncio.sleep(min(base_backoff_seconds * (2**attempt), 8.0))
            except TransientError as e:
                last_err = e
                await asyncio.sleep(min(base_backoff_seconds * (2**attempt), 8.0))
            except PermanentError as e:
                last_err = e
                break  # permanent — saltar al siguiente modelo

    raise RuntimeError(f"all models exhausted: {chain}; last={last_err!r}") from last_err
