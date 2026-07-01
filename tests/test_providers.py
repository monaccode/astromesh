"""Tests for all 6 Astromesh provider adapters."""

from __future__ import annotations

import httpx
import pytest
import respx

from astromesh.errors import ModelProviderError
from astromesh.providers.base import CompletionResponse
from astromesh.providers.hf_tgi_provider import HFTGIProvider
from astromesh.providers.llamacpp_provider import LlamaCppProvider
from astromesh.providers.ollama_provider import OllamaProvider
from astromesh.providers.onnx_provider import ONNXProvider
from astromesh.providers.openai_compat import CACHE_INPUT_PRICING, OpenAICompatProvider, _normalize_tool_calls, _provider_label
from astromesh.providers.vllm_provider import VLLMProvider

# ---------------------------------------------------------------------------
# Helpers — canonical mock responses
# ---------------------------------------------------------------------------

OLLAMA_CHAT_RESPONSE = {
    "message": {"role": "assistant", "content": "Hello from Ollama!"},
    "prompt_eval_count": 10,
    "eval_count": 20,
}

OPENAI_CHAT_RESPONSE = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from OpenAI!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40},
}

MESSAGES = [{"role": "user", "content": "Hi"}]


# ===================================================================
# Ollama
# ===================================================================


@respx.mock
async def test_ollama_complete():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, json=OLLAMA_CHAT_RESPONSE)
    )

    provider = OllamaProvider({"base_url": "http://localhost:11434", "model": "llama3"})
    result = await provider.complete(MESSAGES)

    assert isinstance(result, CompletionResponse)
    assert result.content == "Hello from Ollama!"
    assert result.provider == "ollama"
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 20
    assert result.cost == 0.0


@respx.mock
async def test_ollama_health_check_healthy():
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )

    provider = OllamaProvider({"base_url": "http://localhost:11434"})
    assert await provider.health_check() is True


@respx.mock
async def test_ollama_health_check_unhealthy():
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(500)
    )

    provider = OllamaProvider({"base_url": "http://localhost:11434"})
    assert await provider.health_check() is False


def test_ollama_supports_tools():
    provider = OllamaProvider({"model": "llama3"})
    assert provider.supports_tools() is True


def test_ollama_supports_vision():
    assert OllamaProvider({"model": "llava"}).supports_vision() is True
    assert OllamaProvider({"model": "llava-13b"}).supports_vision() is True
    assert OllamaProvider({"model": "my-vision-model"}).supports_vision() is True
    assert OllamaProvider({"model": "llama3"}).supports_vision() is False


# ===================================================================
# OpenAI-Compatible
# ===================================================================


@respx.mock
async def test_openai_compat_complete():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = OpenAICompatProvider(
        {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-test"}
    )
    result = await provider.complete(MESSAGES)

    assert isinstance(result, CompletionResponse)
    assert result.content == "Hello from OpenAI!"
    assert result.provider == "openai"
    assert result.usage["input_tokens"] == 15
    assert result.usage["output_tokens"] == 25
    assert result.cost > 0


def test_openai_compat_supports_tools():
    provider = OpenAICompatProvider({"model": "gpt-4o", "api_key": "sk-test"})
    assert provider.supports_tools() is True


async def test_openai_compat_missing_api_key_fails_fast(monkeypatch):
    """No API key → fail fast with a clear ModelProviderError instead of an
    empty 'Authorization: Bearer ' header that httpx rejects as illegal."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    provider = OpenAICompatProvider(
        {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-sonnet-4-6",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
    )

    with pytest.raises(ModelProviderError) as exc_info:
        await provider.complete(MESSAGES)

    assert exc_info.value.code == "model_missing_api_key"
    assert "ANTHROPIC_API_KEY" in exc_info.value.hint


OPENAI_TOOL_CALL_RESPONSE = {
    "id": "chatcmpl-tc",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calc_roi",
                            "arguments": '{"monthly_volume": 100, "minutes_saved": 5}',
                        },
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
}


@respx.mock
async def test_openai_compat_normalizes_tool_calls():
    """The API returns tool_calls in OpenAI nested shape
    ({function: {name, arguments-as-json-string}}). complete() must normalize
    to the flat canonical shape {id, name, arguments-as-dict} that astromesh's
    orchestration patterns expect — otherwise patterns.py does tc["name"] and
    raises KeyError: 'name'."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_TOOL_CALL_RESPONSE)
    )

    provider = OpenAICompatProvider(
        {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-test"}
    )
    result = await provider.complete(MESSAGES)

    assert result.tool_calls == [
        {
            "id": "call_1",
            "name": "calc_roi",
            "arguments": {"monthly_volume": 100, "minutes_saved": 5},
        }
    ]


REASONING_TOOL_CALL_RESPONSE = {
    "id": "chatcmpl-reason",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "",
                "reasoning_content": "The user wants ROI; I'll call calc_roi.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "calc_roi", "arguments": '{"inversion": 1000}'},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
}


@respx.mock
async def test_openai_compat_captures_reasoning_content():
    """Thinking models (Kimi k2.5/k2.6 on Moonshot) return a reasoning_content
    field that MUST be surfaced on CompletionResponse — the ReAct pattern echoes
    it back on the next turn's assistant message, or the API 400s. A normal
    response without the field yields None."""
    respx.post("https://api.moonshot.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=REASONING_TOOL_CALL_RESPONSE)
    )
    provider = OpenAICompatProvider(
        {"base_url": "https://api.moonshot.ai/v1", "model": "kimi-k2.5", "api_key": "sk-test"}
    )
    result = await provider.complete(MESSAGES)
    assert result.reasoning_content == "The user wants ROI; I'll call calc_roi."


@respx.mock
async def test_openai_compat_reasoning_content_none_when_absent():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
    )
    provider = OpenAICompatProvider(
        {"base_url": "https://api.openai.com/v1", "model": "gpt-4o", "api_key": "sk-test"}
    )
    result = await provider.complete(MESSAGES)
    assert result.reasoning_content is None


def test_normalize_tool_calls_arg_shapes():
    """_normalize_tool_calls handles non-string-args paths: an already-dict
    arguments value passes through unchanged, a malformed JSON string is
    preserved as {"_raw": ...} for debuggability, and None input yields []."""
    # (a) arguments already a dict — passes through unchanged
    already_dict = _normalize_tool_calls(
        [{"id": "c1", "function": {"name": "f", "arguments": {"k": "v"}}}]
    )
    assert already_dict == [{"id": "c1", "name": "f", "arguments": {"k": "v"}}]

    # (b) malformed JSON string — preserved under "_raw"
    malformed = _normalize_tool_calls(
        [{"id": "c2", "function": {"name": "g", "arguments": "{not json"}}]
    )
    assert malformed == [{"id": "c2", "name": "g", "arguments": {"_raw": "{not json"}}]

    # (c) None input — empty list
    assert _normalize_tool_calls(None) == []


# ===================================================================
# vLLM
# ===================================================================


@respx.mock
async def test_vllm_complete():
    respx.post("http://localhost:8000/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = VLLMProvider({"base_url": "http://localhost:8000", "model": "my-model"})
    result = await provider.complete(MESSAGES)

    assert isinstance(result, CompletionResponse)
    assert result.content == "Hello from OpenAI!"
    assert result.provider == "vllm"
    assert result.usage["input_tokens"] == 15


# ===================================================================
# llama.cpp
# ===================================================================


@respx.mock
async def test_llamacpp_complete():
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = LlamaCppProvider({"base_url": "http://localhost:8080", "model": "local-llama"})
    result = await provider.complete(MESSAGES)

    assert isinstance(result, CompletionResponse)
    assert result.content == "Hello from OpenAI!"
    assert result.provider == "llamacpp"
    assert result.cost == 0.0


# ===================================================================
# HuggingFace TGI
# ===================================================================


@respx.mock
async def test_hf_tgi_complete():
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
    )

    provider = HFTGIProvider({"base_url": "http://localhost:8080", "model": "tgi-model"})
    result = await provider.complete(MESSAGES)

    assert isinstance(result, CompletionResponse)
    assert result.content == "Hello from OpenAI!"
    assert result.provider == "hf_tgi"
    assert result.cost == 0.0


# ===================================================================
# ONNX
# ===================================================================


def test_onnx_provider_init():
    provider = ONNXProvider({"model_path": "/tmp/model.onnx", "model": "my-onnx"})
    assert provider.model_path == "/tmp/model.onnx"
    assert provider.model_name == "my-onnx"
    assert provider.supports_tools() is False
    assert provider.supports_vision() is False
    assert provider.estimated_cost("any", 100, 100) == 0.0
    assert provider._session is None


# ===================================================================
# _provider_label + Kimi pricing (Task 1)
# ===================================================================


def test_provider_label_maps_by_model_prefix():
    assert _provider_label("kimi-k2.5") == "kimi"
    assert _provider_label("kimi-k2.6") == "kimi"
    assert _provider_label("moonshot-v1-8k") == "kimi"
    assert _provider_label("claude-3-5-sonnet") == "anthropic"
    assert _provider_label("gpt-4o") == "openai"
    assert _provider_label("o3-mini") == "openai"
    assert _provider_label("mistral-large") == "openai_compat"


def test_estimated_cost_kimi_nonzero():
    provider = OpenAICompatProvider({"model": "kimi-k2.5", "api_key": "sk-test"})
    # 1000 in + 1000 out → 0.0006 + 0.0025
    assert provider.estimated_cost("kimi-k2.5", 1000, 1000) == pytest.approx(0.0031)
    assert provider.estimated_cost("kimi-k2.6", 1000, 1000) == pytest.approx(0.00495)


@respx.mock
async def test_openai_compat_kimi_reports_kimi_provider_and_cost():
    respx.post("https://api.moonshot.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
    )
    provider = OpenAICompatProvider(
        {"base_url": "https://api.moonshot.ai/v1", "model": "kimi-k2.5", "api_key": "sk-test"}
    )
    result = await provider.complete(MESSAGES)
    assert result.provider == "kimi"
    assert result.cost > 0


# ===================================================================
# Cache pricing + cache_read_input_tokens (Task 1)
# ===================================================================


def test_estimated_cost_applies_cache_discount():
    provider = OpenAICompatProvider({"model": "kimi-k2.5", "api_key": "sk-test"})
    # 2000 input, 1000 cacheados, 500 output:
    #   uncached 1000 * 0.0006/1000 = 0.0006
    #   cached   1000 * 0.0001/1000 = 0.0001
    #   output    500 * 0.0025/1000 = 0.00125
    assert provider.estimated_cost("kimi-k2.5", 2000, 500, 1000) == pytest.approx(0.00195)
    # sin cache = comportamiento previo
    assert provider.estimated_cost("kimi-k2.5", 2000, 500, 0) == pytest.approx(
        (2000 / 1000) * 0.0006 + (500 / 1000) * 0.0025
    )


def test_estimated_cost_clamps_cached_to_input():
    provider = OpenAICompatProvider({"model": "kimi-k2.5", "api_key": "sk-test"})
    # cached > input → se clampa a input; todo cacheado
    assert provider.estimated_cost("kimi-k2.5", 1000, 0, 5000) == pytest.approx(
        (1000 / 1000) * 0.0001
    )


def test_estimated_cost_no_cache_rate_no_discount():
    provider = OpenAICompatProvider({"model": "gpt-4o", "api_key": "sk-test"})
    # gpt-4o no está en CACHE_INPUT_PRICING → la porción "cacheada" se cobra a tarifa normal
    assert provider.estimated_cost("gpt-4o", 1000, 0, 500) == pytest.approx((1000 / 1000) * 0.0025)


@respx.mock
async def test_complete_exposes_cache_read_input_tokens():
    body = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 2000, "completion_tokens": 500, "cached_tokens": 1000},
    }
    respx.post("https://api.moonshot.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=body)
    )
    provider = OpenAICompatProvider(
        {"base_url": "https://api.moonshot.ai/v1", "model": "kimi-k2.5", "api_key": "sk-test"}
    )
    result = await provider.complete(MESSAGES)
    assert result.usage["cache_read_input_tokens"] == 1000
    assert result.usage["input_tokens"] == 2000
    assert result.cost == pytest.approx(0.00195)


def test_cache_input_pricing_has_kimi():
    assert CACHE_INPUT_PRICING["kimi-k2.5"] == 0.0001
    assert CACHE_INPUT_PRICING["kimi-k2.6"] == 0.00016
