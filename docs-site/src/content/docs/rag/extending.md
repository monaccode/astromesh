---
title: Extending
description: Every stage is a small async protocol; register a factory and your splitter, embedder, index or reranker is usable by name from YAML.
---

Every stage is a `typing.Protocol` in `astromesh_rag.stages`. You do not subclass anything:
a class with the right async methods is a stage. To use it from YAML, register a factory
for it under a name.

| Protocol | Methods | YAML key that picks it |
|---|---|---|
| `Splitter` | `async split(doc) -> list[Chunk]` | `chunking.strategy` |
| `Embedder` | `async embed(texts) -> list[list[float]]`, attribute `dimension` | `embeddings.provider` |
| `VectorIndex` | `async upsert(chunks, vectors)`, `async search(vector, k, filters) -> list[Hit]`, `async delete_document(doc_id)` | `vector_store.backend` |
| `Reranker` | `async rerank(query, hits, k) -> list[Hit]` | `reranking.provider` |
| `Retriever` | `async retrieve(query, k) -> list[Hit]`, attribute `name` | Python only |
| `QueryTransform` | `async transform(query) -> list[str]` | Python only |
| `Fusion` | `fuse(lists, k) -> list[Hit]` (sync) | Python only |
| `LLM` | `async complete(prompt) -> str` | `build(spec, llm=...)` |

## The registry

```python
from astromesh_rag import registry

registry.register(kind, name, factory)  # kind: splitter, embedder, index, reranker, llm
registry.names("index")  # ['chroma', 'faiss', 'memory', 'pgvector', 'qdrant']
```

A factory is `factory(cfg: dict, ctx: BuildContext) -> stage`. `cfg` is the whole YAML
section (`vector_store:` for an index, so your own keys travel with it) and `ctx` carries
what the pipeline resolved before your stage: `ctx.dimension` (the embedding size),
`ctx.embedder` and `ctx.llm`. The embedder is built first, then the splitter, the index and
the reranker.

Registering a name that already exists replaces it, for every pipeline built afterwards.
That is how you swap a built-in for a faster one (a native chunker behind `recursive`)
without touching any YAML. Import the module that registers before you call `build`.

## A vector index, end to end

A persistent index on SQLite, stdlib only. It stores normalized vectors as JSON and scans
them on every search: a few thousand chunks, not millions, but it survives restarts.

```python
import json
import math
import sqlite3

from astromesh_rag import Chunk, Hit, registry


def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class SqliteIndex:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, doc_id TEXT, "
            "text TEXT, metadata TEXT, vector TEXT)"
        )

    async def upsert(self, chunks, vectors):
        rows = [
            (c.id, c.doc_id, c.text, json.dumps(c.metadata), json.dumps(_unit(v)))
            for c, v in zip(chunks, vectors, strict=True)
        ]
        self.db.executemany("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, ?)", rows)
        self.db.commit()

    async def search(self, vector, k, filters=None):
        q = _unit(vector)
        hits = []
        for cid, doc_id, text, meta, vec in self.db.execute("SELECT * FROM chunks"):
            metadata = json.loads(meta)
            if filters and any(metadata.get(f) != v for f, v in filters.items()):
                continue
            score = sum(a * b for a, b in zip(q, json.loads(vec)))
            chunk = Chunk(cid, doc_id, text, metadata)
            hits.append(Hit(chunk, score, "vector", {"vector": score}))
        return sorted(hits, key=lambda h: -h.score)[:k]

    async def delete_document(self, doc_id):
        self.db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.db.commit()


registry.register("index", "sqlite", lambda cfg, ctx: SqliteIndex(cfg.get("path", "rag.db")))
```

```yaml
apiVersion: astromesh/v1
kind: RAGPipeline
metadata:
  name: local-docs
spec:
  embeddings: { provider: sentence_transformers }
  vector_store: { backend: sqlite, path: ./local-docs.db }
```

What the pipeline relies on, so your index behaves like the built-ins:

- **`score` is a cosine similarity**, higher is better. `retrieval.similarity_threshold`
  is compared against it.
- **`source` is `"vector"`** and `details` holds `{"vector": score}`; fusion and the
  benchmark read them.
- **`delete_document` removes every chunk of that `doc_id`.** Ingestion calls it before
  writing a document, which is what makes re-ingesting replace instead of duplicate.
- **Upserting an existing chunk id replaces it.**
- **Blocking clients run off the event loop.** The SQLite calls above are fast enough to
  block briefly; a network client should go through `asyncio.to_thread`, as the Qdrant and
  Chroma adapters do.
- **An optional dependency is imported in the constructor** with
  `astromesh_rag._extras.require(module, extra)`, so a missing package fails at build time
  with an install hint instead of on import.

Test it with the shipped doubles, no model needed:

```python
from astromesh_rag import Document
from astromesh_rag.patterns import naive
from astromesh_rag.pipeline import IngestPipeline
from astromesh_rag.splitters import RecursiveSplitter
from astromesh_rag.testing import HashEmbedder

index, embedder = SqliteIndex(":memory:"), HashEmbedder()
ingest = IngestPipeline(RecursiveSplitter(), embedder, index)
await ingest.ingest([Document("refunds within 30 days", id="refunds")])
await ingest.ingest([Document("refunds within 14 days", id="refunds")])  # replaces
result = await naive(embedder, index).query("refunds", k=5)
assert [h.chunk.id for h in result.hits] == ["refunds#0"]
assert "14 days" in result.context
```

The same steps give you an embedder (return vectors, set `dimension` if you know it) or a
reranker (return the hits you keep, best first, with your score in `score` and in
`details["rerank"]`).

## A custom query transform

A `QueryTransform` turns one question into the queries that get searched. `multi_query`
and `hyde` are two of them (`LLMQueryVariants`, `HypotheticalDocument`). Write your own to
change the prompt, add domain rules, or skip the LLM entirely. This one expands known
acronyms, with no model call:

```python
from astromesh_rag.fusion import RRF
from astromesh_rag.pipeline import QueryPipeline
from astromesh_rag.retrievers import VectorRetriever

ACRONYMS = {"2fa": "two-factor authentication", "sso": "single sign-on"}


class ExpandAcronyms:
    name = "acronyms"  # what the trace shows

    async def transform(self, query: str) -> list[str]:
        words = query.lower().split()
        expanded = " ".join(ACRONYMS.get(w.strip("?"), w) for w in words)
        return [expanded] if expanded != query.lower() else []


pipeline = QueryPipeline(
    [VectorRetriever(embedder, index, min_score=0.2)],
    transform=ExpandAcronyms(),
    fusion=RRF(),
)
result = await pipeline.query("how do I turn on 2fa?", k=5)
assert (result.trace[0]["stage"], result.trace[0]["name"]) == ("transform", "acronyms")
```

`QueryPipeline` searches the original question plus every query the transform returns
(`include_original=False` searches only the transform's output), runs every retriever on
every query in parallel, fuses the lists, then reranks if you pass `reranker=` and
`rerank_k=`. An exception in `transform` raises `StageError("transform", name, cause)`.

To change the prompt of a built-in pattern, wrap your `LLM` the same way:

```python
from astromesh_rag.patterns import LLMQueryVariants


class SpanishVariants(LLMQueryVariants):
    async def transform(self, query):
        prompt = f"Reescribí la pregunta de {self.n} maneras, una por línea:\n{query}"
        lines = (await self.llm.complete(prompt)).splitlines()
        return [ln.strip() for ln in lines if ln.strip()][: self.n]
```

Transforms, retrievers and fusions are composed in Python; v0.1 has no YAML key that
selects a custom one. If you need that, build the `QueryPipeline` yourself and keep the
YAML for ingestion (`build(spec).ingest_pipeline`).
