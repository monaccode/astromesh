# Astromech Agent Runtime Platform — Design Document

**Date:** 2026-03-06
**Status:** Approved
**Based on:** NEXUS Agent Runtime Spec v1.0 (renamed NEXUS → Astromech)

---

## 1. Overview

**Astromech** is a multi-model, multi-framework, multi-pattern AI agent runtime platform with persistent memory, MCP/tool extensibility, and declarative configuration. Any business vertical can define, deploy, and operate intelligent agents from configuration — without rewriting code.

Astromech is not an LLM wrapper. It is an **agent runtime** with identity, state, memory, permissions, tools, and orchestration patterns — all decoupled and configurable.

---

## 2. Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package name | `astromech` | Clean, short, matches project name |
| Config API version | `apiVersion: astromech/v1` | Direct rename from NEXUS spec |
| Architecture | Literal spec implementation | Faithful to proven spec design |
| Tooling | `uv + pyproject.toml` | Modern, fast, lockfile support |
| Provider priority | All equal | Full implementation for all 6 providers |
| Runtime language | Python | ML/AI ecosystem, async native, modern typing |
| API framework | FastAPI | Async, auto-docs, Pydantic, WebSocket |
| Config format | YAML | Human-readable, Jinja2 templating |
| Default vector DB | pgvector | Same Postgres for everything |
| Default LLM server | Ollama | Easy to operate, stable API |
| High-perf LLM server | vLLM | Continuous batching, PagedAttention |
| Embeddings server | HF TEI | GPU-optimized, batch inference |
| Conversational memory | Redis | Ultra-fast, native TTL |
| Orchestration | Pattern-based | Each pattern is a module, chosen by config |
| Extensibility | MCP + Internal tools | Open standard + internal flexibility |
| Observability | OpenTelemetry | Vendor-agnostic |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Astromech Agent Runtime                            │
│                                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  Agent       │  │  Agent       │  │  Agent       │  │  Agent      │ │
│  │  Config      │  │  Config      │  │  Config      │  │  Config     │ │
│  │  (YAML)      │  │  (YAML)      │  │  (YAML)      │  │  (YAML)    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬─────┘ │
│         │                  │                  │                  │       │
│  ┌──────▼──────────────────▼──────────────────▼──────────────────▼─────┐│
│  │                    Agent Lifecycle Manager                          ││
│  │  ┌───────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  ││
│  │  │ Identity & │  │  Prompt     │  │ Orchestration│  │ Guardrails│  ││
│  │  │ Permissions│  │  Engine     │  │ Patterns     │  │ Engine    │  ││
│  │  └───────────┘  └─────────────┘  └──────────────┘  └───────────┘  ││
│  └────────────────────────────┬───────────────────────────────────────┘│
│                               │                                         │
│  ┌────────────────────────────▼───────────────────────────────────────┐│
│  │                      Core Services Layer                           ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐    ││
│  │  │ Model Router  │  │ Memory       │  │ Tool / MCP Registry   │    ││
│  │  │ (multi-model) │  │ Manager      │  │                       │    ││
│  │  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────┘    ││
│  └─────────┼──────────────────┼───────────────────────┼───────────────┘│
│            │                  │                       │                 │
│  ┌─────────▼──────┐  ┌───────▼────────┐  ┌──────────▼──────────────┐  │
│  │ Provider Layer  │  │ Storage Layer  │  │ Extension Layer         │  │
│  │ • Ollama        │  │ • PostgreSQL   │  │ • MCP Servers (stdio/   │  │
│  │ • vLLM          │  │ • pgvector     │  │   SSE/streamable HTTP)  │  │
│  │ • llama.cpp     │  │ • Redis        │  │ • Internal Tools        │  │
│  │ • OpenAI compat │  │ • ChromaDB     │  │ • Function Registry     │  │
│  │ • HuggingFace   │  │ • Qdrant       │  │ • Webhook Actions       │  │
│  │ • Custom ONNX   │  │ • SQLite       │  │ • RAG Pipelines         │  │
│  └─────────────────┘  └────────────────┘  └─────────────────────────┘  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Infrastructure Layer                              ││
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────────────┐  ││
│  │  │ GPU Mgmt  │  │ Model     │  │ OTel     │  │ Event Bus         │  ││
│  │  │ (CUDA/    │  │ Registry  │  │ Collector │  │ (Redis Streams /  │  ││
│  │  │  ROCm)    │  │ & Cache   │  │          │  │  NATS / internal) │  ││
│  │  └──────────┘  └───────────┘  └──────────┘  └───────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Project Structure

```
astromech-platform/
├── config/
│   ├── agents/                     # *.agent.yaml
│   ├── rag/                        # *.rag.yaml
│   ├── ml/                         # *.train.yaml
│   ├── providers.yaml
│   └── runtime.yaml
├── astromech/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── model_router.py         # Multi-model routing engine
│   │   ├── memory.py               # Memory manager (conv + semantic + episodic)
│   │   ├── tools.py                # Tool & MCP registry
│   │   ├── prompt_engine.py        # Template rendering + variable injection
│   │   └── guardrails.py           # Input/output guardrails
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # ProviderProtocol
│   │   ├── ollama_provider.py
│   │   ├── vllm_provider.py
│   │   ├── llamacpp_provider.py
│   │   ├── hf_tgi_provider.py
│   │   ├── onnx_provider.py
│   │   └── openai_compat.py
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── patterns.py             # ReAct, Plan&Execute, Parallel, Pipeline
│   │   ├── supervisor.py
│   │   └── swarm.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   ├── redis_conv.py
│   │   │   ├── pg_conv.py
│   │   │   ├── sqlite_conv.py
│   │   │   ├── pgvector_sem.py
│   │   │   ├── chroma_sem.py
│   │   │   ├── qdrant_sem.py
│   │   │   ├── faiss_sem.py
│   │   │   └── pg_episodic.py
│   │   └── strategies/
│   │       ├── __init__.py
│   │       ├── sliding_window.py
│   │       ├── summary.py
│   │       └── token_budget.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── chunking/
│   │   │   ├── __init__.py
│   │   │   ├── fixed.py
│   │   │   ├── recursive.py
│   │   │   ├── semantic.py
│   │   │   └── sentence.py
│   │   ├── embeddings/
│   │   │   ├── __init__.py
│   │   │   ├── hf.py
│   │   │   ├── st.py
│   │   │   └── ollama.py
│   │   ├── stores/
│   │   │   ├── __init__.py
│   │   │   ├── pgvector.py
│   │   │   ├── chroma.py
│   │   │   ├── qdrant.py
│   │   │   └── faiss_store.py
│   │   └── reranking/
│   │       ├── __init__.py
│   │       ├── cross_encoder.py
│   │       └── cohere.py
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── model_registry.py
│   │   ├── training/
│   │   │   ├── __init__.py
│   │   │   ├── classifier.py
│   │   │   └── embeddings.py
│   │   └── serving/
│   │       ├── __init__.py
│   │       ├── onnx_runtime.py
│   │       └── torch_serve.py
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── client.py               # MCP client (stdio, SSE, HTTP)
│   │   └── server.py               # Expose agents AS MCP tools
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── telemetry.py
│   │   ├── metrics.py
│   │   └── cost_tracker.py
│   ├── runtime/
│   │   ├── __init__.py
│   │   └── engine.py               # AgentRuntime + Agent classes
│   └── api/
│       ├── __init__.py
│       ├── main.py                 # FastAPI app
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── agents.py
│       │   ├── memory.py
│       │   ├── tools.py
│       │   └── rag.py
│       └── ws.py                   # WebSocket streaming
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.gpu
│   ├── docker-compose.yaml
│   └── init.sql
├── models/                         # Local model storage
├── tests/
│   ├── __init__.py
│   ├── test_model_router.py
│   ├── test_memory.py
│   ├── test_tools.py
│   ├── test_patterns.py
│   ├── test_rag.py
│   └── test_api.py
├── docs/
│   └── plans/
├── pyproject.toml
├── CLAUDE.md
└── .gitignore
```

---

## 5. Core Modules

### 5.1 Model Router
- Routes requests to optimal provider based on strategy (cost/latency/quality/round-robin/capability)
- Circuit breaker with 3-failure threshold and 60s cooldown
- Health checks per provider
- Automatic fallback chain
- Response normalization to unified `CompletionResponse`

### 5.2 Provider Adapters (6 providers)
All implement `ProviderProtocol`: complete, stream, health_check, supports_tools, supports_vision, estimated_cost.
- **Ollama** — `/api/chat`, native tools (v0.4+)
- **vLLM** — OpenAI-compatible API
- **llama.cpp** — llama.cpp server API
- **HF TGI** — HuggingFace Text Generation Inference
- **ONNX** — ONNX Runtime for custom models
- **OpenAI compat** — Any OpenAI-compatible API (OpenAI, Azure, Groq, etc.)

### 5.3 Memory Manager
Orchestrates 3 memory types per agent:
- **Conversational** — Redis/PG/SQLite backends, strategies: sliding_window, summary, token_budget
- **Semantic** — pgvector/ChromaDB/Qdrant/FAISS, embedding-based recall
- **Episodic** — PostgreSQL, event/action history with importance scoring

### 5.4 Tool & MCP Registry
- Internal Python tools with handler functions
- MCP servers via 3 transports (stdio, SSE, streamable HTTP)
- Webhook tools (external HTTP)
- RAG-as-tool
- Rate limiting, human-in-the-loop approval

### 5.5 Orchestration Patterns (6 patterns)
- **ReAct** — Thought → Action → Observation loop
- **Plan & Execute** — Generate plan, execute steps, synthesize
- **Parallel Fan-Out** — Decompose → parallel execution → combine
- **Pipeline** — Sequential chain, output→input
- **Supervisor** — Supervisor delegates to specialized sub-agents
- **Swarm** — Emergent multi-agent behavior

### 5.6 Prompt Engine
- Jinja2 templating for system prompts
- Variable injection from context providers (RAG, database, etc.)
- Reusable prompt templates

### 5.7 Guardrails
- **Input:** PII detection/redaction, topic filtering
- **Output:** Hallucination check (self-consistency/RAG grounding), toxicity filter, cost limits

### 5.8 RAG Pipeline
- Configurable via YAML
- Chunking strategies: fixed, recursive, semantic, sentence
- Embedding providers: HuggingFace, SentenceTransformers, Ollama
- Vector stores: pgvector, ChromaDB, Qdrant, FAISS
- Optional reranking (cross-encoder, Cohere)

### 5.9 ML Registry
- Local model management (ONNX, PyTorch)
- Training pipelines (classifier, embeddings fine-tune)
- Auto-register on training completion

### 5.10 Observability
- OpenTelemetry traces for every agent run
- Prometheus metrics (request count, latency, cost)
- Cost tracker per agent/session/model

---

## 6. Agent Configuration Schema

```yaml
apiVersion: astromech/v1
kind: Agent
metadata:
  name: <agent-name>
  version: "<semver>"
  namespace: <namespace>
  labels: {}

spec:
  identity:
    display_name: ""
    description: ""
    avatar: ""

  model:
    primary:
      provider: ollama|vllm|llamacpp|openai_compat|huggingface|onnx
      model: "<model-id>"
      endpoint: "<url>"
      parameters: {temperature, max_tokens, top_p, ...}
    fallback: [...]
    routing:
      strategy: cost_optimized|latency_optimized|quality_first|round_robin|capability_match
      max_cost_per_request: <float>
      max_latency_ms: <int>

  prompts:
    system: |
      <Jinja2 template>
    templates: {}
    context_providers: [{type, source|query}]

  memory:
    conversational: {enabled, backend, ttl, max_turns, strategy, summary_model}
    semantic: {enabled, backend, embedding_model, similarity_threshold, max_results}
    episodic: {enabled, backend, retention_days}

  tools:
    internal: [{name, handler, description, parameters, requires_approval}]
    mcp_servers: [{name, transport, command|endpoint, args}]

  orchestration:
    pattern: react|plan_execute|parallel|pipeline|supervisor|swarm
    max_iterations: <int>
    timeout_seconds: <int>

  guardrails:
    input: [{type, action|blocked_topics}]
    output: [{type, strategy|threshold|max_tokens_per_turn|max_cost_per_session}]

  permissions:
    allowed_actions: [...]
    denied_actions: [...]
    data_access: [{database, tables, operations}]
```

---

## 7. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/agents/{name}/run` | Execute agent |
| GET | `/v1/agents` | List agents |
| GET | `/v1/agents/{name}` | Agent details |
| GET | `/v1/agents/{name}/tools` | Agent tools |
| POST | `/v1/rag/{pipeline}/ingest` | Ingest documents |
| POST | `/v1/rag/{pipeline}/query` | Query RAG |
| GET | `/v1/health` | Health check |
| WS | `/v1/agents/{name}/stream` | Streaming via WebSocket |

---

## 8. Docker Compose Stack

| Service | Image | Purpose |
|---------|-------|---------|
| astromech | Custom Dockerfile | Runtime API |
| ollama | ollama/ollama | Local LLM |
| vllm | vllm/vllm-openai | High-perf LLM |
| embeddings | HF TEI | Embeddings |
| reranker | HF TEI | Reranking |
| postgres | pgvector/pgvector:pg16 | DB + vectors |
| redis | redis:7-alpine | Cache + conv memory |
| otel-collector | otel/opentelemetry-collector-contrib | Telemetry |
| prometheus | prom/prometheus | Metrics |
| grafana | grafana/grafana | Dashboards |

---

## 9. Implementation Phases

| Phase | Content | Files |
|-------|---------|-------|
| **0: Foundation** | uv setup, pyproject.toml, project scaffolding, all provider adapters, Model Router, FastAPI skeleton | ~15 files |
| **1: Core Agent** | Agent YAML config loader, AgentRuntime engine, ReAct pattern, Internal tools, Prompt engine | ~8 files |
| **2: Memory & RAG** | All memory backends + strategies, RAG pipeline + chunking + embeddings + stores + reranking | ~20 files |
| **3: Multi-Pattern** | Plan&Execute, Parallel, Pipeline, Supervisor, Swarm patterns | ~5 files |
| **4: MCP** | MCP client (3 transports), tool discovery, Agent-as-MCP-server | ~3 files |
| **5: ML** | Local model registry, ONNX/PyTorch serving, training pipelines | ~6 files |
| **6: Observability** | OTel setup, Prometheus metrics, cost tracker | ~3 files |
| **7: Hardening** | Guardrails engine, permissions, rate limiting, Docker files, tests | ~15 files |
