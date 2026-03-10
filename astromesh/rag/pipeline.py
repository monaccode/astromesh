from __future__ import annotations

from dataclasses import dataclass, field

from astromesh.rag.chunking.base import ChunkingStrategy
from astromesh.rag.embeddings.base import EmbeddingProvider
from astromesh.rag.reranking.base import Reranker
from astromesh.rag.stores.base import VectorStore


@dataclass
class RAGResult:
    chunks: list[dict] = field(default_factory=list)
    query: str = ""
    metadata: dict = field(default_factory=dict)


class RAGPipeline:
    def __init__(
        self,
        chunker: ChunkingStrategy | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        reranker: Reranker | None = None,
    ):
        self._chunker = chunker
        self._embedder = embedding_provider
        self._store = vector_store
        self._reranker = reranker

    async def ingest(self, document: str, metadata: dict, doc_id_prefix: str = "doc") -> int:
        chunks = (
            self._chunker.chunk(document, metadata)
            if self._chunker
            else [{"content": document, "metadata": metadata}]
        )
        for i, chunk in enumerate(chunks):
            doc_id = f"{doc_id_prefix}_{i}"
            embedding = await self._embedder.embed(chunk["content"]) if self._embedder else []
            await self._store.upsert(doc_id, embedding, chunk["content"], chunk["metadata"])
        return len(chunks)

    async def query(self, query: str, top_k: int = 5) -> RAGResult:
        query_embedding = await self._embedder.embed(query) if self._embedder else []
        results = await self._store.search(query_embedding, top_k=top_k * 2) if self._store else []
        if self._reranker and results:
            results = await self._reranker.rerank(query, results, top_k=top_k)
        else:
            results = results[:top_k]
        return RAGResult(chunks=results, query=query)
