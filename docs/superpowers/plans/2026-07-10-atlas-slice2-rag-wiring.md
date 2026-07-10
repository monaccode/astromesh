# Atlas Slice 2 (parte 1) — Cableado de RAG en el runtime · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cablear RAG en astromesh para que un `Agent` recupere de su knowledge base en runtime (retrieval automático) y los endpoints `/rag/{ingest,query}` funcionen de verdad.

**Architecture:** Un `RAGPipelineLoader` (espejo de `WorkflowLoader`) carga `*.rag.yaml` a un registro por nombre; un **factory** mapea la config a instancias concretas de la librería RAG ya existente; el engine resuelve `spec.knowledge.pipeline` del agente y expone la pipeline construida por dos caminos con **una sola resolución**: `self._rag` (inyección always-on al prompt, espejo de la memoria) y `ctx.rag_pipeline` (activa los tools `rag_query`/`rag_ingest` ya existentes pero colgados). El RAG es aditivo y **nunca puede romper una corrida**.

**Tech Stack:** Python 3.13, `uv`, FastAPI, pytest + pytest-asyncio, ruff. Librería RAG existente en `astromesh/rag/{chunking,embeddings,stores,reranking}`.

## Global Constraints

- Repo de trabajo: **astromesh** (rama `feat/atlas-slice2-rag-wiring`). NO tocar `clarus-platform`.
- Verificación de cada tarea: `uv run pytest <archivo> -v` en verde **y** `uv run ruff check .` limpio (ruff ordena imports, regla I001 — correr antes de cada commit).
- **Nunca romper una corrida**: cualquier fallo del camino RAG (pipeline no resuelta, store vacío, error de embedder/store) → log + contexto de conocimiento vacío, el agente corre igual. Igual criterio no-fatal que la memoria.
- No agregar dependencias nuevas. Reusar las clases concretas de `astromesh/rag/*`.
- Espejar patrones existentes: `WorkflowLoader` (`astromesh/workflow/loader.py`) para el loader; `MemoryManager.build_context` + su inyección en `AgentRunner.run` (`astromesh/runtime/engine.py:517,523`) para el retrieval.
- Sin placeholders de config: el factory usa exactamente estos constructores (verificados):
  - Chunkers: `RecursiveChunker(chunk_size=500, overlap=50, separators=None)`, `FixedChunker(chunk_size=500, overlap=50)`, `SentenceChunker(chunk_size=500, overlap=0)`, `SemanticChunker(chunk_size=500, similarity_threshold=0.5, embed_fn=None)`.
  - Embedders: `OllamaEmbeddingProvider(endpoint="http://ollama:11434", model="nomic-embed-text")`, `HFEmbeddingProvider(model_name="BAAI/bge-small-en-v1.5", endpoint=None, api_key=None)`, `SentenceTransformerProvider(model_name="all-MiniLM-L6-v2")`.
  - Stores: `PGVectorStore(dsn=..., table="embeddings", dimensions=384)`, `QdrantStore(collection_name="astromesh", url="http://localhost:6333", api_key=None, dimensions=384)`, `ChromaStore(collection_name="astromesh", host=None, port=8000, persist_directory=None)`, `FAISSStore(dimensions=384)`.
  - Rerankers: `CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")`, `CohereReranker(api_key, model="rerank-english-v3.0")`.

## File Structure

- Create `astromesh/rag/loader.py` — `RAGPipelineSpec` + `RAGPipelineLoader`.
- Create `astromesh/rag/factory.py` — `build_pipeline(spec) -> RAGPipeline` + registries string→clase.
- Create `astromesh/rag/agent_rag.py` — `AgentRAG` (wrapper por-agente: `build_context`) + `format_knowledge`.
- Modify `astromesh/rag/pipeline.py` — agregar `result_to_list(RAGResult|list) -> list[dict]`.
- Modify `astromesh/runtime/engine.py` — bootstrap del registro RAG; resolución en `_build_agent`; `rag` en `AgentRunner`; inyección en `run()`; `rag_pipeline` en `_make_builtin_handler`.
- Modify `astromesh/tools/base.py` — campo `rag_pipeline` en `ToolContext`.
- Modify `astromesh/tools/builtin/rag.py` — normalizar salida con `result_to_list`.
- Modify `astromesh/api/routes/rag.py` — endpoints reales.
- Create `vscode-extension/schemas/rag.schema.json` — schema de `kind: RAGPipeline`.
- Create tests: `tests/rag_fakes.py`, `tests/test_rag_loader.py`, `tests/test_rag_factory.py`, `tests/test_agent_rag.py`, `tests/test_rag_resolution.py`, `tests/test_rag_injection.py`, `tests/test_rag_api.py`, `tests/test_rag_schema.py`; extender `tests/test_rag_tools.py`.

---

### Task 1: `RAGPipelineLoader` + `RAGPipelineSpec`

**Files:**
- Create: `astromesh/rag/loader.py`
- Test: `tests/test_rag_loader.py`

**Interfaces:**
- Produces: `RAGPipelineSpec` (dataclass: `name: str`, `chunking: dict`, `embeddings: dict`, `vector_store: dict`, `reranking: dict`, `retrieval: dict`); `RAGPipelineLoader(dir: str).load_all() -> dict[str, RAGPipelineSpec]` y `.load_file(path: Path) -> RAGPipelineSpec`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_loader.py
from pathlib import Path

from astromesh.rag.loader import RAGPipelineLoader, RAGPipelineSpec


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


VALID = """
apiVersion: astromesh/v1
kind: RAGPipeline
metadata:
  name: product-knowledge
spec:
  chunking: {strategy: recursive, chunk_size: 512}
  embeddings: {provider: ollama, model: nomic-embed-text}
  vector_store: {backend: pgvector, collection: docs}
  reranking: {enabled: false}
  retrieval: {top_k: 5}
"""


def test_load_file_parses_spec(tmp_path):
    p = _write(tmp_path, "pk.rag.yaml", VALID)
    spec = RAGPipelineLoader(str(tmp_path)).load_file(p)
    assert isinstance(spec, RAGPipelineSpec)
    assert spec.name == "product-knowledge"
    assert spec.chunking["strategy"] == "recursive"
    assert spec.retrieval["top_k"] == 5


def test_load_file_rejects_wrong_kind(tmp_path):
    p = _write(tmp_path, "bad.rag.yaml", "kind: Workflow\nmetadata: {name: x}\n")
    import pytest
    with pytest.raises(ValueError):
        RAGPipelineLoader(str(tmp_path)).load_file(p)


def test_load_all_indexes_by_name_and_skips_invalid(tmp_path):
    _write(tmp_path, "ok.rag.yaml", VALID)
    _write(tmp_path, "broken.rag.yaml", "kind: RAGPipeline\nmetadata: {}\n")  # no name
    reg = RAGPipelineLoader(str(tmp_path)).load_all()
    assert set(reg.keys()) == {"product-knowledge"}


def test_load_all_missing_dir_returns_empty(tmp_path):
    reg = RAGPipelineLoader(str(tmp_path / "nope")).load_all()
    assert reg == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: astromesh.rag.loader`.

- [ ] **Step 3: Write minimal implementation**

```python
# astromesh/rag/loader.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RAGPipelineSpec:
    name: str
    chunking: dict = field(default_factory=dict)
    embeddings: dict = field(default_factory=dict)
    vector_store: dict = field(default_factory=dict)
    reranking: dict = field(default_factory=dict)
    retrieval: dict = field(default_factory=dict)


class RAGPipelineLoader:
    """Loads *.rag.yaml files into RAGPipelineSpec instances. Mirrors WorkflowLoader."""

    def __init__(self, rag_dir: str):
        self._dir = Path(rag_dir)

    def load_all(self) -> dict[str, RAGPipelineSpec]:
        if not self._dir.exists():
            return {}
        out: dict[str, RAGPipelineSpec] = {}
        for f in self._dir.glob("*.rag.yaml"):
            try:
                spec = self.load_file(f)
            except Exception:
                continue  # skip invalid files
            out[spec.name] = spec
        return out

    def load_file(self, path: Path) -> RAGPipelineSpec:
        raw = yaml.safe_load(path.read_text())
        if raw.get("kind") != "RAGPipeline":
            raise ValueError(f"Expected kind: RAGPipeline, got: {raw.get('kind')}")
        metadata = raw.get("metadata", {})
        spec = raw.get("spec", {})
        if not metadata.get("name"):
            raise ValueError("RAGPipeline missing metadata.name")
        return RAGPipelineSpec(
            name=metadata["name"],
            chunking=spec.get("chunking", {}),
            embeddings=spec.get("embeddings", {}),
            vector_store=spec.get("vector_store", {}),
            reranking=spec.get("reranking", {}),
            retrieval=spec.get("retrieval", {}),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_loader.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/rag/loader.py tests/test_rag_loader.py
git add astromesh/rag/loader.py tests/test_rag_loader.py
git commit -m "feat(rag): RAGPipelineLoader + RAGPipelineSpec (espejo de WorkflowLoader)"
```

---

### Task 2: Factory config→instancia + `result_to_list`

**Files:**
- Create: `astromesh/rag/factory.py`
- Modify: `astromesh/rag/pipeline.py` (agregar `result_to_list`)
- Test: `tests/test_rag_factory.py`

**Interfaces:**
- Consumes: `RAGPipelineSpec` (Task 1); `RAGPipeline` (`astromesh/rag/pipeline.py`).
- Produces: `build_pipeline(spec: RAGPipelineSpec) -> RAGPipeline`; `result_to_list(result) -> list[dict]` en `pipeline.py`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_factory.py -v`
Expected: FAIL — `ImportError` de `build_pipeline` / `result_to_list`.

- [ ] **Step 3: Write minimal implementation**

Agregar a `astromesh/rag/pipeline.py` (al final del archivo):

```python
def result_to_list(result) -> list[dict]:
    """Normalize a RAGPipeline.query() return (RAGResult) or a raw list to list[dict]."""
    if isinstance(result, RAGResult):
        return result.chunks
    return list(result or [])
```

Crear `astromesh/rag/factory.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_factory.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/rag/factory.py astromesh/rag/pipeline.py tests/test_rag_factory.py
git add astromesh/rag/factory.py astromesh/rag/pipeline.py tests/test_rag_factory.py
git commit -m "feat(rag): factory config→instancia + result_to_list"
```

---

### Task 3: `AgentRAG` wrapper + fakes de test

**Files:**
- Create: `astromesh/rag/agent_rag.py`
- Create: `tests/rag_fakes.py`
- Test: `tests/test_agent_rag.py`

**Interfaces:**
- Consumes: `RAGPipeline`, `result_to_list` (Task 2).
- Produces: `AgentRAG(pipeline: RAGPipeline, top_k: int = 5)` con `async build_context(query_text: str) -> str`; `format_knowledge(chunks: list[dict]) -> str`. Fakes: `FakeEmbedder`, `FakeStore` en `tests/rag_fakes.py`.

- [ ] **Step 1: Write the fakes + failing test**

```python
# tests/rag_fakes.py
from astromesh.rag.embeddings.base import EmbeddingProvider
from astromesh.rag.stores.base import VectorStore


class FakeEmbedder(EmbeddingProvider):
    """Deterministic: vector length = min(len(text), 8), padded — no external service."""

    async def embed(self, text: str) -> list[float]:
        v = [float(len(text) % 7 + 1)] * 8
        return v

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class FakeStore(VectorStore):
    """In-memory store; search returns all docs (most-recent first), ignoring similarity."""

    def __init__(self):
        self._docs: list[dict] = []

    async def upsert(self, doc_id, embedding, content, metadata):
        self._docs.append({"content": content, "metadata": metadata, "score": 1.0})

    async def search(self, query_embedding, top_k=10, filters=None):
        return list(reversed(self._docs))[:top_k]

    async def delete(self, doc_id):
        self._docs = [d for d in self._docs if d.get("metadata", {}).get("id") != doc_id]
```

```python
# tests/test_agent_rag.py
import pytest

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
```

Nota: `tests/conftest.py` ya configura `pytest-asyncio`; los tests `async def` corren sin decorador (modo auto). Si falla por eso, agregar `pytestmark = pytest.mark.asyncio` al tope del archivo.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_rag.py -v`
Expected: FAIL — `ModuleNotFoundError: astromesh.rag.agent_rag`.

- [ ] **Step 3: Write minimal implementation**

```python
# astromesh/rag/agent_rag.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_rag.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/rag/agent_rag.py tests/rag_fakes.py tests/test_agent_rag.py
git add astromesh/rag/agent_rag.py tests/rag_fakes.py tests/test_agent_rag.py
git commit -m "feat(rag): AgentRAG.build_context (retrieval no-fatal) + fakes de test"
```

---

### Task 4: Resolución Agent→RAG en el engine (bootstrap + `_build_agent` + `AgentRunner.rag`)

**Files:**
- Modify: `astromesh/runtime/engine.py` (`__init__`/`bootstrap` cargan el registro RAG; `_build_agent` resuelve `spec.knowledge`; `AgentRunner.__init__` recibe `rag`)
- Test: `tests/test_rag_resolution.py`

**Interfaces:**
- Consumes: `RAGPipelineLoader` (Task 1), `build_pipeline` (Task 2), `AgentRAG` (Task 3).
- Produces: tras `_build_agent`, un `AgentRunner` con `self._rag` = `AgentRAG` cuando el spec trae `knowledge.pipeline` resoluble, o `None` si no.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_resolution.py
from astromesh.rag.loader import RAGPipelineSpec
from astromesh.runtime.engine import AstromeshEngine


def _engine_with_registry():
    eng = AstromeshEngine(config_dir="./config")
    eng._rag_specs = {
        "product-knowledge": RAGPipelineSpec(
            name="product-knowledge",
            chunking={"strategy": "recursive"},
            embeddings={"provider": "ollama"},
            vector_store={"backend": "faiss", "dimensions": 8},
            reranking={"enabled": False},
            retrieval={"top_k": 4},
        )
    }
    return eng


def _agent_config(knowledge: dict | None):
    spec = {
        "model": {},
        "prompts": {"system": "hola"},
        "orchestration": {"pattern": "react"},
    }
    if knowledge is not None:
        spec["knowledge"] = knowledge
    return {"metadata": {"name": "a1"}, "spec": spec}


def test_agent_with_knowledge_gets_rag():
    eng = _engine_with_registry()
    agent = eng._build_agent(_agent_config({"pipeline": "product-knowledge", "top_k": 3}))
    assert agent._rag is not None
    assert agent._rag._top_k == 3


def test_agent_without_knowledge_has_no_rag():
    eng = _engine_with_registry()
    agent = eng._build_agent(_agent_config(None))
    assert agent._rag is None


def test_agent_with_unresolved_pipeline_degrades_to_none():
    eng = _engine_with_registry()
    agent = eng._build_agent(_agent_config({"pipeline": "does-not-exist"}))
    assert agent._rag is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_resolution.py -v`
Expected: FAIL — `AttributeError: 'AgentRunner' object has no attribute '_rag'`.

- [ ] **Step 3: Write minimal implementation**

En `astromesh/runtime/engine.py`:

(a) En `AstromeshEngine.__init__` (línea ~151), inicializar el atributo del registro. Justo después de setear `self._config_dir`:

```python
        self._rag_specs = {}
```

(b) En `bootstrap` (línea ~160), cargar el registro RAG antes del loop de agentes. Justo después de la guarda `agents_dir` / antes de `configs = []`:

```python
        from astromesh.rag.loader import RAGPipelineLoader
        self._rag_specs = RAGPipelineLoader(str(self._config_dir / "rag")).load_all()
```

(c) Agregar un helper de resolución al engine (método nuevo en `AstromeshEngine`):

```python
    def _resolve_rag(self, spec: dict):
        from astromesh.rag.agent_rag import AgentRAG
        from astromesh.rag.factory import build_pipeline

        knowledge = spec.get("knowledge") or {}
        name = knowledge.get("pipeline")
        if not name:
            return None
        rag_spec = self._rag_specs.get(name)
        if rag_spec is None:
            logger.warning("agent references unknown RAGPipeline '%s'; skipping KB", name)
            return None
        try:
            pipeline = build_pipeline(rag_spec)
        except Exception:
            logger.warning("failed to build RAGPipeline '%s'; skipping KB", name, exc_info=True)
            return None
        top_k = knowledge.get("top_k", rag_spec.retrieval.get("top_k", 5))
        return AgentRAG(pipeline, top_k=top_k)
```

(d) En `_build_agent` (línea ~291), calcular el rag junto a la memoria. Después de la línea `memory = MemoryManager(...)`:

```python
        rag = self._resolve_rag(spec)
```

(e) En la construcción del `AgentRunner(...)` al final de `_build_agent`, pasar `rag=rag` como argumento keyword.

(f) En `AgentRunner.__init__` (línea ~466), agregar el parámetro y el atributo. Agregar `rag=None` al final de la firma (después de `orchestration_config`) y, en el cuerpo, después de `self._memory = memory`:

```python
        self._rag = rag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_resolution.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verificar que no rompimos el bootstrap existente + lint + commit**

```bash
uv run pytest tests/ -k "engine or agent or bootstrap" -q
uv run ruff check --fix astromesh/runtime/engine.py tests/test_rag_resolution.py
git add astromesh/runtime/engine.py tests/test_rag_resolution.py
git commit -m "feat(rag): resolución Agent→RAG (registro en bootstrap + self._rag)"
```

---

### Task 5: Inyección always-on en `AgentRunner.run`

**Files:**
- Modify: `astromesh/runtime/engine.py` (`AgentRunner.run`, ~línea 497-525)
- Test: `tests/test_rag_injection.py`

**Interfaces:**
- Consumes: `self._rag` (Task 4), `AgentRAG.build_context` (Task 3).
- Produces: el render del system prompt recibe `knowledge` como variable de contexto (junto a `memory`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_injection.py
from astromesh.runtime.engine import AgentRunner


class _RecordingPromptEngine:
    def __init__(self):
        self.context = None

    def render(self, template, context):
        self.context = context
        return "SYSTEM"


class _StubPattern:
    async def execute(self, *a, **k):
        return {"answer": "ok"}


class _StubMemory:
    async def build_context(self, *a, **k):
        return ""

    async def persist_turn(self, *a, **k):
        return None


class _StubTools:
    def get_tool_schemas(self, *a, **k):
        return []


class _FakeRag:
    async def build_context(self, query_text):
        return f"KB::{query_text}"


def _runner(rag):
    pe = _RecordingPromptEngine()
    runner = AgentRunner(
        name="a1", version="1", namespace="default", description="",
        routers={"default": None}, memory=_StubMemory(), tools=_StubTools(),
        pattern=_StubPattern(), system_prompt="hola", prompt_engine=pe,
        guardrails={}, permissions={}, orchestration_config={}, rag=rag,
    )
    return runner, pe


async def test_run_injects_knowledge_when_rag_present():
    runner, pe = _runner(_FakeRag())
    await runner.run("reembolsos", session_id="s1")
    assert pe.context["knowledge"] == "KB::reembolsos"


async def test_run_injects_empty_knowledge_when_no_rag():
    runner, pe = _runner(None)
    await runner.run("hola", session_id="s1")
    assert pe.context.get("knowledge", "") == ""
```

Si el `AgentRunner.run` real ejecuta ramas que estos stubs no cubren (p.ej. guardrails), ajustar los stubs para que `render` se alcance; el objetivo del test es exclusivamente que `knowledge` llegue al contexto del render.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_injection.py -v`
Expected: FAIL — `pe.context["knowledge"]` no existe (KeyError) porque `run` aún no lo inyecta.

- [ ] **Step 3: Write minimal implementation**

En `AgentRunner.run` (`astromesh/runtime/engine.py`), después del bloque que construye `memory_context` (línea ~517) y antes del `prompt_span`/`render` (~523):

```python
            rag_span = tracing.start_span("rag_build")
            knowledge_context = await self._rag.build_context(query_text) if self._rag else ""
            tracing.finish_span(rag_span)
```

Y modificar la llamada a `self._prompt_engine.render(...)` (línea ~523) para incluir `knowledge`:

```python
            rendered_prompt = self._prompt_engine.render(
                self._system_prompt,
                {**(context or {}), "memory": memory_context, "knowledge": knowledge_context},
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_injection.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/runtime/engine.py tests/test_rag_injection.py
git add astromesh/runtime/engine.py tests/test_rag_injection.py
git commit -m "feat(rag): inyección always-on de knowledge en el prompt (espejo de memoria)"
```

---

### Task 6: Activar los tools `rag_query`/`rag_ingest` (ToolContext + handler + normalización)

**Files:**
- Modify: `astromesh/tools/base.py` (`ToolContext`: campo `rag_pipeline`)
- Modify: `astromesh/runtime/engine.py` (`_make_builtin_handler` recibe/setea `rag_pipeline`; el loop de tools en `_build_agent` lo pasa)
- Modify: `astromesh/tools/builtin/rag.py` (normalizar salida con `result_to_list`)
- Test: extender `tests/test_rag_tools.py`

**Interfaces:**
- Consumes: la pipeline resuelta en `_build_agent` (Task 4), `result_to_list` (Task 2).
- Produces: `ToolContext.rag_pipeline`; `rag_query`/`rag_ingest` devuelven resultados reales cuando el agente tiene pipeline.

- [ ] **Step 1: Write the failing test**

Agregar a `tests/test_rag_tools.py`:

```python
class TestRagQueryToolNormalizes:
    async def test_query_returns_normalized_list_from_ragresult(self):
        from unittest.mock import AsyncMock, MagicMock

        from astromesh.rag.pipeline import RAGResult
        from astromesh.tools.base import ToolContext
        from astromesh.tools.builtin.rag import RagQueryTool

        mock_pipeline = MagicMock()
        mock_pipeline.query = AsyncMock(return_value=RAGResult(chunks=[{"content": "doc"}]))
        ctx = ToolContext(agent_name="t", session_id="s1")
        ctx.rag_pipeline = mock_pipeline

        result = await RagQueryTool().execute({"query": "q"}, ctx)
        assert result.success is True
        assert result.data["results"] == [{"content": "doc"}]


def test_tool_context_has_rag_pipeline_field():
    from astromesh.tools.base import ToolContext

    ctx = ToolContext(agent_name="t", session_id="s")
    assert ctx.rag_pipeline is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_tools.py -v`
Expected: FAIL — `RAGResult` no se normaliza (queda como objeto en `data["results"]`) y/o `ctx.rag_pipeline` no es un campo declarado.

- [ ] **Step 3: Write minimal implementation**

(a) En `astromesh/tools/base.py`, en la dataclass `ToolContext`, agregar el campo (después de `model_fn`):

```python
    rag_pipeline: Any | None = None
```

(b) En `astromesh/tools/builtin/rag.py`, normalizar la salida de `RagQueryTool.execute` — reemplazar el bloque `results = await pipeline.query(...)` / `return ToolResult(success=True, data={"results": results}, ...)` por:

```python
            from astromesh.rag.pipeline import result_to_list

            raw = await pipeline.query(arguments["query"], top_k=arguments.get("top_k", 5))
            return ToolResult(success=True, data={"results": result_to_list(raw)}, metadata={})
```

(c) En `astromesh/runtime/engine.py`, `_make_builtin_handler` (línea ~39) debe aceptar y setear la pipeline:

```python
def _make_builtin_handler(tool_instance, agent_name, rag_pipeline=None):
    """Create an async handler closure for a builtin tool instance."""

    async def _handler(**arguments):
        from astromesh.tools.base import ToolContext

        ctx = ToolContext(agent_name=agent_name, session_id="", trace_span=None)
        ctx.rag_pipeline = rag_pipeline
        result = await tool_instance.execute(arguments, ctx)
        return result.to_dict()

    return _handler
```

(d) En `_build_agent`, el loop de tools llama `_make_builtin_handler(instance, metadata["name"])` (línea ~306). Pasar la pipeline resuelta. Como `rag` (Task 4) es un `AgentRAG | None`, exponer su pipeline: cambiar esa llamada por:

```python
                handler = _make_builtin_handler(
                    instance, metadata["name"], rag_pipeline=(rag.pipeline if rag else None)
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_tools.py -v`
Expected: PASS (todos, incl. los existentes).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/tools/base.py astromesh/tools/builtin/rag.py astromesh/runtime/engine.py tests/test_rag_tools.py
git add astromesh/tools/base.py astromesh/tools/builtin/rag.py astromesh/runtime/engine.py tests/test_rag_tools.py
git commit -m "feat(rag): activa rag_query/rag_ingest (ToolContext.rag_pipeline + normalización)"
```

---

### Task 7: Endpoints REST reales `/rag/ingest` + `/rag/query`

**Files:**
- Modify: `astromesh/api/routes/rag.py`
- Test: `tests/test_rag_api.py`

**Interfaces:**
- Consumes: `RAGPipelineLoader` (Task 1), `build_pipeline` (Task 2), `result_to_list` (Task 2).
- Produces: `POST /rag/ingest {pipeline, document, metadata, doc_id_prefix}` → `{"chunks": N}`; `POST /rag/query {pipeline, query, top_k}` → `{"query", "results", "top_k"}`.

Enfoque de resolución: los endpoints resuelven la pipeline por nombre desde `config/rag/`. Para hacerlos testeables sin un engine vivo, la resolución vive en un helper inyectable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_api.py
import pytest

from astromesh.api.routes import rag as rag_route
from astromesh.rag.pipeline import RAGPipeline
from tests.rag_fakes import FakeEmbedder, FakeStore


@pytest.fixture
def fake_pipeline(monkeypatch):
    p = RAGPipeline(chunker=None, embedding_provider=FakeEmbedder(), vector_store=FakeStore())
    monkeypatch.setattr(rag_route, "resolve_pipeline", lambda name: p)
    return p


async def test_ingest_then_query(client, fake_pipeline):
    r1 = await client.post("/rag/ingest", json={"pipeline": "pk", "document": "reembolsos: 30 días", "metadata": {"id": "d1"}})
    assert r1.status_code == 200
    assert r1.json()["chunks"] >= 1

    r2 = await client.post("/rag/query", json={"pipeline": "pk", "query": "reembolsos", "top_k": 3})
    assert r2.status_code == 200
    body = r2.json()
    assert body["query"] == "reembolsos"
    assert any("30 días" in c.get("content", "") for c in body["results"])


async def test_query_unknown_pipeline_404(client, monkeypatch):
    monkeypatch.setattr(rag_route, "resolve_pipeline", lambda name: None)
    r = await client.post("/rag/query", json={"pipeline": "nope", "query": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_api.py -v`
Expected: FAIL — `resolve_pipeline` no existe y los endpoints devuelven stubs.

- [ ] **Step 3: Write minimal implementation**

Reescribir `astromesh/api/routes/rag.py`:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from astromesh.rag.factory import build_pipeline
from astromesh.rag.loader import RAGPipelineLoader
from astromesh.rag.pipeline import RAGPipeline, result_to_list

router = APIRouter()

_CONFIG_RAG_DIR = "./config/rag"


def resolve_pipeline(name: str) -> RAGPipeline | None:
    """Resolve a RAGPipeline by name from config/rag. Overridable in tests."""
    spec = RAGPipelineLoader(_CONFIG_RAG_DIR).load_all().get(name)
    return build_pipeline(spec) if spec else None


class RAGIngestRequest(BaseModel):
    pipeline: str
    document: str
    metadata: dict = {}
    doc_id_prefix: str = "doc"


class RAGQueryRequest(BaseModel):
    pipeline: str
    query: str
    top_k: int = 5


@router.post("/rag/ingest")
async def ingest_document(request: RAGIngestRequest):
    pipeline = resolve_pipeline(request.pipeline)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {request.pipeline}")
    n = await pipeline.ingest(request.document, metadata=request.metadata, doc_id_prefix=request.doc_id_prefix)
    return {"pipeline": request.pipeline, "chunks": n}


@router.post("/rag/query")
async def query_rag(request: RAGQueryRequest):
    pipeline = resolve_pipeline(request.pipeline)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {request.pipeline}")
    raw = await pipeline.query(request.query, top_k=request.top_k)
    return {"query": request.query, "results": result_to_list(raw), "top_k": request.top_k}
```

Nota: si un test existente llamaba `/rag/ingest`/`/rag/query` con el shape viejo (sin `pipeline`), actualizarlo al nuevo shape.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_api.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix astromesh/api/routes/rag.py tests/test_rag_api.py
git add astromesh/api/routes/rag.py tests/test_rag_api.py
git commit -m "feat(rag): endpoints REST reales /rag/ingest + /rag/query (resolución por nombre)"
```

---

### Task 8: `rag.schema.json` + validación del ejemplo

**Files:**
- Create: `vscode-extension/schemas/rag.schema.json`
- Test: `tests/test_rag_schema.py`

**Interfaces:**
- Consumes: `config/rag/product-knowledge.rag.yaml` (ejemplo existente).
- Produces: schema JSON de `kind: RAGPipeline` con los enums que soporta el factory.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_schema.py
import json
from pathlib import Path

import yaml
from jsonschema import validate


def _schema():
    return json.loads(Path("vscode-extension/schemas/rag.schema.json").read_text())


def test_example_config_validates():
    doc = yaml.safe_load(Path("config/rag/product-knowledge.rag.yaml").read_text())
    validate(instance=doc, schema=_schema())


def test_unknown_backend_fails_schema():
    import pytest
    from jsonschema import ValidationError

    doc = {
        "apiVersion": "astromesh/v1",
        "kind": "RAGPipeline",
        "metadata": {"name": "x"},
        "spec": {"vector_store": {"backend": "not-a-backend"}},
    }
    with pytest.raises(ValidationError):
        validate(instance=doc, schema=_schema())
```

Nota: `jsonschema` ya es dependencia transitiva del repo; si el import falla, correr `uv run python -c "import jsonschema"` para confirmar y, si no está, usar el validador que ya usan los otros schemas (revisar cómo se validan `agent.schema.json`/`workflow.schema.json` en el repo y espejar).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_schema.py -v`
Expected: FAIL — el archivo `rag.schema.json` no existe.

- [ ] **Step 3: Write minimal implementation**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "astromesh RAGPipeline",
  "type": "object",
  "required": ["apiVersion", "kind", "metadata", "spec"],
  "properties": {
    "apiVersion": { "const": "astromesh/v1" },
    "kind": { "const": "RAGPipeline" },
    "metadata": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" },
        "namespace": { "type": "string" }
      }
    },
    "spec": {
      "type": "object",
      "properties": {
        "description": { "type": "string" },
        "chunking": {
          "type": "object",
          "properties": {
            "strategy": { "enum": ["recursive", "fixed", "sentence", "semantic"] },
            "chunk_size": { "type": "integer" },
            "overlap": { "type": "integer" },
            "similarity_threshold": { "type": "number" },
            "separators": { "type": "array", "items": { "type": "string" } }
          }
        },
        "embeddings": {
          "type": "object",
          "properties": {
            "provider": { "enum": ["ollama", "hf", "sentence_transformer"] },
            "model": { "type": "string" },
            "endpoint": { "type": "string" },
            "dimension": { "type": "integer" }
          }
        },
        "vector_store": {
          "type": "object",
          "properties": {
            "backend": { "enum": ["pgvector", "qdrant", "chroma", "faiss"] },
            "collection": { "type": "string" },
            "dimensions": { "type": "integer" },
            "connection": { "type": "object" },
            "url": { "type": "string" },
            "host": { "type": "string" },
            "port": { "type": "integer" }
          }
        },
        "reranking": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean" },
            "provider": { "enum": ["cross_encoder", "cohere"] },
            "model": { "type": "string" },
            "top_k": { "type": "integer" }
          }
        },
        "retrieval": {
          "type": "object",
          "properties": {
            "top_k": { "type": "integer" },
            "similarity_threshold": { "type": "number" }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_schema.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Suite completa + lint + commit**

```bash
uv run pytest tests/ -k rag -q
uv run ruff check .
git add vscode-extension/schemas/rag.schema.json tests/test_rag_schema.py
git commit -m "feat(rag): rag.schema.json (kind: RAGPipeline) + validación del ejemplo"
```

---

## Self-Review

**1. Spec coverage:**
- §Componente 1 (Loader) → Task 1. ✓
- §Componente 2 (Factory, pieza central) → Task 2. ✓
- §Componente 3 (Resolución Agent→RAG, dos consumidores) → Task 4 (self._rag) + Task 6 (ctx.rag_pipeline). ✓
- §Componente 4 (Inyección en run) → Task 5. ✓
- §Componente 5 (REST real + reconciliación RAGResult→lista) → Task 7 (endpoints) + Task 2/6 (`result_to_list`). ✓
- §Componente 6 (rag.schema.json) → Task 8. ✓
- §Contrato `spec.knowledge` (pipeline + top_k override) → Task 4 (resolución lee `knowledge.pipeline`/`knowledge.top_k`). ✓
- §Manejo de errores no-fatal → Task 3 (`AgentRAG.build_context` try/except) + Task 4 (`_resolve_rag` degradaciones) + Task 5 (guard `if self._rag`). ✓
- §Testing (fakes deterministas) → `tests/rag_fakes.py` (Task 3), usados en Tasks 3/7. ✓
- §Criterios de aceptación 1-7 → Tasks 4(1), 7(2), 5(3), 3+4+5(4), 6(5), 8(6), todas las tareas(7). ✓
- §Fuera de alcance (orquestación de ingesta, approval/async, tool-based primario) → no hay tareas, correcto. ✓
- §Follow-up en Clarus → explícitamente fuera de este plan (repo distinto). ✓

**2. Placeholder scan:** sin "TBD"/"similar a"/"agregar manejo de errores" — cada step trae código o comando concreto. Las notas condicionales (p.ej. `pytestmark`, shape viejo de endpoints, validador de schema) son contingencias con acción exacta, no placeholders. ✓

**3. Type consistency:**
- `RAGPipelineSpec` (campos `name/chunking/embeddings/vector_store/reranking/retrieval`) — definido Task 1, usado Tasks 2/4/7 con esos nombres. ✓
- `build_pipeline(spec) -> RAGPipeline` — Task 2, usado Tasks 4/7. ✓
- `result_to_list(result) -> list[dict]` — Task 2, usado Tasks 6/7. ✓
- `AgentRAG(pipeline, top_k)` con `.build_context()` y `.pipeline` — Task 3, usado Tasks 4/5/6. ✓
- `AgentRunner.__init__(..., rag=None)` + `self._rag` — Task 4, usado Task 5. ✓
- `_make_builtin_handler(instance, agent_name, rag_pipeline=None)` — Task 6, coherente con la llamada en `_build_agent`. ✓
- `ToolContext.rag_pipeline` — Task 6, leído por los tools existentes vía `getattr`. ✓
- `resolve_pipeline(name) -> RAGPipeline | None` — Task 7, mock-eable en tests. ✓
