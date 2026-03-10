---
title: Maia Protocol Internals
description: Deep dive into the gossip-based discovery protocol
---

Maia is Astromesh's gossip-based service discovery and coordination protocol. It replaces static peer configuration with dynamic, self-organizing mesh networking. Nodes discover each other, propagate state, detect failures, elect a leader, and route requests — all without external infrastructure like etcd, Consul, or ZooKeeper.

## Overview

In a multi-node Astromesh deployment without Maia, you configure peers statically in YAML:

```yaml
spec:
  peers:
    - url: http://worker-1:8000
    - url: http://worker-2:8000
```

This works but has limitations: adding or removing nodes requires config changes and restarts, there is no failure detection, and routing is not load-aware. Maia solves these problems with a gossip protocol that runs over the existing HTTP/FastAPI transport.

## Joining the Mesh

When a node starts with mesh enabled:

1. The node generates a UUID (`node_id`) and reads its seed list from `spec.mesh.seeds`
2. The node sends `POST /v1/mesh/join` to each seed with its own `NodeState`
3. The seed responds with the full `ClusterState` (all known nodes, current leader, version counter)
4. The joining node merges the received cluster state into its local state
5. On the next gossip round, other nodes learn about the new node

```
New Node                          Seed Node
   |                                  |
   |--- POST /v1/mesh/join ---------> |
   |    Body: { NodeState }           |
   |                                  |
   | <--- 200 OK -------------------- |
   |    Body: { ClusterState }        |
   |                                  |
   |    (node now has full cluster    |
   |     view and begins gossiping)   |
```

If no seeds are reachable, the node operates in standalone mode and retries joining periodically.

## Gossip Protocol

Maia uses a **push-pull gossip** protocol. Every `gossip_interval` seconds (default: 2s), each node:

1. Selects `gossip_fanout` random peers from its known cluster members (default: 3)
2. Sends `POST /v1/mesh/gossip` with its known `NodeState` list
3. Receives the other node's `NodeState` list in the response
4. Merges both lists: for each `node_id`, keeps the state with the most recent `last_heartbeat` timestamp

```
Node A                            Node B
  |                                  |
  |--- POST /v1/mesh/gossip ------>  |
  |    Body: { nodes: [A, C, D] }    |
  |                                  |
  | <--- 200 OK -------------------- |
  |    Body: { nodes: [B, C, E] }    |
  |                                  |
  |    A now knows: A, B, C, D, E    |
  |    B now knows: A, B, C, D, E    |
```

Because each node contacts `gossip_fanout` random peers per round, information spreads exponentially. In a 10-node cluster with fanout of 3, all nodes converge within 3-4 gossip rounds (6-8 seconds at default intervals).

### Convergence Properties

- **Consistency:** Eventual. All nodes converge to the same view of the cluster, but there is a propagation delay.
- **Partition tolerance:** If the network partitions, each side maintains its own view. When the partition heals, gossip re-merges the states.
- **Bandwidth:** O(N) per gossip round per node, where N is the cluster size. Each round transmits the full node state list. This is acceptable for clusters up to ~100 nodes.

## Heartbeats

Every `heartbeat_interval` seconds (default: 5s), each node updates its own `last_heartbeat` timestamp and refreshes its `NodeLoad` (CPU percent, memory percent, active request count). This information propagates to other nodes via gossip.

### Failure Detection

Peers evaluate each node's `last_heartbeat` relative to the current time:

| Condition | Status | Effect |
|-----------|--------|--------|
| `now - last_heartbeat < 15s` | **alive** | Normal routing and scheduling |
| `15s <= now - last_heartbeat < 30s` | **suspect** | Removed from routing (no new requests sent) |
| `now - last_heartbeat >= 30s` | **dead** | Removed from routing, triggers leader re-election if node was leader |

Dead nodes are removed from the cluster state entirely after 60 additional seconds.

```
Time ──────────────────────────────────────────────────────>

Node X heartbeat:
  t=0s    t=5s    t=10s   t=15s   ...silence...
   |       |       |       |
   HB      HB      HB      HB     (last heartbeat)

Other nodes' view:
  t=0-14s : alive   (routing normally)
  t=15-29s: suspect (stop routing to Node X)
  t=30s+  : dead    (remove from cluster, re-elect if leader)
  t=90s+  : purged  (removed from cluster state entirely)
```

The suspect state prevents sending requests to a node that may be failing, while giving it time to recover (e.g., from a long GC pause or temporary network issue). Only after 30 seconds of silence is the node declared dead.

## Leader Election

Maia uses the **bully algorithm** for leader election. The node with the highest `node_id` (lexicographic UUID comparison) becomes the leader. This is simple and deterministic — given the same set of alive nodes, all nodes agree on the same leader.

### Election Triggers

An election starts when:

- A new node joins the cluster (it may have a higher ID than the current leader)
- The current leader is detected as dead (heartbeat timeout)
- A node starts up and finds no leader in the cluster state

### Election Flow

```
Node A (id: aaa)          Node B (id: bbb)          Node C (id: ccc)
     |                         |                         |
     | (detects leader dead)   |                         |
     |                         |                         |
     |-- POST /v1/mesh/election --> B (higher id)        |
     |-- POST /v1/mesh/election -----------------------> C (higher id)
     |                         |                         |
     | <--- "I'm higher" ---- |                          |
     | <--- "I'm higher" --------------------------------|
     |                         |                         |
     | (A backs off)           |                         |
     |                         |-- POST /v1/mesh/election -> C
     |                         |                         |
     |                         | <-- "I'm higher" ------ |
     |                         |                         |
     |                         | (B backs off)           |
     |                         |                         |
     |                         |         C wins election |
     |                         |         sets leader=true|
     |                         |         in its NodeState|
     |                         |                         |
     |    (gossip propagates C as leader to all nodes)   |
```

A node only sends election messages to nodes with higher IDs. If no higher node responds within a timeout, the node declares itself leader. The new leader sets `leader: true` in its `NodeState`, and this propagates via gossip.

### Leader Responsibilities

The leader runs the `Scheduler`, which handles:

- **Agent placement:** decides which nodes should load which agents
- **Request routing:** directs incoming requests to the best node (see below)

If the leader fails, a new election happens automatically and a new leader takes over scheduling duties.

## Request Routing

When a request arrives at a gateway node (or any node that does not run the target agent locally), the `Scheduler` on the leader determines where to send it.

### Routing Strategy: Least Connections

The scheduler uses a **least-connections** strategy: among all nodes that have the target agent loaded, route to the node with the fewest `active_requests`.

```
Incoming request for "support-agent"
         |
         v
    Scheduler checks cluster state:
         |
         +-- worker-1: has support-agent, active_requests = 3
         +-- worker-2: has support-agent, active_requests = 7
         +-- worker-3: does NOT have support-agent
         |
         v
    Route to worker-1 (fewest active connections)
```

Load information is propagated via heartbeats and gossip, so the scheduler always has a recent (though not real-time) view of each node's load. The `active_requests` count is updated on every heartbeat (default every 5 seconds).

### Agent Placement

The leader places agents on all worker nodes that have the `agents` service enabled. By default, every agent is replicated across all available workers. Custom placement strategies (GPU-aware, affinity-based) are planned for a future release.

## Configuration

### Minimal Configuration

Three lines are all you need to join a mesh:

```yaml
spec:
  mesh:
    enabled: true
    seeds:
      - http://seed-node:8000
```

The node generates its own UUID, uses defaults for all intervals, and joins the mesh via the seed.

### Full Configuration

All tuning parameters with their defaults:

```yaml
spec:
  mesh:
    enabled: true
    node_name: "worker-1"            # Human-readable name (optional)
    bind: "0.0.0.0:8000"             # Address this node listens on
    seeds:                            # Seed nodes to contact on boot
      - http://gateway:8000
      - http://worker-2:8000
    heartbeat_interval: 5             # Seconds between heartbeats
    gossip_interval: 2                # Seconds between gossip rounds
    gossip_fanout: 3                  # Number of peers to gossip with per round
    failure_timeout: 15               # Seconds without heartbeat -> suspect
    dead_timeout: 30                  # Seconds without heartbeat -> dead
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enabled` | `false` | Enable mesh protocol |
| `node_name` | hostname | Human-readable node identifier |
| `bind` | `0.0.0.0:8000` | Listen address for mesh and API |
| `seeds` | `[]` | Seed nodes to contact on startup |
| `heartbeat_interval` | `5` | Seconds between heartbeat updates |
| `gossip_interval` | `2` | Seconds between gossip exchanges |
| `gossip_fanout` | `3` | Random peers to contact per gossip round |
| `failure_timeout` | `15` | Seconds of silence before marking node as suspect |
| `dead_timeout` | `30` | Seconds of silence before marking node as dead |

## API Endpoints

All mesh endpoints are under `/v1/mesh/`:

| Endpoint | Method | Body | Response | Description |
|----------|--------|------|----------|-------------|
| `/v1/mesh/join` | POST | `NodeState` | `ClusterState` | Announce a new node to the cluster |
| `/v1/mesh/leave` | POST | `{ node_id }` | 200 OK | Notify graceful departure |
| `/v1/mesh/heartbeat` | POST | `NodeState` (with updated load) | 200 OK | Periodic heartbeat |
| `/v1/mesh/gossip` | POST | `{ nodes: [NodeState...] }` | `{ nodes: [NodeState...] }` | Push-pull state exchange |
| `/v1/mesh/state` | GET | -- | `ClusterState` | Full cluster state (all nodes, leader, version) |
| `/v1/mesh/election` | POST | `{ candidate_id, node_id }` | Election response | Leader election message |

These endpoints are served by the same FastAPI application as the agent API. No additional ports or protocols are required.

## Backward Compatibility

Maia is fully backward compatible with static peer configuration:

| Scenario | Behavior |
|----------|----------|
| No `spec.mesh` in config | Works exactly like pre-Maia versions (static peers from `spec.peers`) |
| `mesh.enabled: false` | Same as no `spec.mesh` — static peers are used |
| `mesh.enabled: true` + `spec.peers` defined | Maia takes control. `spec.peers` is ignored. A warning is logged: "Mesh enabled; ignoring static peer configuration" |
| Mesh node + non-mesh node | The non-mesh node does not participate in gossip but can still be configured as a static peer on other non-mesh nodes |

The `PeerClient` interface (used by route handlers and the runtime to forward requests) is unchanged. When mesh is enabled, `PeerClient.from_mesh(mesh)` creates a peer client that reads peers dynamically from the live `ClusterState` instead of from YAML. The `forward()`, `find_peers()`, and `health_check()` methods work identically.

## Limitations

The following are known limitations of the current Maia implementation. These are intentional scope boundaries for the initial release, with plans to address them in future versions.

- **No automatic rescheduling.** When a node fails, the mesh detects it and reports it, but agents are not automatically relocated. The operator must manually decide where to place them. Automatic rescheduling with circuit breakers (to prevent cascading failures) is planned once failure detection is battle-tested.

- **No agent migration.** A running agent cannot be moved from one node to another mid-execution. This would require state serialization, transfer, and resume, which is complex and error-prone.

- **No distributed memory.** Each node manages its own memory backends independently. Agent sessions are local to the node where the agent runs. Shared memory across the mesh (distributed Redis, CRDTs, session replication) is deferred.

- **No WAN support.** The gossip protocol assumes low-latency networking (LAN, single datacenter, VPN). WAN-aware gossip with region-aware routing, split-brain handling, and latency-based peer selection is future work.

- **No mTLS.** Nodes communicate over plain HTTP. Mutual TLS for node-to-node authentication and encryption is important for production but deferred to keep the protocol simple during initial development.

- **No DNS-based seed discovery.** Seeds are configured manually in `spec.mesh.seeds`. Automatic discovery via DNS SRV records or Kubernetes headless services would simplify container deployments.

- **Only least-connections routing.** The current routing strategy is least-connections. Future strategies include latency-aware routing, GPU-aware placement, affinity rules, priority queues, and preemption.

- **No global rate limiting.** Rate limiting is per-node. Mesh-wide shared counters and distributed token buckets require coordination beyond what the current gossip protocol provides.
