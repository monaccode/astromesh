 # Astromesh Agent Runtime Platform
 
 Multi-model, multi-pattern AI agent runtime with declarative YAML configuration.
 
 Astromesh lets you define intelligent agents, connect them to multiple LLM providers, equip them with tools and memory, and deploy them as a REST/WebSocket API — all through YAML configuration files.
 
 **Related docs**: [Architecture](architecture.md) · [Configuration guide](CONFIGURATION_GUIDE.md) · [WhatsApp integration](WHATSAPP_INTEGRATION.md)

 ## Features

 - **6 LLM Providers** — Ollama, OpenAI-compatible, vLLM, llama.cpp, HuggingFace TGI, ONNX Runtime
 - **Intelligent Model Routing** — Cost-optimized, latency-optimized, quality-first, round-robin, and capability-match strategies with automatic circuit breaker and fallback
 - **6 Orchestration Patterns** — ReAct, Plan & Execute, Parallel Fan-Out, Pipeline, Supervisor, Swarm
 - **3 Memory Types** — Conversational (Redis/PostgreSQL/SQLite), Semantic (pgvector/ChromaDB/Qdrant/FAISS), Episodic (PostgreSQL)
 - **RAG Pipeline** — 4 chunking strategies, 3 embedding providers, 4 vector stores, 2 rerankers
 - **Tool System** — Internal tools, MCP (stdio/SSE/HTTP), webhooks, RAG-as-tool
 - **ML Model Registry** — ONNX and PyTorch serving, classifier and embedding training pipelines
 - **MCP Server** — Expose your agents as MCP tools for other systems
 - **Guardrails** — PII redaction, topic filtering, cost limits, content filtering
 - **Observability** — OpenTelemetry tracing, Prometheus metrics, cost tracking with budgets
 - **WhatsApp Integration** — Receive and reply to WhatsApp messages via Meta Business Cloud API with webhook verification, signature validation, and rate limiting
 - **Declarative Config** — Define everything in YAML with `apiVersion: astromesh/v1`

 ## Quick Start

 ### Prerequisites

 - Python 3.12+
 - [uv](https://docs.astral.sh/uv/) package manager

 ### Installation

 ```bash
 # Clone the repository
 git clone <repo-url> astromesh-platform
 cd astromesh-platform

 # Install with uv
 uv sync

 # Install with optional backends
 uv sync --extra redis --extra postgres --extra observability

 # Install everything
 uv sync --extra all
 ```

 ### Run the API Server

 ```bash
 # Start the server
 uv run uvicorn astromesh.api.main:app --host 0.0.0.0 --port 8000

 # Or with auto-reload for development
 uv run uvicorn astromesh.api.main:app --reload
 ```

 ### Create Your First Agent

 Create a file at `config/agents/my-agent.agent.yaml`:

 ```yaml
 apiVersion: astromesh/v1
 kind: Agent
 metadata:
   name: my-agent
   version: "1.0.0"

 spec:
   identity:
     display_name: "My First Agent"
     description: "A simple assistant"

   model:
     primary:
       provider: ollama
       model: "llama3.1:8b"
       endpoint: "http://localhost:11434"
       parameters:
         temperature: 0.7
         max_tokens: 2048

   prompts:
     system: |
       You are a helpful assistant.

   orchestration:
     pattern: react
     max_iterations: 10
 ```

 ### Talk to Your Agent

 ```bash
 # Health check
 curl http://localhost:8000/v1/health

 # List agents
 curl http://localhost:8000/v1/agents

 # Run agent
 curl -X POST http://localhost:8000/v1/agents/my-agent/run \
   -H "Content-Type: application/json" \
   -d '{"query": "Hello!", "session_id": "session-1"}'
 ```

 ## Docker Deployment

 The full stack includes Ollama, vLLM, embeddings, PostgreSQL (pgvector), Redis, OpenTelemetry Collector, Prometheus, and Grafana.

 ```bash
 cd docker
 docker compose up -d
 ```

 | Service | Port | Description |
 |---------|------|-------------|
 | astromesh | 8000 | Agent Runtime API |
 | ollama | 11434 | Local LLM inference |
 | vllm | 8001 | High-throughput LLM serving |
 | embeddings | 8002 | HuggingFace Text Embeddings |
 | reranker | 8003 | HuggingFace Reranker |
 | postgres | 5432 | PostgreSQL + pgvector |
 | redis | 6379 | Conversation memory cache |
 | otel-collector | 4317/4318 | OpenTelemetry Collector |
 | prometheus | 9090 | Metrics storage |
 | grafana | 3000 | Dashboards (admin/admin) |

 ## API Reference

 ### REST Endpoints

 | Method | Path | Description |
 |--------|------|-------------|
 | GET | `/v1/health` | Health check and version |
 | GET | `/v1/agents` | List all loaded agents |
 | GET | `/v1/agents/{name}` | Get agent details |
 | POST | `/v1/agents/{name}/run` | Execute an agent |
 | GET | `/v1/memory/{agent}/history/{session}` | Get conversation history |
 | DELETE | `/v1/memory/{agent}/history/{session}` | Clear conversation history |
 | GET | `/v1/memory/{agent}/semantic` | Search semantic memory |
 | GET | `/v1/tools` | List registered tools |
 | POST | `/v1/tools/execute` | Execute a tool |
 | POST | `/v1/rag/ingest` | Ingest documents into RAG |
 | POST | `/v1/rag/query` | Query the RAG pipeline |

 ### WebSocket

 ```
 ws://localhost:8000/v1/ws/agent/{agent_name}
 ```

 Send JSON messages:

 ```json
 {"query": "What is...", "session_id": "s1"}
 ```

 Receive streamed token responses in real-time.

 ## Project Structure

 ```
 astromesh-platform/
 ├── astromesh/
 │   ├── api/                  # FastAPI app and routes
 │   │   ├── main.py           # App entry point
 │   │   ├── routes/           # REST endpoints
 │   │   └── ws.py             # WebSocket streaming
 │   ├── core/                 # Core runtime components
 │   │   ├── model_router.py   # Multi-provider routing + circuit breaker
 │   │   ├── memory.py         # Memory manager (3 types, 3 strategies)
 │   │   ├── tools.py          # Tool registry and execution
 │   │   ├── prompt_engine.py  # Jinja2 prompt templating
 │   │   └── guardrails.py     # Input/output guardrails
 │   ├── providers/            # LLM provider implementations
 │   │   ├── base.py           # Protocol + shared types
 │   │   ├── ollama_provider.py
 │   │   ├── openai_compat.py
 │   │   ├── vllm_provider.py
 │   │   ├── llamacpp_provider.py
 │   │   ├── hf_tgi_provider.py
 │   │   └── onnx_provider.py
 │   ├── orchestration/        # Agent execution patterns
 │   │   ├── patterns.py       # ReAct, Plan&Execute, FanOut, Pipeline
 │   │   ├── supervisor.py     # Supervisor pattern
 │   │   └── swarm.py          # Swarm pattern
 │   ├── memory/               # Memory backend implementations
 │   │   ├── backends/         # Redis, SQLite, PG, pgvector, Chroma, Qdrant, FAISS
 │   │   └── strategies/       # sliding_window, summary, token_budget
 │   ├── rag/                  # RAG pipeline
 │   │   ├── chunking/         # fixed, recursive, sentence, semantic
 │   │   ├── embeddings/       # HF API, SentenceTransformers, Ollama
 │   │   ├── stores/           # pgvector, ChromaDB, Qdrant, FAISS
 │   │   ├── reranking/        # cross-encoder, Cohere
 │   │   └── pipeline.py       # RAG orchestrator
 │   ├── mcp/                  # Model Context Protocol
 │   │   ├── client.py         # MCP client (stdio/SSE/HTTP)
 │   │   └── server.py         # MCP server (expose agents as tools)
 │   ├── ml/                   # ML model management
 │   │   ├── model_registry.py # Model registry
 │   │   ├── serving/          # ONNX + PyTorch serving
 │   │   └── training/         # Classifier + embedding training
 │   ├── observability/        # Monitoring and tracing
 │   │   ├── telemetry.py      # OpenTelemetry integration
 │   │   ├── metrics.py        # Prometheus metrics
 │   │   └── cost_tracker.py   # Usage and cost tracking
 │   └── runtime/
 │       └── engine.py         # Agent runtime engine (YAML → agent)
 ├── config/                   # YAML configuration files
 │   ├── runtime.yaml          # Runtime settings
 │   ├── providers.yaml        # Provider registry
 │   ├── agents/               # Agent definitions
 │   └── rag/                  # RAG pipeline configs
 ├── docker/                   # Docker Compose stack
 │   ├── docker-compose.yaml   # Full 10-service stack
 │   ├── Dockerfile            # CPU image
 │   ├── Dockerfile.gpu        # GPU image (CUDA 12.1)
 │   └── init.sql              # PostgreSQL schema
 ├── tests/                    # Test suite (113 tests)
 └── pyproject.toml            # Project config (uv)
 ```

 ## Optional Dependencies

 Install only what you need:

 ```bash
 uv sync --extra redis          # Redis conversation backend
 uv sync --extra postgres       # PostgreSQL backends
 uv sync --extra sqlite         # SQLite conversation backend
 uv sync --extra chromadb       # ChromaDB vector store
 uv sync --extra qdrant         # Qdrant vector store
 uv sync --extra faiss          # FAISS vector store
 uv sync --extra embeddings     # SentenceTransformers
 uv sync --extra onnx           # ONNX Runtime
 uv sync --extra ml             # PyTorch
 uv sync --extra observability  # OpenTelemetry + Prometheus
 uv sync --extra mcp            # Model Context Protocol
 uv sync --extra all            # Everything (except ml)
 ```

 ## Development

 ```bash
 # Install dev dependencies
 uv sync --group dev

 # Run tests
 uv run pytest -v

 # Run with coverage
 uv run pytest --cov=astromesh

 # Lint
 uv run ruff check astromesh/ tests/
 ```

 ## Configuration

 All configuration uses YAML with `apiVersion: astromesh/v1`. See the [Configuration Guide](docs/configuration-guide.md) for detailed documentation on:

 - Agent definitions (`kind: Agent`)
 - Provider registry (`kind: ProviderConfig`)
 - RAG pipelines (`kind: RAGPipeline`)
 - Runtime settings (`kind: RuntimeConfig`)

 ## Architecture

 See [docs/architecture.md](docs/architecture.md) for the full system architecture, including the 4-layer design, component interactions, and data flow diagrams.

 ## WhatsApp Integration

 See [docs/whatsapp-integration.md](docs/whatsapp-integration.md) for the full setup guide covering Meta Business account configuration, environment variables, agent setup, deployment, and troubleshooting.

 ## License

 MIT

