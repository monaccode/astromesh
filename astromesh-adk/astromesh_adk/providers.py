"""Provider resolution from 'provider/model' strings."""

from __future__ import annotations

import os

from astromesh.providers.base import ProviderProtocol
from astromesh.providers.ollama_provider import OllamaProvider
from astromesh.providers.openai_compat import OpenAICompatProvider
from astromesh.providers.vllm_provider import VLLMProvider
from astromesh.providers.llamacpp_provider import LlamaCppProvider
from astromesh.providers.hf_tgi_provider import HFTGIProvider

# Maps provider prefix → {class, env_var, default_endpoint}
PROVIDER_REGISTRY: dict[str, dict] = {
    "openai": {
        "class": OpenAICompatProvider,
        "env_var": "OPENAI_API_KEY",
        "default_endpoint": "https://api.openai.com/v1",
    },
    "anthropic": {
        "class": OpenAICompatProvider,  # v1: uses OpenAI-compat endpoint
        "env_var": "ANTHROPIC_API_KEY",
        "default_endpoint": "https://api.anthropic.com/v1",
    },
    "ollama": {
        "class": OllamaProvider,
        "env_var": None,
        "default_endpoint": "http://localhost:11434",
    },
    "vllm": {
        "class": VLLMProvider,
        "env_var": None,
        "default_endpoint": "http://localhost:8000",
    },
    "llamacpp": {
        "class": LlamaCppProvider,
        "env_var": None,
        "default_endpoint": "http://localhost:8080",
    },
    "hf": {
        "class": HFTGIProvider,
        "env_var": "HF_TOKEN",
        "default_endpoint": None,
    },
}


def parse_model_string(model: str) -> tuple[str, str]:
    """Parse 'provider/model' into (provider_name, model_name).

    If no slash is present, defaults to 'openai' provider.
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
        return provider, model_name
    return "openai", model


def resolve_provider(
    provider_name: str,
    model_name: str,
    model_config: dict | None = None,
) -> ProviderProtocol:
    """Create a configured provider instance."""
    config = model_config or {}
    registry_entry = PROVIDER_REGISTRY.get(provider_name)
    if not registry_entry:
        raise ValueError(f"Unknown provider: {provider_name!r}. Available: {list(PROVIDER_REGISTRY)}")

    provider_cls = registry_entry["class"]
    env_var = config.get("api_key_env") or registry_entry["env_var"]
    endpoint = config.get("endpoint") or registry_entry["default_endpoint"]

    # Build provider config dict matching Astromesh constructors
    provider_config = {"model": model_name}
    if endpoint:
        provider_config["endpoint"] = endpoint
    if env_var:
        api_key = os.environ.get(env_var, "")
        if api_key:
            provider_config["api_key"] = api_key

    # Pass through model parameters
    for param in ("temperature", "top_p", "max_tokens"):
        if param in config:
            provider_config[param] = config[param]

    return provider_cls(provider_config)
