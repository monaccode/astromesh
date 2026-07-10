# tests/test_rag_factory.py
import pytest

from astromesh.rag.chunking.recursive import RecursiveChunker
from astromesh.rag.embeddings.ollama import OllamaEmbeddingProvider
from astromesh.rag.factory import build_pipeline
from astromesh.rag.loader import RAGPipelineSpec
from astromesh.rag.pipeline import RAGPipeline, RAGResult, result_to_list
from astromesh.rag.stores.faiss_store import FAISSStore
from astromesh.rag.stores.pgvector import PGVectorStore


def test_build_pipeline_maps_recursive_ollama_pgvector():
    spec = RAGPipelineSpec(
        name="pk",
        chunking={"strategy": "recursive", "chunk_size": 512, "overlap": 40},
        embeddings={"provider": "ollama", "model": "nomic-embed-text", "endpoint": "http://x:11434", "dimension": 768},
        vector_store={"backend": "pgvector", "connection": {"host": "db", "port": 5432, "database": "astromesh", "user": "u", "password": "p"}, "collection": "docs"},
        reranking={"enabled": False},
        retrieval={"top_k": 5},
    )
    p = build_pipeline(spec)
    assert isinstance(p, RAGPipeline)
    assert isinstance(p._chunker, RecursiveChunker)
    assert p._chunker.chunk_size == 512
    assert isinstance(p._embedder, OllamaEmbeddingProvider)
    assert p._embedder.model == "nomic-embed-text"
    assert isinstance(p._store, PGVectorStore)
    assert p._store.dsn == "postgresql://u:p@db:5432/astromesh"
    assert p._store.table == "docs"
    assert p._reranker is None


def test_build_pipeline_faiss_backend():
    spec = RAGPipelineSpec(name="f", vector_store={"backend": "faiss", "dimensions": 8},
                           embeddings={"provider": "ollama"}, chunking={"strategy": "recursive"})
    p = build_pipeline(spec)
    assert isinstance(p._store, FAISSStore)
    assert p._store.dimensions == 8


def test_build_pipeline_unknown_backend_raises():
    spec = RAGPipelineSpec(name="x", vector_store={"backend": "nope"},
                           embeddings={"provider": "ollama"}, chunking={"strategy": "recursive"})
    with pytest.raises(ValueError, match="vector_store"):
        build_pipeline(spec)


def test_result_to_list_unwraps_ragresult():
    chunks = [{"content": "a"}, {"content": "b"}]
    assert result_to_list(RAGResult(chunks=chunks)) == chunks
    assert result_to_list(chunks) == chunks
