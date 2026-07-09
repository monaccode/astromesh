"""LiteLLM-backed provider adapter: unified access to 100+ cloud LLM providers.

`litellm` is an optional dependency; the import is lazy so the runtime works
without it. Requesting a `source: litellm` candidate without the package
installed surfaces an ImportError, which the engine catches and turns into a
skipped candidate (see runtime.engine).
"""

from __future__ import annotations

import os
import time
from typing import Any, AsyncIterator

from .base import CompletionChunk, CompletionResponse
from .openai_compat import _normalize_tool_calls


def _import_litellm():
    """Import litellm lazily. Isolated for monkeypatching in tests."""
    import litellm  # noqa: PLC0415

    return litellm


def _litellm_provider_label(model: str) -> str:
    """Derive the provider label from a LiteLLM model string (prefix before '/')."""
    return model.split("/", 1)[0] if "/" in (model or "") else "litellm"


class LiteLLMProvider:
    """Provider adapter that routes completions through LiteLLM."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.model: str = config.get("model", "gpt-4o")
        self.timeout: float = float(config.get("timeout", 120.0))
        self.parameters: dict = config.get("parameters", {}) or {}

        api_key = config.get("api_key")
        env_var = config.get("api_key_env")
        if not api_key and env_var:
            api_key = os.environ.get(env_var, "")
        self.api_key: str | None = api_key or None

    def _litellm(self):
        return _import_litellm()

    async def complete(self, messages: list[dict], **kwargs: Any) -> CompletionResponse:
        litellm = self._litellm()
        model = kwargs.pop("model", self.model)
        params = {**self.parameters, **kwargs}
        if self.api_key:
            params.setdefault("api_key", self.api_key)

        start = time.perf_counter()
        resp = await litellm.acompletion(
            model=model, messages=messages, timeout=self.timeout, **params
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        data = resp if isinstance(resp, dict) else resp.model_dump()
        message = data["choices"][0].get("message", {})
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cached = usage.get("cache_read_input_tokens", 0)

        try:
            cost = float(litellm.completion_cost(completion_response=resp))
        except Exception:  # noqa: BLE001 — pricing is best-effort
            cost = 0.0

        return CompletionResponse(
            content=message.get("content", "") or "",
            model=model,
            provider=_litellm_provider_label(model),
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cached,
            },
            latency_ms=latency_ms,
            cost=cost,
            tool_calls=_normalize_tool_calls(message.get("tool_calls")),
            reasoning_content=message.get("reasoning_content"),
        )

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[CompletionChunk]:
        litellm = self._litellm()
        model = kwargs.pop("model", self.model)
        params = {**self.parameters, **kwargs}
        if self.api_key:
            params.setdefault("api_key", self.api_key)
        response = await litellm.acompletion(
            model=model, messages=messages, stream=True, timeout=self.timeout, **params
        )
        async for chunk in response:
            data = chunk if isinstance(chunk, dict) else chunk.model_dump()
            delta = data["choices"][0].get("delta", {})
            yield CompletionChunk(
                content=delta.get("content", "") or "",
                model=model,
                provider=_litellm_provider_label(model),
                done=False,
            )
        yield CompletionChunk(
            content="", model=model, provider=_litellm_provider_label(model), done=True
        )

    async def health_check(self) -> bool:
        try:
            self._litellm()
            return True
        except Exception:  # noqa: BLE001
            return False

    def supports_tools(self) -> bool:
        try:
            return bool(self._litellm().supports_function_calling(self.model))
        except Exception:  # noqa: BLE001
            return True

    def supports_vision(self) -> bool:
        try:
            return bool(self._litellm().supports_vision(self.model))
        except Exception:  # noqa: BLE001
            return False

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        try:
            litellm = self._litellm()
            prompt, completion = litellm.cost_per_token(
                model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens
            )
            return float(prompt) + float(completion)
        except Exception:  # noqa: BLE001
            return 0.0
