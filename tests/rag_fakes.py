from astromesh.rag.embeddings.base import EmbeddingProvider
from astromesh.rag.stores.base import VectorStore


class FakeEmbedder(EmbeddingProvider):
    """Deterministic: vector length = min(len(text), 8), padded — no external service."""

    async def embed(self, text: str) -> list[float]:
        v = [float(len(text) % 7 + 1)] * 8
        return v

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class FakeStore(VectorStore):
    """In-memory store; search returns all docs (most-recent first), ignoring similarity."""

    def __init__(self):
        self._docs: list[dict] = []

    async def upsert(self, doc_id, embedding, content, metadata):
        self._docs.append({"content": content, "metadata": metadata, "score": 1.0})

    async def search(self, query_embedding, top_k=10, filters=None):
        return list(reversed(self._docs))[:top_k]

    async def delete(self, doc_id):
        self._docs = [d for d in self._docs if d.get("metadata", {}).get("id") != doc_id]
