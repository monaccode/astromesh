
from astromesh.rag.chunking.fixed import FixedChunker
from astromesh.rag.chunking.recursive import RecursiveChunker
from astromesh.rag.chunking.sentence import SentenceChunker
from astromesh.rag.pipeline import RAGPipeline, RAGResult


def test_fixed_chunker():
    chunker = FixedChunker(chunk_size=50, overlap=10)
    text = "A" * 120
    chunks = chunker.chunk(text, {"source": "test"})
    assert len(chunks) >= 2
    assert all("content" in c for c in chunks)


def test_fixed_chunker_small_text():
    chunker = FixedChunker(chunk_size=500, overlap=50)
    chunks = chunker.chunk("Short text", {"source": "test"})
    assert len(chunks) == 1


def test_sentence_chunker():
    chunker = SentenceChunker(chunk_size=100, overlap=0)
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    chunks = chunker.chunk(text, {})
    assert len(chunks) >= 1
    assert all("content" in c for c in chunks)


def test_recursive_chunker():
    chunker = RecursiveChunker(chunk_size=50, overlap=0)
    text = "Para one.\n\nPara two.\n\nPara three that is somewhat longer."
    chunks = chunker.chunk(text, {})
    assert len(chunks) >= 2


async def test_rag_pipeline_ingest_and_query():
    from unittest.mock import AsyncMock

    store = AsyncMock()
    store.search.return_value = [
        {"content": "result 1", "score": 0.9},
        {"content": "result 2", "score": 0.8},
    ]
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3]
    chunker = FixedChunker(chunk_size=500)

    pipeline = RAGPipeline(
        chunker=chunker, embedding_provider=embedder, vector_store=store
    )
    count = await pipeline.ingest("Test document content", {"source": "test"})
    assert count >= 1
    result = await pipeline.query("test query", top_k=2)
    assert isinstance(result, RAGResult)
    assert len(result.chunks) == 2
