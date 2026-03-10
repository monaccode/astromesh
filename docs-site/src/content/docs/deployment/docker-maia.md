---
title: "Docker Maia"
description: "Mesh deployment with automatic node discovery"
---

This guide covers deploying Astromesh as a multi-node mesh using the Maia gossip protocol for automatic node discovery. Nodes find each other, exchange state, elect a leader, and route requests intelligently -- all without static peer configuration.

## What and Why

Maia is the Astromesh mesh protocol. It transforms a collection of independent Astromesh nodes into a self-organizing cluster:

- **Gossip-based discovery** -- nodes periodically exchange state with random peers over HTTP. No central registry, no single point of failure.
- **Leader election** -- a bully-algorithm leader handles scheduling decisions (agent placement, request routing).
- **Role-based services** -- each node enables a subset of services (gateway, worker, inference). The mesh routes requests to the right node automatically.
- **Failure detection** -- missed heartbeats mark nodes as suspect, then dead. The leader reroutes traffic.

Use Maia when you want a distributed Astromesh deployment that scales horizontally and self-heals, without managing static peer lists.

### Maia vs Static Peers

| Feature | Static Peers | Maia Gossip |
|---------|-------------|-------------|
| Discovery | Manual `peers:` list in YAML | Automatic via seed nodes |
| Adding nodes | Edit config on every node, restart | New node contacts a seed, joins automatically |
| Failure detection | None (requests fail) | Heartbeat timeout, node marked suspect/dead |
| Request routing | Round-robin to known peers | Leader-driven scheduling based on load |
| Leader election | None | Bully algorithm, automatic failover |
| Configuration | `spec.peers` in runtime.yaml | `spec.mesh.seeds` in runtime.yaml |

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Docker | 24.0+ | `docker --version` |
| Docker Compose | v2.20+ | `docker compose version` |

## Understanding Roles

Each node in the mesh enables a different set of services based on its role:

| Service | Gateway | Worker | Inference |
|---------|:-------:|:------:|:---------:|
| api | yes | yes | yes |
| agents | -- | yes | -- |
| tools | -- | yes | -- |
| memory | -- | yes | -- |
| rag | -- | yes | -- |
| channels | yes | -- | -- |
| inference | -- | -- | yes |
| observability | yes | yes | yes |

**Gateway** receives external requests and routes them to workers. **Worker** executes agents, runs tools, and manages memory. **Inference** runs LLM providers (Ollama, vLLM) and serves completion requests.

### Request flow

```
Client → Gateway → Worker → Inference → Worker → Gateway → Client
         (route)   (agent)   (LLM)      (result)  (response)
```

## Step-by-step Setup

### 1. Create a project directory

```bash
mkdir astromesh-mesh && cd astromesh-mesh
```

### 2. Create the Docker Compose file

Create `docker-compose.yml`:

```yaml
# Astromesh Maia Mesh — 3 Nodes
services:
  gateway:
    image: ghcr.io/monaccode/astromesh:0.10.0
    ports:
      - "8000:8000"
    environment:
      - ASTROMESH_ROLE=gateway
      - ASTROMESH_NODE_NAME=gateway
      - ASTROMESH_MESH_ENABLED=true
      - ASTROMESH_MESH_SEEDS=gateway:8000
    networks:
      - astromesh-mesh

  worker:
    image: ghcr.io/monaccode/astromesh:0.10.0
    environment:
      - ASTROMESH_ROLE=worker
      - ASTROMESH_NODE_NAME=worker
      - ASTROMESH_MESH_ENABLED=true
      - ASTROMESH_MESH_SEEDS=gateway:8000
      - OLLAMA_HOST=http://ollama:11434
      - DATABASE_URL=postgresql://astromesh:astromesh@postgres:5432/astromesh
      - REDIS_URL=redis://redis:6379
    depends_on:
      - gateway
      - redis
      - postgres
    networks:
      - astromesh-mesh

  inference:
    image: ghcr.io/monaccode/astromesh:0.10.0
    environment:
      - ASTROMESH_ROLE=inference
      - ASTROMESH_NODE_NAME=inference
      - ASTROMESH_MESH_ENABLED=true
      - ASTROMESH_MESH_SEEDS=gateway:8000
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - gateway
    networks:
      - astromesh-mesh

  # --- Supporting infrastructure ---

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - astromesh-mesh

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - astromesh-mesh

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: astromesh
      POSTGRES_USER: astromesh
      POSTGRES_PASSWORD: astromesh
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - astromesh-mesh

volumes:
  ollama-models:
  redis-data:
  postgres-data:

networks:
  astromesh-mesh:
    driver: bridge
```

### 3. Start the mesh

```bash
docker compose up -d
```

Expected output:

```
[+] Running 7/7
 ✔ Network astromesh-mesh_astromesh-mesh  Created
 ✔ Container astromesh-mesh-ollama-1      Started
 ✔ Container astromesh-mesh-redis-1       Started
 ✔ Container astromesh-mesh-postgres-1    Started
 ✔ Container astromesh-mesh-gateway-1     Started
 ✔ Container astromesh-mesh-worker-1      Started
 ✔ Container astromesh-mesh-inference-1   Started
```

### 4. Pull a model

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

### 5. Verify the mesh

```bash
curl http://localhost:8000/v1/mesh/state
```

Expected output:

```json
{
  "cluster_size": 3,
  "leader": "gateway",
  "nodes": [
    {
      "name": "gateway",
      "status": "alive",
      "role": "gateway",
      "services": ["api", "channels", "observability"],
      "address": "gateway:8000",
      "last_heartbeat": "2026-03-09T10:00:05Z"
    },
    {
      "name": "worker",
      "status": "alive",
      "role": "worker",
      "services": ["api", "agents", "tools", "memory", "rag", "observability"],
      "address": "worker:8000",
      "last_heartbeat": "2026-03-09T10:00:04Z"
    },
    {
      "name": "inference",
      "status": "alive",
      "role": "inference",
      "services": ["api", "inference", "observability"],
      "address": "inference:8000",
      "last_heartbeat": "2026-03-09T10:00:03Z"
    }
  ]
}
```

All three nodes should show `"status": "alive"`.

## Configuration

### How it works

When `ASTROMESH_MESH_ENABLED=true`, the container entrypoint:

1. Reads `ASTROMESH_ROLE` to select the service profile (gateway, worker, inference)
2. Enables the Maia gossip protocol
3. Contacts seed nodes listed in `ASTROMESH_MESH_SEEDS`
4. Joins the cluster, begins heartbeats and state exchange
5. Participates in leader election

The first seed node typically becomes the initial leader.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_MESH_ENABLED` | `false` | Enable gossip-based mesh |
| `ASTROMESH_MESH_SEEDS` | -- | Comma-separated seed addresses (`host:port,host:port`) |
| `ASTROMESH_NODE_NAME` | hostname | Unique name for this node |
| `ASTROMESH_ROLE` | `full` | Service profile: `gateway`, `worker`, `inference`, `full` |
| `OLLAMA_HOST` | -- | Ollama endpoint (for inference and worker nodes) |
| `OPENAI_API_KEY` | -- | OpenAI API key |
| `DATABASE_URL` | -- | PostgreSQL connection string (for worker nodes) |
| `REDIS_URL` | -- | Redis connection string (for worker nodes) |

### Scaling workers

Add more workers to handle increased agent execution load:

```bash
docker compose up -d --scale worker=3
```

Expected output:

```
[+] Running 8/8
 ✔ Container astromesh-mesh-worker-1  Running
 ✔ Container astromesh-mesh-worker-2  Started
 ✔ Container astromesh-mesh-worker-3  Started
```

The new workers contact the seed, join the mesh automatically, and begin accepting agent execution requests. Verify:

```bash
curl http://localhost:8000/v1/mesh/state | python3 -m json.tool
```

You should see 5 nodes (gateway + 3 workers + inference).

### Adding API keys

Pass API keys as environment variables on the nodes that need them:

```yaml
worker:
  environment:
    - OPENAI_API_KEY=sk-...
    - ANTHROPIC_API_KEY=sk-ant-...

inference:
  environment:
    - OPENAI_API_KEY=sk-...
```

### Custom agents on workers

Mount agent definitions on worker nodes:

```yaml
worker:
  volumes:
    - ./agents:/etc/astromesh/agents:ro
```

### Infrastructure services

**Redis** is used for conversational memory (chat history). Only worker nodes need access.

**PostgreSQL** (with pgvector) is used for episodic memory and vector-based semantic search. Only worker nodes need access.

**Ollama** serves LLM models. Both inference nodes and workers can connect to it, but typically only inference nodes use it directly.

## CLI via Docker exec

Run `astromeshctl` commands inside any Astromesh container:

```bash
# Mesh status
docker compose exec gateway astromeshctl mesh status
```

Expected output:

```
┌───────────────────────────────────────────┐
│              Mesh Status                  │
├──────────────┬────────────────────────────┤
│ Cluster size │ 3                          │
│ Leader       │ gateway                    │
│ Protocol     │ gossip (Maia)              │
│ Heartbeat    │ 5s                         │
└──────────────┴────────────────────────────┘
```

```bash
# List nodes
docker compose exec gateway astromeshctl mesh nodes
```

Expected output:

```
┌───────────┬─────────┬───────────┬─────────────────────┐
│ Name      │ Role    │ Status    │ Services            │
├───────────┼─────────┼───────────┼─────────────────────┤
│ gateway   │ gateway │ ● Alive   │ api, channels       │
│ worker    │ worker  │ ● Alive   │ agents, tools, mem  │
│ inference │ infrnc  │ ● Alive   │ inference           │
└───────────┴─────────┴───────────┴─────────────────────┘
```

```bash
# Gracefully leave the mesh
docker compose exec worker astromeshctl mesh leave
```

## Common Operations

### Check which node handles a request

The response headers include routing information:

```bash
curl -v -X POST http://localhost:8000/v1/agents/default/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello"}' 2>&1 | grep X-Astromesh
```

Expected output:

```
< X-Astromesh-Node: gateway
< X-Astromesh-Routed-To: worker
< X-Astromesh-Inference-Node: inference
```

### View logs per node

```bash
docker compose logs gateway
docker compose logs worker
docker compose logs inference
```

### Restart a single node

```bash
docker compose restart worker
```

The worker leaves the mesh, restarts, contacts the seed, and rejoins automatically.

## Troubleshooting

### Nodes not discovering each other

Check that all nodes are on the same Docker network:

```bash
docker network inspect astromesh-mesh_astromesh-mesh
```

Verify the seed address is correct. The seed must be reachable from other nodes:

```bash
docker compose exec worker curl http://gateway:8000/health
```

Expected output:

```json
{"status": "healthy", "version": "0.10.0"}
```

If this fails, the containers are not on the same network.

### Node stuck in "suspect" status

A node is marked suspect when it misses heartbeats. This usually means:

1. The node is overloaded and slow to respond
2. Network issues between nodes
3. The node's process is hung

Check the node's logs:

```bash
docker compose logs worker
```

Restart the suspect node:

```bash
docker compose restart worker
```

### Node shows "dead" status

A dead node has been unreachable for longer than the failure timeout (default 30 seconds). It is removed from scheduling but stays in the cluster state until it either rejoins or is explicitly removed.

If the node is actually running, check network connectivity and restart it.

### Seeds wrong or unreachable

```
ERROR: Failed to join mesh — cannot reach seed gateway:8000
```

Verify the seed node is running:

```bash
docker compose ps gateway
```

Verify the `ASTROMESH_MESH_SEEDS` variable matches the actual service name and port:

```yaml
environment:
  - ASTROMESH_MESH_SEEDS=gateway:8000
```

The seed address must use the Docker Compose service name, not `localhost` or an external IP.

### Requests returning 503

```json
{"detail": "No available node provides service: agents"}
```

This means no worker node is alive in the mesh. Check:

```bash
curl http://localhost:8000/v1/mesh/state
```

If workers are missing, start them:

```bash
docker compose up -d worker
```
