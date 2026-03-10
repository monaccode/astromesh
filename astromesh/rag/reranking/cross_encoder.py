from __future__ import annotations

from astromesh.rag.reranking.base import Reranker


class CrossEncoderReranker(Reranker):
    """Reranker using a cross-encoder model from sentence-transformers."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    async def rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        if not documents:
            return []

        model = self._get_model()
        pairs = [[query, doc.get("content", "")] for doc in documents]
        scores = model.predict(pairs)

        scored_docs = []
        for doc, score in zip(documents, scores):
            scored_docs.append({**doc, "rerank_score": float(score)})

        scored_docs.sort(key=lambda d: d["rerank_score"], reverse=True)
        return scored_docs[:top_k]
