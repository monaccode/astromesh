import os

from astromesh.rag.chunking.base import ChunkingStrategy

try:
    from astromesh._native import rust_fixed_chunk as _native_chunk
except ImportError:
    _native_chunk = None


class FixedChunker(ChunkingStrategy):
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, document: str, metadata: dict) -> list[dict]:
        if not document:
            return []

        if _native_chunk is not None and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            return _native_chunk(document, metadata, self.chunk_size, self.overlap)

        chunks: list[dict] = []
        start = 0
        i = 0

        while start < len(document):
            end = start + self.chunk_size
            content = document[start:end]
            chunks.append(
                {
                    "content": content,
                    "metadata": {**metadata, "chunk_index": i, "strategy": "fixed"},
                }
            )
            i += 1
            start += self.chunk_size - self.overlap
            if start >= len(document):
                break

        return chunks
