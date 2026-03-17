# Astromesh ADK (Agent Development Kit) — Design Spec

**Date:** 2026-03-17
**Status:** Approved
**Author:** Design session (brainstorming)

---

## 1. Overview

**astromesh-adk** is a Python-first framework for building, running, and deploying AI agents. It provides a developer-friendly API (decorators, builders, classes) on top of the Astromesh core runtime engine, enabling developers to define agents entirely in Python with a DX comparable to FastAPI.

### Design Principles

- **Python-first:** Agents, tools, and configuration defined in Python with decorators and type hints
- **Shared Core:** Reuses Astromesh internal modules (providers, runtime, memory, tools, orchestration) — zero duplication
- **Framework-first:** The SDK is the primary product; Astromesh remote is an optional execution target
- **Progressive complexity:** Simple things are simple (decorator), complex things are possible (class inheritance)

### Package Identity

- **PyPI name:** `astromesh-adk`
- **Import:** `from astromesh_adk import Agent, tool, connect`
- **CLI:** `astromesh-adk`
- **Dependency:** `astromesh` (core engine, no FastAPI/API layer)

---

## 2. Package Structure

```
astromesh-adk/
├── astromesh_adk/
│   ├── __init__.py               # Public API: Agent, tool, Tool, connect, AgentTeam, etc.
│   ├── agent.py                  # @agent decorator + Agent base class
│   ├── tools.py                  # @tool decorator + Tool base class
│   ├── providers.py              # Provider resolution from "provider/model" strings
│   ├── memory.py                 # Memory config builders and shorthands
│   ├── guardrails.py             # Guardrail config helpers
│   ├── orchestration.py          # Pattern selection helpers
│   ├── context.py                # RunContext, ToolContext
│   ├── result.py                 # RunResult (answer, steps, trace, cost, tokens)
│   ├── callbacks.py              # Callbacks base class for observability hooks
│   ├── connection.py             # connect(), disconnect(), remote() context manager
│   ├── team.py                   # AgentTeam for multi-agent composition
│   ├── mcp.py                    # mcp_tools() helper for MCP server integration
│   ├── runner.py                 # Local runtime (embedded) + dev server bootstrap
│   └── cli/
│       ├── __init__.py
│       └── main.py               # CLI: dev, run, chat, list, check
├── pyproject.toml
├── tests/
└── examples/
    ├── quickstart.py
    ├── tools_example.py
    ├── multi_agent.py
    ├── remote_execution.py
    └── callbacks_example.py
```

### Dependency Relationship

```
astromesh-adk (DX layer)
    └── astromesh (core engine)
            ├── astromesh.providers   → ProviderProtocol implementations
            ├── astromesh.core        → ModelRouter, MemoryManager, ToolRegistry, PromptEngine, GuardrailsEngine
            ├── astromesh.runtime     → AgentRuntime, Agent execution
            ├── astromesh.orchestration → ReAct, PlanAndExecute, Supervisor, Swarm, etc.
            ├── astromesh.memory      → Backend implementations
            ├── astromesh.tools       → BuiltinTool catalog
            ├── astromesh.mcp         → MCPClient
            └── astromesh.observability → TracingContext, CostTracker
```

The ADK does **not** depend on `astromesh.api` (FastAPI layer). It imports only the engine and core modules.

---

## 3. Agent Definition API

### 3.1 Decorator-based (simple agents)

```python
from astromesh_adk import agent, tool

# Minimal agent — docstring is the system prompt, body is the run handler
@agent(
    name="research-assistant",
    model="openai/gpt-4o",
    description="Research assistant with web access",
)
async def research_assistant(ctx):
    """You are a research assistant. Provide accurate, sourced information."""
    # The function body IS the run handler. It receives a RunContext.
    # For simple agents, just return None to use the default orchestration pipeline.
    # For custom logic, use ctx to interact with the agent's capabilities:
    #   result = await ctx.complete("sub-query")   # call the model directly
    #   data = await ctx.call_tool("web_search", {"query": "..."})
    #   ctx.memory.store("key", "value")
    return None  # None = use default orchestration (ReAct, PlanAndExecute, etc.)


# Agent with custom pre/post processing in the handler
@agent(name="enriched-agent", model="openai/gpt-4o", tools=[web_search])
async def enriched_agent(ctx):
    """You are a helpful assistant."""
    # Custom pre-processing
    ctx.metadata["start_time"] = time.time()

    # Run default orchestration and get result
    result = await ctx.run_default()

    # Custom post-processing
    result.metadata["duration"] = time.time() - ctx.metadata["start_time"]
    return result
```

- The **docstring** serves as the system prompt (Jinja2 supported)
- The **decorator** transforms the function into an `Agent` object with `.run()` and `.stream()`
- The **function body** is the run handler — it receives a `RunContext` and can:
  - Return `None` to use the default orchestration pipeline (most common case)
  - Call `ctx.run_default()` to execute default orchestration with pre/post processing
  - Use `ctx.complete()`, `ctx.call_tool()` for fully custom execution logic

#### Decorator Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Agent identifier |
| `model` | `str` | Provider/model string (e.g., `"openai/gpt-4o"`) |
| `description` | `str` | Agent description |
| `fallback_model` | `str` | Fallback provider/model |
| `routing` | `str` | Routing strategy: `cost_optimized`, `latency_optimized`, `quality_first`, `round_robin` |
| `model_config` | `dict` | Extended model config (endpoint, api_key_env, temperature, max_tokens) |
| `tools` | `list` | List of `@tool` functions or `Tool` instances |
| `pattern` | `str` | Orchestration pattern: `react`, `plan_and_execute`, `parallel`, `pipeline`, `supervisor`, `swarm` |
| `max_iterations` | `int` | Max orchestration iterations |
| `memory` | `str \| dict` | Memory config (shorthand or full) |
| `guardrails` | `dict` | `{"input": ["pii_detection", "topic_filter"], "output": ["pii_detection", "cost_limit"]}` |

### 3.2 Class-based (advanced agents)

```python
from astromesh_adk import Agent, RunContext

class CustomAgent(Agent):
    name = "custom-agent"
    model = "ollama/llama3"
    pattern = "plan_and_execute"
    tools = [web_search, calculator]

    def system_prompt(self, ctx: RunContext) -> str:
        return f"You are an assistant for {ctx.user_id}. Date: {ctx.timestamp}"

    async def on_before_run(self, ctx: RunContext):
        """Hook: before agent execution."""
        pass

    async def on_after_run(self, ctx: RunContext, result):
        """Hook: after agent execution."""
        pass

    async def on_tool_call(self, ctx: RunContext, tool_name: str, args: dict):
        """Hook: intercept tool calls."""
        pass
```

#### Lifecycle Hooks

| Hook | When | Use Case |
|------|------|----------|
| `on_before_run` | Before execution starts | Auth checks, context enrichment |
| `on_after_run` | After execution completes | Logging, cleanup, notifications |
| `on_tool_call` | Before each tool call | Approval flows, auditing, transformation |

### 3.3 RunContext

`RunContext` is the object passed to both decorator handlers and class hooks:

```python
@dataclass
class RunContext:
    query: str                    # The user's input query
    session_id: str               # Session identifier
    agent_name: str               # Name of the executing agent
    user_id: str | None           # Extracted from context dict
    timestamp: datetime           # Execution start time
    metadata: dict                # Arbitrary metadata (from context param + runtime)
    memory: MemoryAccessor        # Read/write access to agent's memory
    tools: list[str]              # Available tool names

    async def run_default(self) -> RunResult:
        """Execute the default orchestration pipeline."""
    async def complete(self, query: str, **kwargs) -> str:
        """Call the model directly, bypassing orchestration."""
    async def call_tool(self, name: str, args: dict) -> Any:
        """Execute a tool by name."""
```

`RunContext` is constructed from the `session_id` and `context` dict passed to `.run()`. The `user_id` field is extracted from `context.get("user_id")` if present.

### 3.4 Execution

```python
# One-shot
result = await research_assistant.run("What is CRISPR?")
print(result.answer)

# With session
result = await sales_agent.run(
    "Quote for 50 licenses",
    session_id="lead-123",
    context={"company": "Acme Corp", "user_id": "u-456"},
)

# Streaming
async for chunk in research_assistant.stream("Explain machine learning"):
    print(chunk.content, end="")
```

### 3.5 Streaming Architecture

Streaming operates at two levels:

1. **Token streaming (default):** Streams tokens from the final model response only. The orchestration pattern (ReAct, etc.) runs to completion, then the final answer is streamed token-by-token using `provider.stream()` instead of `provider.complete()`.

2. **Step streaming (opt-in):** Streams intermediate steps as they happen during orchestration. Each tool call result, thought, and observation is emitted as a `StreamEvent`.

```python
# Token streaming — streams the final answer
async for chunk in agent.stream("query"):
    print(chunk.content, end="")  # CompletionChunk

# Step streaming — streams the full execution
async for event in agent.stream("query", stream_steps=True):
    if event.type == "step":
        print(f"[Step] {event.step.action}: {event.step.thought}")
    elif event.type == "token":
        print(event.content, end="")
    elif event.type == "done":
        print(f"\nCost: ${event.result.cost}")
```

**Implementation path:**
- Token streaming reuses `ProviderProtocol.stream()` which all providers already implement
- Step streaming requires a new `AsyncIterator`-based wrapper around `OrchestrationPattern.execute()` that yields `StreamEvent` objects at each iteration boundary
- The orchestration patterns don't need modification — the wrapper intercepts the `model_fn` and `tool_fn` closures to emit events before/after each call

---

## 4. Tool Definition API

### 4.1 Decorator-based (simple tools)

```python
from astromesh_adk import tool

@tool(description="Search the web for information")
async def web_search(query: str, max_results: int = 5) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.search.com?q={query}&n={max_results}")
        return resp.text
```

- JSON schema is **auto-generated** from type hints (str, int, float, bool, list, dict, Optional, Enum)
- Description comes from the decorator parameter
- Rate limiting, approval, and timeout are optional decorator parameters

#### Decorator Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Tool description for LLM |
| `rate_limit` | `dict` | `{"max_calls": N, "window_seconds": N}` |
| `requires_approval` | `bool` | Require user approval before execution |
| `timeout` | `int` | Execution timeout in seconds |

### 4.2 Class-based (stateful tools)

```python
from astromesh_adk import Tool, ToolContext

class SlackNotifier(Tool):
    name = "slack_notify"
    description = "Send Slack notifications"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.client = httpx.AsyncClient()

    def parameters(self):
        return {
            "channel": {"type": "string", "description": "Slack channel"},
            "message": {"type": "string", "description": "Message to send"},
        }

    async def execute(self, args: dict, ctx: ToolContext) -> str:
        resp = await self.client.post(self.webhook_url, json={...})
        return f"Sent to #{args['channel']}"

    async def cleanup(self):
        await self.client.aclose()
```

### 4.3 MCP Tools Integration

```python
from astromesh_adk import mcp_tools

github_tools = mcp_tools(
    transport="stdio",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]},
)

@agent(name="dev-agent", model="openai/gpt-4o", tools=[web_search, *github_tools])
async def dev_agent(ctx):
    """Developer agent with GitHub access."""
    return None
```

**MCP initialization is lazy:** `mcp_tools()` returns a `MCPToolSet` descriptor at import time (no async, no connection). The actual MCP server connection and tool discovery happens on first agent run. The `MCPToolSet` implements `__iter__` so it can be unpacked with `*` in the tools list. Internally, when the agent's `ToolRegistry` is initialized, it calls `await mcp_tool_set.discover()` which connects to the MCP server and registers the discovered tools.

### 4.4 Internal Mapping

- `@tool` functions → `ToolType.INTERNAL` in Astromesh `ToolRegistry`
- `Tool` classes → `ToolType.INTERNAL` with lifecycle management
- `mcp_tools()` → `ToolType.MCP_STDIO/HTTP/SSE` via Astromesh `MCPClient`

---

## 5. Provider Configuration

### 5.1 String Shorthand

```python
@agent(model="openai/gpt-4o")           # OpenAI
@agent(model="anthropic/claude-sonnet-4-20250514")  # Anthropic
@agent(model="ollama/llama3")            # Ollama local
@agent(model="vllm/mistral-7b")         # vLLM
```

API keys are resolved automatically from environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.

### 5.2 Provider Resolution

The `"provider/model"` string is parsed into:
1. **Provider name** → maps to Astromesh `ProviderProtocol` implementation
2. **Model name** → passed to the provider's `complete()`/`stream()`

Provider mapping:
| Prefix | Astromesh Provider | Env Var | Notes |
|--------|-------------------|---------|-------|
| `openai/` | `OpenAICompatProvider` | `OPENAI_API_KEY` | |
| `anthropic/` | `AnthropicProvider` (new) | `ANTHROPIC_API_KEY` | Native Anthropic API; falls back to `OpenAICompatProvider` if not available |
| `ollama/` | `OllamaProvider` | — | |
| `vllm/` | `VLLMProvider` | — | |
| `llamacpp/` | `LlamaCppProvider` | — | |
| `hf/` | `HFTGIProvider` | `HF_TOKEN` | |

> **Note:** v1 ships `anthropic/` via `OpenAICompatProvider` using Anthropic's OpenAI-compatible endpoint. A dedicated `AnthropicProvider` with native API support (system prompt handling, tool use format) is planned for v1.1.

### 5.3 Extended Configuration

```python
@agent(
    model="openai/gpt-4o",
    model_config={
        "endpoint": "https://my-proxy.com/v1",
        "api_key_env": "MY_CUSTOM_KEY",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    fallback_model="ollama/llama3",
    routing="cost_optimized",
)
```

---

## 6. Memory Configuration

### 6.1 Shorthands

```python
@agent(model="openai/gpt-4o", memory="sqlite")          # Conversational only
@agent(model="openai/gpt-4o", memory="redis")            # Conversational Redis
```

### 6.2 Full Configuration

```python
@agent(
    model="openai/gpt-4o",
    memory={
        "conversational": {
            "backend": "sqlite",
            "strategy": "sliding_window",
            "max_turns": 20,
        },
        "semantic": {
            "backend": "chromadb",
            "similarity_threshold": 0.7,
            "max_results": 5,
        },
    },
)
```

### 6.3 Internal Mapping

Memory config is translated to Astromesh `MemoryManager` configuration, using the same backend implementations (SQLite, Redis, PostgreSQL, ChromaDB, Qdrant, FAISS, PGVector).

---

## 7. Multi-Agent Composition

### 7.1 Agent as Tool

```python
@agent(
    name="coordinator",
    model="openai/gpt-4o",
    tools=[researcher.as_tool(), writer.as_tool()],
    pattern="plan_and_execute",
)
async def coordinator(ctx):
    """Coordinate research and writing tasks."""
    return None
```

`agent.as_tool()` registers the agent as `ToolType.AGENT` in Astromesh's `ToolRegistry`.

### 7.2 AgentTeam

```python
from astromesh_adk import AgentTeam

# Supervisor pattern
team = AgentTeam(
    name="support-team",
    pattern="supervisor",
    supervisor=coordinator,
    workers=[researcher, writer],
)
result = await team.run("Write an article about AI in healthcare")

# Swarm pattern
team = AgentTeam(
    name="sales-pipeline",
    pattern="swarm",
    agents=[qualifier, negotiator, closer],
    entry_agent=qualifier,
)

# Pipeline pattern
team = AgentTeam(
    name="doc-pipeline",
    pattern="pipeline",
    agents=[extractor, summarizer, translator],
)

# Parallel fan-out
team = AgentTeam(
    name="research-team",
    pattern="parallel",
    agents=[market_researcher, tech_researcher, competitor_analyst],
)
```

### 7.3 Internal Mapping — Translation Layer

`AgentTeam` maps to Astromesh `OrchestrationPattern` implementations through a translation layer:

| ADK Pattern | Astromesh Class | Translation |
|---|---|---|
| `"supervisor"` | `SupervisorPattern` | `workers` dict built from agent names |
| `"swarm"` | `SwarmPattern` | `agent_configs` dict built from agent names + descriptions |
| `"pipeline"` | `PipelinePattern` | `stages` list built from agent names in order |
| `"parallel"` | `ParallelFanOutPattern` | Agents registered as subtask handlers |

> **Note:** ADK uses `"parallel"` as shorthand for Astromesh's `"parallel_fan_out"`.

**Translation process for `AgentTeam.run()`:**

1. **Register agents as tools:** Each agent in `workers`/`agents` list is registered into a shared `ToolRegistry` as `ToolType.AGENT` (using the existing agent-as-tool mechanism)
2. **Build pattern config:** Construct the pattern-specific config dict from the ADK agents:
   - Supervisor: `workers = {agent.name: {"description": agent.description} for agent in self.workers}`
   - Swarm: `agent_configs = {agent.name: {"description": agent.description, "tools": [...]} for agent in self.agents}`
   - Pipeline: `stages = [agent.name for agent in self.agents]`
   - Parallel: decomposition targets = agent names
3. **Create coordinator agent:** A synthetic agent is created with the team's pattern, the shared `ToolRegistry`, and a system prompt that describes the available workers/agents
4. **Execute:** The coordinator runs using `AgentRuntime.run()` with the constructed pattern

---

## 8. Observability

### 8.1 RunResult

```python
result = await my_agent.run("query")
result.answer       # str: Final response
result.steps        # list[AgentStep]: Execution steps
result.trace        # TracingContext: Full span tree
result.cost         # float: Total cost in USD
result.tokens       # dict: {"input": N, "output": N}
result.latency_ms   # float: Total latency
result.model        # str: Model used (including fallback)
```

**Construction from Astromesh internals:**

`RunResult` is built by aggregating data from the `TracingContext` returned by `AgentRuntime.run()`:

| Field | Source |
|-------|--------|
| `answer` | `runtime_result["answer"]` |
| `steps` | `runtime_result["steps"]` → list of `AgentStep` |
| `trace` | `runtime_result["trace"]` → `TracingContext` object |
| `cost` | Sum of `span.attributes["cost"]` across all `llm.complete` spans in the trace |
| `tokens` | Sum of `span.attributes["input_tokens"]` and `["output_tokens"]` across `llm.complete` spans |
| `latency_ms` | Root span `duration_ms` |
| `model` | Last `llm.complete` span's `attributes["model"]` (captures fallback) |

### 8.2 Callbacks (Observational)

Callbacks are **observational hooks** — they receive data after events happen but cannot modify or block execution. They are distinct from agent lifecycle hooks (Section 3.2) which are **control-flow hooks** that can intercept and modify behavior.

```python
from astromesh_adk import Callbacks

class MyCallbacks(Callbacks):
    async def on_step(self, step): ...
    async def on_tool_result(self, tool_name, args, result): ...   # post-execution, read-only
    async def on_model_call(self, model, messages, response): ...
    async def on_error(self, error, context): ...

result = await agent.run("query", callbacks=MyCallbacks())
```

| Mechanism | Purpose | Can modify? | Where defined |
|-----------|---------|-------------|---------------|
| Agent hooks (`on_before_run`, `on_tool_call`) | Control flow, interception | Yes | Class-based agent |
| Callbacks (`on_step`, `on_tool_result`) | Observation, logging, metrics | No | Passed to `.run()` |

When both are used, agent hooks fire first (can block), then callbacks fire (observe the result).

### 8.3 Structured Logging

The ADK emits structured logs via Python's `logging` module:
```
DEBUG astromesh_adk.runner: agent=name step=1 action=web_search
INFO  astromesh_adk.runner: agent=name completed tokens=1650 cost=$0.003 latency=2340ms
```

### 8.4 Dev Server Traces Panel

`astromesh-adk dev` serves a trace viewer at `localhost:8000/traces` consuming `TracingContext.to_dict()`.

---

## 9. Remote Connection

### 9.1 Explicit Connection

```python
from astromesh_adk import connect, disconnect

connect(url="https://my-cluster.astromesh.io", api_key="ask-xxx")
result = await my_agent.run("query")  # Executes on Astromesh remote

disconnect()
result = await my_agent.run("query")  # Executes locally
```

### 9.2 Context Manager (recommended for async)

```python
from astromesh_adk import remote

async with remote("https://my-cluster.astromesh.io", api_key="..."):
    result = await my_agent.run("Runs on Astromesh")

result = await my_agent.run("Runs locally")
```

### 9.3 Per-agent Binding

```python
# Bind a specific agent to a remote without affecting others
my_agent.bind(remote="https://my-cluster.astromesh.io", api_key="...")
result = await my_agent.run("Runs on Astromesh")

other_agent.run("Still runs locally")
```

### 9.4 Concurrency Safety

The connection state uses `contextvars.ContextVar` so that `remote()` context manager works correctly in async concurrent scenarios. Each async task inherits or overrides the connection context independently.

```python
# Safe: concurrent agents with different targets
async with remote("https://cluster-a.io", api_key="..."):
    task_a = asyncio.create_task(agent_a.run("query"))

async with remote("https://cluster-b.io", api_key="..."):
    task_b = asyncio.create_task(agent_b.run("query"))

await asyncio.gather(task_a, task_b)
```

**Resolution priority:** `agent.bind()` > `remote()` context > `connect()` global > local runtime.

### 9.5 Internal Behavior

When connected:
1. Agent definition is synced to Astromesh via API (new registration endpoint needed)
2. `.run()` → `POST /v1/agents/{name}/run`
3. `.stream()` → WebSocket `/v1/ws/agent/{name}`
4. Memory, tools, providers resolved server-side

When disconnected:
1. Embedded `AgentRuntime` handles execution locally
2. All providers, tools, memory run in-process

---

## 10. Error Handling

### 10.1 Exception Hierarchy

```
ADKError (base)
├── AgentError          — Agent execution failures
│   ├── AgentNotFoundError
│   └── OrchestrationError (max iterations, timeout)
├── ProviderError       — LLM provider failures
│   ├── ProviderUnavailableError (all providers down, circuit open)
│   ├── AuthenticationError (invalid API key)
│   └── RateLimitError
├── ToolError           — Tool execution failures
│   ├── ToolNotFoundError
│   ├── ToolTimeoutError
│   └── ToolPermissionError
├── GuardrailError      — Input/output guardrail blocks
│   ├── InputBlockedError
│   └── OutputBlockedError
└── ConnectionError     — Remote Astromesh connection failures
    ├── RemoteUnavailableError
    └── SyncError (agent registration failed)
```

### 10.2 Error Propagation

- `agent.run()` raises typed exceptions from the hierarchy above
- The circuit breaker in `ModelRouter` (3 failures → 60s cooldown) is transparent — if all providers fail, `ProviderUnavailableError` is raised with details of each attempt
- Tool errors within orchestration are captured as `AgentStep.observation` and the LLM decides whether to retry or respond — only unrecoverable errors bubble up
- Guardrail blocks raise immediately with the blocking reason

### 10.3 Error in Callbacks

Callback errors are logged but **never** propagate to the caller. A failing callback should not break agent execution.

---

## 11. Runtime Lifecycle

### 11.1 Embedded Runtime Cleanup

```python
from astromesh_adk import ADKRuntime

# Explicit lifecycle management
runtime = ADKRuntime()
await runtime.start()  # Initialize providers, MCP connections, memory backends
result = await my_agent.run("query", runtime=runtime)
await runtime.shutdown()  # Close all connections, cleanup resources

# Context manager (recommended)
async with ADKRuntime() as runtime:
    result = await my_agent.run("query", runtime=runtime)
# All resources cleaned up automatically

# Implicit runtime (convenience for scripts)
result = await my_agent.run("query")
# Creates a default runtime, reuses it, cleaned up at process exit via atexit
```

The implicit runtime is created lazily on first `.run()` call and registered with `atexit` for cleanup. This covers the simple script/notebook use case without requiring explicit lifecycle management.

### 11.2 CLI Check Command

`astromesh-adk check file.py` performs:
1. **Import validation:** Import the file, discover `@agent` decorated objects
2. **Config validation:** Validate all decorator parameters against expected types/values
3. **Provider check:** Verify required env vars exist (e.g., `OPENAI_API_KEY` for `openai/` prefix)
4. **Tool validation:** Verify tool schemas can be generated from type hints
5. **MCP validation:** Verify MCP server commands exist on PATH (no connection attempt)
6. **Memory validation:** Verify memory backend packages are installed (e.g., `chromadb` for `"chromadb"`)

---

## 12. CLI

> See also Section 11.2 for `check` command details.

| Command | Description |
|---------|-------------|
| `astromesh-adk run file.py:agent "query"` | One-shot agent execution |
| `astromesh-adk chat file.py:agent --session ID` | Interactive terminal chat |
| `astromesh-adk dev file.py --port 8000 --reload` | Dev server with playground + traces |
| `astromesh-adk list file.py` | List agents defined in file |
| `astromesh-adk check file.py` | Validate providers, tools, config |

### Dev Server

`astromesh-adk dev` boots:
- REST API at `localhost:8000/v1/...` (reuses Astromesh API routes)
- WebSocket at `localhost:8000/v1/ws/...`
- Playground UI at `localhost:8000/` (interactive chat)
- Traces panel at `localhost:8000/traces`
- Hot reload via `watchfiles`

---

## 13. New Astromesh Endpoints Required

The ADK's remote mode requires new API endpoints on Astromesh:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/agents` | `POST` | Register agent from ADK definition |
| `/v1/agents/{name}` | `PUT` | Update agent definition |
| `/v1/agents/{name}` | `DELETE` | Remove agent |
| `/v1/auth/token` | `POST` | API key validation |

---

## 14. Documentation Plan

### 12.1 In-repo docs (`docs/`)

- `docs/ADK_QUICKSTART.md` — 5-minute getting started guide
- `docs/ADK_REFERENCE.md` — Complete API reference
- `docs/ADK_EXAMPLES.md` — Cookbook with common patterns

### 12.2 Docs site (`docs-site/`, Astro Starlight)

New sidebar section in `astro.config.mjs`:

```javascript
{
  label: 'Agent Development Kit',
  items: [
    { label: 'Introduction', slug: 'adk/introduction' },
    { label: 'Installation', slug: 'adk/installation' },
    { label: 'Quick Start', slug: 'adk/quickstart' },
    { label: 'Defining Agents', slug: 'adk/defining-agents' },
    { label: 'Creating Tools', slug: 'adk/creating-tools' },
    { label: 'Provider Configuration', slug: 'adk/providers' },
    { label: 'Memory & State', slug: 'adk/memory' },
    { label: 'Multi-Agent Teams', slug: 'adk/multi-agent' },
    { label: 'Observability', slug: 'adk/observability' },
    { label: 'Remote Execution', slug: 'adk/remote-execution' },
    { label: 'CLI Reference', slug: 'adk/cli-reference' },
    { label: 'API Reference', slug: 'adk/api-reference' },
    { label: 'Examples & Cookbook', slug: 'adk/examples' },
    { label: 'Migration from YAML', slug: 'adk/migration-from-yaml' },
  ],
},
```

---

## 15. Testing Strategy

- **Unit tests:** Each module (agent.py, tools.py, providers.py, etc.) tested independently
- **Integration tests:** Agent execution with mocked providers (respx)
- **E2E tests:** Full agent runs with Ollama local provider
- **CLI tests:** CLI commands via subprocess or Click testing
- **Snapshot tests:** JSON schema generation from type hints

---

## 16. Out of Scope (v1)

- Custom UI playground (v1 uses basic HTML, enhanced UI in v2)
- Plugin marketplace / registry
- Multi-language SDKs (TypeScript, Go)
- Agent versioning and rollback
- Built-in auth/RBAC for remote mode
