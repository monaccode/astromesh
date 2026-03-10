---
title: Memory Manager
description: Memory types, backends, and strategies
---

The Memory Manager provides agents with persistent context across conversations through three distinct memory types, each with pluggable backends and configurable retention strategies. It lives in `astromesh/core/memory.py`.

## Memory Types

```
┌─────────────────────────────────────────────────────┐
│                  MemoryManager                       │
│                                                      │
│  ┌───────────────┐ ┌──────────────┐ ┌─────────────┐ │
│  │ Conversational│ │   Semantic   │ │   Episodic  │ │
│  │               │ │              │ │             │ │
│  │ Chat history  │ │ Vector       │ │ Event logs  │ │
│  │ (turns)       │ │ embeddings   │ │ (actions)   │ │
│  │               │ │ (similarity) │ │             │ │
│  └───────┬───────┘ └──────┬───────┘ └──────┬──────┘ │
│          │                │                │         │
│          ▼                ▼                ▼         │
│     ┌─────────┐    ┌───────────┐    ┌──────────┐   │
│     │ Backend │    │  Backend  │    │ Backend  │   │
│     └─────────┘    └───────────┘    └──────────┘   │
└─────────────────────────────────────────────────────┘
```

| Memory Type | What It Stores | Access Pattern | Purpose |
|-------------|---------------|----------------|---------|
| **Conversational** | User and assistant message turns for the current session | Sequential (recent history) | Maintain conversation continuity within a session |
| **Semantic** | Vector embeddings of past interactions and documents | Similarity search (nearest neighbor) | Recall relevant past information across sessions |
| **Episodic** | Structured event logs (tool calls, decisions, outcomes) | Filtered query (by type, time, agent) | Track what the agent did and why, audit trail |

## Backend Options

Each memory type supports multiple storage backends:

### Conversational Memory Backends

| Backend | Identifier | Description |
|---------|-----------|-------------|
| In-memory | `memory` | Dictionary-based, lost on restart. Good for development |
| Redis | `redis` | Persistent across restarts, TTL support, shared across instances |
| PostgreSQL | `postgres` | Full durability, SQL queryable, suitable for production |

### Semantic Memory Backends

| Backend | Identifier | Description |
|---------|-----------|-------------|
| In-memory | `memory` | Simple cosine similarity, no persistence |
| ChromaDB | `chroma` | Embedded vector database, file-based persistence |
| PostgreSQL + pgvector | `pgvector` | Production vector store with SQL integration |

### Episodic Memory Backends

| Backend | Identifier | Description |
|---------|-----------|-------------|
| In-memory | `memory` | List-based, lost on restart |
| PostgreSQL | `postgres` | Durable event log with timestamp indexing |

## Strategies

Strategies control how conversational memory is trimmed to fit within the model's context window.

| Strategy | Behavior | Configuration |
|----------|----------|---------------|
| `sliding_window` | Keep only the last N turns. Oldest turns are dropped | `window_size: 20` |
| `summary` | When history exceeds the threshold, compress older turns into a summary using the LLM | `summary_threshold: 30` |
| `token_budget` | Keep as many recent turns as fit within a token limit. Counts tokens and drops oldest turns first | `max_tokens: 8000` |

### Strategy Configuration

```yaml
spec:
  memory:
    conversational:
      backend: redis
      strategy: sliding_window
      window_size: 20
    semantic:
      backend: chroma
      collection: "agent_memory"
    episodic:
      backend: postgres
```

## Core Methods

### `build_context(agent_name, session_id, query)`

Assembles context from all configured memory types into a single context object for prompt rendering.

```python
async def build_context(
    agent_name: str,
    session_id: str,
    query: str,
) -> MemoryContext
```

**Steps:**
1. Load conversational history for the session from the backend
2. Apply the configured strategy (sliding_window, summary, or token_budget) to trim history
3. If semantic memory is enabled, embed the current query and retrieve top-k similar past entries
4. If episodic memory is enabled, retrieve recent events relevant to the agent/session
5. Return a `MemoryContext` combining all three

**MemoryContext fields:**

| Field | Type | Description |
|-------|------|-------------|
| `history` | `list[Message]` | Trimmed conversational turns |
| `semantic_results` | `list[SemanticResult]` | Relevant past interactions (text + similarity score) |
| `episodes` | `list[Episode]` | Recent event log entries |

### `persist_turn(agent_name, session_id, user_message, assistant_message)`

Stores a completed user/assistant exchange in all configured memory backends.

```python
async def persist_turn(
    agent_name: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    metadata: dict | None = None,
) -> None
```

**Steps:**
1. Append user and assistant messages to conversational memory
2. If semantic memory is enabled, embed the exchange and store the vector
3. If episodic memory is enabled, log a `turn_completed` event with metadata (tokens used, tools called, latency)

### `clear_history(agent_name, session_id)`

Delete all conversational history for a session.

```python
async def clear_history(
    agent_name: str,
    session_id: str,
) -> None
```

## Agent YAML Configuration

Full memory configuration example:

```yaml
spec:
  memory:
    conversational:
      backend: redis
      strategy: token_budget
      max_tokens: 8000
      redis:
        url: "redis://localhost:6379/0"
        ttl: 86400
    semantic:
      backend: chroma
      collection: "my_agent_memory"
      top_k: 5
      chroma:
        path: "./data/chroma"
    episodic:
      backend: postgres
      postgres:
        dsn: "postgresql://user:pass@localhost:5432/astromesh"
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `conversational.backend` | No | `memory` | Storage backend for chat history |
| `conversational.strategy` | No | `sliding_window` | Retention strategy |
| `conversational.window_size` | No | `20` | Turns to keep (sliding_window strategy) |
| `conversational.summary_threshold` | No | `30` | Turn count that triggers summarization (summary strategy) |
| `conversational.max_tokens` | No | `8000` | Token budget limit (token_budget strategy) |
| `semantic.backend` | No | -- | Backend for vector memory. Omit to disable semantic memory |
| `semantic.collection` | No | `{agent_name}_memory` | Vector store collection name |
| `semantic.top_k` | No | `5` | Number of similar results to retrieve |
| `episodic.backend` | No | -- | Backend for event logs. Omit to disable episodic memory |
