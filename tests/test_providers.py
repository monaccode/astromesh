"""Tests for all 6 Astromech provider adapters."""

from __future__ import annotations

import httpx
import pytest
import respx

from astromech.providers.base import CompletionResponse
from astromech.providers.hf_tgi_provider import HFTGIProvider
from astromech.providers.llamacpp_provider import LlamaCppProvider
from astromech.providers.ollama_provider import OllamaProvider
from astromech.providers.onnx_provider import ONNXProvider
from astromech.providers.openai_compat import OpenAICompatProvider
from astromech.providers.vllm_provider import VLLMProvider

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
    assert result.provider == "openai_compat"
    assert result.usage["input_tokens"] == 15
    assert result.usage["output_tokens"] == 25
    assert result.cost > 0


def test_openai_compat_supports_tools():
    provider = OpenAICompatProvider({"model": "gpt-4o", "api_key": "sk-test"})
    assert provider.supports_tools() is True


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
