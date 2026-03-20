# Astromesh Maia — Automatic Discovery & Coordination

> **Looking for a hands-on guide?** See [MAIA_GUIDE.md](MAIA_GUIDE.md) for Docker recipes, environment variables, and step-by-step setup instructions.

**What it does:** Nodes find each other automatically, detect failures, elect a leader, and route requests intelligently — no manual peer configuration needed.

**Related docs:** [OS](ASTROMESH_OS.md) · [Nodes](ASTROMESH_NODES.md) · [Architecture](GENERAL_ARCHITECTURE.md) · [Developer Guide](MAIA_GUIDE.md)

---

## The Big Picture

With [Astromesh Nodes](ASTROMESH_NODES.md) you can split services across multiple nodes, but you have to manually list every peer in each node's config. If a node goes down, nobody knows. If you add a new node, you have to update everyone's config.

Astromesh Maia solves this. Nodes join a cluster, gossip with each other to stay informed, detect failures automatically, and route requests to the best available node.

```
       ┌──────────┐    gossip    ┌──────────┐
       │ Gateway  │◄────────────►│  Worker  │
       │ (leader) │              │          │
       └────┬─────┘              └────┬─────┘
            │          gossip         │
            │    ┌──────────────┐     │
            └───►│  Inference   │◄────┘
                 │              │
                 └──────────────┘

     Every node knows about every other node.
     If one dies, the others notice within seconds.
```

---

## How It Works — Step by Step

### 1. A Node Starts and Joins the Cluster

When `astromeshd` starts with `mesh.enabled: true`, it:

1. Creates a unique `node_id` (UUID)
2. Contacts the **seed nodes** listed in `mesh.seeds`
3. Sends its own state (name, URL, services, agents) via `POST /v1/mesh/join`
4. Receives the current cluster state back
5. Now it knows about every other node in the cluster

```yaml
# mesh-worker.yaml
spec:
  mesh:
    enabled: true
    node_name: worker-1
    seeds:
      - http://gateway:8000    # ← "Call this address to join"
```

The **gateway** typically has `seeds: []` because it IS the seed — it's the first node everyone contacts. Workers and inference nodes list the gateway as their seed.

### 2. Nodes Gossip to Stay in Sync

Every 2 seconds (configurable), each node picks random peers and exchanges state:

```
Worker                              Inference
  │                                    │
  │  POST /v1/mesh/gossip              │
  │  body: [my state, gateway state]   │
  │  ──────────────────────────────►   │
  │                                    │
  │  response: [inference state]       │
  │  ◄──────────────────────────────   │
  │                                    │
  Both nodes now have the same view of the cluster.
```

This is called **push-pull gossip**: "here's what I know, tell me what you know." After a few rounds, every node has the same information — even if they can't all talk to each other directly.

### 3. Heartbeats Detect Failures

Every 5 seconds (configurable), each node updates its own heartbeat timestamp. When a node checks its peers during gossip, it looks at how old each peer's heartbeat is:

| Heartbeat age | Status | What it means |
|--------------|--------|---------------|
| < 15 seconds | `alive` | Normal operation |
| 15–30 seconds | `suspect` | Might be down, stop sending new requests |
| > 30 seconds | `dead` | Confirmed down, remove from routing |

```
Timeline:
  0s   Worker sends heartbeat                    status: alive
  5s   Worker sends heartbeat                    status: alive
  10s  Worker crashes 💥
  15s  (no heartbeat received)                   status: alive
  20s  Gateway gossips, sees stale heartbeat     status: suspect
  25s  (still no heartbeat)                      status: suspect
  40s  Gateway gossips again                     status: dead
```

No single node decides — every node independently evaluates heartbeat timestamps. Because they all gossip, they converge on the same conclusion.

### 4. Leader Election (Bully Algorithm)

The cluster picks a leader: the node with the highest `node_id` (alphabetically) among all alive nodes. That's it.

```
Nodes:          node_id
─────────────────────────
gateway         abc-123
worker          def-456
inference       xyz-789  ← Leader (highest ID)
```

The leader doesn't do anything special today — it's there for future features (coordinated scheduling, agent migration). Re-election happens automatically when:
- A new node joins (might have a higher ID)
- The current leader dies

### 5. Request Routing

When a request comes in, the **Scheduler** decides where to send it:

**Agent placement:** Which nodes have an agent loaded?
→ All alive nodes that list the agent name in their state.

**Request routing:** Among those nodes, which one should handle THIS request?
→ The one with the fewest active connections (least-connections strategy).

```
Request: "Run agent research-bot"

Scheduler checks:
  gateway  → services: [api, channels]     → doesn't run agents
  worker   → agents: [research-bot, qa-bot] → ✓ active_requests: 3
  inference → agents: []                    → doesn't run agents

Route to: worker (only option with research-bot)
```

If multiple workers have the same agent, the scheduler picks the one with the lowest load.

---

## Configuration

### Minimal Maia Config

```yaml
spec:
  mesh:
    enabled: true
    node_name: my-node
    seeds:
      - http://gateway:8000
```

That's all you need. Everything else has sensible defaults.

### Full Maia Config (with defaults shown)

```yaml
spec:
  mesh:
    enabled: true
    node_name: my-node          # Human-readable name for this node
    bind: "0.0.0.0:8000"        # Address this node listens on
    seeds:                       # Nodes to contact when joining
      - http://gateway:8000
    heartbeat_interval: 5        # Seconds between heartbeats
    gossip_interval: 2           # Seconds between gossip rounds
    gossip_fanout: 3             # Number of random peers to gossip with each round
    failure_timeout: 15          # Seconds before marking a node "suspect"
    dead_timeout: 30             # Seconds before marking a node "dead"
```

### Config Profiles

Pre-built Maia profiles are available:

| Profile | File | Role |
|---------|------|------|
| Maia Gateway | `config/profiles/mesh-gateway.yaml` | Entry point, no agents, `seeds: []` |
| Maia Worker | `config/profiles/mesh-worker.yaml` | Runs agents + tools, seeds to gateway |
| Maia Inference | `config/profiles/mesh-inference.yaml` | LLM serving only, seeds to gateway |

Copy one to `config/runtime.yaml` and adjust `node_name` and `seeds`.

---

## CLI Commands

```bash
# Cluster overview: how many nodes, who's the leader, how many alive/suspect/dead
astromeshctl mesh status

# Detailed table of all nodes: name, URL, services, agents, load, status
astromeshctl mesh nodes

# Gracefully leave the cluster
astromeshctl mesh leave
```

---

## API Endpoints

These endpoints are used by nodes to communicate with each other. You normally don't call them directly, but they're useful for debugging.

| Endpoint | What it does |
|----------|-------------|
| `GET /v1/mesh/state` | Returns the full cluster state (all nodes) |
| `POST /v1/mesh/join` | A node requests to join the cluster |
| `POST /v1/mesh/leave` | A node announces it's leaving |
| `POST /v1/mesh/heartbeat` | A node sends its heartbeat |
| `POST /v1/mesh/gossip` | Nodes exchange state |
| `POST /v1/mesh/election` | Trigger a leader election |

If Maia is not enabled, all these endpoints return `503 Service Unavailable`.

---

## Docker Compose — Try It Locally

The project includes a 3-node Maia cluster for local development:

```bash
cd docker
docker compose -f docker-compose.gossip.yml up -d
```

This starts:

| Container | Role | Port | Seeds |
|-----------|------|------|-------|
| `astromesh-gateway` | Gateway | 8000 | (none — is the seed) |
| `astromesh-worker` | Worker | 8001 | gateway:8000 |
| `astromesh-inference` | Inference | 8002 | gateway:8000 |

Plus Ollama, Redis, and PostgreSQL.

After startup, check the cluster:

```bash
# From gateway
curl http://localhost:8000/v1/mesh/state
# Returns all 3 nodes with their services, agents, and load

astromeshctl mesh nodes
# Pretty table with all node details
```

---

## Maia vs Static Peers

| Feature | Static Peers (Nodes) | Maia |
|---------|---------------------|------|
| Configuration | List every peer URL manually | Only list seed nodes |
| Discovery | None — you tell each node about its peers | Automatic via gossip |
| Failure detection | None — if a peer dies, requests fail | Automatic (suspect → dead) |
| Adding a node | Update config on every existing node | New node joins via seeds |
| Removing a node | Update config on every existing node | Node leaves or times out |
| Leader election | None | Automatic (bully algorithm) |
| Request routing | Round-robin across listed peers | Least-connections across alive nodes |

**When Maia is enabled, `spec.peers` is ignored.** Maia replaces static peer configuration with dynamic discovery. If you have both, a warning is logged.

---

## Backward Compatibility

- **No `spec.mesh` in config** → Everything works exactly like Astromesh Nodes (static peers)
- **`mesh.enabled: false`** → Same as not having Maia config at all
- **Maia enabled + static peers** → Maia takes over, static peers are ignored (with a warning)

You can upgrade from Nodes to Maia incrementally: add `spec.mesh` to one node at a time.

---

## How the Pieces Fit Together

```
Astromesh Node        →  "How to run the daemon and use the CLI"
    ↓
Astromesh Nodes       →  "How to split services across multiple daemons"
    ↓
Astromesh Maia        →  "How to make those daemons find each other automatically"
```

Each layer builds on the previous one. You can stop at any level:

- **Just OS** — Single node, all services, managed by systemd.
- **OS + Nodes** — Multiple nodes with manual peer configuration.
- **OS + Nodes + Maia** — Multiple nodes with automatic discovery and failure handling.

---

## What Maia Does NOT Do (Yet)

These are documented for future implementation:

- **Automatic rescheduling** — If a node dies, its agents are NOT automatically moved to another node. You need to restart them manually.
- **Agent migration** — You can't move a running agent from one node to another.
- **Distributed memory** — Each node has its own memory. There's no automatic memory replication across nodes.
- **WAN support** — Designed for LAN/datacenter use. No NAT traversal or WAN optimization.
- **mTLS** — Node-to-node communication is plain HTTP. No encryption between nodes.
- **DNS discovery** — Seed nodes must be specified by URL. No DNS-based auto-discovery.
- **Smart scheduling strategies** — Only least-connections routing is available. No affinity, latency-based, or cost-based scheduling.
