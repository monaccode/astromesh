"""OpenAI-compatible provider adapter for the Astromesh Agent Runtime."""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx

from astromesh.errors import ModelProviderError

from .base import CompletionChunk, CompletionResponse

# Pricing per 1 000 tokens (input, output) in USD
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4o-mini": (0.000150, 0.000600),
    "gpt-4-turbo": (0.0100, 0.0300),
    "gpt-4": (0.0300, 0.0600),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    # Moonshot / Kimi (cache-miss). Confirm against the account before publishing.
    "kimi-k2.5": (0.0006, 0.0025),
    "kimi-k2.6": (0.00095, 0.0040),
}

# Cached-input pricing per 1 000 tokens in USD (Moonshot/Kimi context cache).
CACHE_INPUT_PRICING: dict[str, float] = {
    "kimi-k2.5": 0.0001,
    "kimi-k2.6": 0.00016,
}


def _provider_label(model: str) -> str:
    """Etiqueta del proveedor derivada del nombre del modelo. El adapter
    OpenAI-compat sirve a OpenAI, Anthropic y Moonshot/Kimi con la misma clase y
    no recibe un identificador de proveedor, así que se deriva del modelo."""
    m = (model or "").lower()
    if m.startswith(("kimi", "moonshot")):
        return "kimi"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    return "openai_compat"


def _normalize_tool_calls(raw: list[dict] | None) -> list[dict]:
    """Normalize OpenAI nested tool-calls to astromesh's flat canonical shape.

    OpenAI/Anthropic-compat APIs return tool calls as
    {"id", "type", "function": {"name", "arguments": "<json string>"}}.
    astromesh's orchestration patterns and clarus's structured-output consumer
    expect {"id", "name", "arguments": <dict>}.
    """
    normalized: list[dict] = []
    for tc in raw or []:
        fn = tc.get("function", {})
        args = fn.get("arguments", tc.get("arguments", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        normalized.append(
            {
                "id": tc.get("id", ""),
                "name": fn.get("name") or tc.get("name", ""),
                "arguments": args,
            }
        )
    return normalized


class OpenAICompatProvider:
    """Provider adapter for any OpenAI-compatible API (OpenAI, Azure, etc.)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.base_url: str = config.get("base_url", "https://api.openai.com/v1")
        self.model: str = config.get("model", "gpt-4o")
        self.timeout: float = config.get("timeout", 120.0)

        env_var = config.get("api_key_env", "OPENAI_API_KEY")
        api_key = config.get("api_key")
        if not api_key:
            api_key = os.environ.get(env_var, "")
        self.api_key: str = api_key
        self.api_key_env: str = env_var
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if not self.api_key:
            raise ModelProviderError(
                f"No API key for OpenAI-compatible provider (model '{self.model}').",
                hint=(
                    f"Set the {self.api_key_env} environment variable, or pass "
                    f"'api_key' in the provider config. Endpoint: {self.base_url}"
                ),
                code="model_missing_api_key",
            )
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    # ------------------------------------------------------------------
    # ProviderProtocol implementation
    # ------------------------------------------------------------------

    async def complete(self, messages: list[dict], **kwargs: Any) -> CompletionResponse:
        client = await self._get_client()
        model = kwargs.pop("model", self.model)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        payload.update(kwargs)

        start = time.perf_counter()
        resp = await client.post("/chat/completions", json=payload)
        latency_ms = (time.perf_counter() - start) * 1000
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        usage_data = data.get("usage", {})
        input_tokens = usage_data.get("prompt_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0)
        cached_tokens = usage_data.get("cached_tokens", 0)
        cost = self.estimated_cost(model, input_tokens, output_tokens, cached_tokens)

        return CompletionResponse(
            content=message.get("content", "") or "",
            model=model,
            provider=_provider_label(model),
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cached_tokens,
            },
            latency_ms=latency_ms,
            cost=cost,
            tool_calls=_normalize_tool_calls(message.get("tool_calls")),
            reasoning_content=message.get("reasoning_content"),
        )

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[CompletionChunk]:
        client = await self._get_client()
        model = kwargs.pop("model", self.model)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        payload.update(kwargs)

        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[len("data: ") :]
                if raw.strip() == "[DONE]":
                    yield CompletionChunk(
                        content="", model=model, provider="openai_compat", done=True
                    )
                    break
                chunk_data = json.loads(raw)
                delta = chunk_data["choices"][0].get("delta", {})
                yield CompletionChunk(
                    content=delta.get("content", "") or "",
                    model=model,
                    provider="openai_compat",
                    done=False,
                )

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        model_lower = self.model.lower()
        return "vision" in model_lower or "gpt-4o" in model_lower

    def estimated_cost(
        self, model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
    ) -> float:
        pricing = PRICING.get(model)
        if pricing is None:
            return 0.0
        input_price, output_price = pricing
        cached = max(0, min(cached_tokens, input_tokens))  # cached ⊆ input
        cache_price = CACHE_INPUT_PRICING.get(model, input_price)  # sin tarifa → sin descuento
        return (
            ((input_tokens - cached) / 1000) * input_price
            + (cached / 1000) * cache_price
            + (output_tokens / 1000) * output_price
        )
