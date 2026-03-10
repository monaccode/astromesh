---
title: Scheduling & Routing
description: Agent placement and request routing in mesh mode
---

In mesh mode, multiple Astromesh nodes form a cluster. The scheduling and routing layer determines which node handles each incoming request based on agent placement, current load, and leader election.

## Agent Placement

Each node loads and serves the agents defined in its local `config/agents/` directory. The cluster's gossip protocol propagates this information so every node knows which agents are available on which peers.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  node-alpha  │    │  node-beta   │    │  node-gamma  │
│              │    │              │    │              │
│  assistant   │    │  researcher  │    │  assistant   │
│  support     │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

When a request arrives for a specific agent, the receiving node checks:

1. **Local first:** If this node has the agent loaded, handle locally
2. **Remote routing:** If this node does not have the agent, forward to a peer that does

If multiple nodes serve the same agent, the request is routed using the least-connections algorithm.

## Least-Connections Routing

When multiple nodes can serve a given agent, the router selects the node with the fewest active (in-flight) requests.

### Algorithm

```
Incoming request for agent "assistant"
              │
              ▼
  Find all nodes serving "assistant"
  ┌──────────────────────────────────┐
  │  node-alpha:  12 active requests │
  │  node-gamma:   3 active requests │
  └──────────────────────────────────┘
              │
              ▼
  Select node with fewest active: node-gamma
              │
              ▼
  Forward request to node-gamma
```

**Tie-breaking:** When multiple nodes have equal active request counts, the node with the lower `avg_latency_ms` is preferred.

**Health awareness:** Nodes in `suspect` state are deprioritized (treated as if they have +100 virtual active requests). Nodes in `dead` state are excluded entirely.

### Active Request Tracking

Each node reports its active request count in gossip metadata. The count is updated in real-time:

- Incremented when a request begins execution
- Decremented when a response is sent or the request times out

Gossip propagation means remote counts may be slightly stale (up to one gossip interval behind). This is acceptable because perfect accuracy is not required for effective load balancing.

## Leader Election

The cluster elects a single leader node using the **bully algorithm**. The leader is responsible for:

- Cluster-wide health monitoring
- Coordinating agent rebalancing when nodes join or leave
- Serving as the tiebreaker for scheduling conflicts

### Bully Algorithm

The node with the **highest `node_id`** (lexicographic comparison) becomes the leader.

```
Nodes in cluster:
  node-alpha   (id: "alpha")
  node-beta    (id: "beta")
  node-gamma   (id: "gamma")

Leader: node-gamma (highest id)
```

### Election Process

```
  Trigger event
  (node join, leader death, startup)
         │
         ▼
  Node sends ELECTION message
  to all nodes with higher IDs
         │
         ├──── No response within timeout
         │     → This node becomes leader
         │     → Sends COORDINATOR message to all
         │
         └──── Higher node responds with OK
               → Higher node takes over election
               → Wait for COORDINATOR message
```

### Re-Election Triggers

| Trigger | Description |
|---------|-------------|
| **Leader death** | Leader node's heartbeat exceeds `dead_threshold`. Any node detecting this initiates election |
| **New node joins** | If the new node has a higher `node_id` than the current leader, election is triggered |
| **Network partition heals** | When previously partitioned nodes reconnect, they compare leaders and re-elect if needed |
| **Startup** | Each node initiates election on first joining the cluster |

## Routing Decision Flow

Complete flow for an incoming API request in mesh mode:

```
Client request: POST /v1/agents/assistant/run
                    │
                    ▼
           ┌───────────────┐
           │ Receiving Node │
           └───────┬───────┘
                   │
         ┌─────────▼──────────┐
         │ Agent loaded        │
         │ locally?            │
         └─────────┬──────────┘
              │          │
           Yes │          │ No
              │          │
              ▼          ▼
     ┌────────────┐  ┌──────────────────┐
     │ Check local│  │ Find peers with  │
     │ load vs    │  │ this agent       │
     │ remote     │  └────────┬─────────┘
     └─────┬──────┘           │
           │                  ▼
           │         ┌───────────────────┐
           │         │ Any peers found?  │
           │         └────────┬──────────┘
           │              │        │
           │           Yes │        │ No
           │              │        │
           │              ▼        ▼
           │    ┌─────────────┐  Return 404
           │    │ Least-conn  │  "Agent not
           │    │ select peer │  found in
           │    └──────┬──────┘  cluster"
           │           │
           ▼           ▼
     Execute locally   Forward to
     or on best node   selected peer
```

## Future Scheduling Strategies

The following strategies are planned for future releases:

| Strategy | Description | Status |
|----------|-------------|--------|
| **Affinity** | Route requests from the same session to the same node for memory locality | Planned |
| **Latency-based** | Route to the node with the lowest observed round-trip time from the client | Planned |
| **Cost-based** | Factor in per-node compute cost (cloud instance pricing) for routing decisions | Planned |
| **Capability-aware** | Route based on hardware capabilities (GPU availability, memory capacity) | Planned |

## Configuration

Scheduling parameters are set in `runtime.yaml`:

```yaml
mesh:
  enabled: true
  routing:
    strategy: least_connections
    local_preference: true
    suspect_penalty: 100
  election:
    algorithm: bully
    timeout: 5s
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `routing.strategy` | `least_connections` | Routing algorithm for multi-node agents |
| `routing.local_preference` | `true` | Prefer local execution when the agent is loaded on this node |
| `routing.suspect_penalty` | `100` | Virtual active requests added to suspect nodes |
| `election.algorithm` | `bully` | Leader election algorithm |
| `election.timeout` | `5s` | Timeout for election responses before self-declaring leader |
