# Astromech Architecture

## Overview

Astromech is a multi-model, multi-pattern AI agent runtime platform. It follows a 4-layer architecture where each layer has a clear responsibility and communicates with adjacent layers through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                   │
│         REST endpoints  ·  WebSocket streaming           │
├─────────────────────────────────────────────────────────┤
│                    Runtime Engine                        │
│         YAML loading  ·  Agent lifecycle                 │
├─────────────────────────────────────────────────────────┤
│                    Core Services                        │
│  ModelRouter · MemoryManager · ToolRegistry · Guardrails │
├─────────────────────────────────────────────────────────┤
│                    Infrastructure                       │
│  Providers · Backends · Vector Stores · Observability    │
└─────────────────────────────────────────────────────────┘
```

## Layer 1: API Layer

**Module:** `astromech/api/`

The API layer exposes the runtime through HTTP and WebSocket interfaces using FastAPI.

### REST API (`astromech/api/main.py` + `routes/`)

- **Agents** — List, inspect, and execute agents via `/v1/agents`
- **Memory** — Query and manage conversation history via `/v1/memory`
- **Tools** — List and execute tools via `/v1/tools`
- **RAG** — Ingest documents and query knowledge bases via `/v1/rag`
- **Health** — Health check and version at `/v1/health`

### WebSocket (`astromech/api/ws.py`)

- Real-time streaming at `/v1/ws/agent/{name}`
- `ConnectionManager` tracks active connections per agent
- Sends partial responses as tokens are generated

## Layer 2: Runtime Engine

**Module:** `astromech/runtime/engine.py`

The runtime engine is the heart of Astromech. It handles two things:

### AgentRuntime

Bootstraps the system by scanning `config/agents/*.agent.yaml`, parsing each file, and assembling a fully wired `Agent` object with all its dependencies (router, memory, tools, orchestration pattern, prompt engine).

### Agent

Executes the full agent pipeline for each request:

```
Query → Guardrails (input) → Memory Context → Prompt Rendering
  → Orchestration Pattern → Model Routing → Tool Execution
  → Response → Guardrails (output) → Memory Persistence
```

Each agent has:
- A **ModelRouter** for multi-provider inference
- A **MemoryManager** for conversational, semantic, and episodic memory
- A **ToolRegistry** for tool access
- An **OrchestrationPattern** that controls the reasoning loop
- A **PromptEngine** for Jinja2-based prompt rendering
- **Guardrails** for input/output safety

## Layer 3: Core Services

### Model Router (`astromech/core/model_router.py`)

Routes completion requests across multiple providers with intelligent selection.

```
                    ┌─────────────┐
    Request ──────► │ ModelRouter  │
                    │             │
                    │ 1. Rank     │──► Strategy-based ordering
                    │ 2. Try      │──► Circuit breaker check
                    │ 3. Fallback │──► Next provider on failure
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          ┌───────┐   ┌────────┐   ┌───────┐
          │Ollama │   │ OpenAI │   │ vLLM  │  ...
          └───────┘   └────────┘   └───────┘
```

**Routing Strategies:**

| Strategy | Behavior |
|----------|----------|
| `cost_optimized` | Cheapest provider first (based on `estimated_cost()`) |
| `latency_optimized` | Fastest provider first (exponential moving average) |
| `quality_first` | Highest quality score first |
| `round_robin` | Rotate across providers evenly |
| `capability_match` | Filter by required capabilities (tools, vision) |

**Circuit Breaker:**
- Opens after 3 consecutive failures
- 60-second cooldown before half-open retry
- Automatic recovery on success

### Memory Manager (`astromech/core/memory.py`)

Manages three types of memory with pluggable backends and strategies.

```
                    ┌──────────────────┐
                    │  MemoryManager   │
                    │                  │
                    │ build_context()  │──► Assemble context from all memory types
                    │ persist_turn()   │──► Store conversation turns
                    └──────┬───────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────────┐ ┌───────────┐ ┌───────────┐
    │Conversational│ │ Semantic  │ │ Episodic  │
    │              │ │           │ │           │
    │Redis/PG/     │ │pgvector/  │ │PostgreSQL │
    │SQLite        │ │Chroma/    │ │           │
    │              │ │Qdrant/    │ │           │
    │              │ │FAISS      │ │           │
    └──────────────┘ └───────────┘ └───────────┘
```

**Memory Strategies:**

| Strategy | Description |
|----------|-------------|
| `sliding_window` | Keep the last N turns |
| `summary` | Compress older turns into summaries |
| `token_budget` | Fit as many turns as possible within a token limit |

### Tool Registry (`astromech/core/tools.py`)

Central registry for all tools an agent can use.

**Tool Types:**
- `internal` — Python functions registered directly
- `mcp` — Tools from MCP servers (stdio, SSE, HTTP transports)
- `webhook` — External HTTP endpoints
- `rag` — RAG pipeline exposed as a tool

Features: rate limiting, permission-based filtering, schema generation for LLM function calling.

### Prompt Engine (`astromech/core/prompt_engine.py`)

Jinja2-based prompt rendering with `SilentUndefined` (missing variables render as empty strings instead of errors). Supports template registration and variable injection.

### Guardrails Engine (`astromech/core/guardrails.py`)

Applies safety checks on both input and output:

| Guardrail | Description |
|-----------|-------------|
| `pii_detection` | Detects and redacts emails, phones, SSNs, credit cards |
| `topic_filter` | Blocks messages matching forbidden topics |
| `max_length` | Enforces character limits on input |
| `cost_limit` | Enforces token-per-turn limits on output |
| `content_filter` | Blocks messages with forbidden keywords |

## Layer 4: Infrastructure

### LLM Providers (`astromech/providers/`)

All providers implement `ProviderProtocol` (a `runtime_checkable` Protocol):

| Provider | Backend | Endpoint Style |
|----------|---------|----------------|
| `OllamaProvider` | Ollama | `/api/chat` |
| `OpenAICompatProvider` | OpenAI API | `/v1/chat/completions` |
| `VLLMProvider` | vLLM | OpenAI-compatible |
| `LlamaCppProvider` | llama.cpp | OpenAI-compatible |
| `HFTGIProvider` | HuggingFace TGI | OpenAI-compatible |
| `ONNXProvider` | ONNX Runtime | Local inference |

Each provider reports: `estimated_cost()`, `supports_tools()`, `supports_vision()`, `avg_latency_ms`.

### Orchestration Patterns (`astromech/orchestration/`)

Control how agents reason and use tools:

| Pattern | Description |
|---------|-------------|
| `ReAct` | Think → Act → Observe loop until done |
| `PlanAndExecute` | Create a plan, then execute steps sequentially |
| `ParallelFanOut` | Send to multiple sub-models simultaneously, merge results |
| `Pipeline` | Chain multiple steps sequentially |
| `Supervisor` | Delegate sub-tasks to worker agents |
| `Swarm` | Agents hand off conversations to each other |

### RAG Pipeline (`astromech/rag/`)

Full retrieval-augmented generation pipeline:

```
Documents → Chunking → Embedding → Vector Store
                                        │
Query → Embedding → Vector Search ──────┘
                         │
                    Reranking → Top-K results
```

**Components:**

| Stage | Options |
|-------|---------|
| Chunking | Fixed, Recursive, Sentence, Semantic |
| Embeddings | HuggingFace API, SentenceTransformers, Ollama |
| Vector Store | pgvector, ChromaDB, Qdrant, FAISS |
| Reranking | Cross-encoder, Cohere |

### MCP Integration (`astromech/mcp/`)

- **Client** — Connect to external MCP servers via stdio, SSE, or HTTP. Discover and invoke remote tools.
- **Server** — Expose Astromech agents as MCP tools via a JSON-RPC endpoint at `/mcp`, allowing other systems to call your agents.

### ML Model Registry (`astromech/ml/`)

- **Registry** — Register, version, load, and serve ML models
- **Serving** — ONNX Runtime and PyTorch model servers
- **Training** — Classifier and embedding fine-tuning pipelines (stubs)

### Observability (`astromech/observability/`)

```
Agent Execution ──► TelemetryManager ──► OpenTelemetry Collector ──► Jaeger/Zipkin
                         │
                    MetricsCollector ──► Prometheus ──► Grafana
                         │
                    CostTracker ──► Usage records + budget alerts
```

- **Telemetry** — Distributed tracing with OpenTelemetry (with `_NoOpSpan` fallback when OTel is not installed)
- **Metrics** — Request counts, latency histograms, active agents gauge via Prometheus
- **Cost Tracking** — Per-provider usage records, budget enforcement, grouped cost reports

## Data Flow

### Agent Execution Flow

```
1. HTTP POST /v1/agents/{name}/run
   └── AgentRuntime.run(agent_name, query, session_id)
       └── Agent.run(query, session_id)
           ├── MemoryManager.build_context()          # Load memory
           ├── PromptEngine.render(system_prompt)      # Render prompt
           ├── ToolRegistry.get_tool_schemas()          # Get available tools
           └── Pattern.execute()                        # Run reasoning loop
               ├── model_fn() → ModelRouter.route()     #   LLM call
               │   └── Provider.complete()              #     Provider execution
               └── tool_fn() → ToolRegistry.execute()   #   Tool call
           ├── MemoryManager.persist_turn(user)         # Save user turn
           └── MemoryManager.persist_turn(assistant)    # Save response
```

### Configuration Loading Flow

```
config/
├── agents/*.agent.yaml    ──► AgentRuntime.bootstrap()
│                               ├── Parse YAML
│                               ├── Build ModelRouter
│                               ├── Build MemoryManager
│                               ├── Build ToolRegistry
│                               ├── Select OrchestrationPattern
│                               └── Create Agent instance
├── providers.yaml         ──► Provider registration
├── rag/*.rag.yaml         ──► RAG pipeline configuration
└── runtime.yaml           ──► API and runtime defaults
```

## Design Principles

- **Declarative over imperative** — Agents are defined in YAML, not code
- **Protocol-based interfaces** — All providers implement `ProviderProtocol` (Python Protocols)
- **Pluggable backends** — Every storage, provider, and strategy is swappable
- **Async throughout** — All I/O operations use `async/await`
- **Graceful degradation** — Circuit breakers, fallback providers, optional dependencies
- **Minimal core dependencies** — Only FastAPI, httpx, PyYAML, Pydantic, Jinja2 required; everything else is optional
