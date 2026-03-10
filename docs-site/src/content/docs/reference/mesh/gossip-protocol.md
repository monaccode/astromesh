---
title: Gossip Protocol
description: Push-pull gossip, heartbeats, and failure detection
---

Astromesh nodes in mesh mode use a push-pull gossip protocol to share cluster state, detect failures, and maintain a consistent view of the network without centralized coordination.

## Algorithm

Astromesh uses **push-pull gossip**: when two nodes exchange state, both sides send their current state and merge the received state. This ensures bidirectional convergence -- each exchange brings both nodes closer to a consistent view.

### Gossip Exchange Sequence

```
    Node A                          Node B
      │                               │
      │  1. Select random peer        │
      │──────── push state ─────────▶ │
      │                               │
      │                               │  2. Merge received state
      │                               │     with local state
      │                               │
      │◀──────── pull state ──────────│  3. Send own state back
      │                               │
      │  4. Merge received state      │
      │     with local state          │
      │                               │
    Both nodes now have the union
    of both states
```

Each gossip round:

1. Node selects up to **fanout** random peers from its membership list
2. For each selected peer, initiate a push-pull exchange
3. Merge the received state, keeping the most recent information for each node (highest heartbeat counter wins)

## Timing Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gossip_interval` | `2s` | How often each node initiates a gossip round |
| `gossip_fanout` | `3` | Number of random peers contacted per gossip round |
| `heartbeat_interval` | `5s` | How often each node increments its own heartbeat counter |

## Heartbeats

Each node maintains a monotonically increasing heartbeat counter. The counter is incremented every `heartbeat_interval` (5 seconds by default) and included in gossip exchanges.

A node's liveness is determined by how recently its heartbeat was observed to change:

```
heartbeat counter:  101   102   103   104   105   106
                     │     │     │     │     │     │
time:               0s    5s   10s   15s   20s   25s
```

Other nodes track the last time they observed a new heartbeat value for each peer. If the observed heartbeat stops advancing, the peer is suspected and eventually declared dead.

## Failure Detection

Nodes are classified into three states based on how long since their heartbeat was last seen to change:

```
        Last heartbeat seen
              │
  ┌───────────┼───────────┬───────────┐
  │  < 15s    │  15-30s   │  > 30s    │
  │           │           │           │
  ▼           ▼           ▼           ▼
┌───────┐  ┌─────────┐  ┌──────┐
│ Alive │  │ Suspect │  │ Dead │
└───────┘  └─────────┘  └──────┘
```

| State | Threshold | Description |
|-------|-----------|-------------|
| **Alive** | < 15 seconds since last heartbeat change | Node is healthy and responsive |
| **Suspect** | 15 -- 30 seconds since last heartbeat change | Node may be down. Still routed to but with lower priority |
| **Dead** | > 30 seconds since last heartbeat change | Node is considered failed. Removed from routing, agents reassigned |

### Configurable Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `suspect_threshold` | `15s` | Time without heartbeat update before marking suspect |
| `dead_threshold` | `30s` | Time without heartbeat update before marking dead |
| `cleanup_threshold` | `120s` | Time after death before removing node from state entirely |

## State Convergence

Gossip protocols provide **eventual consistency** -- all nodes converge to the same state given enough gossip rounds without further changes.

**Convergence speed** depends on cluster size, gossip interval, and fanout:

| Cluster Size | Expected Rounds to Converge | Time at 2s Interval |
|-------------|---------------------------|---------------------|
| 3 nodes | 2 -- 3 rounds | 4 -- 6 seconds |
| 10 nodes | 4 -- 5 rounds | 8 -- 10 seconds |
| 50 nodes | 6 -- 8 rounds | 12 -- 16 seconds |

The push-pull approach converges roughly twice as fast as push-only gossip because each exchange synchronizes both participants.

## Gossip State Payload

Each gossip message contains the sender's full membership table:

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | `string` | Unique identifier for the node |
| `address` | `string` | Host and port (e.g., `10.0.1.10:8000`) |
| `heartbeat` | `integer` | Monotonic heartbeat counter |
| `state` | `string` | Node state as perceived by sender: `alive`, `suspect`, `dead` |
| `agents` | `list[string]` | Agent names loaded on this node |
| `meta` | `object` | Arbitrary metadata (role, version, capabilities) |

## Configuration

Gossip parameters are set in `runtime.yaml` under the `mesh` section:

```yaml
mesh:
  enabled: true
  node_name: "node-alpha"
  bind_port: 8001
  seeds:
    - "10.0.1.10:8001"
    - "10.0.1.11:8001"
  gossip:
    interval: 2s
    fanout: 3
  heartbeat:
    interval: 5s
  failure_detection:
    suspect_threshold: 15s
    dead_threshold: 30s
    cleanup_threshold: 120s
```
