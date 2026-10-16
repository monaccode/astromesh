"""Factory mapping declarative memory config to memory backends.

Cada backend se importa dentro de su rama: `astromesh.api.main` tiene que
importar sin extras (la imagen de astromesh-os no los instala).
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Awaitable, Callable

from astromesh.core.memory import ConversationBackend, EpisodicBackend, SemanticBackend
from astromesh.errors import AgentConfigError

_DEFAULT_TTL = 259200  # 72h


def build_conversation_backend(conv_config: dict | None) -> ConversationBackend | None:
    """Build a ConversationBackend from a normalized conversational config.

    conv_config is memory_config["conversational"], e.g.
    {"backend": "redis", "connection": {"url": "redis://..."}, "ttl": 259200}.
    Returns None when no backend is declared.
    """
    if not conv_config:
        return None
    backend = conv_config.get("backend")
    if not backend:
        return None

    if backend == "redis":
        from astromesh.memory.backends.redis_conv import RedisConversationBackend

        url = conv_config["connection"]["url"]
        ttl = conv_config.get("ttl", _DEFAULT_TTL)
        return RedisConversationBackend(url, ttl=ttl)

    raise ValueError(f"unknown conversational backend {backend!r}")


# backend → (módulo, clase, extra que lo instala)
_SEMANTIC = {
    "chromadb": ("chroma_sem", "ChromaSemanticBackend", "chromadb"),
    "faiss": ("faiss_sem", "FAISSSemanticBackend", "faiss"),
    "pgvector": ("pgvector_sem", "PGVectorSemanticBackend", "postgres"),
    "qdrant": ("qdrant_sem", "QdrantSemanticBackend", "qdrant"),
}
_EMBEDDERS = ("ollama", "hf", "sentence_transformer")


def _clase(seccion: str, backend: str, modulo: str, clase: str, extra: str):
    try:
        mod = importlib.import_module(f"astromesh.memory.backends.{modulo}")
    except ImportError as err:
        raise AgentConfigError(
            f"memory.{seccion}.backend {backend!r} necesita el extra: "
            f"pip install 'astromesh[{extra}]'"
        ) from err
    return getattr(mod, clase)


def build_semantic_memory(
    cfg: dict | None,
) -> tuple[SemanticBackend, Callable[[str], Awaitable[list[float]]]] | None:
    """Backend semántico + `embedding_fn` desde `memory.semantic`, o None si no se declara."""
    if not cfg:
        return None
    backend = cfg.get("backend")
    if backend not in _SEMANTIC:
        raise AgentConfigError(
            f"memory.semantic.backend {backend!r} no existe; los válidos son: "
            f"{', '.join(sorted(_SEMANTIC))}"
        )
    emb_cfg = cfg.get("embeddings")
    if not emb_cfg:
        # Sin default implícito: elegir uno sería llamar a un servicio que nadie declaró.
        raise AgentConfigError(
            "memory.semantic necesita `embeddings` (provider: ollama | hf | "
            "sentence_transformer, model, ...)"
        )
    provider = emb_cfg.get("provider")
    if provider not in _EMBEDDERS:
        raise AgentConfigError(
            f"memory.semantic.embeddings.provider {provider!r} no existe; "
            f"los válidos son: {', '.join(_EMBEDDERS)}"
        )
    if (
        provider == "sentence_transformer"
        and importlib.util.find_spec("sentence_transformers") is None
    ):
        raise AgentConfigError(
            "memory.semantic.embeddings.provider 'sentence_transformer' necesita el extra: "
            "pip install 'astromesh[embeddings]'"
        )
    dimension = cfg.get("dimension")
    if backend != "chromadb" and not dimension:
        raise AgentConfigError(f"memory.semantic.backend {backend!r} necesita `dimension`")
    url = (cfg.get("connection") or {}).get("url")
    if backend == "pgvector" and not url:
        raise AgentConfigError("memory.semantic.backend 'pgvector' necesita `connection.url`")

    cls = _clase("semantic", backend, *_SEMANTIC[backend])
    if backend == "chromadb":
        sem = cls(path=cfg.get("path"))
    elif backend == "faiss":
        sem = cls(dimension=dimension)
    elif backend == "pgvector":
        sem = cls(dsn=url, dimension=dimension)
    else:
        sem = cls(url=url, dimension=dimension)

    from astromesh.rag.factory import build_embedder

    return sem, build_embedder(emb_cfg).embed


def build_episodic_backend(cfg: dict | None) -> EpisodicBackend | None:
    """Backend episódico desde `memory.episodic`, o None si no se declara."""
    if not cfg:
        return None
    backend = cfg.get("backend")
    if backend != "postgres":
        raise AgentConfigError(
            f"memory.episodic.backend {backend!r} no existe; el único válido es: postgres"
        )
    url = (cfg.get("connection") or {}).get("url")
    if not url:
        raise AgentConfigError("memory.episodic.backend 'postgres' necesita `connection.url`")
    cls = _clase("episodic", backend, "pg_episodic", "PGEpisodicBackend", "postgres")
    return cls(dsn=url)
