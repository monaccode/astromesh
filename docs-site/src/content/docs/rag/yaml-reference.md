---
title: YAML Reference
description: Every key and default of a kind RAGPipeline file — chunking, embeddings, vector_store, reranking and retrieval — and what a query returns.
---

A pipeline file is a `kind: RAGPipeline` document, the same format the Astromesh runtime
loads. Every section under `spec` is optional; a missing key takes the default listed here.

```yaml
apiVersion: astromesh/v1
kind: RAGPipeline
metadata:
  name: product-knowledge
spec:
  chunking: { strategy: recursive, chunk_size: 512, overlap: 50 }
  embeddings: { provider: ollama, model: nomic-embed-text, endpoint: "http://localhost:11434", dimension: 768 }
  vector_store: { backend: qdrant, url: "http://localhost:6333", collection: product_docs }
  reranking: { enabled: true, provider: cross_encoder, top_k: 5 }
  retrieval:
    pattern: hybrid
    top_k: 5
    candidates: 20
    similarity_threshold: 0.3
    hybrid: { fusion: rrf }
    bm25_path: ./product_docs.bm25.json
```

```python
from astromesh_rag.spec import build, load_spec, load_spec_file

spec = load_spec_file("product.rag.yaml")  # or load_spec(dict) for an already-parsed body
pipeline = build(spec)  # build(spec, llm=...) for multi_query and hyde
await pipeline.ingest(docs)  # -> number of chunks written
result = await pipeline.query("question", k=5)
```

## Loading and validation

`load_spec` checks the shape and nothing else; `build` resolves every name. Both raise
`SpecError` (a `RAGError`) on the problems below. Nothing waits for the first query to fail.

| Problem | Raised by |
|---|---|
| The body is not a mapping, `kind` is not `RAGPipeline`, `metadata.name` is missing, `spec` or one of its sections is not a mapping | `load_spec` |
| An unknown component name (`strategy`, `provider`, `backend`); the message lists the known ones | `build` |
| An unknown `retrieval.pattern` | `build` |
| `multi_query` or `hyde` without `build(spec, llm=...)` | `build` |
| `fixed` or `recursive` chunking with `chunk_size <= 0`, `overlap < 0` or `overlap >= chunk_size` | `build` |
| A `pgvector` table name that is not a plain SQL identifier | `build` |

A missing extra raises `MissingExtraError` with the `pip install 'astromesh-rag[<extra>]'`
to run, also from `build` (pgvector checks `asyncpg` on its first query or ingestion).

**Unknown keys are ignored**, on purpose: provider sections carry provider-specific keys,
and files written by other tools must keep loading. `apiVersion` is not checked. The flip
side is that a misspelled key is silently ignored too, so check the `trace` and the hit
counts the first time you run a new file.

## `chunking`

How documents become chunks. Sizes are in characters.

| Key | Default | Effect |
|---|---|---|
| `strategy` | `recursive` | `fixed`, `recursive`, `sentence`, `semantic`, or any name registered as a `splitter` |
| `chunk_size` | `500` | Maximum chunk length |
| `overlap` | `50` | Characters repeated between consecutive chunks. Used by `fixed` and `recursive`; ignored by `sentence` and `semantic` |
| `separators` | `["\n\n", "\n", ". ", " "]` | `recursive` only: tried in order, coarsest first |
| `similarity_threshold` | `0.5` | `semantic` only: two consecutive sentences stay in one chunk while their cosine is at least this. Not the same key as `retrieval.similarity_threshold` |

- **`fixed`** cuts every `chunk_size` characters, stepping `chunk_size - overlap`.
- **`recursive`** splits on the first separator that breaks the text into pieces that fit,
  recursing into pieces that are still too long.
- **`sentence`** packs whole sentences (split after `.`, `!`, `?`) up to `chunk_size`.
- **`semantic`** embeds every sentence with the pipeline's embedder and starts a new chunk
  where the topic shifts (cosine below `chunking.similarity_threshold`) or the chunk is full.
  It costs one embedding per sentence at ingestion.

Every chunk's metadata carries the document's metadata plus `chunk_index` and `strategy`.
Chunk ids are `<doc_id>#<n>`; `doc_id` is `Document.id`, or `sha256:` plus the first 16 hex
characters of the text's SHA-256 when the document has none.

## `embeddings`

| Key | Default | Effect |
|---|---|---|
| `provider` | `ollama` | `ollama`, `hf`, `sentence_transformers` (alias `sentence_transformer`), `hash`, or any registered `embedder` |
| `model` | per provider | `ollama`: `nomic-embed-text`; `hf`: `BAAI/bge-small-en-v1.5`; `sentence_transformers`: `all-MiniLM-L6-v2` |
| `endpoint` | per provider | `ollama`: `http://ollama:11434` (the Astromesh Docker hostname; set it to `http://localhost:11434` outside Docker). `hf`: the Hugging Face Inference API URL for `model`; point it at a TEI server to self-host |
| `api_key` | none | `hf` only |
| `dimension` | see below | The vector size the index is created with |

**Set `dimension` whenever the index needs it** (`faiss`, `qdrant`, `pgvector`). The
pipeline uses `embeddings.dimension`, else the size the embedder reports at build time,
else 384. Ollama and Hugging Face report nothing until they are called, and
sentence-transformers only after the model loads, so without the key those indexes are
created for 384-dimensional vectors: right for `all-MiniLM-L6-v2`, wrong for
`nomic-embed-text` (768).

`hash` is `astromesh_rag.testing.HashEmbedder`: deterministic, offline, 64 dimensions, and
meaningless for real retrieval. Use it in tests.

## `vector_store`

| Key | Default | Effect |
|---|---|---|
| `backend` | `faiss` | `memory`, `faiss`, `chroma`, `qdrant`, `pgvector`, or any registered `index` |

Every backend scores by cosine similarity, so `retrieval.similarity_threshold` means the
same thing on all of them.

| Backend | Keys (default) | Notes |
|---|---|---|
| `memory` | none | Pure Python, no extra, lives in the process. Good up to a few thousand chunks and for tests |
| `faiss` | `dimensions` (the embedding dimension) | In-process exact search (`IndexFlatIP` over normalized vectors); not persisted. Note the plural key |
| `chroma` | `collection` (`astromesh`), `host`, `port` (`8000`), `persist_directory` | `host` connects to a server; else `persist_directory` stores on disk; else in memory. Collections use cosine space |
| `qdrant` | `collection` (`astromesh`), `url` (`http://localhost:6333`), `api_key` | `url: ":memory:"` runs an in-process instance. Creates the collection with cosine distance if it does not exist. Point ids are UUIDv5 of the chunk id |
| `pgvector` | `dsn`, or `connection` with `host` (`localhost`), `port` (`5432`), `database`, `user`, `password` (all `astromesh`); `collection` (`embeddings`) | `collection` is the table name. On first query or ingest it runs `CREATE EXTENSION IF NOT EXISTS vector` and creates the table and a `doc_id` index. Filters are bound parameters |

Re-ingesting a document deletes its previous chunks first, on every backend, so the index
never holds two versions of one document.

## `reranking`

| Key | Default | Effect |
|---|---|---|
| `enabled` | `false` | Turns reranking on |
| `provider` | `cross_encoder` | `cross_encoder`, `cohere`, or any registered `reranker` |
| `model` | per provider | `cross_encoder`: `cross-encoder/ms-marco-MiniLM-L-6-v2`; `cohere`: `rerank-english-v3.0` |
| `api_key` | none | `cohere` only |
| `top_k` | `retrieval.top_k` | How many hits the reranker keeps |

The reranker sees every candidate (up to `retrieval.candidates`) and replaces each hit's
`score` with its own; the retrieval score stays in `details`.

## `retrieval`

| Key | Default | Effect |
|---|---|---|
| `pattern` | `naive` | `naive`, `hybrid`, `multi_query`, `hyde`. See [Patterns](/astromesh/rag/patterns/) |
| `top_k` | `5` | Default number of hits `query()` returns; also sizes `candidates` and `reranking.top_k` when they are not set |
| `candidates` | `top_k * 2` | How many hits each retriever fetches, per query, before fusion and reranking |
| `similarity_threshold` | none | Drops vector hits whose cosine is below this |
| `hybrid.fusion` | `rrf` | `hybrid` only: `rrf` or `weighted`. Also accepted as `retrieval.fusion`, which wins if both are set |
| `hybrid.weights` | none | `hybrid` only: `[vector, bm25]` weights for `weighted` fusion. Exactly two weights; defaults to `[0.5, 0.5]` |
| `bm25_path` | none | `hybrid` only: a JSON file for the BM25 index, loaded at build time if it exists and rewritten after every ingestion |
| `multi_query.variants` | `3` | `multi_query` only: how many rewrites to ask the LLM for. The flat form `retrieval.variants` is also accepted; the nested one wins |

**How many hits come back** is `retrieval.top_k` by default; an explicit
`pipeline.query(q, k=...)` overrides it.

**`similarity_threshold`** filters inside the vector retriever, before fusion and before
reranking, with the cosine the index returned. It never touches BM25 hits, and it is never
applied to reranker scores: cross-encoder scores are logits, not 0–1 similarities, so a
threshold of 0.7 would mean something different for every model. A threshold that is too
high shows up in the trace as a `retrieve vector` stage with `out: 0`.

**`reranking.top_k`** caps what the reranker returns; the query then keeps the first `k` of
those. With `reranking.top_k: 3` and `query(q, k=5)` you get 3 hits.

**Fusion.** RRF scores each chunk `sum(1 / (60 + rank))` over the lists it appears in, so
it needs no score calibration. `weighted` min-max normalizes each list to 0–1 and adds the
weighted scores, which lets you favor one retriever; a list whose scores are all equal
normalizes to 1.0. `multi_query` and `hyde` always use RRF.

**BM25 lives in memory.** `hybrid` builds it during the same ingestion as the vector index.
With a persistent vector store, set `bm25_path`, or after a restart the vector side still
has your documents and BM25 has none (the query still runs, on vector hits only). Each
query scans every chunk, which is fine for thousands of chunks and slow for millions.

## The result

`pipeline.query` returns a `QueryResult`:

| Field | Content |
|---|---|
| `hits` | `Hit(chunk, score, source, details)`, best first. `source` is `vector`, `bm25` or `bm25+vector`; `details` holds every score the hit collected (`vector`, `bm25`, `rrf` or `fused`, `rerank`) |
| `context` | The hit texts joined by blank lines, ready for a prompt |
| `trace` | One dict per stage: `stage` (`transform`, `retrieve`, `fuse`, `rerank`, `context`), `name`, `ms`, `in`, `out`, and `error` if it failed |
| `to_list()` | `[{"doc_id", "content", "metadata", "score", "source"}]`, where `doc_id` is the chunk id: the shape the Astromesh runtime consumes |

An empty or blank query returns an empty result without calling anything. A failing
transform or reranker raises `StageError(stage, name, cause)`; a failing retriever is
recorded in the trace and only raises when every retriever failed.
