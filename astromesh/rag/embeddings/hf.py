from __future__ import annotations

import httpx

from astromesh.rag.embeddings.base import EmbeddingProvider

_DEFAULT_HF_API = "https://api-inference.huggingface.co/pipeline/feature-extraction"


class HFEmbeddingProvider(EmbeddingProvider):
    """Hugging Face Inference API / TEI embedding provider."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        endpoint: str | None = None,
        api_key: str | None = None,
    ):
        self.model_name = model_name
        self.endpoint = endpoint or f"{_DEFAULT_HF_API}/{model_name}"
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                json={"inputs": text},
                headers=self._headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            # HF API may return nested list or flat list
            if isinstance(data, list) and data and isinstance(data[0], list):
                return data[0]
            return data

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                json={"inputs": texts},
                headers=self._headers(),
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()
