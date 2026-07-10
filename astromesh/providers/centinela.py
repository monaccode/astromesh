"""Centinela provider — typed classifier capability + routable chat shim.

Centinela classifiers/extractors are served on HF Inference Endpoints running TGI
(OpenAI-compatible `/v1/chat/completions`). This module wraps that endpoint.

Typed facade: `classify()` returns a Pydantic `SentimentResult`. It applies the SAME
`nebula.validation.constrain_label` used by the foundry eval-gate, so a served model can
never emit a label outside the closed contract set. Expose it to an ADK agent by wrapping
`classify` in an `@tool` from the agent side (kept out of core to avoid a core->adk cycle):

    from astromesh_adk import tool
    from pydantic import BaseModel

    class TextInput(BaseModel):
        text: str

    @tool("Clasifica sentimiento financiero")
    async def centinela_sentiment(inp: TextInput) -> SentimentResult:
        return await client.classify(inp.text)

Routable facade: `CentinelaProvider` implements ProviderProtocol so the model_router can
select Centinela (estimated_cost approx 0 -> preferred under cost_optimized).
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx
from pydantic import BaseModel

from nebula.validation import constrain_label

from .base import CompletionChunk, CompletionResponse


class SentimentResult(BaseModel):
    """Typed classifier output. `score` is None under generative (TGI) serving."""

    label: str | None
    valid: bool
    raw: str
    score: float | None = None


def _build_system_prompt(labels: list[str]) -> str:
    joined = ", ".join(labels)
    return (
        "Clasificá el texto. Respondé únicamente con una sola de estas etiquetas, "
        f"sin explicación ni puntuación: {joined}."
    )


class _CentinelaEndpointClient:
    """httpx core over a Centinela HF Inference Endpoint (TGI, OpenAI-compatible)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.endpoint: str = (config.get("endpoint") or "http://localhost:8080").rstrip("/")
        self.model: str = config.get("model", "centinela")
        self.timeout: float = float(config.get("timeout", 30.0))
        contract = config.get("contract") or {}
        self.labels: list[str] = list(contract.get("labels", []))
        self.invalid_policy: str = config.get("invalid_policy", "mark")
        self.max_retries: int = int(config.get("max_retries", 1))
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.endpoint, timeout=self.timeout)
        return self._client

    async def _raw_label(self, text: str) -> str:
        client = await self._get_client()
        messages = [
            {"role": "system", "content": _build_system_prompt(self.labels)},
            {"role": "user", "content": text},
        ]
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": self.model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0].get("message", {}).get("content", "") or "").strip()

    async def classify(self, text: str) -> SentimentResult:
        attempts = self.max_retries if self.invalid_policy == "retry" else 1
        raw = ""
        label: str | None = None
        for _ in range(max(1, attempts)):
            raw = await self._raw_label(text)
            label = constrain_label(raw, self.labels)
            if label is not None:
                break
        return SentimentResult(label=label, valid=label is not None, raw=raw, score=None)

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False


class CentinelaProvider:
    """Routable ProviderProtocol shim over the Centinela typed capability.

    Structural implementation (does not inherit ProviderProtocol). `estimated_cost`
    reports ~0 so the model_router prefers Centinela under the cost_optimized strategy.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._client = _CentinelaEndpointClient(config)
        self.model = self._client.model

    async def complete(self, messages: list[dict], **kwargs: Any) -> CompletionResponse:
        model = kwargs.pop("model", self.model)
        text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                text = m.get("content", "") or ""
                break

        start = time.perf_counter()
        result = await self._client.classify(text)
        latency_ms = (time.perf_counter() - start) * 1000

        return CompletionResponse(
            content=result.label or "",
            model=model,
            provider="centinela",
            usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=latency_ms,
            cost=0.0,
            metadata={
                "label": result.label,
                "valid": result.valid,
                "raw": result.raw,
                "score": result.score,
            },
        )

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[CompletionChunk]:
        resp = await self.complete(messages, **kwargs)
        yield CompletionChunk(
            content=resp.content, model=resp.model, provider="centinela", done=True
        )

    async def health_check(self) -> bool:
        return await self._client.health_check()

    def supports_tools(self) -> bool:
        return False

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0
