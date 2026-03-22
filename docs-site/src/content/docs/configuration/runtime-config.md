---
title: Runtime Configuration
description: Global runtime settings and service toggles
---

The runtime configuration controls global settings for the Astromesh platform: which services are enabled, network binding, peer connections, mesh networking, and default agent behavior. It is the first file the runtime reads at startup.

## File Location

Runtime configuration lives at `config/runtime.yaml` (development) or `/etc/astromesh/runtime.yaml` (production).

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
```

## Full Example

Below is a complete `runtime.yaml` with all available fields:

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: production

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

  peers:
    - name: worker-1
      url: http://worker-1:8000
      services: [agents, tools, memory, rag]
    - name: inference-1
      url: http://inference-1:8000
      services: [inference]

  mesh:
    enabled: true
    node_name: gateway
    bind: "0.0.0.0:8000"
    seeds: []
    heartbeat_interval: 5
    gossip_interval: 2
    gossip_fanout: 3
    failure_timeout: 15
    dead_timeout: 30

  defaults:
    orchestration:
      pattern: react
      max_iterations: 10
```

## `spec.api`

Controls the HTTP server binding.

| Field | Default | Description |
|-------|---------|-------------|
| `host` | `"0.0.0.0"` | IP address to bind. Use `"0.0.0.0"` to listen on all interfaces, `"127.0.0.1"` for localhost only. |
| `port` | `8000` | TCP port for the API server. |

```yaml
spec:
  api:
    host: "0.0.0.0"
    port: 8000
```

## `spec.services`

Eight boolean toggles that control which subsystems are active on this node. Disabling a service means the node will not run that subsystem — requests for that service are either forwarded to peers or rejected.

| Service | Description |
|---------|-------------|
| `api` | The FastAPI HTTP/WebSocket server. Almost always `true` — disable only for headless worker nodes that receive work via mesh. |
| `agents` | The agent runtime engine. Loads agent YAML definitions and executes agent queries. Disable on gateway-only or inference-only nodes. |
| `inference` | LLM provider connections and model routing. Disable on nodes that delegate inference to dedicated inference peers. |
| `memory` | Memory backends (Redis, PostgreSQL, SQLite) for conversational, semantic, and episodic memory. Disable on nodes that do not manage state. |
| `tools` | The tool registry for internal, MCP, webhook, and RAG-as-tool execution. Disable on nodes that do not run tools. |
| `channels` | Channel adapters for external messaging platforms (WhatsApp, etc.). Enable on gateway or standalone nodes that receive external messages. |
| `rag` | RAG pipeline execution — document chunking, embedding, vector search, and reranking. Disable on nodes that do not serve RAG queries. |
| `observability` | OpenTelemetry tracing, metrics, and logging. Recommended to keep enabled on all nodes for operational visibility. |

```yaml
spec:
  services:
    api: true
    agents: true
    inference: true
    memory: true
    tools: true
    channels: true
    rag: true
    observability: true
```

When all services are `true`, the node operates as a standalone deployment. For multi-node setups, disable services that run on other nodes and configure `peers` or `mesh` to route requests.

## `spec.peers`

Static peer configuration for multi-node deployments without Maia mesh networking. Each peer declares its URL and which services it provides.

```yaml
spec:
  peers:
    - name: worker-1
      url: http://worker-1:8000
      services: [agents, tools, memory, rag]
    - name: inference-1
      url: http://inference-1:8000
      services: [inference]
```

| Field | Description |
|-------|-------------|
| `name` | A human-readable identifier for the peer. Used in logs and health check reporting. |
| `url` | The peer's API endpoint URL. Must be reachable from this node. |
| `services` | List of services the peer provides. The runtime routes requests for these services to this peer. |

Peers are checked periodically for health. If a peer becomes unreachable, it is temporarily removed from the routing pool.

Use `peers` when you have a fixed number of nodes with known addresses. For dynamic environments where nodes join and leave, use [Maia mesh networking](#specmesh) instead.

## `spec.mesh`

Maia mesh networking configuration. When enabled, nodes discover each other automatically using a gossip protocol instead of static peer lists.

```yaml
spec:
  mesh:
    enabled: true
    node_name: gateway
    bind: "0.0.0.0:8000"
    seeds:
      - http://gateway:8000
    heartbeat_interval: 5
    gossip_interval: 2
    gossip_fanout: 3
    failure_timeout: 15
    dead_timeout: 30
```

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `false` | Enable Maia mesh networking on this node. |
| `node_name` | — | Unique name for this node in the mesh. Used in gossip protocol messages. |
| `bind` | `"0.0.0.0:8000"` | Address and port for mesh protocol communication. |
| `seeds` | `[]` | List of seed node URLs to contact when joining the mesh. Leave empty on the first node (it becomes the seed). |
| `heartbeat_interval` | `5` | Seconds between heartbeat broadcasts to announce this node is alive. |
| `gossip_interval` | `2` | Seconds between gossip protocol rounds for state synchronization. |
| `gossip_fanout` | `3` | Number of random peers to contact during each gossip round. |
| `failure_timeout` | `15` | Seconds without a heartbeat before a node is marked as suspected failed. |
| `dead_timeout` | `30` | Seconds without a heartbeat before a node is marked as dead and removed from the mesh. |

The `seeds` list bootstraps mesh membership. When a node starts, it contacts each seed to join the mesh and receive the current member list. The seed node itself should have an empty `seeds` list — it is the initial contact point.

## `spec.defaults`

Default values applied to agents that do not specify these fields in their own YAML.

```yaml
spec:
  defaults:
    orchestration:
      pattern: react
      max_iterations: 10
```

| Field | Default | Description |
|-------|---------|-------------|
| `orchestration.pattern` | `react` | Default orchestration pattern for agents without an explicit `spec.orchestration.pattern`. |
| `orchestration.max_iterations` | `10` | Default maximum iterations for agents without an explicit `spec.orchestration.max_iterations`. |

Agent-level settings always override these defaults.

## Environment Variable Override

You can change where the runtime looks for configuration files by setting the `ASTROMESH_CONFIG_DIR` environment variable:

```bash
# Point to a custom config directory
ASTROMESH_CONFIG_DIR=/opt/myapp/config uv run uvicorn astromesh.api.main:app

# Or export it
export ASTROMESH_CONFIG_DIR=/opt/myapp/config
```

The runtime loads all configuration files (`runtime.yaml`, `providers.yaml`, `channels.yaml`, `agents/*.agent.yaml`, `rag/*.rag.yaml`) from the specified directory.

### Forge, API persistence, and templates

Agents created from **Forge** or **`POST /v1/agents`** are written under `agents/` by default, and Forge **templates** are resolved from one or more directories (merged). Empty `templates/` folders do not hide built-in templates.

For details and environment variables (`ASTROMESH_PERSIST_AGENTS`, `ASTROMESH_TEMPLATES_DIR`), see **[Forge, API & on-disk agents](/astromesh/configuration/forge-api-storage/)**.

## Multiple Environments

Use separate config directories for different environments:

```bash
# Development
ASTROMESH_CONFIG_DIR=./config/dev uv run uvicorn astromesh.api.main:app

# Staging
ASTROMESH_CONFIG_DIR=./config/staging uv run uvicorn astromesh.api.main:app

# Production
ASTROMESH_CONFIG_DIR=/etc/astromesh uv run uvicorn astromesh.api.main:app
```

A typical project structure for multi-environment configs:

```
config/
├── dev/
│   ├── runtime.yaml
│   ├── providers.yaml
│   └── agents/
├── staging/
│   ├── runtime.yaml
│   ├── providers.yaml
│   └── agents/
└── prod/
    ├── runtime.yaml
    ├── providers.yaml
    └── agents/
```

## Docker Override

When running in Docker, mount your config directory into the container:

```yaml
# docker-compose.override.yaml
services:
  astromesh:
    volumes:
      - ./my-configs:/app/config
```

Or set the environment variable in your `docker-compose.yaml`:

```yaml
services:
  astromesh:
    environment:
      - ASTROMESH_CONFIG_DIR=/app/config
    volumes:
      - ./my-configs:/app/config
```
