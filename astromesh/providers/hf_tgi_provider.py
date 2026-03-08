"""HuggingFace Text Generation Inference provider adapter for the Astromesh Agent Runtime."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx

from .base import CompletionChunk, CompletionResponse


class HFTGIProvider:
    """Provider adapter for HuggingFace TGI (OpenAI-compatible)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.base_url: str = config.get("base_url", "http://localhost:8080")
        self.model: str = config.get("model", "default")
        self.timeout: float = config.get("timeout", 120.0)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

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
        resp = await client.post("/v1/chat/completions", json=payload)
        latency_ms = (time.perf_counter() - start) * 1000
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        usage_data = data.get("usage", {})
        input_tokens = usage_data.get("prompt_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0)

        return CompletionResponse(
            content=message.get("content", "") or "",
            model=model,
            provider="hf_tgi",
            usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            latency_ms=latency_ms,
            cost=0.0,
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

        async with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[len("data: "):]
                if raw.strip() == "[DONE]":
                    yield CompletionChunk(
                        content="", model=model, provider="hf_tgi", done=True
                    )
                    break
                import json

                chunk_data = json.loads(raw)
                delta = chunk_data["choices"][0].get("delta", {})
                yield CompletionChunk(
                    content=delta.get("content", "") or "",
                    model=model,
                    provider="hf_tgi",
                    done=False,
                )

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0
