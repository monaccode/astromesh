# Astromesh Architecture

This document provides the **architecture diagrams for Astromesh**, designed in a style inspired by Kubernetes‑like control plane / data plane systems.

These diagrams are intended to be embedded directly in the project README or documentation.

---

# High-Level Architecture

Astromesh is designed as an **Agent Runtime Platform** with layered architecture.

```mermaid
flowchart TB
    ext["`**External Interfaces**
    REST API /v1/agents
    WebSocket API /v1/ws/agent/*
    WhatsApp Channel Meta Cloud API
    Future Channels Slack/Telegram`"]
    api["`**API / Channel Layer**
    FastAPI Routes: Agents, Memory, Tools, RAG
    WebSocket Gateway: Streaming tokens, Live sessions
    Channel Adapters: WhatsApp, Future adapters`"]
    cp["`**Agent Runtime Control Plane**
    AgentRuntime: Load YAML definitions, Bootstrap agents, Wire dependencies, Manage lifecycle
    Agent Execution Pipeline: Query → Guardrails → Memory → Prompt Rendering → Orchestration → Model Routing → Tool Calls → Response → Persistence`"]
    core["`**Core Services**
    Model Router: Provider select, Fallback, Circuit breaker, Capability match
    Memory Manager: Conversational, Semantic, Episodic, Context build
    Tool Registry: Internal tools, MCP tools, Webhooks, RAG as tool
    Guardrails: PII detect, Topic filter, Cost limits, Content rules`"]
    orch["`**Orchestration / Reasoning Layer**
    ReAct, Plan & Execute, Pipeline, Parallel Fan-Out, Supervisor, Swarm`"]
    plane["`**Execution Plane**
    LLM Providers: Ollama, OpenAI-compatible, vLLM, llama.cpp, HuggingFace TGI
    Retrieval / Knowledge: Chunking, Embeddings, Vector search, Reranking, pgvector / Chroma / Qdrant / FAISS
    ML / Inference: ONNX models, PyTorch, Registries`"]
    store["`**Storage / Observability**
    Redis, PostgreSQL, SQLite, Prometheus, OpenTelemetry
    pgvector, ChromaDB, Qdrant, Grafana, Cost Tracking`"]
    ext --> api --> cp --> core --> orch --> plane --> store
```

---

# Runtime Architecture (Control Plane + Workers)

This diagram shows how the **runtime behaves similarly to distributed platforms** such as Kubernetes.

```mermaid
flowchart TB
    cp["`**Astromesh Control Plane**
    AgentRuntime
    Config Loader (YAML)
    Dependency Wiring
    Routing Policies
    Guardrails Policies
    Tool Permissions
    Agent Lifecycle`"]
    wa["`**Agent Worker A**
    ReAct
    Tool Calls
    Prompt Rendering`"]
    wb["`**Agent Worker B**
    Plan & Execute
    Memory Access
    Model Routing`"]
    wc["`**Agent Worker C**
    Supervisor/Swarm
    Multi-Agent Flow
    Delegation`"]
    model["`**Model Execution**
    Ollama
    OpenAI-compatible APIs
    vLLM
    llama.cpp
    HuggingFace TGI
    ONNX Runtime`"]
    tools["`**Tool / Knowledge**
    Internal Python tools
    MCP tools
    Webhooks
    RAG pipelines
    Vector retrieval
    Reranking`"]
    state["`**State / Storage / Telemetry**
    Redis
    PostgreSQL / SQLite
    pgvector / ChromaDB / Qdrant / FAISS
    OpenTelemetry / Prometheus / Grafana
    Cost Tracking`"]
    cp --> wa
    cp --> wb
    cp --> wc
    wa --> model
    wb --> model
    wc --> model
    wa --> tools
    wb --> tools
    wc --> tools
    model --> state
    tools --> state
```

---

# Mermaid Architecture Diagram

GitHub supports Mermaid diagrams natively.

```mermaid
flowchart TB
    A[External Interfaces<br/>REST API / WebSocket / WhatsApp / Future Channels] --> B[API and Channel Layer<br/>FastAPI Routes / WebSocket Gateway / Channel Adapters]

    B --> C[Agent Runtime Control Plane<br/>YAML Loader / Bootstrap / Lifecycle / Dependency Wiring]
    C --> D[Agent Execution Pipeline<br/>Guardrails → Memory → Prompt → Orchestration → Routing → Tools → Persistence]

    D --> E[Core Services]
    E --> E1[Model Router]
    E --> E2[Memory Manager]
    E --> E3[Tool Registry]
    E --> E4[Guardrails]

    E --> F[Orchestration Layer]
    F --> F1[ReAct]
    F --> F2[Plan and Execute]
    F --> F3[Pipeline]
    F --> F4[Parallel Fan-Out]
    F --> F5[Supervisor]
    F --> F6[Swarm]

    F --> G[Execution Plane]
    G --> G1[LLM Providers<br/>Ollama / OpenAI-compatible / vLLM / llama.cpp / HF TGI / ONNX]
    G --> G2[Knowledge Layer<br/>Chunking / Embeddings / Vector Search / Reranking]
    G --> G3[Tools<br/>Internal / MCP / Webhooks / RAG]

    G --> H[Storage and Observability]
    H --> H1[Redis / PostgreSQL / SQLite]
    H --> H2[pgvector / ChromaDB / Qdrant / FAISS]
    H --> H3[Prometheus / Grafana / OpenTelemetry / Cost Tracking]
```



---

# Why This Architecture

This architecture separates **agent control**, **reasoning orchestration**, and **execution infrastructure** into distinct layers.

Benefits include:

- Declarative agent definitions
- Swappable LLM providers
- Pluggable memory backends
- Multi-agent orchestration
- Built-in observability
- Channel integrations
- Safe tool execution

This design allows Astromesh to scale from **single-agent applications to distributed agentic systems**.