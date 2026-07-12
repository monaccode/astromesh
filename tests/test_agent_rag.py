from astromesh.rag.agent_rag import AgentRAG, format_knowledge
from astromesh.rag.pipeline import RAGPipeline
from tests.rag_fakes import FakeEmbedder, FakeStore


def _pipeline():
    return RAGPipeline(chunker=None, embedding_provider=FakeEmbedder(), vector_store=FakeStore())


async def test_build_context_returns_retrieved_text():
    p = _pipeline()
    await p.ingest("La política de reembolsos es 30 días.", {"id": "d1"})
    ctx = await AgentRAG(p, top_k=3).build_context("reembolsos")
    assert "30 días" in ctx


async def test_build_context_empty_store_returns_empty_string():
    ctx = await AgentRAG(_pipeline(), top_k=3).build_context("cualquier cosa")
    assert ctx == ""


async def test_build_context_never_raises_on_error():
    class Boom(RAGPipeline):
        async def query(self, *a, **k):
            raise RuntimeError("store caído")

    ctx = await AgentRAG(Boom(), top_k=3).build_context("x")
    assert ctx == ""


def test_format_knowledge_joins_chunks():
    out = format_knowledge([{"content": "uno"}, {"content": "dos"}])
    assert "uno" in out and "dos" in out
