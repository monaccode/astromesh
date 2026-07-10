# astromesh/rag/factory.py
from __future__ import annotations

from astromesh.rag.chunking.fixed import FixedChunker
from astromesh.rag.chunking.recursive import RecursiveChunker
from astromesh.rag.chunking.semantic import SemanticChunker
from astromesh.rag.chunking.sentence import SentenceChunker
from astromesh.rag.embeddings.hf import HFEmbeddingProvider
from astromesh.rag.embeddings.ollama import OllamaEmbeddingProvider
from astromesh.rag.embeddings.st import SentenceTransformerProvider
from astromesh.rag.loader import RAGPipelineSpec
from astromesh.rag.pipeline import RAGPipeline
from astromesh.rag.reranking.cohere import CohereReranker
from astromesh.rag.reranking.cross_encoder import CrossEncoderReranker
from astromesh.rag.stores.chroma import ChromaStore
from astromesh.rag.stores.faiss_store import FAISSStore
from astromesh.rag.stores.pgvector import PGVectorStore
from astromesh.rag.stores.qdrant import QdrantStore


def _build_chunker(cfg: dict):
    strategy = cfg.get("strategy", "recursive")
    if strategy == "recursive":
        return RecursiveChunker(
            chunk_size=cfg.get("chunk_size", 500),
            overlap=cfg.get("overlap", 50),
            separators=cfg.get("separators"),
        )
    if strategy == "fixed":
        return FixedChunker(chunk_size=cfg.get("chunk_size", 500), overlap=cfg.get("overlap", 50))
    if strategy == "sentence":
        return SentenceChunker(chunk_size=cfg.get("chunk_size", 500), overlap=cfg.get("overlap", 0))
    if strategy == "semantic":
        return SemanticChunker(
            chunk_size=cfg.get("chunk_size", 500),
            similarity_threshold=cfg.get("similarity_threshold", 0.5),
        )
    raise ValueError(f"Unknown chunking.strategy: {strategy}")


def _build_embedder(cfg: dict):
    provider = cfg.get("provider", "ollama")
    if provider == "ollama":
        return OllamaEmbeddingProvider(
            endpoint=cfg.get("endpoint", "http://ollama:11434"),
            model=cfg.get("model", "nomic-embed-text"),
        )
    if provider == "hf":
        return HFEmbeddingProvider(
            model_name=cfg.get("model", "BAAI/bge-small-en-v1.5"),
            endpoint=cfg.get("endpoint"),
            api_key=cfg.get("api_key"),
        )
    if provider == "sentence_transformer":
        return SentenceTransformerProvider(model_name=cfg.get("model", "all-MiniLM-L6-v2"))
    raise ValueError(f"Unknown embeddings.provider: {provider}")


def _pg_dsn(cfg: dict) -> str:
    if cfg.get("dsn"):
        return cfg["dsn"]
    c = cfg.get("connection", {})
    return (
        f"postgresql://{c.get('user', 'astromesh')}:{c.get('password', 'astromesh')}"
        f"@{c.get('host', 'localhost')}:{c.get('port', 5432)}/{c.get('database', 'astromesh')}"
    )


def _build_store(cfg: dict, dimensions: int):
    backend = cfg.get("backend", "faiss")
    if backend == "pgvector":
        return PGVectorStore(dsn=_pg_dsn(cfg), table=cfg.get("collection", "embeddings"), dimensions=dimensions)
    if backend == "qdrant":
        return QdrantStore(
            collection_name=cfg.get("collection", "astromesh"),
            url=cfg.get("url", "http://localhost:6333"),
            api_key=cfg.get("api_key"),
            dimensions=dimensions,
        )
    if backend == "chroma":
        return ChromaStore(
            collection_name=cfg.get("collection", "astromesh"),
            host=cfg.get("host"),
            port=cfg.get("port", 8000),
            persist_directory=cfg.get("persist_directory"),
        )
    if backend == "faiss":
        return FAISSStore(dimensions=cfg.get("dimensions", dimensions))
    raise ValueError(f"Unknown vector_store.backend: {backend}")


def _build_reranker(cfg: dict):
    if not cfg.get("enabled"):
        return None
    provider = cfg.get("provider", "cross_encoder")
    if provider == "cross_encoder":
        return CrossEncoderReranker(model_name=cfg.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
    if provider == "cohere":
        return CohereReranker(api_key=cfg.get("api_key", ""), model=cfg.get("model", "rerank-english-v3.0"))
    raise ValueError(f"Unknown reranking.provider: {provider}")


def build_pipeline(spec: RAGPipelineSpec) -> RAGPipeline:
    dimensions = spec.embeddings.get("dimension", 384)
    return RAGPipeline(
        chunker=_build_chunker(spec.chunking),
        embedding_provider=_build_embedder(spec.embeddings),
        vector_store=_build_store(spec.vector_store, dimensions),
        reranker=_build_reranker(spec.reranking),
    )
