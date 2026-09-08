"""OpenAI-compatible provider adapter for the Astromesh Agent Runtime."""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from astromesh.errors import ModelProviderError

from .base import CompletionChunk, CompletionResponse, read_cached_tokens

# Pricing per 1 000 tokens (input, output) in USD
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4o-mini": (0.000150, 0.000600),
    "gpt-4-turbo": (0.0100, 0.0300),
    "gpt-4": (0.0300, 0.0600),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    # Moonshot / Kimi (cache-miss), from the vendor's published tables, read
    # 2026-09-08: platform.kimi.ai/docs/pricing/chat-{k26,k27-code,k3}. Divide the
    # per-1M prices there by 1000. `kimi-k2.6` already matched those three numbers
    # before this table listed a source, which is what makes the rest credible.
    #
    # `kimi-k2.5` is RETIRED — Moonshot answers 404 for it since 2026-09-08. The row
    # stays because removing a price rewrites what a past run cost, and nothing can
    # call the model any more anyway.
    #
    # The account balance is NOT a way to confirm these: /v1/users/me/balance settles
    # in arrears (measured 2026-09-08 — two paid calls, balance unchanged 12s later),
    # so a before/after read shows zero and proves nothing.
    "kimi-k2.5": (0.0006, 0.0025),
    "kimi-k2.6": (0.00095, 0.0040),
    "kimi-k2.7-code": (0.00095, 0.0040),
    "kimi-k2.7-code-highspeed": (0.0019, 0.0080),
    "kimi-k3": (0.0030, 0.0150),
}

# Cached-input rates (Moonshot/Kimi context cache), same source and same date.
# A model absent here is charged the cache-MISS rate on its cached tokens, which
# overstates the cost rather than understating it — see estimated_cost().
CACHE_INPUT_PRICING: dict[str, float] = {
    "kimi-k2.5": 0.0001,
    "kimi-k2.6": 0.00016,
    "kimi-k2.7-code": 0.00019,
    "kimi-k2.7-code-highspeed": 0.00038,
    "kimi-k3": 0.00030,
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


# Cuánto del cuerpo del proveedor entra en el mensaje de error. Suficiente para
# el JSON de error de cualquier API compatible; corto para que un ingress que
# devuelve una página de HTML no llene el log ni el `lastError` de quien consume.
_TOPE_CUERPO_ERROR = 800


async def _fallar_si_es_error(resp: httpx.Response, model: str, base_url: str) -> None:
    """Convierte un status de error en un `ModelProviderError` que DICE qué pasó.

    Reemplaza a `resp.raise_for_status()`, que descarta el cuerpo: httpx sólo
    deja "Client error '400 Bad Request' for url ...", y quien opera se queda
    sin lo único que sirve. Las APIs compatibles con OpenAI mandan el motivo
    exacto en el cuerpo —qué campo del payload está mal, qué límite se pasó— y
    eso es lo que hay que propagar.

    Sube por `ModelRouter.route`, que hace `str(last_error)` para armar el error
    final (`errors.py:83`), así que el motivo llega hasta quien invocó al agente.

    Del cuerpo del proveedor, y nunca del request: el payload lleva el prompt y
    los headers la credencial. Acá no se toca ninguno de los dos.
    """
    if not resp.is_error:
        return

    # En el camino de streaming el cuerpo todavía no se leyó. Sobre una
    # respuesta ya leída `aread()` devuelve lo cacheado, así que sirve para los
    # dos usos sin ramificar.
    try:
        await resp.aread()
        cuerpo = " ".join(resp.text.split())[:_TOPE_CUERPO_ERROR]
    except Exception:  # noqa: BLE001  (un cuerpo ilegible no puede tapar el status)
        cuerpo = ""

    raise ModelProviderError(
        f"Provider returned {resp.status_code} for model {model!r}: "
        f"{cuerpo or '(empty response body)'}",
        hint=(
            f"The message above is verbatim from the provider at {base_url}. "
            "Fix what it names — a rejected request is not a transport failure "
            "and retrying will reproduce it."
        ),
        code="model_provider_http_error",
    )


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
        self.parameters: dict = config.get("parameters", {}) or {}

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
        # Configured parameters first, per-call kwargs win — same precedence as
        # LiteLLMProvider's {**self.parameters, **kwargs}.
        payload.update({**self.parameters, **kwargs})

        start = time.perf_counter()
        resp = await client.post("/chat/completions", json=payload)
        latency_ms = (time.perf_counter() - start) * 1000
        await _fallar_si_es_error(resp, model, self.base_url)
        data = resp.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        usage_data = data.get("usage", {})
        input_tokens = usage_data.get("prompt_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0)
        cached_tokens = read_cached_tokens(usage_data)
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
        payload.update({**self.parameters, **kwargs})

        # TODO: if a streaming consumer ever needs cache tokens, the streamed usage
        # must also carry cache_read_input_tokens (from the final [DONE] chunk) like complete() does.
        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            await _fallar_si_es_error(resp, model, self.base_url)
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
        except Exception:  # noqa: BLE001  (cualquier fallo del sondeo significa 'no sano')
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
