import os
from collections.abc import Callable

from astromesh.rag.chunking.base import ChunkingStrategy
from astromesh.rag.chunking.sentence import SentenceChunker

try:
    from astromesh._native import rust_cosine_similarity as _native_cosine
    from astromesh._native import rust_semantic_group as _native_group
except ImportError:
    _native_cosine = None
    _native_group = None


class SemanticChunker(ChunkingStrategy):
    def __init__(
        self,
        chunk_size: int = 500,
        similarity_threshold: float = 0.5,
        embed_fn: Callable[[str], list[float]] | None = None,
    ):
        self.chunk_size = chunk_size
        self.similarity_threshold = similarity_threshold
        self.embed_fn = embed_fn

    def chunk(self, document: str, metadata: dict) -> list[dict]:
        if not document:
            return []

        if self.embed_fn is None:
            # Fall back to sentence chunking
            fallback = SentenceChunker(chunk_size=self.chunk_size)
            return fallback.chunk(document, metadata)

        sentences = SentenceChunker._split_sentences(document)
        if not sentences:
            return []

        embeddings = [self.embed_fn(s) for s in sentences]

        groups: list[list[str]] = [[sentences[0]]]
        for i in range(1, len(sentences)):
            sim = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            if sim >= self.similarity_threshold and (
                sum(len(s) for s in groups[-1]) + len(sentences[i]) <= self.chunk_size
            ):
                groups[-1].append(sentences[i])
            else:
                groups.append([sentences[i]])

        chunks: list[dict] = []
        for idx, group in enumerate(groups):
            content = "".join(group).strip()
            if content:
                chunks.append(
                    {
                        "content": content,
                        "metadata": {**metadata, "chunk_index": idx, "strategy": "semantic"},
                    }
                )

        return chunks

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if _native_cosine is not None and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            return _native_cosine(a, b)
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
