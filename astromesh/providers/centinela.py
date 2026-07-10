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

from typing import Any

import httpx
from pydantic import BaseModel

from nebula.validation import constrain_label


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
