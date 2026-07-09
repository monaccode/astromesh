"""Tests for source-aware candidate building and per-role routers."""

from __future__ import annotations

from astromesh.providers.litellm_provider import LiteLLMProvider
from astromesh.providers.ollama_provider import OllamaProvider
from astromesh.providers.openai_compat import OpenAICompatProvider
from astromesh.runtime.engine import build_candidate_provider


def test_builds_ollama_from_source():
    prov = build_candidate_provider({"source": "ollama", "model": "llama3.1:8b"})
    assert isinstance(prov, OllamaProvider)


def test_builds_litellm_from_source(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider(
        {
            "source": "litellm",
            "model": "anthropic/claude-opus-4-8",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
    )
    assert isinstance(prov, LiteLLMProvider)


def test_infers_litellm_from_prefixed_model(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider({"model": "gemini/gemini-2.0-pro"})
    assert isinstance(prov, LiteLLMProvider)


def test_infers_openai_compat_without_prefix():
    prov = build_candidate_provider({"model": "gpt-4o-mini"})
    assert isinstance(prov, OpenAICompatProvider)


def test_legacy_provider_key_maps_to_source():
    prov = build_candidate_provider({"provider": "ollama", "model": "llama3"})
    assert isinstance(prov, OllamaProvider)


def test_unknown_source_returns_none():
    assert build_candidate_provider({"source": "does-not-exist", "model": "x"}) is None


def test_litellm_missing_dependency_skips_candidate(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    def boom():
        raise ImportError("litellm not installed")

    monkeypatch.setattr(_llm, "_import_litellm", boom)
    assert (
        build_candidate_provider({"source": "litellm", "model": "anthropic/claude-opus-4-8"})
        is None
    )
