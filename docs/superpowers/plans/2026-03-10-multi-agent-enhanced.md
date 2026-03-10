# Multi-agent Enhanced Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable agents to invoke other agents as tools (`type: agent`), with Jinja2 context transforms for data shaping, and wire this into Supervisor and Swarm patterns so multi-agent coordination uses a single unified invocation mechanism.

**Architecture:** A new `ToolType.AGENT` enum value in `ToolRegistry` with a `register_agent_tool()` method that captures a reference to `AgentRuntime`. When `execute()` encounters an AGENT tool, it calls `runtime.run(agent_name, ...)`, optionally applying a Jinja2 `context_transform` to reshape input. Supervisor and Swarm patterns delegate to agent tools instead of using internal `_workers`/`_agents` dicts. Each agent-as-tool invocation creates a child span via `TracingContext` for full nested observability. Circular references are detected at bootstrap time via topological analysis.

**Tech Stack:** Python 3.12+, Jinja2 (already a dependency), existing `TracingContext`

**Spec:** `docs/superpowers/specs/2026-03-10-astromesh-ecosystem-design.md`

**Depends on:** Sub-project 1 (Built-in Tools + Observability) — complete

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `tests/test_agent_as_tool.py` | Core agent-as-tool registration, execution, context transforms, circular detection |
| `tests/test_context_transform.py` | Jinja2 context transform edge cases |
| `tests/test_supervisor_agents.py` | Supervisor pattern using agent tools as workers |
| `tests/test_swarm_agents.py` | Swarm pattern using agent tools for handoffs |

### Modified Files

| File | Changes |
|------|---------|
| `astromesh/core/tools.py` | Add `ToolType.AGENT`, `agent_config` and `context_transform` fields to `ToolDefinition`, `register_agent_tool()` method, AGENT branch in `execute()` |
| `astromesh/runtime/engine.py` | Wire `type: agent` tools in `_build_agent()`, pass runtime ref to `ToolRegistry`, detect circular agent references at bootstrap |
| `astromesh/orchestration/supervisor.py` | Use `tool_fn` to invoke agent tools instead of internal `_workers` dict |
| `astromesh/orchestration/swarm.py` | Use `tool_fn` to invoke agent tools for handoffs |

---

## Chunk 1: Agent-as-Tool Core — ToolType.AGENT, Registration, Execution

### Task 1: Add ToolType.AGENT and ToolDefinition fields

**Files:**
- Modify: `astromesh/core/tools.py`
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write failing tests for ToolType.AGENT and ToolDefinition**

```python
# tests/test_agent_as_tool.py
import pytest
from astromesh.core.tools import ToolRegistry, ToolType, ToolDefinition


class TestToolTypeAgent:
    def test_agent_enum_exists(self):
        assert ToolType.AGENT == "agent"
        assert ToolType.AGENT.value == "agent"

    def test_tool_definition_agent_config(self):
        tool = ToolDefinition(
            name="qualify-lead",
            description="Qualify a sales lead",
            tool_type=ToolType.AGENT,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            agent_config={"agent_name": "sales-qualifier"},
        )
        assert tool.agent_config["agent_name"] == "sales-qualifier"
        assert tool.context_transform is None

    def test_tool_definition_with_context_transform(self):
        tool = ToolDefinition(
            name="qualify-lead",
            description="Qualify a sales lead",
            tool_type=ToolType.AGENT,
            parameters={"type": "object", "properties": {}},
            agent_config={"agent_name": "sales-qualifier"},
            context_transform="{company: data.company, summary: data.summary}",
        )
        assert tool.context_transform is not None

    def test_tool_definition_defaults_unchanged(self):
        """Existing ToolDefinition usage still works with new fields defaulting."""
        tool = ToolDefinition(
            name="old-tool",
            description="Legacy tool",
            tool_type=ToolType.INTERNAL,
            parameters={},
        )
        assert tool.agent_config is None
        assert tool.context_transform is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_as_tool.py::TestToolTypeAgent -v`
Expected: FAIL — `AttributeError: AGENT is not a member of ToolType` or similar

- [ ] **Step 3: Add AGENT to ToolType and new fields to ToolDefinition**

```python
# astromesh/core/tools.py — ToolType enum (add AGENT member)
class ToolType(str, Enum):
    INTERNAL = "internal"
    MCP_STDIO = "mcp_stdio"
    MCP_SSE = "mcp_sse"
    MCP_HTTP = "mcp_http"
    WEBHOOK = "webhook"
    RAG = "rag"
    AGENT = "agent"
```

```python
# astromesh/core/tools.py — ToolDefinition dataclass (add two fields)
@dataclass
class ToolDefinition:
    name: str
    description: str
    tool_type: ToolType
    parameters: dict
    handler: Callable | None = None
    mcp_config: dict = field(default_factory=dict)
    requires_approval: bool = False
    timeout_seconds: int = 30
    rate_limit: dict | None = None
    permissions: list[str] = field(default_factory=list)
    agent_config: dict | None = None
    context_transform: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_as_tool.py::TestToolTypeAgent -v`

---

### Task 2: register_agent_tool() method

**Files:**
- Modify: `astromesh/core/tools.py`
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write failing tests for register_agent_tool()**

```python
# tests/test_agent_as_tool.py — add to file
class TestRegisterAgentTool:
    def test_register_agent_tool_basic(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        assert "qualify-lead" in registry._tools
        tool = registry._tools["qualify-lead"]
        assert tool.tool_type == ToolType.AGENT
        assert tool.agent_config["agent_name"] == "sales-qualifier"

    def test_register_agent_tool_with_transform(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="summarize",
            agent_name="summarizer",
            description="Summarize content",
            context_transform="{text: data.content}",
        )
        tool = registry._tools["summarize"]
        assert tool.context_transform == "{text: data.content}"

    def test_register_agent_tool_generates_schema(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        schemas = registry.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "qualify-lead"
        assert schemas[0]["function"]["description"] == "Qualify a sales lead"

    def test_register_agent_tool_custom_parameters(self):
        registry = ToolRegistry()
        params = {
            "type": "object",
            "properties": {"company": {"type": "string"}},
            "required": ["company"],
        }
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
            parameters=params,
        )
        tool = registry._tools["qualify-lead"]
        assert tool.parameters == params
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_as_tool.py::TestRegisterAgentTool -v`
Expected: FAIL — `AttributeError: 'ToolRegistry' object has no attribute 'register_agent_tool'`

- [ ] **Step 3: Implement register_agent_tool()**

```python
# astromesh/core/tools.py — add method to ToolRegistry class
    def register_agent_tool(
        self,
        name: str,
        agent_name: str,
        description: str,
        parameters: dict | None = None,
        context_transform: str | None = None,
        **kwargs,
    ):
        """Register an agent as a callable tool."""
        default_params = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query or task to send to the agent",
                },
            },
            "required": ["query"],
        }
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            tool_type=ToolType.AGENT,
            parameters=parameters or default_params,
            agent_config={"agent_name": agent_name},
            context_transform=context_transform,
            **kwargs,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_as_tool.py::TestRegisterAgentTool -v`

---

### Task 3: Execute agent tools via runtime.run()

**Files:**
- Modify: `astromesh/core/tools.py`
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write failing tests for agent tool execution**

```python
# tests/test_agent_as_tool.py — add to file
from unittest.mock import AsyncMock, MagicMock


class TestExecuteAgentTool:
    @pytest.fixture
    def runtime_mock(self):
        runtime = AsyncMock()
        runtime.run = AsyncMock(
            return_value={"answer": "Lead is qualified", "steps": []}
        )
        return runtime

    @pytest.fixture
    def registry_with_agent(self, runtime_mock):
        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        return registry

    @pytest.mark.asyncio
    async def test_execute_agent_tool(self, registry_with_agent, runtime_mock):
        result = await registry_with_agent.execute(
            "qualify-lead",
            {"query": "Is Acme Corp a good lead?"},
            context={"session": "sess-1"},
        )
        runtime_mock.run.assert_called_once_with(
            "sales-qualifier",
            "Is Acme Corp a good lead?",
            session_id="sess-1",
            context=None,
        )
        assert result["answer"] == "Lead is qualified"

    @pytest.mark.asyncio
    async def test_execute_agent_tool_no_runtime(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        result = await registry.execute("qualify-lead", {"query": "test"})
        assert "error" in result
        assert "runtime" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_agent_tool_extracts_session(self, runtime_mock):
        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        await registry.execute(
            "qualify-lead",
            {"query": "test"},
            context={"session": "sess-42", "agent": "parent-agent"},
        )
        runtime_mock.run.assert_called_once_with(
            "sales-qualifier",
            "test",
            session_id="sess-42",
            context=None,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_as_tool.py::TestExecuteAgentTool -v`
Expected: FAIL — `AttributeError: 'ToolRegistry' object has no attribute 'set_runtime'`

- [ ] **Step 3: Implement set_runtime() and AGENT execution branch**

```python
# astromesh/core/tools.py — add to ToolRegistry.__init__()
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._mcp_clients: dict[str, Any] = {}
        self._call_counts: dict[str, list[float]] = {}
        self._runtime: Any | None = None

# astromesh/core/tools.py — add set_runtime method
    def set_runtime(self, runtime):
        """Set the AgentRuntime reference for agent-as-tool execution."""
        self._runtime = runtime

# astromesh/core/tools.py — add AGENT branch in execute() after the INTERNAL branch
        elif tool.tool_type == ToolType.AGENT:
            if not self._runtime:
                return {"error": "AgentRuntime not set — cannot execute agent tool"}
            agent_name = tool.agent_config["agent_name"]
            query = arguments.get("query", "")
            session_id = (context or {}).get("session", "")
            transform_ctx = None
            if tool.context_transform:
                from jinja2 import Environment, BaseLoader
                env = Environment(loader=BaseLoader())
                template = env.from_string("{% set result = " + tool.context_transform + " %}{{ result | tojson }}")
                import json
                rendered = template.render(data=arguments)
                transform_ctx = json.loads(rendered)
            return await self._runtime.run(
                agent_name, query, session_id=session_id, context=transform_ctx
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_as_tool.py::TestExecuteAgentTool -v`

---

## Chunk 2: Context Transforms and Tracing

### Task 4: Jinja2 context transforms

**Files:**
- Modify: `astromesh/core/tools.py` (refine transform logic)
- Test: `tests/test_context_transform.py`

- [ ] **Step 1: Write failing tests for context transforms**

```python
# tests/test_context_transform.py
import pytest
from unittest.mock import AsyncMock
from astromesh.core.tools import ToolRegistry


@pytest.fixture
def runtime_mock():
    runtime = AsyncMock()
    runtime.run = AsyncMock(return_value={"answer": "ok", "steps": []})
    return runtime


@pytest.fixture
def registry(runtime_mock):
    reg = ToolRegistry()
    reg.set_runtime(runtime_mock)
    return reg


class TestContextTransform:
    @pytest.mark.asyncio
    async def test_no_transform_passes_query(self, registry, runtime_mock):
        """No context_transform: query string passed as-is."""
        registry.register_agent_tool(
            name="agent-b",
            agent_name="my-agent",
            description="Agent B",
        )
        await registry.execute(
            "agent-b",
            {"query": "hello world"},
            context={"session": "s1"},
        )
        runtime_mock.run.assert_called_once_with(
            "my-agent", "hello world", session_id="s1", context=None,
        )

    @pytest.mark.asyncio
    async def test_transform_reshapes_context(self, registry, runtime_mock):
        """context_transform produces a dict passed as context kwarg."""
        registry.register_agent_tool(
            name="agent-b",
            agent_name="my-agent",
            description="Agent B",
            context_transform="{score: data.score, name: data.name}",
        )
        await registry.execute(
            "agent-b",
            {"query": "evaluate", "score": 95, "name": "Alice"},
            context={"session": "s2"},
        )
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs.kwargs["context"] == {"score": 95, "name": "Alice"}

    @pytest.mark.asyncio
    async def test_transform_with_nested_data(self, registry, runtime_mock):
        """Transform can access nested fields."""
        registry.register_agent_tool(
            name="agent-c",
            agent_name="deep-agent",
            description="Agent C",
            context_transform="{city: data.address.city}",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "address": {"type": "object"},
                },
            },
        )
        await registry.execute(
            "agent-c",
            {"query": "lookup", "address": {"city": "Portland", "state": "OR"}},
            context={"session": "s3"},
        )
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs.kwargs["context"] == {"city": "Portland"}

    @pytest.mark.asyncio
    async def test_transform_error_returns_error_dict(self, registry):
        """Invalid transform template returns error instead of crashing."""
        registry.register_agent_tool(
            name="bad-agent",
            agent_name="crash-agent",
            description="Bad transform",
            context_transform="{broken: data.nonexistent.deep.path}",
        )
        result = await registry.execute(
            "bad-agent",
            {"query": "test"},
            context={"session": "s4"},
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_transform_treated_as_none(self, registry, runtime_mock):
        """Empty string transform treated same as no transform."""
        registry.register_agent_tool(
            name="agent-d",
            agent_name="my-agent",
            description="Agent D",
            context_transform="",
        )
        await registry.execute(
            "agent-d",
            {"query": "go"},
            context={"session": "s5"},
        )
        runtime_mock.run.assert_called_once_with(
            "my-agent", "go", session_id="s5", context=None,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context_transform.py -v`

- [ ] **Step 3: Refine context transform implementation in execute()**

Update the AGENT branch in `ToolRegistry.execute()` to handle edge cases:

```python
# astromesh/core/tools.py — refined AGENT branch in execute()
        elif tool.tool_type == ToolType.AGENT:
            if not self._runtime:
                return {"error": "AgentRuntime not set — cannot execute agent tool"}
            agent_name = tool.agent_config["agent_name"]
            query = arguments.get("query", "")
            session_id = (context or {}).get("session", "")
            transform_ctx = None
            if tool.context_transform and tool.context_transform.strip():
                try:
                    from jinja2 import Environment, BaseLoader, UndefinedError
                    import json as json_mod
                    env = Environment(loader=BaseLoader())
                    tpl_str = "{% set result = " + tool.context_transform + " %}{{ result | tojson }}"
                    template = env.from_string(tpl_str)
                    rendered = template.render(data=_DotDict(arguments))
                    transform_ctx = json_mod.loads(rendered)
                except (UndefinedError, Exception) as exc:
                    return {"error": f"Context transform failed: {exc}"}
            return await self._runtime.run(
                agent_name, query, session_id=session_id, context=transform_ctx
            )
```

Also add a helper class for dot-notation access inside Jinja2:

```python
# astromesh/core/tools.py — add before ToolRegistry class
class _DotDict(dict):
    """Dict subclass enabling dot-notation access for Jinja2 templates."""

    def __init__(self, data):
        super().__init__(data)
        for key, value in data.items():
            if isinstance(value, dict):
                self[key] = _DotDict(value)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"No attribute '{key}'")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_context_transform.py -v`

---

### Task 5: Nested tracing for agent-as-tool calls

**Files:**
- Modify: `astromesh/core/tools.py`
- Modify: `astromesh/runtime/engine.py`
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write failing tests for nested tracing**

```python
# tests/test_agent_as_tool.py — add to file
class TestAgentToolTracing:
    @pytest.mark.asyncio
    async def test_agent_tool_creates_child_span(self):
        """Agent-as-tool calls should appear as child spans in the trace."""
        from astromesh.observability.tracing import TracingContext

        child_trace = {
            "trace_id": "child-trace-123",
            "spans": [{"name": "agent.run", "span_id": "s1"}],
        }
        runtime_mock = AsyncMock()
        runtime_mock.run = AsyncMock(
            return_value={"answer": "done", "steps": [], "trace": child_trace}
        )

        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="sub-agent",
            agent_name="worker-agent",
            description="Sub agent",
        )

        tracing = TracingContext(agent_name="parent", session_id="s1")
        parent_span = tracing.start_span("tool.call", {"tool": "sub-agent"})

        result = await registry.execute(
            "sub-agent",
            {"query": "do work"},
            context={"session": "s1", "tracing": tracing, "parent_span": parent_span},
        )

        assert result["answer"] == "done"
        # The runtime.run call should have received parent trace info
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_agent_tool_result_includes_child_trace(self):
        """Result from agent tool includes child trace for merging."""
        child_trace = {
            "trace_id": "child-abc",
            "spans": [{"name": "agent.run", "span_id": "cs1"}],
        }
        runtime_mock = AsyncMock()
        runtime_mock.run = AsyncMock(
            return_value={"answer": "result", "steps": [], "trace": child_trace}
        )

        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="sub-agent",
            agent_name="worker",
            description="Worker",
        )

        result = await registry.execute(
            "sub-agent",
            {"query": "work"},
            context={"session": "s1"},
        )
        assert "trace" in result
        assert result["trace"]["trace_id"] == "child-abc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_as_tool.py::TestAgentToolTracing -v`

- [ ] **Step 3: Wire tracing into agent tool execution**

The AGENT branch in `execute()` already returns the full `runtime.run()` result, which includes `trace`. No changes needed for the basic case. The parent `tool_fn` in `engine.py` already creates a `tool.call` span. The child agent's `Agent.run()` creates its own `TracingContext`, so spans are naturally nested.

Verify the existing flow produces correct spans and add `parent_trace_id` propagation:

```python
# astromesh/runtime/engine.py — in Agent.run(), accept optional parent_trace_id
    async def run(self, query, session_id, context=None, parent_trace_id=None):
        from datetime import datetime
        from astromesh.core.memory import ConversationTurn
        from astromesh.observability.tracing import TracingContext, SpanStatus

        tracing = TracingContext(agent_name=self.name, session_id=session_id)
        if parent_trace_id:
            tracing.trace_id = parent_trace_id  # share trace tree
        # ... rest unchanged
```

```python
# astromesh/core/tools.py — AGENT branch, pass parent trace context
            parent_trace_id = (context or {}).get("trace_id")
            return await self._runtime.run(
                agent_name, query, session_id=session_id, context=transform_ctx,
                parent_trace_id=parent_trace_id,
            )
```

```python
# astromesh/runtime/engine.py — AgentRuntime.run() accept and forward parent_trace_id
    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(query, session_id, context, parent_trace_id=parent_trace_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_as_tool.py::TestAgentToolTracing -v`

---

### Task 6: Circular agent reference detection

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write failing tests for circular detection**

```python
# tests/test_agent_as_tool.py — add to file
import yaml
from pathlib import Path
from unittest.mock import patch


class TestCircularAgentDetection:
    def _make_agent_config(self, name, agent_tools=None):
        """Helper to build a minimal agent YAML config dict."""
        tools = []
        for at in (agent_tools or []):
            tools.append({"name": at, "type": "agent", "agent": at})
        return {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": name, "version": "0.1.0"},
            "spec": {
                "identity": {"description": f"Agent {name}"},
                "model": {"routing": {"strategy": "cost_optimized"}},
                "tools": tools,
                "orchestration": {"pattern": "react"},
            },
        }

    def test_direct_self_reference_detected(self):
        """Agent referencing itself as a tool should raise at bootstrap."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [self._make_agent_config("agent-a", agent_tools=["agent-a"])]
        with pytest.raises(ValueError, match="[Cc]ircular"):
            runtime._detect_circular_refs(configs)

    def test_indirect_cycle_detected(self):
        """A -> B -> A cycle should raise at bootstrap."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [
            self._make_agent_config("agent-a", agent_tools=["agent-b"]),
            self._make_agent_config("agent-b", agent_tools=["agent-a"]),
        ]
        with pytest.raises(ValueError, match="[Cc]ircular"):
            runtime._detect_circular_refs(configs)

    def test_no_cycle_passes(self):
        """A -> B -> C (no cycle) should not raise."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [
            self._make_agent_config("agent-a", agent_tools=["agent-b"]),
            self._make_agent_config("agent-b", agent_tools=["agent-c"]),
            self._make_agent_config("agent-c"),
        ]
        # Should not raise
        runtime._detect_circular_refs(configs)

    def test_diamond_dependency_no_false_positive(self):
        """A -> B, A -> C, B -> D, C -> D is not circular."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [
            self._make_agent_config("a", agent_tools=["b", "c"]),
            self._make_agent_config("b", agent_tools=["d"]),
            self._make_agent_config("c", agent_tools=["d"]),
            self._make_agent_config("d"),
        ]
        # Should not raise
        runtime._detect_circular_refs(configs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_as_tool.py::TestCircularAgentDetection -v`
Expected: FAIL — `AttributeError: 'AgentRuntime' object has no attribute '_detect_circular_refs'`

- [ ] **Step 3: Implement _detect_circular_refs()**

```python
# astromesh/runtime/engine.py — add method to AgentRuntime
    def _detect_circular_refs(self, configs: list[dict]):
        """Detect circular agent-as-tool references. Raises ValueError if cycle found."""
        # Build adjacency list
        graph: dict[str, list[str]] = {}
        for config in configs:
            name = config["metadata"]["name"]
            agent_tools = [
                t["agent"]
                for t in config["spec"].get("tools", [])
                if t.get("type") == "agent"
            ]
            graph[name] = agent_tools

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in graph}

        def dfs(node, path):
            color[node] = GRAY
            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue  # references external agent, skip
                if color[neighbor] == GRAY:
                    cycle = path + [neighbor]
                    raise ValueError(
                        f"Circular agent reference detected: {' -> '.join(cycle)}"
                    )
                if color[neighbor] == WHITE:
                    dfs(neighbor, path + [neighbor])
            color[node] = BLACK

        for node in graph:
            if color[node] == WHITE:
                dfs(node, [node])
```

Then call it in `bootstrap()` after loading configs but before building agents:

```python
# astromesh/runtime/engine.py — in bootstrap(), after loading YAML files
    async def bootstrap(self):
        if self.service_manager and not self.service_manager.is_enabled("agents"):
            return
        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return
        configs = []
        for f in agents_dir.glob("*.agent.yaml"):
            configs.append(yaml.safe_load(f.read_text()))
        self._detect_circular_refs(configs)
        for config in configs:
            agent = self._build_agent(config)
            self._agents[agent.name] = agent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_as_tool.py::TestCircularAgentDetection -v`

---

## Chunk 3: Supervisor and Swarm Integration

### Task 7: Wire agent tools in _build_agent()

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write failing tests for agent tool wiring**

```python
# tests/test_agent_as_tool.py — add to file
class TestBuildAgentWiring:
    def _make_config(self, tools=None):
        return {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "test-agent", "version": "0.1.0"},
            "spec": {
                "identity": {"description": "Test"},
                "model": {"routing": {"strategy": "cost_optimized"}},
                "tools": tools or [],
                "orchestration": {"pattern": "react"},
                "prompts": {"system": "You are a test agent."},
                "memory": {},
                "guardrails": {},
                "permissions": {},
            },
        }

    def test_build_agent_registers_agent_tools(self):
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime(config_dir="./config")
        config = self._make_config(
            tools=[
                {
                    "name": "qualify-lead",
                    "type": "agent",
                    "agent": "sales-qualifier",
                    "description": "Qualify a lead",
                },
            ]
        )
        agent = runtime._build_agent(config)
        assert "qualify-lead" in agent._tools._tools
        tool = agent._tools._tools["qualify-lead"]
        assert tool.tool_type == ToolType.AGENT
        assert tool.agent_config["agent_name"] == "sales-qualifier"

    def test_build_agent_sets_runtime_on_registry(self):
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime(config_dir="./config")
        config = self._make_config(
            tools=[
                {
                    "name": "sub-agent",
                    "type": "agent",
                    "agent": "worker",
                },
            ]
        )
        agent = runtime._build_agent(config)
        assert agent._tools._runtime is runtime

    def test_build_agent_with_context_transform(self):
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime(config_dir="./config")
        config = self._make_config(
            tools=[
                {
                    "name": "qualify-lead",
                    "type": "agent",
                    "agent": "sales-qualifier",
                    "context_transform": "{company: data.company}",
                },
            ]
        )
        agent = runtime._build_agent(config)
        tool = agent._tools._tools["qualify-lead"]
        assert tool.context_transform == "{company: data.company}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_as_tool.py::TestBuildAgentWiring -v`

- [ ] **Step 3: Add agent tool wiring in _build_agent()**

```python
# astromesh/runtime/engine.py — in _build_agent(), extend the tool_def loop
        for tool_def in spec.get("tools", []):
            tool_type = tool_def.get("type", "internal")
            if tool_type == "builtin":
                instance = loader.create(tool_def["name"], config=tool_def.get("config"))
                handler = _make_builtin_handler(instance, metadata["name"])
                tools.register_internal(
                    name=tool_def["name"],
                    handler=handler,
                    description=instance.description,
                    parameters=instance.parameters,
                    rate_limit=tool_def.get("rate_limit"),
                )
            elif tool_type == "agent":
                tools.register_agent_tool(
                    name=tool_def["name"],
                    agent_name=tool_def["agent"],
                    description=tool_def.get(
                        "description",
                        f"Invoke agent '{tool_def['agent']}'",
                    ),
                    parameters=tool_def.get("parameters"),
                    context_transform=tool_def.get("context_transform"),
                )
                tools.set_runtime(self)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_as_tool.py::TestBuildAgentWiring -v`

---

### Task 8: Supervisor pattern uses agent tools

**Files:**
- Modify: `astromesh/orchestration/supervisor.py`
- Test: `tests/test_supervisor_agents.py`

- [ ] **Step 1: Write failing tests for supervisor with agent tools**

```python
# tests/test_supervisor_agents.py
import json
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromesh.orchestration.supervisor import SupervisorPattern


@dataclass
class CompletionResponse:
    content: str
    tool_calls: list | None = None


def make_response(content, tool_calls=None):
    return CompletionResponse(content=content, tool_calls=tool_calls)


class TestSupervisorWithAgentTools:
    @pytest.mark.asyncio
    async def test_supervisor_delegates_via_tool_fn(self):
        """Supervisor should call tool_fn for agent tool delegation."""
        delegate_json = json.dumps({"delegate": "qualify-lead", "task": "Check Acme"})
        final_json = json.dumps({"final_answer": "Acme is qualified"})

        model_fn = AsyncMock(
            side_effect=[
                make_response(delegate_json),
                make_response(final_json),
            ]
        )
        tool_fn = AsyncMock(return_value={"answer": "Lead score: 85", "steps": []})
        agent_tools = [
            {
                "type": "function",
                "function": {
                    "name": "qualify-lead",
                    "description": "Qualify a lead",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        pattern = SupervisorPattern(workers={"qualify-lead": "sales-qualifier"})
        result = await pattern.execute(
            query="Qualify Acme Corp",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=agent_tools,
        )

        tool_fn.assert_called_once_with("qualify-lead", {"query": "Check Acme"})
        assert result["answer"] == "Acme is qualified"

    @pytest.mark.asyncio
    async def test_supervisor_final_answer_no_delegation(self):
        """Supervisor returns immediately if model gives final_answer."""
        final_json = json.dumps({"final_answer": "Already done"})
        model_fn = AsyncMock(return_value=make_response(final_json))
        tool_fn = AsyncMock()

        pattern = SupervisorPattern()
        result = await pattern.execute(
            query="Simple task",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert result["answer"] == "Already done"
        tool_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_supervisor_multiple_delegations(self):
        """Supervisor can delegate to multiple agent tools in sequence."""
        model_fn = AsyncMock(
            side_effect=[
                make_response(json.dumps({"delegate": "researcher", "task": "Research X"})),
                make_response(json.dumps({"delegate": "writer", "task": "Write about X"})),
                make_response(json.dumps({"final_answer": "Here is the report"})),
            ]
        )
        tool_fn = AsyncMock(
            side_effect=[
                {"answer": "Research results", "steps": []},
                {"answer": "Draft written", "steps": []},
            ]
        )

        pattern = SupervisorPattern(
            workers={"researcher": "research-agent", "writer": "writer-agent"}
        )
        result = await pattern.execute(
            query="Write a report on X",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert tool_fn.call_count == 2
        assert result["answer"] == "Here is the report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_supervisor_agents.py -v`

- [ ] **Step 3: Update SupervisorPattern to use tool_fn for delegation**

```python
# astromesh/orchestration/supervisor.py
from astromesh.orchestration.patterns import OrchestrationPattern, AgentStep
import json as json_mod


class SupervisorPattern(OrchestrationPattern):
    """Supervisor delegates to worker sub-agents and coordinates."""

    def __init__(self, workers: dict | None = None):
        self._workers = workers or {}

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        steps = []
        worker_names = list(self._workers.keys()) or ["default"]

        for iteration in range(max_iterations):
            supervisor_prompt = (
                f"You are a supervisor managing workers: {worker_names}\n"
                f"Task: {query}\n"
                f"Previous steps: {[s.result or s.observation for s in steps]}\n"
                f'Decide: delegate to a worker (respond with JSON {{"delegate": "worker_name", "task": "..."}})'
                f' or provide final answer (respond with JSON {{"final_answer": "..."}})'
            )

            response = await model_fn(
                [{"role": "user", "content": supervisor_prompt}], tools
            )

            try:
                decision = json_mod.loads(response.content)
            except json_mod.JSONDecodeError:
                steps.append(AgentStep(result=response.content))
                return {"answer": response.content, "steps": steps}

            if "final_answer" in decision:
                steps.append(AgentStep(result=decision["final_answer"]))
                return {"answer": decision["final_answer"], "steps": steps}

            if "delegate" in decision:
                worker_name = decision["delegate"]
                worker_task = decision.get("task", query)
                # Use tool_fn to invoke agent tools (unified mechanism)
                observation = await tool_fn(worker_name, {"query": worker_task})
                worker_result = (
                    observation.get("answer", str(observation))
                    if isinstance(observation, dict)
                    else str(observation)
                )
                steps.append(
                    AgentStep(
                        thought=f"Delegated to {worker_name}: {worker_task}",
                        observation=worker_result,
                    )
                )

        return {"answer": "Max iterations reached", "steps": steps}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_supervisor_agents.py -v`

---

### Task 9: Swarm pattern uses agent tools

**Files:**
- Modify: `astromesh/orchestration/swarm.py`
- Test: `tests/test_swarm_agents.py`

- [ ] **Step 1: Write failing tests for swarm with agent tools**

```python
# tests/test_swarm_agents.py
import json
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock

from astromesh.orchestration.swarm import SwarmPattern


@dataclass
class CompletionResponse:
    content: str
    tool_calls: list | None = None


def make_response(content, tool_calls=None):
    return CompletionResponse(content=content, tool_calls=tool_calls)


class TestSwarmWithAgentTools:
    @pytest.mark.asyncio
    async def test_swarm_handoff_via_tool_fn(self):
        """Swarm handoff should invoke the target agent via tool_fn."""
        handoff_json = json.dumps(
            {"handoff": "specialist", "context": "Need expert analysis"}
        )
        model_fn = AsyncMock(
            side_effect=[
                make_response(handoff_json),
                make_response("Expert analysis complete."),
            ]
        )
        tool_fn = AsyncMock(
            return_value={"answer": "Specialist context loaded", "steps": []}
        )

        pattern = SwarmPattern(agent_configs={"specialist": "specialist-agent"})
        result = await pattern.execute(
            query="Analyze this data",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        tool_fn.assert_called_once_with(
            "specialist", {"query": "Need expert analysis"}
        )
        assert result["answer"] == "Expert analysis complete."

    @pytest.mark.asyncio
    async def test_swarm_no_handoff_returns_directly(self):
        """If no handoff, swarm returns the agent's direct answer."""
        model_fn = AsyncMock(return_value=make_response("Direct answer."))
        tool_fn = AsyncMock()

        pattern = SwarmPattern()
        result = await pattern.execute(
            query="Simple question",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert result["answer"] == "Direct answer."
        tool_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_swarm_multiple_handoffs(self):
        """Chain of handoffs: A -> B -> C -> final answer."""
        model_fn = AsyncMock(
            side_effect=[
                make_response(json.dumps({"handoff": "agent-b", "context": "step 1"})),
                make_response(json.dumps({"handoff": "agent-c", "context": "step 2"})),
                make_response("Final from agent-c."),
            ]
        )
        tool_fn = AsyncMock(
            side_effect=[
                {"answer": "B loaded", "steps": []},
                {"answer": "C loaded", "steps": []},
            ]
        )

        pattern = SwarmPattern(
            agent_configs={"agent-b": "agent-b", "agent-c": "agent-c"}
        )
        result = await pattern.execute(
            query="Multi-step task",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert tool_fn.call_count == 2
        assert result["answer"] == "Final from agent-c."
        assert result["final_agent"] == "agent-c"

    @pytest.mark.asyncio
    async def test_swarm_tool_calls_still_work(self):
        """Regular tool calls (non-handoff) still work within swarm."""
        tool_call = {"id": "tc_1", "name": "web_search", "arguments": {"q": "test"}}
        model_fn = AsyncMock(
            side_effect=[
                make_response("Searching...", tool_calls=[tool_call]),
                make_response("Found the answer."),
            ]
        )
        tool_fn = AsyncMock(return_value={"results": ["result1"]})

        pattern = SwarmPattern()
        result = await pattern.execute(
            query="Search for something",
            context={},
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=[],
        )

        assert result["answer"] == "Found the answer."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_swarm_agents.py -v`

- [ ] **Step 3: Update SwarmPattern to use tool_fn for handoffs**

```python
# astromesh/orchestration/swarm.py
from astromesh.orchestration.patterns import OrchestrationPattern, AgentStep
import json as json_mod


class SwarmPattern(OrchestrationPattern):
    """Agents hand off to each other based on context."""

    def __init__(self, agent_configs: dict | None = None):
        self._agents = agent_configs or {}

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        current_agent = "default"
        steps = []
        messages = [{"role": "user", "content": query}]

        for _ in range(max_iterations):
            agent_prompt = (
                f"You are agent '{current_agent}'. "
                f"Available agents to hand off to: {list(self._agents.keys()) or ['default']}\n"
                'Respond with your answer, or hand off with JSON '
                '{"handoff": "agent_name", "context": "..."}'
            )

            full_messages = [{"role": "system", "content": agent_prompt}] + messages
            response = await model_fn(full_messages, tools)

            try:
                parsed = json_mod.loads(response.content)
                if "handoff" in parsed:
                    target = parsed["handoff"]
                    handoff_context = parsed.get("context", "")
                    steps.append(
                        AgentStep(
                            thought=f"Agent '{current_agent}' hands off to '{target}'",
                            result=handoff_context,
                        )
                    )
                    # Invoke the target agent via tool_fn if it's a known agent
                    if target in self._agents:
                        await tool_fn(target, {"query": handoff_context})
                    current_agent = target
                    messages.append(
                        {"role": "assistant", "content": response.content}
                    )
                    continue
            except (json_mod.JSONDecodeError, KeyError):
                pass

            if response.tool_calls:
                for tc in response.tool_calls:
                    obs = await tool_fn(tc["name"], tc["arguments"])
                    steps.append(
                        AgentStep(
                            thought=response.content,
                            action=tc["name"],
                            action_input=tc["arguments"],
                            observation=str(obs),
                        )
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": str(obs),
                            "tool_call_id": tc["id"],
                        }
                    )
            else:
                steps.append(AgentStep(result=response.content))
                return {
                    "answer": response.content,
                    "steps": steps,
                    "final_agent": current_agent,
                }

        return {"answer": "Max iterations reached", "steps": steps}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_swarm_agents.py -v`

---

### Task 10: End-to-end integration test

**Files:**
- Test: `tests/test_agent_as_tool.py`

- [ ] **Step 1: Write integration test for full agent-as-tool pipeline**

```python
# tests/test_agent_as_tool.py — add to file
class TestAgentAsToolIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline_agent_calls_agent(self):
        """
        End-to-end: parent agent's tool_fn invokes a child agent via ToolRegistry,
        which calls runtime.run(), returns result, and the parent continues.
        """
        child_result = {
            "answer": "Lead score: 92",
            "steps": [],
            "trace": {"trace_id": "child-trace", "spans": []},
        }
        runtime_mock = AsyncMock()
        runtime_mock.run = AsyncMock(return_value=child_result)

        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
            context_transform="{company: data.company}",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "company": {"type": "string"},
                },
            },
        )

        # Simulate what tool_fn does in engine.py
        result = await registry.execute(
            "qualify-lead",
            {"query": "Check this lead", "company": "Acme Corp"},
            context={"session": "integration-sess"},
        )

        assert result["answer"] == "Lead score: 92"
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs.args[0] == "sales-qualifier"
        assert call_kwargs.args[1] == "Check this lead"
        assert call_kwargs.kwargs["context"] == {"company": "Acme Corp"}

    @pytest.mark.asyncio
    async def test_agent_tool_appears_in_schemas(self):
        """Agent tools appear in get_tool_schemas() for LLM function calling."""
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="research-agent",
            agent_name="researcher",
            description="Research a topic thoroughly",
        )
        registry.register_internal(
            name="calculator",
            handler=AsyncMock(return_value={"result": 42}),
            description="Calculate",
            parameters={"type": "object", "properties": {}},
        )

        schemas = registry.get_tool_schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert "research-agent" in names
        assert "calculator" in names

    @pytest.mark.asyncio
    async def test_agent_tool_with_permissions(self):
        """Agent tools respect permission filtering in get_tool_schemas()."""
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="admin-agent",
            agent_name="admin",
            description="Admin operations",
            permissions=["admin"],
        )
        registry.register_agent_tool(
            name="public-agent",
            agent_name="public",
            description="Public operations",
        )

        # No filter — both visible
        schemas = registry.get_tool_schemas()
        assert len(schemas) == 2

        # Filter by admin — only admin-agent
        schemas = registry.get_tool_schemas(agent_permissions=["admin"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "admin-agent"
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/test_agent_as_tool.py tests/test_context_transform.py tests/test_supervisor_agents.py tests/test_swarm_agents.py -v`

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `uv run pytest tests/test_tools.py tests/test_patterns.py tests/test_engine.py -v`

- [ ] **Step 4: Run full project test suite**

Run: `uv run pytest -v`
