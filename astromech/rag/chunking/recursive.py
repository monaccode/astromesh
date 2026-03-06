from astromech.rag.chunking.base import ChunkingStrategy


class RecursiveChunker(ChunkingStrategy):
    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = separators or ["\n\n", "\n", ". ", " "]

    def chunk(self, document: str, metadata: dict) -> list[dict]:
        if not document:
            return []

        pieces = self._split_recursive(document, self.separators)
        chunks: list[dict] = []
        for i, piece in enumerate(pieces):
            chunks.append({
                "content": piece,
                "metadata": {**metadata, "chunk_index": i, "strategy": "recursive"},
            })
        return chunks

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]

        for sep in separators:
            parts = text.split(sep)
            if len(parts) <= 1:
                continue

            # Re-attach the separator to each part (except last)
            rebuilt: list[str] = []
            for idx, part in enumerate(parts):
                if idx < len(parts) - 1:
                    rebuilt.append(part + sep)
                else:
                    if part:
                        rebuilt.append(part)

            # Merge parts into chunks that fit within chunk_size
            merged = self._merge_parts(rebuilt)
            if all(len(m) <= self.chunk_size for m in merged):
                return merged

            # Recursively split any oversized chunks with remaining separators
            remaining_seps = separators[separators.index(sep) + 1 :]
            result: list[str] = []
            for m in merged:
                if len(m) <= self.chunk_size:
                    result.append(m)
                elif remaining_seps:
                    result.extend(self._split_recursive(m, remaining_seps))
                else:
                    result.extend(self._fixed_split(m))
            return result

        # No separator worked, fall back to fixed splitting
        return self._fixed_split(text)

    def _merge_parts(self, parts: list[str]) -> list[str]:
        merged: list[str] = []
        current = ""
        for part in parts:
            if current and len(current) + len(part) > self.chunk_size:
                merged.append(current)
                current = part
            else:
                current += part
        if current:
            merged.append(current)
        return merged

    def _fixed_split(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.overlap
            if start >= len(text):
                break
        return chunks
