# Astromesh OS Phase 2 — Containerized Node Roles

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/astromesh-os-phase2
**Depends on:** Phase 1 (v0.6.0)

---

## Overview

Phase 2 transforms Astromesh from a single-process daemon into a **containerized unit of processing with configurable roles**. Each Astromesh node is a Docker container running `astromeshd`, with its role defined entirely by configuration — not by code or image variant.

This phase establishes the building block for Phase 3 (Mesh): each container becomes a node in a distributed agent infrastructure.

**Key insight:** The container IS Astromesh. Not "tools in containers" — Astromesh itself runs as a container with a defined identity, capabilities, and peer relationships.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| What to containerize | Astromesh itself as role-based nodes | Building block for mesh, not just tool isolation |
| Role definition | Config-driven (no hardcoded roles) | Maximum flexibility, roles emerge from enabled services |
| Inter-node transport | HTTP via existing FastAPI API | Zero new protocol, reuses all existing endpoints |
| Peer discovery | Static config in runtime.yaml | Simple, portable, replaceable by dynamic discovery in mesh phase |
| Container image | Single universal image + config mounts | One image, multiple roles via mounted config |
| Container runtime | Docker (via Docker SDK for Python) | Mature SDK, well-documented, standard tooling |

---

## Architecture

```
+---------------------------------------------------+
| Astromesh Node (Docker container)                 |
|                                                   |
|  runtime.yaml defines which services activate:    |
|  +-------------+ +----------+ +---------------+   |
|  | API Gateway  | | Inference| | Memory / RAG  |   |
|  | (optional)   | |(optional)| | (optional)    |   |
|  +-------------+ +----------+ +---------------+   |
|  +-------------+ +----------+ +---------------+   |
|  | Tools       | | Channels | | Orchestration |   |
|  | (optional)   | |(optional)| | (optional)    |   |
|  +-------------+ +----------+ +---------------+   |
|                                                   |
|  astromeshd (always runs)                         |
|  peers: [{url: http://other-node:8000}]           |
+---------------------------------------------------+
```

### Multi-Node Example

```
[Gateway Node]  <-->  [Worker Node]  <-->  [Inference Node]
  api: true             agents: true          api: true
  channels: true        tools: true           inference: true
  observability: true   memory: true          observability: true
                        rag: true
```

- Gateway receives queries from external clients and channels
- Gateway forwards to Worker for agent execution
- Worker delegates inference requests to Inference Node
- All communication via HTTP (`/v1/*` endpoints)

---

## Services Configuration

### runtime.yaml Extension

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000

  # NEW: services section controls what this node activates
  services:
    api: true           # FastAPI endpoints (always true if node accepts requests)
    agents: true        # AgentRuntime loads and executes agents
    inference: false     # Local LLM providers (Ollama, vLLM, llama.cpp, HF TGI)
    memory: true        # Memory backends (Redis, SQLite, PG, vector stores)
    tools: true         # ToolRegistry and tool execution
    channels: false      # Channel adapters (WhatsApp, Slack, etc.)
    rag: false           # RAG pipeline (chunking, embeddings, reranking)
    observability: true  # OpenTelemetry tracing + Prometheus metrics

  # NEW: peer nodes this node knows about
  peers:
    - name: inference-1
      url: http://inference-node:8000
      services: [inference]
    - name: memory-1
      url: http://memory-node:8000
      services: [memory, rag]

  defaults:
    orchestration:
      pattern: react
      max_iterations: 10
```

### Service Behavior

| Service | When enabled | When disabled |
|---------|-------------|---------------|
| `api` | FastAPI starts, all enabled route groups registered | Only health endpoint responds |
| `agents` | AgentRuntime loads `*.agent.yaml`, `/v1/agents/*` active | `/v1/agents/*` returns 503 |
| `inference` | Providers initialized, health checks active | Model requests forwarded to peers |
| `memory` | Memory backends initialized, `/v1/memory/*` active | Memory requests forwarded to peers |
| `tools` | ToolRegistry loaded, tool execution available | `/v1/tools/*` returns 503 |
| `channels` | Channel adapters started, webhooks active | `/v1/channels/*` returns 503 |
| `rag` | RAG pipeline initialized, `/v1/rag/*` active | RAG requests forwarded to peers |
| `observability` | OTel + Prometheus exporters active | No telemetry exported |

### Peer Resolution

When a node needs a service it doesn't have enabled:
1. Look up peers that advertise that service
2. Forward the HTTP request to the peer
3. If multiple peers have the service, round-robin
4. If no peer has it, return 503 with message indicating which service is missing

---

## Config Profiles

Pre-built config files for common node roles:

### profiles/full.yaml

All services enabled. Single-node deployment, development.

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: full
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: true
    inference: true
    memory: true
    tools: true
    channels: true
    rag: true
    observability: true
  peers: []
```

### profiles/gateway.yaml

Public entry point. Receives external requests, routes to workers.

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: gateway
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: false
    inference: false
    memory: false
    tools: false
    channels: true
    rag: false
    observability: true
  peers:
    - name: worker-1
      url: http://worker:8000
      services: [agents, tools, memory, rag]
```

### profiles/worker.yaml

Agent execution. Runs agents, tools, memory, RAG.

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: worker
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: true
    inference: false
    memory: true
    tools: true
    channels: false
    rag: true
    observability: true
  peers:
    - name: inference-1
      url: http://inference:8000
      services: [inference]
```

### profiles/inference.yaml

LLM model serving. Runs Ollama/vLLM, responds to completion requests.

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: inference
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: false
    inference: true
    memory: false
    tools: false
    channels: false
    rag: false
    observability: true
  peers: []
```

---

## Components to Implement

### 1. ServiceManager (`astromesh/runtime/services.py`)

Central component that reads `spec.services` and controls subsystem initialization.

```python
class ServiceManager:
    """Manages which services are active on this node."""

    def __init__(self, services_config: dict[str, bool]):
        self._services = services_config

    def is_enabled(self, service: str) -> bool:
        """Check if a service is enabled on this node."""

    def enabled_services(self) -> list[str]:
        """List all enabled services."""

    def validate(self) -> list[str]:
        """Return warnings for invalid combos (e.g., agents without tools)."""
```

Responsibilities:
- Parse `spec.services` from runtime.yaml
- Provide `is_enabled()` check used by daemon, routes, and runtime
- Validate service combinations (warn if agents enabled without tools)
- Expose enabled services list for `/v1/system/status` and peer advertisement

### 2. PeerClient (`astromesh/runtime/peers.py`)

HTTP client that communicates with other Astromesh nodes.

```python
class PeerClient:
    """Manages communication with peer Astromesh nodes."""

    def __init__(self, peers_config: list[dict]):
        self._peers = peers_config
        self._http = httpx.AsyncClient(timeout=30.0)

    async def forward(self, service: str, method: str, path: str, **kwargs) -> dict:
        """Forward a request to a peer that has the given service."""

    async def health_check(self, peer_name: str) -> bool:
        """Check if a peer is reachable."""

    async def health_check_all(self) -> dict[str, bool]:
        """Health check all peers."""

    def find_peers(self, service: str) -> list[dict]:
        """Find peers that advertise a given service."""
```

Responsibilities:
- Maintain peer list with their advertised services
- Forward HTTP requests to peers when local service is disabled
- Round-robin load balancing across multiple peers with same service
- Health check peers (used by `astromeshctl peers list` and `/v1/system/doctor`)
- Timeout and error handling (peer unreachable → try next, then 503)

### 3. Dockerfile (`Dockerfile`)

Universal Astromesh OS image. Multi-stage build.

```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml .
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/
RUN pip install --no-cache-dir ".[all]"

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /opt/astromesh
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/astromeshd /usr/local/bin/
COPY --from=builder /usr/local/bin/astromeshctl /usr/local/bin/
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/

# Default config (can be overridden via volume mount)
COPY config/ /etc/astromesh/

EXPOSE 8000
ENTRYPOINT ["astromeshd", "--config", "/etc/astromesh"]
```

Image includes ALL optional dependencies. Role is determined by mounted config, not by image contents. One image to build, tag, and distribute.

### 4. Docker Compose Mesh (`docker/docker-compose.mesh.yml`)

Multi-node cluster for local development and testing.

```yaml
services:
  gateway:
    build: ..
    volumes:
      - ../config/profiles/gateway.yaml:/etc/astromesh/runtime.yaml
      - ../config/agents:/etc/astromesh/agents
    ports:
      - "8000:8000"
    depends_on:
      - worker
      - inference

  worker:
    build: ..
    volumes:
      - ../config/profiles/worker.yaml:/etc/astromesh/runtime.yaml
      - ../config/agents:/etc/astromesh/agents
    depends_on:
      - inference

  inference:
    build: ..
    volumes:
      - ../config/profiles/inference.yaml:/etc/astromesh/runtime.yaml

  # Supporting infrastructure
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"

  redis:
    image: redis:7-alpine

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: astromesh
      POSTGRES_USER: astromesh
      POSTGRES_PASSWORD: astromesh
```

### 5. Runtime Modifications

**`daemon/astromeshd.py`:**
- Read `spec.services` from config, create `ServiceManager`
- Read `spec.peers`, create `PeerClient`
- Pass both to `AgentRuntime.bootstrap()`
- Only initialize enabled subsystems

**`astromesh/runtime/engine.py`:**
- `AgentRuntime.bootstrap()` accepts `ServiceManager` and `PeerClient`
- Conditional initialization: only load agents if `agents` enabled, only init providers if `inference` enabled, etc.
- When a service is needed but not local, delegate to `PeerClient`

**`astromesh/api/main.py`:**
- Routes check `ServiceManager.is_enabled()` before handling
- Disabled service routes return 503 with descriptive message
- Alternative: only register route groups for enabled services

**`astromesh/api/routes/system.py`:**
- `/v1/system/status` includes `services` (enabled list) and `peers` (names + status)
- `/v1/system/doctor` checks peer health in addition to local checks

### 6. CLI Updates

**New command: `astromeshctl peers`**

| Command | Action | Endpoint |
|---------|--------|----------|
| `peers list` | Show all peers, their services, and health status | `GET /v1/system/status` (peers section) |
| `peers health` | Health check all peers | `GET /v1/system/doctor` (peer checks) |

**New command: `astromeshctl services`**

| Command | Action | Endpoint |
|---------|--------|----------|
| `services` | Show enabled/disabled services on this node | `GET /v1/system/status` (services section) |

**Updated commands:**

| Command | Change |
|---------|--------|
| `status` | Now shows node role profile, enabled services count, peer count |
| `doctor` | Now checks peer connectivity in addition to local health |

### 7. New API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v1/system/peers` | List peers with health status |
| `POST /v1/system/peers/{name}/health` | Health check specific peer |

Existing endpoints updated:
- `GET /v1/system/status` — adds `services` and `peers` fields
- `GET /v1/system/doctor` — adds peer health checks

---

## New Directory Structure

```
config/
+-- profiles/                  # Pre-built role configs
|   +-- full.yaml
|   +-- gateway.yaml
|   +-- worker.yaml
|   +-- inference.yaml

astromesh/
+-- runtime/
|   +-- engine.py              # Modified: conditional bootstrap
|   +-- services.py            # NEW: ServiceManager
|   +-- peers.py               # NEW: PeerClient

docker/
+-- docker-compose.mesh.yml    # NEW: multi-node cluster

cli/
+-- commands/
|   +-- peers.py               # NEW: peers list/health
|   +-- services.py            # NEW: services status

Dockerfile                     # NEW: universal Astromesh image
```

---

## New Dependencies

```toml
[project.optional-dependencies]
container = ["docker>=7.0.0"]
```

Added as optional extra. Only needed if running container management features.

---

## Future: Phase 3 (Mesh)

This phase prepares the foundation for mesh by establishing:
- **Node identity** — each node has a name, services, and peers
- **Inter-node communication** — HTTP forwarding between nodes
- **Service resolution** — "I need inference" → find peer that has it

Phase 3 replaces:
- Static peers → dynamic service discovery (mDNS, etcd, or gossip protocol)
- Manual config → auto-registration ("I just booted, here are my services")
- Single peer selection → intelligent scheduling (load-aware, latency-aware)
- No coordination → leader election, work distribution, shared state
