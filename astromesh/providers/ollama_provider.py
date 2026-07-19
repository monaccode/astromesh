"""Ollama provider adapter for the Astromesh Agent Runtime."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

import httpx

from .base import CompletionChunk, CompletionResponse

logger = logging.getLogger(__name__)

# Ollama's native /api/chat takes sampling parameters in a nested `options`
# object; anything left at the top level is accepted and ignored. The agent
# schema spells these keys the OpenAI way, so one of them needs translating.
# Names verified against the ModelOptions schema at docs.ollama.com/api/chat.
_OPTION_ALIASES = {"max_tokens": "num_predict"}
_KNOWN_OPTIONS = frozenset(
    {"seed", "temperature", "top_k", "top_p", "min_p", "stop", "num_ctx", "num_predict"}
)


def _split_options(params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a flat param dict into (ollama `options`, top-level fields).

    Keys that name a sampling option go into `options` under ollama's own
    spelling; everything else (format, keep_alive, think, ...) stays top-level.
    """
    options: dict[str, Any] = {}
    top_level: dict[str, Any] = {}
    for key, value in params.items():
        name = _OPTION_ALIASES.get(key, key)
        if name in _KNOWN_OPTIONS:
            options[name] = value
        else:
            top_level[key] = value
    return options, top_level


class OllamaProvider:
    """Provider adapter that talks to a local Ollama instance."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.base_url: str = config.get("base_url", "http://localhost:11434")
        self.model: str = config.get("model", "llama3")
        self.timeout: float = config.get("timeout", 120.0)
        self.parameters: dict = config.get("parameters", {}) or {}
        self._client: httpx.AsyncClient | None = None

        # presence_penalty / frequency_penalty exist on ollama's OpenAI-compat
        # surface (/v1) but not in the native ModelOptions schema, so they would
        # ride along and do nothing. Say so once instead of failing silently —
        # dropping a declared parameter without a word is the bug this fixes.
        unsupported = [
            k for k in self.parameters if _OPTION_ALIASES.get(k, k) not in _KNOWN_OPTIONS
        ]
        if unsupported:
            logger.warning(
                "ollama model %r: parameter(s) %s are not in ollama's native ModelOptions "
                "and will be ignored by the server; they are sent verbatim at the top level",
                self.model,
                ", ".join(sorted(unsupported)),
            )

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

        # Configured parameters first, per-call kwargs win — same precedence as
        # the other providers' {**self.parameters, **kwargs}.
        options, top_level = _split_options({**self.parameters, **kwargs})
        payload.update(top_level)
        if options:
            payload["options"] = options

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
        options, top_level = _split_options({**self.parameters, **kwargs})
        payload.update(top_level)
        if options:
            payload["options"] = options

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
