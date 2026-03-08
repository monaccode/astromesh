# Astromesh
### Agent Runtime Platform for building AI agents

> Build, orchestrate and run AI agents with multi-model routing, tools, memory, and RAG — all configured declaratively.

Astromesh is an open-source runtime for agentic systems, designed to standardize how AI agents execute, reason, and interact with external systems.

**Think of it as Kubernetes for AI Agents.**

> ⭐ If you find this project useful, consider starring the repository.

---

## Why Astromesh

Most AI applications repeatedly rebuild the same infrastructure:

- model orchestration
- tool execution
- memory systems
- RAG pipelines
- agent reasoning loops
- observability
- cost control

Astromesh centralizes these capabilities into a single runtime platform.

Instead of writing orchestration logic yourself, you define agents declaratively and let the runtime manage execution.

---

## Documentation

- **Tech overview**: [`docs/TECH_OVERVIEW.md`](docs/TECH_OVERVIEW.md)
- **General architecture**: [`docs/GENERAL_ARCHITECTURE.md`](docs/GENERAL_ARCHITECTURE.md)
- **Kubernetes-style architecture diagrams**: [`docs/K8S_ARCHITECTURE.md`](docs/K8S_ARCHITECTURE.md)
- **Configuration guide**: [`docs/CONFIGURATION_GUIDE.md`](docs/CONFIGURATION_GUIDE.md)
- **WhatsApp integration**: [`docs/WHATSAPP_INTEGRATION.md`](docs/WHATSAPP_INTEGRATION.md)

---

## Key Features

### Multi-Model Runtime

Run agents across multiple LLM providers:

- Ollama
- OpenAI-compatible APIs
- vLLM
- llama.cpp
- HuggingFace TGI
- ONNX Runtime

The built-in **Model Router** automatically selects the best model using strategies such as:

- cost optimized
- latency optimized
- quality first
- round robin
- capability match

---

### Multiple Agent Reasoning Patterns

Astromesh includes several orchestration strategies:

| Pattern | Description |
|---|---|
| ReAct | reasoning + tool usage loop |
| Plan & Execute | generate plan then execute |
| Pipeline | sequential processing |
| Parallel Fan-Out | multi-model collaboration |
| Supervisor | hierarchical agents |
| Swarm | distributed agent collaboration |

---

### Built-in Memory System

Agents can maintain multiple memory layers:

| Memory Type | Purpose |
|---|---|
| Conversational | chat history |
| Semantic | vector embeddings |
| Episodic | event logs |

Supported backends:

- Redis
- PostgreSQL
- SQLite
- pgvector
- ChromaDB
- Qdrant
- FAISS

---

### Retrieval-Augmented Generation (RAG)

Astromesh includes a complete RAG pipeline:

- document chunking
- embeddings
- vector search
- reranking
- context injection

Supported vector stores:

- pgvector
- ChromaDB
- Qdrant
- FAISS

---

### Tool System

Agents can interact with external systems using tools.

Supported tool types:

- Python functions
- MCP tools
- Webhooks
- RAG pipelines

The runtime automatically exposes tools to models using structured schemas.

---

### Messaging Channels

Astromesh supports external messaging integrations.

**Current integration:**
- WhatsApp (Meta Cloud API)

**Future integrations:**
- Slack
- Telegram
- Discord
- Web chat
- Voice assistants

---

### Observability

Built-in monitoring stack:

- OpenTelemetry tracing
- Prometheus metrics
- cost tracking
- token usage monitoring

---

## Architecture

Astromesh follows a layered architecture (see also [`docs/GENERAL_ARCHITECTURE.md`](docs/GENERAL_ARCHITECTURE.md) for the full reference):

```
API Layer
REST / WebSocket
        ↓
Runtime Engine
Agent lifecycle and execution
        ↓
Core Services
Model Router · Memory Manager · Tool Registry · Guardrails
        ↓
Infrastructure
LLM Providers · Vector Databases · Observability · Storage Backends
```

---

## Quick Start

### Requirements

- Python 3.12+
- uv package manager

### Install uv

```bash
pip install uv
```

### Clone the repository

```bash
git clone https://github.com/your-org/astromesh
cd astromesh
```

### Install dependencies

```bash
uv sync
```

### Run the runtime

```bash
uv run uvicorn astromesh.api.main:app --reload
```

API will be available at `http://localhost:8000`

---

## Create Your First Agent

Create the file: `config/agents/my-agent.agent.yaml`

```yaml
apiVersion: astromesh/v1
kind: Agent

metadata:
  name: my-agent

spec:
  identity:
    display_name: "My Agent"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"

  prompts:
    system: |
      You are a helpful assistant.

  orchestration:
    pattern: react
```

### Run the Agent

```bash
curl -X POST http://localhost:8000/v1/agents/my-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query":"Hello","session_id":"demo"}'
```

---

## Example Use Cases

### AI Copilots
- developer assistants
- support agents
- internal knowledge assistants

### Autonomous Workflows
- document processing
- business automation
- API orchestration

### Multi-Agent Systems
- distributed reasoning
- hierarchical agents
- collaborative agents

### AI APIs
Expose agents as programmable services.

---

## Docker Deployment

Astromesh includes a full development stack:

```bash
docker compose up
```

Includes:

- Agent runtime API
- Ollama inference
- vLLM inference
- embeddings service
- PostgreSQL + pgvector
- Redis
- Prometheus
- Grafana

---

## Project Structure

```
astromesh/
 ├── api
 ├── runtime
 ├── core
 ├── providers
 ├── orchestration
 ├── memory
 ├── rag
 ├── channels
 └── observability
```

Configuration:

```
config/
 ├── agents/
 ├── rag/
 ├── providers.yaml
 └── runtime.yaml
```

---

## Roadmap

Planned capabilities:

- distributed agent execution
- GPU-aware model scheduling
- event-driven agents
- multi-tenant runtime
- agent lifecycle management
- agent marketplace

---

## Contributing

Contributions are welcome.

Ways to contribute:

- new providers
- orchestration patterns
- vector stores
- tools
- bug fixes
- documentation improvements

---

## License

MIT

---

## Community

Community resources coming soon:

- Discord
- Roadmap discussions
- Contributor guide

---

> ⭐ If you like Astromesh, give the repo a star. It helps the project reach more developers.