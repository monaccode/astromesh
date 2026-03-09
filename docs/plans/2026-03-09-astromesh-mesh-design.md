# Astromesh Mesh — Distributed Multi-Node Agent Execution

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/astromesh-mesh
**Depends on:** Phase 2 (v0.7.0)
**Version target:** v0.8.0

---

## Overview

Phase 4 transforms Astromesh from a multi-node system with static peer configuration into a **self-organizing mesh** with dynamic service discovery, leader election, and intelligent workload scheduling. Nodes join and leave the mesh automatically, propagate state via gossip, and a lightweight leader coordinates agent placement and request routing.

**Key insight:** The mesh is an evolution of Phase 2's peer system, not a replacement. `PeerClient` keeps working — the mesh just feeds it dynamic peers instead of static config.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Service discovery | Gossip protocol (HTTP-based) | No SPOF, scales horizontally, no external dependencies |
| Coordination model | Hybrid — gossip for state, leader for scheduling | Pragmatic: decentralized state + centralized decisions |
| Scheduling granularity | Two levels: agent placement + request routing | Leader places agents on nodes, gateway routes individual requests |
| Failure handling | Detection + alert, manual rescheduling | Conservative for v1; automatic rescheduling is future work |
| Gossip transport | HTTP piggyback on existing FastAPI | No new protocol, works through firewalls/proxies |
| Seed discovery | Seed nodes in config (`spec.mesh.seeds`) | Natural extension of `spec.peers`, works everywhere |

---

## Architecture

```
+----------------------------------------------------------+
|                    Astromesh Mesh                         |
|                                                          |
|  +------------+    gossip/HTTP    +------------+         |
|  |  Node A    |<----------------->|  Node B    |         |
|  |  (gateway) |    heartbeat      |  (worker)  |         |
|  |  LEADER    |<----------------->|            |         |
|  +-----+------+                   +-----+------+         |
|        |          gossip/HTTP           |                |
|        +----------+   +---------+-------+                |
|                   |   |                                  |
|              +----+---+----+                             |
|              |  Node C     |                             |
|              | (inference)  |                             |
|              +--------------+                            |
+----------------------------------------------------------+
```

Each node has:
- **MeshManager** — gossip, heartbeats, cluster state
- **LeaderElector** — bully algorithm leader election
- **Scheduler** (leader only) — agent placement + request routing
- **MeshAPI** — HTTP endpoints for mesh protocol

### Node Lifecycle

1. **Boot:** read `spec.mesh.seeds` from config
2. **Join:** contact seeds via `POST /v1/mesh/join`, receive cluster state
3. **Gossip:** exchange state periodically with N random nodes
4. **Heartbeat:** send heartbeat every `heartbeat_interval` (default 5s)
5. **Leader duties:** if elected, run scheduling decisions
6. **Leave:** notify cluster via `POST /v1/mesh/leave` (graceful) or detected by heartbeat timeout (failure)

### Request Flow (End-to-End)

```
1. Client → POST /v1/agents/support-agent/run → Gateway node

2. Gateway (no agents service):
   → PeerClient.forward("agents", ...)
   → Cluster state: worker-1 (load: 3), worker-2 (load: 7)
   → Scheduler.route_request("support-agent") → worker-1
   → Forward to worker-1

3. Worker-1 (agents + tools, no inference):
   → AgentRuntime.run("support-agent", query)
   → Needs LLM completion
   → PeerClient.forward("inference", ...)
   → Cluster state: inference-1 (load: 1)
   → Forward to inference-1

4. Inference-1 → completion → Worker-1 → result → Gateway → Client
```

---

## Components

### 1. NodeState (`astromesh/mesh/state.py`)

Data model propagated via gossip.

```python
@dataclass
class NodeLoad:
    cpu_percent: float
    memory_percent: float
    active_requests: int

@dataclass
class NodeState:
    node_id: str              # UUID generated at boot
    name: str                 # From config metadata.name
    url: str                  # http://host:port
    services: list[str]       # Enabled services
    agents: list[str]         # Loaded agents
    load: NodeLoad            # Current resource usage
    leader: bool              # Is this node the leader?
    joined_at: float          # Timestamp
    last_heartbeat: float     # Timestamp of last heartbeat
    status: str               # "alive", "suspect", "dead"

@dataclass
class ClusterState:
    nodes: dict[str, NodeState]   # node_id → NodeState
    leader_id: str | None
    version: int                  # Monotonic counter, incremented on change
```

### 2. MeshManager (`astromesh/mesh/manager.py`)

Central mesh component. Manages gossip, heartbeats, and cluster state.

```python
class MeshManager:
    def __init__(self, config: MeshConfig, service_manager: ServiceManager)
    async def join(self)              # Contact seeds, announce this node
    async def leave(self)             # Notify cluster, graceful shutdown
    async def heartbeat_loop(self)    # Background: send heartbeats
    async def gossip_loop(self)       # Background: propagate state to N random nodes
    def cluster_state(self) -> ClusterState
    def is_alive(self, node_id: str) -> bool
    def update_node(self, node_id: str, state: NodeState)  # Receive gossip
```

**Gossip protocol (push-pull):**

Every `gossip_interval` seconds:
1. Select `gossip_fanout` random nodes from cluster
2. Send `POST /v1/mesh/gossip` with known `NodeState` list
3. Receive other node's `NodeState` list
4. Merge: keep state with most recent `last_heartbeat` for each node

**Failure detection:**
- `now - last_heartbeat > failure_timeout` → node becomes `suspect`
- `now - last_heartbeat > dead_timeout` → node becomes `dead`
- `suspect` confirmed via gossip (if other nodes also see it)
- `dead` nodes removed from cluster state after 60 seconds

### 3. LeaderElector (`astromesh/mesh/leader.py`)

Bully algorithm — node with highest ID wins. Simple, deterministic.

```python
class LeaderElector:
    def __init__(self, mesh: MeshManager)
    async def start_election(self)
    def current_leader(self) -> str | None
    def is_leader(self) -> bool
    async def on_node_joined(self, node_id: str)
    async def on_node_failed(self, node_id: str)  # If leader, trigger election
```

**Election flow:**
1. Node detects leader is dead (via gossip failure detection)
2. Node sends `POST /v1/mesh/election` to all nodes with higher IDs
3. If no higher node responds within timeout → this node becomes leader
4. New leader announces via gossip (sets `leader: true` in its `NodeState`)

### 4. Scheduler (`astromesh/mesh/scheduler.py`)

Active only on the leader node. Two responsibilities:

```python
class Scheduler:
    def __init__(self, mesh: MeshManager)
    def place_agent(self, agent_name: str) -> list[str]    # Returns node_ids
    def route_request(self, agent_name: str) -> str         # Returns best node_id
    def placement_table(self) -> dict[str, list[str]]       # agent → [node_ids]
```

**Placement strategy (least-loaded):** Place agent on all worker nodes that have `agents` service enabled. Default: replicate on all available workers.

**Routing strategy (least-connections):** Route request to the node with fewest `active_requests` among nodes that have the agent loaded.

### 5. MeshConfig (runtime.yaml extension)

```yaml
spec:
  mesh:
    enabled: true
    node_name: "worker-1"
    bind: "0.0.0.0:8000"
    seeds:
      - http://gateway:8000
      - http://worker-2:8000
    heartbeat_interval: 5       # Seconds between heartbeats
    gossip_interval: 2          # Seconds between gossip rounds
    gossip_fanout: 3            # Nodes to contact per gossip round
    failure_timeout: 15         # Seconds without heartbeat → suspect
    dead_timeout: 30            # Seconds suspect → dead
```

---

## Mesh API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /v1/mesh/join` | POST | Node announces itself. Body: `NodeState`. Response: `ClusterState` |
| `POST /v1/mesh/leave` | POST | Node notifies departure. Body: `{node_id}` |
| `POST /v1/mesh/heartbeat` | POST | Periodic heartbeat. Body: `NodeState` (with updated load) |
| `POST /v1/mesh/gossip` | POST | State exchange. Body: `{nodes: [NodeState...]}`. Response: `{nodes: [NodeState...]}` |
| `GET /v1/mesh/state` | GET | Full cluster state (all nodes, leader, placement table) |
| `POST /v1/mesh/election` | POST | Leader election message. Body: `{candidate_id, node_id}` |

---

## CLI Commands

| Command | Action | Source |
|---------|--------|--------|
| `astromeshctl mesh status` | Mesh summary: nodes, leader, total services | `GET /v1/mesh/state` |
| `astromeshctl mesh nodes` | Table: name, url, services, load, status | `GET /v1/mesh/state` |
| `astromeshctl mesh join <seed_url>` | Force manual join to a seed | `POST /v1/mesh/join` via daemon |
| `astromeshctl mesh leave` | Graceful leave from mesh | `POST /v1/mesh/leave` via daemon |

---

## Integration with Phase 2

### PeerClient Transition

```python
# In daemon startup:
if mesh_config.enabled:
    mesh = MeshManager(mesh_config, service_manager)
    await mesh.join()
    # PeerClient fed dynamically from cluster state
    peer_client = PeerClient.from_mesh(mesh)
else:
    # Phase 2 behavior: static peers from config
    peer_client = PeerClient(peers_config)
```

`PeerClient.from_mesh()` creates a PeerClient that reads peers from live `ClusterState` instead of YAML. The public interface (`forward()`, `find_peers()`, `health_check()`) doesn't change. Route handlers and runtime are unaware whether peers are static or dynamic.

### Status Endpoint Extension

`GET /v1/system/status` adds mesh section:

```json
{
  "version": "0.8.0",
  "services": {"api": true, "agents": true},
  "peers": [...],
  "mesh": {
    "enabled": true,
    "node_id": "a1b2c3",
    "node_name": "worker-1",
    "leader": "gateway-1",
    "cluster_size": 3,
    "status": "alive"
  }
}
```

### Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| No `spec.mesh` in config | Works exactly like v0.7.0 (static peers) |
| `mesh.enabled: false` | Same as no `spec.mesh` |
| `mesh.enabled: true` + `spec.peers` | Mesh takes control, `spec.peers` ignored (warning in logs) |
| Mesh node + non-mesh node | Non-mesh node doesn't participate in gossip but can be a static peer |

---

## New Directory Structure

```
astromesh/
├── mesh/
│   ├── __init__.py
│   ├── state.py          # NodeState, NodeLoad, ClusterState
│   ├── manager.py        # MeshManager (gossip, heartbeats, cluster state)
│   ├── leader.py         # LeaderElector (bully algorithm)
│   └── scheduler.py      # Scheduler (placement + routing)

astromesh/api/routes/
├── mesh.py               # Mesh API endpoints (/v1/mesh/*)

cli/commands/
├── mesh.py               # CLI mesh commands

config/profiles/
├── mesh-gateway.yaml     # Gateway with mesh enabled
├── mesh-worker.yaml      # Worker with mesh enabled
├── mesh-inference.yaml   # Inference with mesh enabled
```

---

## New Dependencies

```toml
[project.optional-dependencies]
mesh = ["psutil>=5.9.0"]  # For CPU/memory load metrics
```

No external service dependencies. The gossip protocol runs over existing HTTP/FastAPI.

---

## Excluded from This Phase (Future Work)

The following features are intentionally deferred to keep this phase focused and deliverable:

### Automatic Rescheduling
When a node fails, the mesh detects and reports it but does NOT automatically relocate agents. The operator manually decides where to place them. Automatic rescheduling with circuit breakers (to prevent cascading failures) is planned for a future phase once failure detection is battle-tested.

### Distributed Memory / Shared State
Each node manages its own memory backends independently. Agent sessions are local to the node where the agent runs. Shared memory across the mesh (distributed Redis, CRDTs, session replication) requires careful consistency guarantees and is deferred.

### Agent Migration (Hot)
Moving a running agent from one node to another mid-execution. Requires state serialization, transfer, and resume — complex and error-prone. Deferred until placement and routing are proven stable.

### Multi-Region / WAN Mesh
The current gossip protocol assumes low-latency networking (LAN, single datacenter, VPN). WAN-aware gossip with region-aware routing, split-brain handling, and latency-based peer selection is future work.

### Inter-Node Authentication (mTLS)
Nodes currently communicate over plain HTTP. Mutual TLS for node-to-node authentication and encryption is important for production but deferred to keep the mesh protocol simple during development.

### Global Rate Limiting
Rate limiting is per-node today. Mesh-wide rate limiting (shared counters, distributed token buckets) requires distributed coordination beyond what the current gossip provides.

### DNS-Based Seed Discovery
Automatic seed discovery via DNS SRV records or Kubernetes headless services. Currently seeds are configured manually in `spec.mesh.seeds`. DNS discovery would make Kubernetes and Docker deployments more seamless.

### Intelligent Scheduling Strategies
Current scheduling is least-loaded (placement) and least-connections (routing). Future strategies: latency-aware routing, GPU-aware placement, affinity rules, priority queues, preemption.
