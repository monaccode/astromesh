"""OpenAI-compatible provider adapter for the Astromesh Agent Runtime."""

from __future__ import annotations

import os
import time
from typing import Any, AsyncIterator

import httpx

from .base import CompletionChunk, CompletionResponse

# Pricing per 1 000 tokens (input, output) in USD
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4o-mini": (0.000150, 0.000600),
    "gpt-4-turbo": (0.0100, 0.0300),
    "gpt-4": (0.0300, 0.0600),
    "gpt-3.5-turbo": (0.0005, 0.0015),
}


class OpenAICompatProvider:
    """Provider adapter for any OpenAI-compatible API (OpenAI, Azure, etc.)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.base_url: str = config.get("base_url", "https://api.openai.com/v1")
        self.model: str = config.get("model", "gpt-4o")
        self.timeout: float = config.get("timeout", 120.0)

        api_key = config.get("api_key")
        if not api_key:
            env_var = config.get("api_key_env", "OPENAI_API_KEY")
            api_key = os.environ.get(env_var, "")
        self.api_key: str = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
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
        cost = self.estimated_cost(model, input_tokens, output_tokens)

        return CompletionResponse(
            content=message.get("content", "") or "",
            model=model,
            provider="openai_compat",
            usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            latency_ms=latency_ms,
            cost=cost,
            tool_calls=message.get("tool_calls", []),
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
                import json

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

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = PRICING.get(model)
        if pricing is None:
            return 0.0
        input_price, output_price = pricing
        return (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price
