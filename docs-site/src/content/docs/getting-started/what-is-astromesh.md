---
title: What is Astromesh?
description: Overview of the AI Agent Runtime Platform
---

Astromesh is a **multi-model, multi-pattern AI agent runtime platform**. You define agents in YAML, connect them to LLM providers, equip them with tools and memory, and deploy them as REST or WebSocket APIs — all without writing application code for each new agent.

Astromesh is not an LLM wrapper. It is a full **agent runtime** with identity, state, memory, permissions, tools, guardrails, and orchestration patterns — all decoupled, composable, and configurable.

## The Problem

Building production AI agents means stitching together a long list of concerns:

- **LLM provider integration** — each provider has its own API, auth model, and quirks. You want to swap providers, set up fallbacks, and route requests intelligently.
- **Tool execution** — agents need to call functions, query APIs, and interact with external systems. You need schema generation, permissions, rate limiting, and error handling.
- **Memory management** — conversational history, semantic recall, and episodic event logs all require different storage backends and retention strategies.
- **Prompt engineering** — system prompts need templating, context injection, and version control.
- **Safety and compliance** — PII detection, content filtering, topic restrictions, and cost limits must wrap every agent interaction.
- **Orchestration** — simple request-response is not enough. Agents need multi-step reasoning (ReAct), planning (PlanAndExecute), parallel execution, and supervisor delegation.

Most teams end up building bespoke agent frameworks that are tightly coupled to a single provider, hard to test, and expensive to maintain. Astromesh provides a unified runtime that handles all of these concerns declaratively.

## Who It's For

- **Backend engineers** building AI-powered features who want to define agent behavior in config rather than code.
- **ML engineers** who need to swap models, providers, and orchestration strategies without rewriting application logic.
- **DevOps / Platform teams** deploying and operating agent workloads with observability, health checks, and infrastructure-as-code patterns.

## Key Concepts

### Agents

An agent is the central unit in Astromesh. Each agent is defined in a YAML file following the `apiVersion: astromesh/v1, kind: Agent` schema. An agent definition includes:

- **Identity** — display name, description, namespace
- **Model** — primary provider and model, optional fallback, routing strategy
- **Prompts** — Jinja2-templated system prompt with variable injection
- **Orchestration** — which reasoning pattern to use and its constraints
- **Tools** — which tools the agent can invoke
- **Memory** — conversation history, semantic search, episodic logs
- **Guardrails** — input and output safety filters

Agents are loaded at startup from `config/agents/*.agent.yaml` (dev mode) or `/etc/astromesh/agents/*.agent.yaml` (system mode). Adding a new agent is as simple as dropping a YAML file in the directory.

### Providers

Astromesh supports **six LLM backends** out of the box:

| Provider | Use Case |
|----------|----------|
| **Ollama** | Local development, easy model management |
| **OpenAI** | GPT-4o, o-series, cloud-hosted models |
| **vLLM** | High-throughput production serving with continuous batching |
| **llama.cpp** | Lightweight GGUF model serving |
| **HuggingFace TGI** | GPU-optimized transformer inference |
| **ONNX Runtime** | Cross-platform optimized inference |

The **Model Router** selects which provider handles each request based on configurable strategies: `cost_optimized`, `latency_optimized`, `quality_first`, or `round_robin`. A built-in **circuit breaker** tracks provider health — after 3 consecutive failures, a provider enters a 60-second cooldown and traffic is rerouted to the fallback.

### Orchestration Patterns

Astromesh ships with **six orchestration patterns** that control how an agent reasons and acts:

| Pattern | Description |
|---------|-------------|
| **ReAct** | Reason-Act loop. The agent thinks, picks an action, observes the result, and repeats. |
| **PlanAndExecute** | The agent generates a plan upfront, then executes each step sequentially. |
| **ParallelFanOut** | Distributes subtasks across parallel executions and merges results. |
| **Pipeline** | Chains multiple processing stages sequentially, each transforming the output. |
| **Supervisor** | A supervisor agent delegates tasks to specialized worker agents. |
| **Swarm** | Multiple peer agents collaborate through message passing. |

Each pattern is selected per-agent in YAML and can be tuned with `max_iterations` and `timeout_seconds`.

### Memory

Astromesh manages three types of memory, each suited to different recall needs:

- **Conversational** — chat history for maintaining context within a session. Backends: Redis, PostgreSQL, SQLite. Strategies: `sliding_window`, `summary`, `token_budget`.
- **Semantic** — vector embeddings for similarity search over documents and past interactions. Backends: pgvector, ChromaDB, Qdrant, FAISS.
- **Episodic** — structured event logs for tracking what happened and when. Backend: PostgreSQL.

Memory types are composable. An agent can use all three simultaneously — conversational memory for short-term context, semantic memory for knowledge retrieval, and episodic memory for audit trails.

### Tools

Agents interact with the outside world through tools. Astromesh supports four tool types:

- **Internal (Python)** — Python functions registered with the `ToolRegistry`. Schema is auto-generated for LLM function calling.
- **MCP Servers** — Tools exposed through the Model Context Protocol via stdio, SSE, or streamable HTTP transports.
- **Webhooks** — HTTP endpoints called as tools, useful for integrating existing services.
- **RAG-as-Tool** — RAG pipelines exposed as tools that agents can invoke to search knowledge bases.

All tools support permissions, rate limiting, and schema validation.

### Guardrails

Guardrails wrap agent input and output with safety checks:

- **PII Detection** — identifies and redacts personally identifiable information (names, emails, phone numbers, etc.)
- **Topic Filtering** — restricts agents to approved topic domains
- **Cost Limits** — caps token usage per turn or per session
- **Content Filtering** — blocks harmful, inappropriate, or off-topic content

Guardrails are configured per-agent in YAML and execute as part of the agent pipeline — input guardrails fire before the LLM call, output guardrails fire after.

## Architecture

Astromesh follows a **four-layer architecture** where everything flows through the Runtime Engine:

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                  │
│         REST endpoints  ·  WebSocket streaming          │
├─────────────────────────────────────────────────────────┤
│                    Runtime Engine                       │
│         YAML loading  ·  Agent lifecycle                │
├─────────────────────────────────────────────────────────┤
│                    Core Services                        │
│  ModelRouter · MemoryManager · ToolRegistry · Guardrails│
├─────────────────────────────────────────────────────────┤
│                    Infrastructure                       │
│  Providers · Backends · Vector Stores · Observability   │
└─────────────────────────────────────────────────────────┘
```

**API Layer** — FastAPI-based REST and WebSocket endpoints. Agents are invoked via `POST /v1/agents/{name}/run` or streamed via `WS /v1/ws/agent/{name}`. Channel adapters (WhatsApp, etc.) also live here.

**Runtime Engine** — Loads agent YAML definitions, bootstraps `AgentRuntime` instances, and manages agent lifecycle. This is the orchestrator that wires together all the services below.

**Core Services** — The four pillars: `ModelRouter` handles provider selection and failover, `MemoryManager` coordinates memory reads and writes, `ToolRegistry` manages tool discovery and execution, and `GuardrailsEngine` enforces safety policies.

**Infrastructure** — The concrete implementations: LLM providers, database backends, vector stores, message brokers, and the OpenTelemetry observability stack.

## Deployment Options

Astromesh supports multiple deployment models depending on your scale and operational requirements:

| Deployment | Best For | Guide |
|-----------|----------|-------|
| **Standalone (from source)** | Development, CI, experimentation | [View guide →](/astromesh/deployment/standalone/) |
| **Astromesh Node** | Native system service (Linux, macOS, Windows) | [View guide →](/astromesh/node/introduction/) |
| **Docker Single Node** | Containerized single-server deployment | [View guide →](/astromesh/deployment/docker-single/) |
| **Docker Maia** | Multi-node mesh with gossip protocol | [View guide →](/astromesh/deployment/docker-maia/) |
| **Docker Maia + GPU** | Multi-node mesh with GPU model serving | [View guide →](/astromesh/deployment/docker-maia-gpu/) |
| **Helm / Kubernetes** | Cloud-native orchestrated deployment | [View guide →](/astromesh/deployment/helm-kubernetes/) |
| **ArgoCD / GitOps** | GitOps-driven continuous deployment | [View guide →](/astromesh/deployment/argocd-gitops/) |

## Next Steps

Ready to get started? Head to the [Installation](/astromesh/getting-started/installation/) guide to set up Astromesh on your machine.
