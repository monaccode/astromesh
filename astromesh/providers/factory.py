"""Factory for creating provider instances dynamically (used by BYOK flow)."""


def create_provider(provider_name: str, api_key: str):
    """Create a provider instance by name with the given API key."""
    if provider_name in ("openai", "anthropic", "vllm", "hf"):
        from astromesh.providers.openai_compat import OpenAICompatProvider

        base_urls = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
        }
        return OpenAICompatProvider(
            config={
                "name": provider_name,
                "base_url": base_urls.get(provider_name, "https://api.openai.com/v1"),
                "api_key": api_key,
            }
        )
    elif provider_name == "ollama":
        from astromesh.providers.ollama_provider import OllamaProvider

        # OllamaProvider does not use an API key; pass through for future use.
        return OllamaProvider(config={})
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
