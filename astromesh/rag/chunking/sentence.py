import os
import re

from astromesh.rag.chunking.base import ChunkingStrategy

try:
    from astromesh._native import rust_sentence_chunk as _native_chunk
except ImportError:
    _native_chunk = None


class SentenceChunker(ChunkingStrategy):
    def __init__(self, chunk_size: int = 500, overlap: int = 0):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, document: str, metadata: dict) -> list[dict]:
        if not document:
            return []

        if _native_chunk is not None and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            return _native_chunk(document, metadata, self.chunk_size, self.overlap)

        sentences = self._split_sentences(document)
        chunks: list[dict] = []
        current = ""
        i = 0

        for sentence in sentences:
            if current and len(current) + len(sentence) > self.chunk_size:
                chunks.append({
                    "content": current.strip(),
                    "metadata": {**metadata, "chunk_index": i, "strategy": "sentence"},
                })
                i += 1
                current = sentence
            else:
                current += sentence

        if current.strip():
            chunks.append({
                "content": current.strip(),
                "metadata": {**metadata, "chunk_index": i, "strategy": "sentence"},
            })

        return chunks

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text on sentence boundaries, keeping delimiters attached."""
        parts = re.split(r"(?<=[.!?])\s+", text)
        # Re-add trailing space for all but the last
        sentences: list[str] = []
        for idx, part in enumerate(parts):
            if idx < len(parts) - 1:
                sentences.append(part + " ")
            else:
                sentences.append(part)
        return sentences
