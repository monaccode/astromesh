from __future__ import annotations

import httpx

from astromech.rag.embeddings.base import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using Ollama's REST API."""

    def __init__(
        self,
        endpoint: str = "http://ollama:11434",
        model: str = "nomic-embed-text",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.endpoint}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        async with httpx.AsyncClient() as client:
            for text in texts:
                response = await client.post(
                    f"{self.endpoint}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                results.append(response.json()["embedding"])
        return results
