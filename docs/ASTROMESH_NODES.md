# Astromesh Nodes — Multi-Node Roles

**What it does:** Lets you split one big Astromesh instance into multiple specialized nodes, each running only the services it needs.

**Related docs:** [OS](ASTROMESH_OS.md) · [Maia](ASTROMESH_MAIA.md) · [Architecture](GENERAL_ARCHITECTURE.md)

---

## The Big Picture

A single Astromesh node runs everything: API, agents, inference, memory, tools, channels, RAG, and observability. That's simple, but it doesn't scale. You might want:

- A **gateway** that only handles incoming requests and routes them
- **Workers** that run agents with tools and memory
- **Inference nodes** that run GPU-heavy LLM models

Astromesh Nodes lets you do this by enabling/disabling services per node and connecting them with peer links.

```
                    Internet
                       │
                ┌──────┴──────┐
                │   Gateway   │  services: api, channels
                │  port 8000  │  forwards agent requests →
                └──────┬──────┘
                       │
            ┌──────────┼─────────┐
            │                    │
     ┌──────┴──────┐       ┌─────┴───────┐
     │   Worker    │       │  Inference  │  services: inference
     │  port 8000  │──────►│  port 8000  │
     │             │       │             │
     │ agents,     │       │  GPU models │
     │ tools,      │       │             │
     │ memory, rag │       └─────────────┘
     └─────────────┘
```

---

## How It Works

### 1. Choose Which Services Each Node Runs

In `runtime.yaml` (or a config profile), list services as `true`/`false`:

```yaml
# Gateway: only API + channels + observability
spec:
  services:
    api: true
    agents: false
    inference: false
    memory: false
    tools: false
    channels: true
    rag: false
    observability: true
```

The **ServiceManager** reads this and tells the runtime "only bootstrap what's enabled." If `agents: false`, no agent YAML files are loaded. If `inference: false`, no LLM providers are initialized.

### Available Services

| Service | What it does |
|---------|-------------|
| `api` | FastAPI HTTP + WebSocket endpoints |
| `agents` | Loads and runs agent definitions from YAML |
| `inference` | LLM providers (Ollama, vLLM, etc.) |
| `memory` | Conversation, semantic, and episodic memory backends |
| `tools` | Tool registry and execution |
| `channels` | External messaging (WhatsApp, etc.) |
| `rag` | Document ingestion and retrieval |
| `observability` | Tracing, metrics, cost tracking |

If you don't set `spec.services` at all, everything defaults to `true` (same as a single-node setup).

### 2. Tell Nodes About Each Other with Peers

When a gateway receives a request for an agent it doesn't run, it needs to know where to forward it. That's what `spec.peers` is for:

```yaml
# Gateway config — knows about the worker
spec:
  services:
    api: true
    agents: false
    channels: true
  peers:
    - name: worker-1
      url: http://worker:8000
      services: [agents, tools, memory, rag]
```

```yaml
# Worker config — knows about the inference node
spec:
  services:
    agents: true
    tools: true
    memory: true
  peers:
    - name: inference-1
      url: http://inference:8000
      services: [inference]
```

The **PeerClient** uses this to:
- Forward requests to the right node based on what services it offers
- Round-robin across multiple peers offering the same service
- Periodically health-check peers and skip unhealthy ones

### 3. Use a Config Profile

Instead of writing `runtime.yaml` from scratch, use one of the pre-built profiles:

| Profile | File | Services enabled |
|---------|------|-----------------|
| Full (single node) | `config/profiles/full.yaml` | All |
| Gateway | `config/profiles/gateway.yaml` | api, channels, observability |
| Worker | `config/profiles/worker.yaml` | api, agents, memory, tools, rag, observability |
| Inference | `config/profiles/inference.yaml` | api, inference, observability |

Copy the profile you need to `config/runtime.yaml` and adjust the peer URLs.

---

## Example: 3-Node Setup with Docker Compose

The project includes a Docker Compose file that runs this exact topology:

```bash
cd docker
docker compose -f docker-compose.mesh.yml up -d
```

This starts:
- **gateway** (port 8000) — receives HTTP requests, forwards to worker
- **worker** (port 8001) — runs agents with tools and memory
- **inference** (port 8002) — runs LLM models with Ollama

Plus shared infrastructure: PostgreSQL, Redis, Ollama.

---

## Validation Warnings

The ServiceManager catches common misconfigurations:

| Warning | What it means |
|---------|---------------|
| "agents enabled without tools" | Your agents won't be able to call tools |
| "agents enabled without memory" | Your agents won't have conversation history |

These are warnings, not errors — the node will still start.

---

## CLI Commands

```bash
# What services are enabled on this node?
astromeshctl services

# What peers does this node know about?
astromeshctl peers list
```

---

## How Forwarding Works

When the gateway gets `POST /v1/agents/my-agent/run`:

1. Gateway checks: "Do I have `agents` service enabled?" → No
2. Gateway asks PeerClient: "Who has `agents`?" → worker-1
3. Gateway forwards the request to `http://worker:8000/v1/agents/my-agent/run`
4. Worker runs the agent, returns the response
5. Gateway sends the response back to the caller

The caller doesn't know (or care) that the request was forwarded. It's transparent.

---

## Limitations

- **Static topology** — Peers are defined in YAML at startup. If a node goes down, you have to update config and restart.
- **Manual URLs** — You need to know the address of each peer node.
- **No automatic discovery** — Nodes don't find each other.

To solve these, see [Astromesh Maia](ASTROMESH_MAIA.md) — it replaces static peers with automatic discovery and failure detection.

---

## What's Next

- If you're running a single node, this is all you need (or just use the `full.yaml` profile).
- If you want nodes to discover each other automatically, handle failures, and elect a leader, see [Astromesh Maia](ASTROMESH_MAIA.md).
