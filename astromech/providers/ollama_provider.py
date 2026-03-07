"""Ollama provider adapter for the Astromech Agent Runtime."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from .base import CompletionChunk, CompletionResponse


class OllamaProvider:
    """Provider adapter that talks to a local Ollama instance."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.base_url: str = config.get("base_url", "http://localhost:11434")
        self.model: str = config.get("model", "llama3")
        self.timeout: float = config.get("timeout", 120.0)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Tool conversion helper
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Convert a generic tool list into Ollama's expected format."""
        converted: list[dict] = []
        for tool in tools:
            if "function" in tool:
                converted.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["function"]["name"],
                            "description": tool["function"].get("description", ""),
                            "parameters": tool["function"].get("parameters", {}),
                        },
                    }
                )
            else:
                converted.append(tool)
        return converted

    # ------------------------------------------------------------------
    # Multimodal conversion helper
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_multimodal_messages(messages: list[dict]) -> list[dict]:
        """Convert OpenAI-style multimodal messages to Ollama format.

        Ollama expects images as base64 strings in a top-level ``images``
        list on the message, rather than inline ``image_url`` content parts.
        """
        converted: list[dict] = []
        for msg in messages:
            content = msg.get("content")
            if not isinstance(content, list):
                converted.append(msg)
                continue
            text_parts: list[str] = []
            images: list[str] = []
            for part in content:
                if part.get("type") == "text":
                    text_parts.append(part["text"])
                elif part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    # Strip data URI prefix to get raw base64.
                    if url.startswith("data:"):
                        url = url.split(",", 1)[-1]
                    images.append(url)
            new_msg = {**msg, "content": " ".join(text_parts)}
            if images:
                new_msg["images"] = images
            converted.append(new_msg)
        return converted

    # ------------------------------------------------------------------
    # ProviderProtocol implementation
    # ------------------------------------------------------------------

    async def complete(self, messages: list[dict], **kwargs: Any) -> CompletionResponse:
        client = await self._get_client()
        model = kwargs.pop("model", self.model)
        messages = self._convert_multimodal_messages(messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = self._convert_tools(tools)

        payload.update(kwargs)

        start = time.perf_counter()
        resp = await client.post("/api/chat", json=payload)
        latency_ms = (time.perf_counter() - start) * 1000
        resp.raise_for_status()
        data = resp.json()

        content = data.get("message", {}).get("content", "")
        tool_calls = data.get("message", {}).get("tool_calls", [])
        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        return CompletionResponse(
            content=content,
            model=model,
            provider="ollama",
            usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            latency_ms=latency_ms,
            cost=0.0,
            tool_calls=tool_calls,
        )

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[CompletionChunk]:
        client = await self._get_client()
        model = kwargs.pop("model", self.model)
        messages = self._convert_multimodal_messages(messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        payload.update(kwargs)

        async with client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk_data = json.loads(line)
                done = chunk_data.get("done", False)
                usage = None
                if done:
                    usage = {
                        "input_tokens": chunk_data.get("prompt_eval_count", 0),
                        "output_tokens": chunk_data.get("eval_count", 0),
                    }
                yield CompletionChunk(
                    content=chunk_data.get("message", {}).get("content", ""),
                    model=model,
                    provider="ollama",
                    done=done,
                    usage=usage,
                )

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        model_lower = self.model.lower()
        return "llava" in model_lower or "vision" in model_lower

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0
