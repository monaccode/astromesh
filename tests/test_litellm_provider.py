"""Tests for the LiteLLM-backed provider adapter (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from astromesh.providers.base import CompletionResponse
from astromesh.providers.litellm_provider import LiteLLMProvider, _litellm_provider_label


def _fake_model_response() -> SimpleNamespace:
    """Mimics litellm.ModelResponse.model_dump() shape (OpenAI-compatible)."""
    return SimpleNamespace(
        model_dump=lambda: {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello from Claude!",
                        "tool_calls": [
                            {
                                "id": "tc_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": '{"q": "x"}'},
                            }
                        ],
                        "reasoning_content": "thinking...",
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "cache_read_input_tokens": 4},
        }
    )


def test_provider_label():
    assert _litellm_provider_label("anthropic/claude-opus-4-8") == "anthropic"
    assert _litellm_provider_label("gpt-4o") == "litellm"


async def test_complete_maps_response(monkeypatch):
    import astromesh.providers.litellm_provider as mod

    async def fake_acompletion(**kwargs):
        assert kwargs["model"] == "anthropic/claude-opus-4-8"
        return _fake_model_response()

    fake_litellm = SimpleNamespace(
        acompletion=fake_acompletion,
        completion_cost=lambda **_: 0.0031,
    )
    monkeypatch.setattr(mod, "_import_litellm", lambda: fake_litellm)

    provider = LiteLLMProvider(config={"model": "anthropic/claude-opus-4-8"})
    resp = await provider.complete([{"role": "user", "content": "hi"}])

    assert isinstance(resp, CompletionResponse)
    assert resp.content == "Hello from Claude!"
    assert resp.provider == "anthropic"
    assert resp.usage["input_tokens"] == 12
    assert resp.usage["output_tokens"] == 7
    assert resp.usage["cache_read_input_tokens"] == 4
    assert resp.cost == 0.0031
    assert resp.tool_calls == [{"id": "tc_1", "name": "lookup", "arguments": {"q": "x"}}]
    assert resp.reasoning_content == "thinking..."


def test_missing_dependency_raises_on_use(monkeypatch):
    import astromesh.providers.litellm_provider as mod

    def boom():
        raise ImportError("litellm not installed")

    monkeypatch.setattr(mod, "_import_litellm", boom)
    provider = LiteLLMProvider(config={"model": "anthropic/claude-opus-4-8"})
    with pytest.raises(ImportError):
        provider._litellm()
