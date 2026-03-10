---
title: API Endpoints
description: Complete REST API and WebSocket reference
---

All endpoints are served by the Astromesh daemon (`astromeshd`) and are prefixed with `/v1`. The default base URL is `http://localhost:8000`.

## Core API

### `GET /v1/health`

Health check endpoint. Returns 200 if the daemon is running.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.10.0",
  "uptime_seconds": 8072
}
```

---

### `GET /v1/agents`

List all loaded agents.

**Response:**
```json
{
  "agents": [
    {
      "name": "assistant",
      "description": "General-purpose assistant",
      "model": "openai/gpt-4o",
      "orchestration": "react",
      "status": "ready"
    },
    {
      "name": "researcher",
      "description": "Research and analysis agent",
      "model": "anthropic/claude-sonnet-4-20250514",
      "orchestration": "plan_and_execute",
      "status": "ready"
    }
  ]
}
```

---

### `GET /v1/agents/{name}`

Get details for a specific agent.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Agent name as defined in YAML |

**Response:**
```json
{
  "name": "assistant",
  "description": "General-purpose assistant",
  "model": {
    "primary": { "provider": "openai", "model": "gpt-4o" },
    "fallback": { "provider": "anthropic", "model": "claude-sonnet-4-20250514" },
    "routing": "cost_optimized"
  },
  "orchestration": { "pattern": "react", "max_iterations": 10, "timeout": 120 },
  "tools": ["web_search", "knowledge_base"],
  "memory": { "conversational": "redis", "semantic": "chroma" },
  "status": "ready"
}
```

**Errors:**

| Status | Description |
|--------|-------------|
| `404` | Agent not found |

---

### `POST /v1/agents/{name}/run`

Execute an agent with a user query.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Agent name |

**Request body:**
```json
{
  "query": "What are the latest trends in AI?",
  "session_id": "sess_abc123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | `string` | Yes | User input text |
| `session_id` | `string` | No | Session ID for memory continuity. Auto-generated if omitted |

**Response:**
```json
{
  "response": "Based on my research, the latest trends in AI include...",
  "session_id": "sess_abc123",
  "tool_calls": [
    {
      "tool": "web_search",
      "input": { "query": "latest AI trends 2026" },
      "output": "..."
    }
  ],
  "usage": {
    "input_tokens": 1250,
    "output_tokens": 430,
    "total_tokens": 1680
  },
  "timing": {
    "total_ms": 3200,
    "model_ms": 2800,
    "tool_ms": 400
  },
  "model": "openai/gpt-4o",
  "provider": "openai"
}
```

**Errors:**

| Status | Description |
|--------|-------------|
| `404` | Agent not found |
| `503` | All providers unavailable |
| `408` | Orchestration timeout exceeded |

---

### `GET /v1/memory/{agent}/history/{session}`

Retrieve conversational history for an agent session.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `agent` | `string` | Agent name |
| `session` | `string` | Session ID |

**Response:**
```json
{
  "agent": "assistant",
  "session_id": "sess_abc123",
  "messages": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hi! How can I help?" },
    { "role": "user", "content": "What is Astromesh?" },
    { "role": "assistant", "content": "Astromesh is..." }
  ]
}
```

---

### `DELETE /v1/memory/{agent}/history/{session}`

Clear conversational history for an agent session.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `agent` | `string` | Agent name |
| `session` | `string` | Session ID |

**Response:**
```json
{
  "status": "cleared",
  "agent": "assistant",
  "session_id": "sess_abc123"
}
```

---

### `GET /v1/memory/{agent}/semantic`

Query semantic memory for an agent.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `agent` | `string` | Agent name |

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `string` | (required) | Text to search for semantically similar entries |
| `top_k` | `integer` | `5` | Number of results to return |

**Response:**
```json
{
  "results": [
    {
      "text": "Previous conversation about deployment...",
      "score": 0.92,
      "metadata": { "session_id": "sess_xyz", "timestamp": "2026-03-08T14:30:00Z" }
    }
  ]
}
```

---

### `GET /v1/tools`

List all registered tools across all agents.

**Response:**
```json
{
  "tools": [
    {
      "name": "web_search",
      "type": "internal",
      "description": "Search the web for current information",
      "agents": ["assistant", "researcher"]
    },
    {
      "name": "mcp_filesystem",
      "type": "mcp",
      "description": "File system operations",
      "agents": ["assistant"]
    }
  ]
}
```

---

### `POST /v1/tools/execute`

Execute a tool directly (outside of an agent context).

**Request body:**
```json
{
  "tool": "web_search",
  "input": {
    "query": "Astromesh documentation",
    "max_results": 3
  }
}
```

**Response:**
```json
{
  "tool": "web_search",
  "output": {
    "results": [
      { "title": "Astromesh Docs", "url": "https://..." }
    ]
  },
  "timing_ms": 320
}
```

---

### `POST /v1/rag/ingest`

Ingest documents into a RAG collection.

**Request body:**
```json
{
  "collection": "product_docs",
  "documents": [
    {
      "text": "Astromesh supports multiple LLM providers...",
      "metadata": { "source": "docs", "page": 1 }
    }
  ],
  "chunk_size": 512,
  "chunk_overlap": 50
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `collection` | `string` | Yes | -- | Target collection name |
| `documents` | `array` | Yes | -- | Documents to ingest (text + metadata) |
| `chunk_size` | `integer` | No | `512` | Characters per chunk for splitting |
| `chunk_overlap` | `integer` | No | `50` | Overlap between chunks |

**Response:**
```json
{
  "collection": "product_docs",
  "documents_ingested": 1,
  "chunks_created": 4
}
```

---

### `POST /v1/rag/query`

Query a RAG collection.

**Request body:**
```json
{
  "collection": "product_docs",
  "query": "How does the model router work?",
  "top_k": 5,
  "score_threshold": 0.7
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `collection` | `string` | Yes | -- | Collection to search |
| `query` | `string` | Yes | -- | Natural language query |
| `top_k` | `integer` | No | `5` | Maximum results |
| `score_threshold` | `float` | No | `0.0` | Minimum similarity score |

**Response:**
```json
{
  "results": [
    {
      "text": "The Model Router selects which LLM provider...",
      "score": 0.89,
      "metadata": { "source": "docs", "page": 3 }
    }
  ]
}
```

### `GET /v1/tools/builtin`

List all available built-in tools with metadata.

**Response:**
```json
{
  "tools": [
    {
      "name": "datetime_now",
      "description": "Get the current date and time with optional timezone",
      "parameters": {
        "type": "object",
        "properties": {
          "timezone": {
            "type": "string",
            "description": "Timezone name (e.g. 'UTC', 'US/Eastern')"
          }
        }
      }
    }
  ],
  "count": 17
}
```

---

## Observability API

### `GET /v1/traces/`

List collected traces with optional filtering.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `string` | — | Filter by agent name |
| `limit` | `integer` | `20` | Max traces to return (1-100) |

**Response:**
```json
{
  "traces": [
    {
      "trace_id": "abc123",
      "agent": "assistant",
      "session_id": "sess_xyz",
      "spans": [
        {
          "name": "agent.run",
          "span_id": "s1",
          "duration_ms": 2340,
          "attributes": {"agent": "assistant"},
          "status": "OK"
        }
      ]
    }
  ]
}
```

---

### `GET /v1/traces/{trace_id}`

Get a specific trace by ID.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `trace_id` | `string` | Trace identifier |

**Errors:**

| Status | Description |
|--------|-------------|
| `404` | Trace not found |

---

### `GET /v1/metrics/`

Get in-memory counters and histograms.

**Response:**
```json
{
  "counters": {
    "agent.runs": 150,
    "tool.executions": 420
  },
  "histograms": {
    "agent.latency_ms": {
      "count": 150,
      "sum": 345000,
      "avg": 2300,
      "min": 450,
      "max": 8900
    }
  }
}
```

---

### `POST /v1/metrics/reset`

Clear all in-memory metrics.

**Response:**
```json
{
  "status": "reset"
}
```

---

## System API (Astromesh OS)

### `GET /v1/system/status`

System status including version, uptime, and resource usage.

**Response:**
```json
{
  "version": "0.10.0",
  "status": "running",
  "mode": "standalone",
  "pid": 48291,
  "uptime_seconds": 8072,
  "agents_loaded": 3,
  "providers": {
    "healthy": 2,
    "degraded": 0,
    "unavailable": 0
  }
}
```

---

### `GET /v1/system/doctor`

Run health checks on all subsystems.

**Response:**
```json
{
  "checks": [
    { "name": "runtime", "status": "healthy", "message": null },
    { "name": "openai", "status": "healthy", "message": "avg latency: 420ms" },
    { "name": "redis", "status": "healthy", "message": null },
    { "name": "chromadb", "status": "failing", "message": "connection refused on localhost:8000" }
  ],
  "summary": {
    "healthy": 3,
    "degraded": 0,
    "failing": 1
  }
}
```

## Mesh API (Maia)

These endpoints are only available when mesh mode is enabled (`ASTROMESH_MESH_ENABLED=true`).

### `GET /v1/mesh/state`

Get the full mesh state as seen by this node.

**Response:**
```json
{
  "this_node": "node-beta",
  "leader": "node-alpha",
  "nodes": [
    {
      "node_id": "node-alpha",
      "address": "10.0.1.10:8000",
      "state": "alive",
      "heartbeat": 4521,
      "agents": ["assistant", "support"],
      "active_requests": 12
    },
    {
      "node_id": "node-beta",
      "address": "10.0.1.11:8000",
      "state": "alive",
      "heartbeat": 4519,
      "agents": ["researcher"],
      "active_requests": 5
    }
  ]
}
```

---

### `POST /v1/mesh/join`

Request to join the cluster. Called by new nodes during startup.

**Request body:**
```json
{
  "node_id": "node-gamma",
  "address": "10.0.1.12:8000",
  "agents": ["assistant"],
  "meta": { "version": "0.10.0" }
}
```

**Response:**
```json
{
  "status": "joined",
  "leader": "node-alpha",
  "cluster_size": 3
}
```

---

### `POST /v1/mesh/leave`

Gracefully leave the cluster. Notifies peers and drains requests.

**Request body:**
```json
{
  "node_id": "node-gamma"
}
```

**Response:**
```json
{
  "status": "left",
  "drained_requests": 2
}
```

---

### `POST /v1/mesh/heartbeat`

Receive a heartbeat from a peer node.

**Request body:**
```json
{
  "node_id": "node-alpha",
  "heartbeat": 4522,
  "active_requests": 14
}
```

**Response:**
```json
{
  "ack": true
}
```

---

### `POST /v1/mesh/gossip`

Exchange gossip state with a peer. Push-pull: receives the sender's state and returns this node's state.

**Request body:**
```json
{
  "sender": "node-alpha",
  "state": [
    { "node_id": "node-alpha", "heartbeat": 4522, "state": "alive", "agents": ["assistant"] },
    { "node_id": "node-beta", "heartbeat": 4519, "state": "alive", "agents": ["researcher"] }
  ]
}
```

**Response:**
```json
{
  "sender": "node-beta",
  "state": [
    { "node_id": "node-alpha", "heartbeat": 4520, "state": "alive", "agents": ["assistant"] },
    { "node_id": "node-beta", "heartbeat": 4520, "state": "alive", "agents": ["researcher"] },
    { "node_id": "node-gamma", "heartbeat": 4510, "state": "suspect", "agents": ["assistant"] }
  ]
}
```

---

### `POST /v1/mesh/election`

Trigger or participate in a leader election.

**Request body:**
```json
{
  "type": "election",
  "sender": "node-beta"
}
```

| `type` Value | Description |
|-------------|-------------|
| `election` | Initiate election. Higher-ID nodes respond with `ok` |
| `ok` | Response from a higher-ID node (it will take over the election) |
| `coordinator` | Announcement from the new leader |

**Response:**
```json
{
  "type": "ok",
  "sender": "node-gamma"
}
```

## WebSocket

### `ws://host:port/v1/ws/agent/{name}`

Stream agent responses in real-time over WebSocket.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `string` | Agent name |

**Client sends:**
```json
{
  "query": "Explain quantum computing",
  "session_id": "sess_abc123"
}
```

**Server sends (multiple messages):**

Token chunks:
```json
{
  "type": "token",
  "content": "Quantum"
}
```

Tool call notification:
```json
{
  "type": "tool_call",
  "tool": "web_search",
  "input": { "query": "quantum computing basics" }
}
```

Tool result:
```json
{
  "type": "tool_result",
  "tool": "web_search",
  "output": "..."
}
```

Completion:
```json
{
  "type": "done",
  "usage": {
    "input_tokens": 800,
    "output_tokens": 350,
    "total_tokens": 1150
  },
  "timing": {
    "total_ms": 2400
  }
}
```

Error:
```json
{
  "type": "error",
  "message": "Provider unavailable"
}
```
