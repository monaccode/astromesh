from __future__ import annotations

import logging

from astromesh.rag.pipeline import RAGPipeline, result_to_list

logger = logging.getLogger(__name__)


def format_knowledge(chunks: list[dict]) -> str:
    """Render retrieved chunks into a plain text block for prompt injection."""
    parts = [str(c.get("content", "")).strip() for c in chunks if c.get("content")]
    return "\n\n".join(p for p in parts if p)


class AgentRAG:
    """Per-agent RAG retriever. Mirrors MemoryManager.build_context: additive, never fatal."""

    def __init__(self, pipeline: RAGPipeline, top_k: int = 5):
        self._pipeline = pipeline
        self._top_k = top_k

    @property
    def pipeline(self) -> RAGPipeline:
        return self._pipeline

    async def build_context(self, query_text: str) -> str:
        try:
            result = await self._pipeline.query(query_text, top_k=self._top_k)
            return format_knowledge(result_to_list(result))
        except Exception:  # never break a run
            logger.warning("rag.build_context failed; continuing without knowledge", exc_info=True)
            return ""
