import os
import pytest
from astromesh_adk.providers import parse_model_string, resolve_provider, PROVIDER_REGISTRY


def test_parse_model_string_openai():
    provider, model = parse_model_string("openai/gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"


def test_parse_model_string_with_org():
    provider, model = parse_model_string("anthropic/claude-sonnet-4-20250514")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-20250514"


def test_parse_model_string_ollama():
    provider, model = parse_model_string("ollama/llama3")
    assert provider == "ollama"
    assert model == "llama3"


def test_parse_model_string_no_slash():
    """Without slash, assume openai provider."""
    provider, model = parse_model_string("gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"


def test_provider_registry_has_all_providers():
    expected = {"openai", "anthropic", "ollama", "vllm", "llamacpp", "hf"}
    assert expected.issubset(set(PROVIDER_REGISTRY.keys()))


def test_provider_registry_env_vars():
    assert PROVIDER_REGISTRY["openai"]["env_var"] == "OPENAI_API_KEY"
    assert PROVIDER_REGISTRY["anthropic"]["env_var"] == "ANTHROPIC_API_KEY"
    assert PROVIDER_REGISTRY["ollama"]["env_var"] is None


def test_resolve_provider_ollama():
    """Ollama doesn't need an API key."""
    provider = resolve_provider("ollama", "llama3", model_config=None)
    assert provider is not None


def test_resolve_provider_with_config():
    provider = resolve_provider(
        "openai",
        "gpt-4o",
        model_config={
            "endpoint": "https://my-proxy.com/v1",
            "api_key_env": "MY_KEY",
            "temperature": 0.7,
        },
    )
    assert provider is not None
