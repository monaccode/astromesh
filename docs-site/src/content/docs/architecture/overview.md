---
title: Architecture Overview
description: High-level view of Astromesh components and design principles
---

Astromesh is a **multi-model, multi-pattern AI agent runtime platform**. It provides a complete framework for defining, deploying, and operating intelligent agents through declarative YAML configuration files rather than imperative code.

This page offers a high-level map of the system -- its layered architecture, core capabilities, design philosophy, and project layout. For detailed breakdowns of each layer, see [Four-Layer Design](/astromesh/architecture/four-layer-design/). For a step-by-step trace of a request, see [Agent Execution Pipeline](/astromesh/architecture/agent-pipeline/).

## The 4-Layer Architecture

Every component in Astromesh belongs to one of four layers. Each layer has a single responsibility and communicates only with its adjacent layers through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                   │
│         REST endpoints  ·  WebSocket streaming          │
├─────────────────────────────────────────────────────────┤
│                    Runtime Engine                        │
│         YAML loading  ·  Agent lifecycle                 │
├─────────────────────────────────────────────────────────┤
│                    Core Services                         │
│  ModelRouter · MemoryManager · ToolRegistry · Guardrails │
├─────────────────────────────────────────────────────────┤
│                    Infrastructure                        │
│  Providers · Backends · Vector Stores · Observability    │
└─────────────────────────────────────────────────────────┘
```

**Layer 1 -- API Layer** accepts HTTP and WebSocket requests and routes them to the Runtime Engine. It never contains business logic -- it only translates transport protocols into runtime calls.

**Layer 2 -- Runtime Engine** is the control plane. It loads YAML configuration files, bootstraps `Agent` instances with all their dependencies wired together, and manages agent lifecycle. When a request arrives, the engine looks up the target agent and delegates execution to it.

**Layer 3 -- Core Services** are the building blocks that every agent uses. The ModelRouter picks the best LLM provider. The MemoryManager assembles conversation context. The ToolRegistry manages tool discovery and execution. The GuardrailsEngine enforces safety policies. The PromptEngine renders Jinja2 templates.

**Layer 4 -- Infrastructure** contains the concrete implementations: LLM provider adapters, memory backend drivers, vector store connectors, the RAG pipeline, MCP integration, the ML model registry, and the observability stack.

### How layers communicate

Each layer only talks to its immediate neighbors. The API Layer calls into the Runtime Engine but never directly accesses a provider. The Runtime Engine delegates to Core Services but does not know which vector store is backing semantic memory. Core Services call into Infrastructure through abstract interfaces (Python Protocols and abstract base classes), meaning any backend can be swapped without touching the layers above it.

### Channel Adapters

Channel adapters sit **above** the API Layer, connecting external messaging platforms to the Agent Runtime. Each adapter translates platform-specific webhook events into Astromesh agent requests and formats agent responses back to the platform's expected format.

```
External Platforms          Channel Adapters              Agent Runtime
┌───────────┐          ┌──────────────────────┐      ┌──────────────┐
│ WhatsApp  │─webhook─►│  WhatsApp Adapter    │─────►│              │
│ Business  │◄──reply──│  (verify, parse,     │◄─────│  AgentRuntime│
│ Cloud API │          │   send, signatures)  │      │  .run()      │
└───────────┘          └──────────────────────┘      └──────────────┘
```

Currently supported channels:

- **WhatsApp** -- Receives messages via Meta Business Cloud API webhooks, validates signatures with `app_secret`, and sends replies through the WhatsApp Business Cloud API.

Channel configuration is defined in `config/channels.yaml` with environment variable references (`${VAR_NAME}`) for secrets. Each channel maps to a `default_agent` that handles its conversations.

## Feature Summary

Astromesh ships with a broad set of capabilities out of the box:

| Category | Capabilities |
|----------|-------------|
| **LLM Providers** | 6 providers -- Ollama, OpenAI-compatible, vLLM, llama.cpp, HuggingFace TGI, ONNX Runtime |
| **Model Routing** | 5 strategies -- cost-optimized, latency-optimized, quality-first, round-robin, capability-match. Automatic circuit breaker with fallback chains. |
| **Orchestration** | 6 patterns -- ReAct, Plan & Execute, Parallel Fan-Out, Pipeline, Supervisor, Swarm |
| **Memory** | 3 types -- Conversational (Redis/PostgreSQL/SQLite), Semantic (pgvector/ChromaDB/Qdrant/FAISS), Episodic (PostgreSQL). 3 strategies -- sliding window, summary, token budget. |
| **RAG Pipeline** | 4 chunking strategies, 3 embedding providers, 4 vector stores, 2 rerankers |
| **Tool System** | Internal Python tools, MCP tools (stdio/SSE/HTTP), webhook tools, RAG-as-tool |
| **MCP Integration** | Client (connect to external MCP servers) and Server (expose agents as MCP tools) |
| **Guardrails** | PII redaction, topic filtering, content filtering, cost limits, max length |
| **ML Registry** | ONNX and PyTorch model serving, classifier and embedding training pipelines |
| **Observability** | OpenTelemetry tracing, Prometheus metrics, cost tracking with budget enforcement |
| **Channels** | WhatsApp Business Cloud API with webhook verification and signature validation |
| **Configuration** | Declarative YAML with `apiVersion: astromesh/v1` for all resource types |

## Design Principles

Astromesh follows six design principles that guide every architectural decision:

### Declarative over imperative

Agents, providers, RAG pipelines, and runtime settings are all defined in YAML files with a Kubernetes-inspired schema (`apiVersion`, `kind`, `metadata`, `spec`). You describe **what** you want, not **how** to wire it up. The Runtime Engine handles instantiation and dependency injection.

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: support-agent
  version: "1.0.0"
spec:
  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
  orchestration:
    pattern: react
    max_iterations: 10
```

### Protocol-based interfaces

All LLM providers implement `ProviderProtocol`, a `runtime_checkable` Python Protocol. This means any class that implements the required methods (`complete()`, `stream()`, `health_check()`, `supports_tools()`, `estimated_cost()`) automatically satisfies the interface -- no inheritance required. The same pattern applies to memory backends, vector stores, and other extension points.

### Pluggable backends

Every storage system, LLM provider, embedding model, vector store, and orchestration strategy is swappable. Want to switch from Redis to PostgreSQL for conversation memory? Change one line in YAML. Want to add a new LLM provider? Implement the Protocol and register it. The core system does not need to change.

### Async throughout

All I/O operations -- provider calls, memory reads/writes, tool execution, HTTP handlers -- use Python's `async/await`. This ensures the system can handle many concurrent agent executions without blocking threads, which is critical for a runtime that may be orchestrating multiple LLM calls and tool invocations per request.

### Graceful degradation

When things go wrong, Astromesh degrades gracefully rather than failing hard:

- The **circuit breaker** in the ModelRouter opens after 3 consecutive failures to a provider, with a 60-second cooldown before retrying. Meanwhile, requests automatically route to fallback providers.
- **Optional dependencies** are detected at import time. If Redis is not installed, the system falls back to SQLite for conversation memory. If OpenTelemetry is not installed, tracing uses a no-op implementation.
- **Rust native extensions** provide 5-50x speedups for CPU-bound paths, but the system runs correctly with pure Python fallbacks when Rust extensions are not compiled.

### Minimal core dependencies

The core runtime requires only five packages: **FastAPI**, **httpx**, **PyYAML**, **Pydantic**, and **Jinja2**. Everything else -- Redis, PostgreSQL, ChromaDB, OpenTelemetry, MCP, PyTorch -- is an optional extra that you install only if you need it.

```bash
uv sync                    # Core only -- 5 dependencies
uv sync --extra redis      # Add Redis backend
uv sync --extra postgres   # Add PostgreSQL backends
uv sync --extra all        # Install everything
```

## Project Structure

The following tree shows the key directories and files in the Astromesh codebase:

```
astromesh-platform/
├── astromesh/                       # Main Python package
│   ├── api/                         # Layer 1: API Layer
│   │   ├── main.py                  # FastAPI app entry point, bootstrap
│   │   ├── routes/                  # REST endpoint modules
│   │   │   ├── agents.py            # /v1/agents/* routes
│   │   │   ├── memory.py            # /v1/memory/* routes
│   │   │   ├── tools.py             # /v1/tools/* routes
│   │   │   ├── rag.py               # /v1/rag/* routes
│   │   │   └── health.py            # /v1/health route
│   │   └── ws.py                    # WebSocket streaming + ConnectionManager
│   │
│   ├── runtime/                     # Layer 2: Runtime Engine
│   │   └── engine.py                # AgentRuntime: YAML → Agent instances
│   │
│   ├── core/                        # Layer 3: Core Services
│   │   ├── model_router.py          # Multi-provider routing + circuit breaker
│   │   ├── memory.py                # MemoryManager (3 types, 3 strategies)
│   │   ├── tools.py                 # ToolRegistry and execution
│   │   ├── prompt_engine.py         # Jinja2 prompt rendering
│   │   └── guardrails.py            # Input/output guardrails
│   │
│   ├── providers/                   # Layer 4: LLM provider implementations
│   │   ├── base.py                  # ProviderProtocol + shared types
│   │   ├── ollama_provider.py       # Ollama (/api/chat)
│   │   ├── openai_compat.py         # OpenAI-compatible (/v1/chat/completions)
│   │   ├── vllm_provider.py         # vLLM (OpenAI-compatible)
│   │   ├── llamacpp_provider.py     # llama.cpp (OpenAI-compatible)
│   │   ├── hf_tgi_provider.py       # HuggingFace TGI (OpenAI-compatible)
│   │   └── onnx_provider.py         # ONNX Runtime (local inference)
│   │
│   ├── orchestration/               # Layer 4: Agent execution patterns
│   │   ├── patterns.py              # ReAct, PlanAndExecute, FanOut, Pipeline
│   │   ├── supervisor.py            # Supervisor pattern
│   │   └── swarm.py                 # Swarm pattern
│   │
│   ├── memory/                      # Layer 4: Memory backend implementations
│   │   ├── backends/                # Redis, SQLite, PostgreSQL, pgvector,
│   │   │                            # ChromaDB, Qdrant, FAISS
│   │   └── strategies/              # sliding_window, summary, token_budget
│   │
│   ├── rag/                         # Layer 4: RAG pipeline
│   │   ├── pipeline.py              # RAG orchestrator
│   │   ├── chunking/                # fixed, recursive, sentence, semantic
│   │   ├── embeddings/              # HF API, SentenceTransformers, Ollama
│   │   ├── stores/                  # pgvector, ChromaDB, Qdrant, FAISS
│   │   └── reranking/               # cross-encoder, Cohere
│   │
│   ├── mcp/                         # Layer 4: Model Context Protocol
│   │   ├── client.py                # MCP client (stdio/SSE/HTTP)
│   │   └── server.py                # MCP server (expose agents as tools)
│   │
│   ├── ml/                          # Layer 4: ML model management
│   │   ├── model_registry.py        # Model registry
│   │   ├── serving/                 # ONNX + PyTorch model servers
│   │   └── training/                # Classifier + embedding training
│   │
│   ├── channels/                    # Channel adapters (above API Layer)
│   │   └── whatsapp.py              # WhatsApp Business Cloud adapter
│   │
│   └── observability/               # Layer 4: Monitoring and tracing
│       ├── telemetry.py             # OpenTelemetry integration
│       ├── metrics.py               # Prometheus metrics
│       └── cost_tracker.py          # Usage and cost tracking
│
├── config/                          # YAML configuration files
│   ├── runtime.yaml                 # Runtime settings (kind: RuntimeConfig)
│   ├── providers.yaml               # Provider registry (kind: ProviderConfig)
│   ├── channels.yaml                # Channel adapter configuration
│   ├── agents/                      # Agent definitions (kind: Agent)
│   │   └── *.agent.yaml
│   └── rag/                         # RAG pipeline configs (kind: RAGPipeline)
│       └── *.rag.yaml
│
├── docker/                          # Docker deployment
│   ├── docker-compose.yaml          # Full 10-service stack
│   ├── Dockerfile                   # CPU image
│   ├── Dockerfile.gpu               # GPU image (CUDA 12.1)
│   └── init.sql                     # PostgreSQL schema
│
├── tests/                           # Test suite
│   └── *.py                         # pytest with asyncio_mode = "auto"
│
└── pyproject.toml                   # Project config (uv + hatchling)
```

## What's Next

- **[Four-Layer Design](/astromesh/architecture/four-layer-design/)** -- Detailed walkthrough of each architectural layer, including component diagrams, configuration tables, and interface contracts.
- **[Agent Execution Pipeline](/astromesh/architecture/agent-pipeline/)** -- Step-by-step trace of how a request flows through an agent, from HTTP arrival to response delivery.
- **[Kubernetes-Style Architecture](/astromesh/architecture/k8s-architecture/)** -- How Astromesh's resource model mirrors Kubernetes CRDs, and the future operator design for cloud-native deployment.
