from __future__ import annotations

import httpx

from astromesh.rag.reranking.base import Reranker

_COHERE_RERANK_URL = "https://api.cohere.ai/v1/rerank"


class CohereReranker(Reranker):
    """Reranker using Cohere's rerank API."""

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-english-v3.0",
    ):
        self.api_key = api_key
        self.model = model

    async def rerank(
        self, query: str, documents: list[dict], top_k: int = 5
    ) -> list[dict]:
        if not documents:
            return []

        doc_texts = [doc.get("content", "") for doc in documents]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                _COHERE_RERANK_URL,
                json={
                    "model": self.model,
                    "query": query,
                    "documents": doc_texts,
                    "top_n": top_k,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        results: list[dict] = []
        for item in data.get("results", []):
            idx = item["index"]
            results.append({
                **documents[idx],
                "rerank_score": item["relevance_score"],
            })

        return results
