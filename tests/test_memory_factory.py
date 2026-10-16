import importlib.util
import os
import subprocess
import sys

import pytest

from astromesh.errors import AgentConfigError
from astromesh.memory.factory import (
    build_conversation_backend,
    build_episodic_backend,
    build_semantic_memory,
)


def test_returns_none_when_no_backend():
    assert build_conversation_backend({}) is None
    assert build_conversation_backend({"backend": None}) is None


def test_builds_redis_backend_lazily():
    be = build_conversation_backend(
        {"backend": "redis", "connection": {"url": "redis://localhost:6379/0"}, "ttl": 100}
    )
    # Check by class name, not isinstance: test_memory_backends.py pops and
    # re-imports astromesh.memory.backends.redis_conv with a fake aioredis,
    # leaving a distinct RedisConversationBackend class object in sys.modules,
    # so identity-based isinstance is fragile under full-suite ordering.
    assert type(be).__name__ == "RedisConversationBackend"
    assert be._ttl == 100  # aioredis.from_url is lazy; no live server needed


def test_redis_defaults_ttl():
    be = build_conversation_backend(
        {"backend": "redis", "connection": {"url": "redis://localhost:6379/0"}}
    )
    assert be._ttl == 259200


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="unknown conversational backend"):
        build_conversation_backend({"backend": "cassandra"})


def test_semantic_ausente_es_none():
    assert build_semantic_memory(None) is None
    assert build_episodic_backend({}) is None


def test_semantic_backend_desconocido_nombra_los_validos():
    with pytest.raises(AgentConfigError, match="chromadb, faiss, pgvector, qdrant"):
        build_semantic_memory({"backend": "in_memory", "embeddings": {"provider": "ollama"}})


def test_semantic_sin_embeddings_es_error():
    with pytest.raises(AgentConfigError, match="embeddings"):
        build_semantic_memory({"backend": "chromadb"})


@pytest.mark.parametrize("backend", ["faiss", "pgvector", "qdrant"])
def test_dimension_requerida(backend):
    with pytest.raises(AgentConfigError, match="dimension"):
        build_semantic_memory(
            {
                "backend": backend,
                "embeddings": {"provider": "ollama"},
                "connection": {"url": "postgresql://x"},
            }
        )


def test_pgvector_sin_url_es_error():
    with pytest.raises(AgentConfigError, match=r"connection\.url"):
        build_semantic_memory(
            {"backend": "pgvector", "dimension": 8, "embeddings": {"provider": "ollama"}}
        )


@pytest.mark.parametrize(
    ("modulo", "backend", "extra", "archivo"),
    [
        ("chromadb", "chromadb", "chromadb", "chroma_sem"),
        ("faiss", "faiss", "faiss", "faiss_sem"),
        ("qdrant_client", "qdrant", "qdrant", "qdrant_sem"),
        ("asyncpg", "pgvector", "postgres", "pgvector_sem"),
    ],
)
def test_falta_el_extra_nombra_el_extra(monkeypatch, modulo, backend, extra, archivo):
    monkeypatch.setitem(sys.modules, modulo, None)
    monkeypatch.delitem(sys.modules, f"astromesh.memory.backends.{archivo}", raising=False)
    with pytest.raises(AgentConfigError, match=rf"astromesh\[{extra}\]"):
        build_semantic_memory(
            {
                "backend": backend,
                "dimension": 8,
                "connection": {"url": "postgresql://x"},
                "embeddings": {"provider": "ollama"},
            }
        )


def test_episodic_sin_extra_nombra_el_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "asyncpg", None)
    monkeypatch.delitem(sys.modules, "astromesh.memory.backends.pg_episodic", raising=False)
    with pytest.raises(AgentConfigError, match=r"astromesh\[postgres\]"):
        build_episodic_backend({"backend": "postgres", "connection": {"url": "postgresql://x"}})


def test_sentence_transformer_sin_extra_es_error(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda n, *a: None if n == "sentence_transformers" else real(n, *a),
    )
    with pytest.raises(AgentConfigError, match=r"astromesh\[embeddings\]"):
        build_semantic_memory(
            {"backend": "faiss", "dimension": 8, "embeddings": {"provider": "sentence_transformer"}}
        )


def test_embeddings_provider_desconocido_es_error():
    with pytest.raises(AgentConfigError, match=r"embeddings\.provider"):
        build_semantic_memory({"backend": "faiss", "dimension": 8, "embeddings": {"provider": "x"}})


def test_semantic_construye_backend_y_embedder():
    backend, embed = build_semantic_memory(
        {"backend": "faiss", "dimension": 8, "embeddings": {"provider": "ollama", "model": "m"}}
    )
    assert type(backend).__name__ == "FAISSSemanticBackend"
    assert backend._dimension == 8
    assert embed.__self__.model == "m"


def test_episodic_construye_postgres():
    be = build_episodic_backend({"backend": "postgres", "connection": {"url": "postgresql://x"}})
    assert type(be).__name__ == "PGEpisodicBackend"
    assert be._dsn == "postgresql://x"


def test_episodic_solo_postgres_con_url():
    with pytest.raises(AgentConfigError, match="postgres"):
        build_episodic_backend({"backend": "redis"})
    with pytest.raises(AgentConfigError, match=r"connection\.url"):
        build_episodic_backend({"backend": "postgres"})


def test_api_main_importa_sin_extras():
    code = (
        "import sys\n"
        "for m in ('chromadb','faiss','qdrant_client','asyncpg','sentence_transformers'):"
        " sys.modules[m] = None\n"
        "import astromesh.api.main"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "ASTROMESH_SKIP_RUNTIME": "1"},
        check=False,
    )
    assert r.returncode == 0, r.stderr
