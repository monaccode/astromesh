---
title: Memory Manager
description: Memory types, backends, and strategies
---

The Memory Manager provides agents with persistent context across conversations through three distinct memory types, each with pluggable backends and configurable retention strategies. It lives in `astromesh/core/memory.py`.

## Memory Types

```mermaid
flowchart TB
    subgraph mm ["MemoryManager"]
        conv["`**Conversational**
        Chat history (turns)`"]
        sem["`**Semantic**
        Vector embeddings (similarity)`"]
        epi["`**Episodic**
        Event logs (actions)`"]
    end
    conv --> cb["Backend"]
    sem --> sb["Backend"]
    epi --> eb["Backend"]
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
| Redis | `redis` | Persistent across restarts, TTL support, shared across instances. **The only one the factory builds.** |

:::caution[`redis` or no memory]
`agent.schema.json` also accepts `postgres`, `sqlite` and `in_memory`, but
`build_conversation_backend` constructs only `redis`. Declaring one of the other three logs
a warning naming the backend, and the agent runs **without conversational memory**. The
schema and the factory do not yet say the same thing; the schema is the one that is ahead.

Omitting `connection.url`, or running a build without the `redis` extra installed, degrades
the same way — with a warning that names what is missing.
:::

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

Strategies control how conversational memory is read back. All of them read the last `max_turns` turns; the token budget below is then applied on top.

| Strategy | Behavior | Configuration |
|----------|----------|---------------|
| `sliding_window` | Keep only the last `max_turns` turns. Oldest turns are dropped | `max_turns: 20` |
| `summary` | Turns that leave the `max_turns` window are folded into an incremental summary, kept next to the verbatim turns | `max_turns: 20` |
| `token_budget` | Keep as many recent turns as fit the budget, newest first | `max_turns: 20` |

### History budget and delivery

The engine calls `fit_history(context, budget)` after it has measured the rest of the prompt:

```
budget = 90% of context window − (system prompt + tool schemas + response max_tokens + prompts.context)
```

Turns are kept newest first until the budget is spent. A summary is counted first and dropped if it alone does not fit.

**Window resolution**, in order: `context_window` on the model candidate in the YAML, then `parameters.num_ctx` (Ollama), then litellm's model info. With several candidates in the default role, the smallest window is used. If none resolves, the window is unknown: **no budget trimming**, only `max_turns` applies, and a warning is logged at load time.

**Delivery.** History reaches the model as chat messages (`react` and `glyph` patterns), so the system prompt stays identical between turns and the provider cache can work. If `prompts.system` references `memory.conversation` (detected by `memory\.conversation\b`), the legacy path is used instead: history is rendered into the system prompt, no messages are sent, and a warning is logged.

**Token counts.** `persist_turn` stores each turn with its `token_count` (litellm if installed, otherwise `len/4`). Old rows stored with `0` are estimated when read. Assistant replies over 50 tokens go to semantic memory when it is wired.

**Summary.** With `strategy: summary`, after the assistant turn of an exchange, once `max_turns` is exceeded, `persist_turn` makes one call to the agent's `summarizer` role (or `default`) that merges the turns just leaving the verbatim window into the previous summary. It runs inline and a failure does not break `persist_turn`.

### Strategy Configuration

```yaml
spec:
  memory:
    conversational:
      backend: redis
      strategy: sliding_window
      max_turns: 20
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
2. Read the last `max_turns` turns (plus the running summary with `summary`). With `max_tokens` set, trim to it; without it nothing is trimmed here and the engine applies the budget later with `fit_history`
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
      max_turns: 20
      connection:
        url: "redis://localhost:6379/0"   # required, no default
      ttl: 86400                          # default: 259200 (72h)
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
| `conversational.backend` | No | -- | `redis`. Omit to run without conversational memory |
| `conversational.connection.url` | With `redis` | -- | Redis URL. Read with no default |
| `conversational.ttl` | No | `259200` | Seconds a session's history survives (72h) |
| `conversational.strategy` | No | `sliding_window` | Retention strategy |
| `conversational.max_turns` | No | `50` | Turns read back per run; with `summary`, the verbatim window |
| `semantic.backend` | No | -- | Backend for vector memory. Omit to disable semantic memory |
| `semantic.collection` | No | `{agent_name}_memory` | Vector store collection name |
| `semantic.top_k` | No | `5` | Number of similar results to retrieve |
| `episodic.backend` | No | -- | Backend for event logs. Omit to disable episodic memory |
