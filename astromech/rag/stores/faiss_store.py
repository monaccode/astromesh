from __future__ import annotations

import numpy as np

from astromech.rag.stores.base import VectorStore


class FAISSStore(VectorStore):
    """In-memory vector store backed by FAISS."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions
        self._index = None
        self._docs: list[dict] = []
        self._id_map: dict[str, int] = {}

    def _get_index(self):
        if self._index is None:
            import faiss

            self._index = faiss.IndexFlatIP(self.dimensions)
        return self._index

    async def upsert(
        self, doc_id: str, embedding: list[float], content: str, metadata: dict
    ):
        index = self._get_index()
        vec = np.array([embedding], dtype=np.float32)

        # Normalize for cosine similarity via inner product
        norm = np.linalg.norm(vec, axis=1, keepdims=True)
        if norm > 0:
            vec = vec / norm

        if doc_id in self._id_map:
            # Replace existing — FAISS doesn't support in-place update for flat index,
            # so we mark the old entry and append a new one
            old_idx = self._id_map[doc_id]
            self._docs[old_idx] = None  # type: ignore[assignment]

        idx = index.ntotal
        index.add(vec)
        self._id_map[doc_id] = idx
        self._docs.append({
            "doc_id": doc_id,
            "content": content,
            "metadata": metadata,
        })

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:
        index = self._get_index()
        if index.ntotal == 0:
            return []

        vec = np.array([query_embedding], dtype=np.float32)
        norm = np.linalg.norm(vec, axis=1, keepdims=True)
        if norm > 0:
            vec = vec / norm

        # Search more than needed to account for deleted entries
        k = min(top_k * 3, index.ntotal)
        scores, indices = index.search(vec, k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._docs):
                continue
            doc = self._docs[idx]
            if doc is None:
                continue

            if filters:
                if not all(doc["metadata"].get(fk) == fv for fk, fv in filters.items()):
                    continue

            results.append({
                "doc_id": doc["doc_id"],
                "content": doc["content"],
                "metadata": doc["metadata"],
                "score": float(score),
            })
            if len(results) >= top_k:
                break

        return results

    async def delete(self, doc_id: str):
        if doc_id in self._id_map:
            idx = self._id_map.pop(doc_id)
            if idx < len(self._docs):
                self._docs[idx] = None  # type: ignore[assignment]
