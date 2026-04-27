"""Tests for the internal llm_dispatch helper."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from astromesh_adk._internal.llm_dispatch import (
    LlmCall,
    LlmResult,
    RateLimitError,
    TransientError,
    PermanentError,
    dispatch_with_fallback,
)


@pytest.mark.asyncio
async def test_dispatch_retries_on_rate_limit_then_succeeds():
    calls = []

    async def fake_call(model: str, payload: dict) -> LlmResult:
        calls.append(model)
        if len(calls) == 1:
            raise RateLimitError("quota exceeded")
        return LlmResult(text="ok", input_tokens=10, output_tokens=5, model=model, cost_usd=0.01)

    result = await dispatch_with_fallback(
        primary_model="claude-sonnet-4-6",
        fallback_models=["claude-haiku-4-5"],
        routing="quality_first",
        payload={"system": "s", "user": "u"},
        caller=fake_call,
        max_attempts_per_model=3,
    )
    assert result.text == "ok"
    assert calls == ["claude-sonnet-4-6", "claude-sonnet-4-6"]


@pytest.mark.asyncio
async def test_dispatch_falls_back_when_primary_exhausts_retries():
    calls = []

    async def fake_call(model: str, payload: dict) -> LlmResult:
        calls.append(model)
        if model == "claude-sonnet-4-6":
            raise TransientError("502 bad gateway")
        return LlmResult(text="from-fallback", input_tokens=8, output_tokens=4, model=model, cost_usd=0.005)

    result = await dispatch_with_fallback(
        primary_model="claude-sonnet-4-6",
        fallback_models=["claude-haiku-4-5"],
        routing="quality_first",
        payload={},
        caller=fake_call,
        max_attempts_per_model=2,
    )
    assert result.text == "from-fallback"
    assert calls == ["claude-sonnet-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]


@pytest.mark.asyncio
async def test_dispatch_skips_fallback_on_permanent_error():
    """PermanentError en primario debe saltar inmediatamente al fallback."""
    calls = []

    async def fake_call(model: str, payload: dict) -> LlmResult:
        calls.append(model)
        if model == "claude-sonnet-4-6":
            raise PermanentError("invalid api key")
        return LlmResult(text="fb", input_tokens=1, output_tokens=1, model=model, cost_usd=0.001)

    result = await dispatch_with_fallback(
        primary_model="claude-sonnet-4-6",
        fallback_models=["claude-haiku-4-5"],
        routing="quality_first",
        payload={},
        caller=fake_call,
    )
    assert calls == ["claude-sonnet-4-6", "claude-haiku-4-5"]
    assert result.text == "fb"


@pytest.mark.asyncio
async def test_dispatch_raises_when_all_models_fail():
    async def fake_call(model: str, payload: dict) -> LlmResult:
        raise TransientError(f"{model} down")

    with pytest.raises(RuntimeError, match="all models exhausted"):
        await dispatch_with_fallback(
            primary_model="claude-sonnet-4-6",
            fallback_models=["claude-haiku-4-5"],
            routing="quality_first",
            payload={},
            caller=fake_call,
            max_attempts_per_model=2,
        )
