# Built-in Tools + Observability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 17 built-in Python tools and full observability (tracing, metrics, structured logging) to Astromesh, so developers can build powerful agents with zero custom tool code.

**Architecture:** New `astromesh/tools/` package with `BuiltinTool` ABC and auto-discovery via `ToolLoader`. Observability wraps the existing execution pipeline with `TracingContext` (contextvars-based), enhances existing `MetricsCollector`/`TelemetryManager`, and adds REST endpoints for trace/metrics queries. Built-in tools are registered as `ToolType.INTERNAL` in the existing `ToolRegistry` — `type: builtin` in YAML is syntactic sugar resolved at load time. `ToolRegistry.execute()` continues returning `dict` in this phase — `ToolResult` is internal to builtin tools and converted via `.to_dict()`.

**Tech Stack:** Python 3.12+, httpx (HTTP tools), Jinja2 (transforms), existing OpenTelemetry + Prometheus

**Spec:** `docs/superpowers/specs/2026-03-10-astromesh-ecosystem-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `astromesh/tools/__init__.py` | `ToolLoader` — auto-discovers and registers built-in tools |
| `astromesh/tools/base.py` | `BuiltinTool` ABC, `ToolContext`, `ToolResult` dataclasses |
| `astromesh/tools/builtin/__init__.py` | Exports all builtin tool classes |
| `astromesh/tools/builtin/web_search.py` | `WebSearchTool`, `WebScrapeTool`, `WikipediaTool` |
| `astromesh/tools/builtin/http.py` | `HttpRequestTool`, `GraphQLQueryTool` |
| `astromesh/tools/builtin/files.py` | `ReadFileTool`, `WriteFileTool` |
| `astromesh/tools/builtin/database.py` | `SqlQueryTool` |
| `astromesh/tools/builtin/communication.py` | `SendEmailTool`, `SendSlackTool`, `SendWebhookTool` |
| `astromesh/tools/builtin/utilities.py` | `DatetimeNowTool`, `JsonTransformTool`, `CacheStoreTool` |
| `astromesh/tools/builtin/ai.py` | `TextSummarizeTool` |
| `astromesh/tools/builtin/rag.py` | `RagQueryTool`, `RagIngestTool` |
| `astromesh/observability/tracing.py` | `TracingContext`, `Span`, span propagation via contextvars |
| `astromesh/observability/logging.py` | `StructuredLogger` — JSON-formatted structured logging |
| `astromesh/observability/collector.py` | `Collector` ABC, `StdoutCollector`, `InternalCollector`, `OTLPCollector` |
| `astromesh/api/routes/traces.py` | REST endpoints: `/v1/traces/`, `/v1/traces/{trace_id}` |
| `astromesh/api/routes/metrics_api.py` | REST endpoints: `/v1/metrics/`, `/v1/metrics/cost` |
| `tests/test_tool_base.py` | Tests for ToolResult, ToolContext, BuiltinTool ABC, ToolLoader |
| `tests/test_builtin_tools.py` | Tests for all 18 built-in tools |
| `tests/test_tracing.py` | Tests for TracingContext, spans, collectors |
| `tests/test_traces_api.py` | Tests for trace/metrics REST endpoints |

### Modified Files

| File | Changes |
|------|---------|
| `astromesh/core/tools.py` | Add `register_builtin()` method (execute() return type stays `dict`) |
| `astromesh/runtime/engine.py` | Wire `ToolLoader` for `type: builtin`, create `TracingContext` per run, parse observability config, wire StructuredLogger |
| `astromesh/api/main.py` | Mount `/v1/traces` and `/v1/metrics` routes |
| `astromesh/api/routes/tools.py` | Return actual registered tools from registry |
| `astromesh/observability/metrics.py` | Add tool latency, cost, orchestration iterations, memory ops metrics |
| `astromesh/observability/telemetry.py` | Bridge as OTLPCollector backend |
| `pyproject.toml` | No new deps needed (httpx, jinja2 already in base deps) |

---

## Chunk 1: Foundation — ToolResult, ToolContext, BuiltinTool ABC, ToolLoader

### Task 1: ToolResult and ToolContext dataclasses

**Files:**
- Create: `astromesh/tools/__init__.py`
- Create: `astromesh/tools/base.py`
- Create: `astromesh/tools/builtin/__init__.py`
- Test: `tests/test_tool_base.py`

- [ ] **Step 1: Write failing tests for ToolResult**

```python
# tests/test_tool_base.py
import pytest
from astromesh.tools.base import ToolResult, ToolContext


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"key": "value"}, metadata={})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self):
        result = ToolResult(success=False, data=None, metadata={}, error="Something failed")
        assert result.success is False
        assert result.error == "Something failed"

    def test_to_dict(self):
        result = ToolResult(success=True, data="hello", metadata={"tokens": 10})
        d = result.to_dict()
        assert d == {
            "success": True,
            "data": "hello",
            "metadata": {"tokens": 10},
            "error": None,
        }

    def test_to_dict_backward_compat(self):
        """ToolResult.to_dict() can be used where old dict returns were expected."""
        result = ToolResult(success=True, data={"answer": "42"}, metadata={})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["data"]["answer"] == "42"


class TestToolContext:
    def test_context_has_required_fields(self):
        ctx = ToolContext(
            agent_name="test-agent",
            session_id="sess-123",
            trace_span=None,
            cache={},
            secrets={},
        )
        assert ctx.agent_name == "test-agent"
        assert ctx.session_id == "sess-123"
        assert ctx.trace_span is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.tools'`

- [ ] **Step 3: Implement ToolResult and ToolContext**

```python
# astromesh/tools/__init__.py
"""Built-in tools package for Astromesh."""

# astromesh/tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standardized result from any tool execution."""
    success: bool
    data: Any
    metadata: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class ToolContext:
    """Context passed to tools during execution."""
    agent_name: str
    session_id: str
    trace_span: Any | None = None
    cache: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)


class BuiltinTool(ABC):
    """Base class for all built-in tools."""
    name: str = ""
    description: str = ""
    parameters: dict = {}
    config_schema: dict = {}

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        ...

    async def validate_config(self, config: dict) -> None:
        """Validate tool configuration. Override to add validation."""
        pass

    async def health_check(self) -> bool:
        """Check if tool dependencies are available. Override if needed."""
        return True
```

```python
# astromesh/tools/builtin/__init__.py
"""Built-in tool implementations."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tool_base.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/ tests/test_tool_base.py
git commit -m "feat: add ToolResult, ToolContext, and BuiltinTool ABC"
```

### Task 2: ToolLoader — auto-discovery and registration

**Files:**
- Modify: `astromesh/tools/__init__.py`
- Modify: `astromesh/core/tools.py`
- Test: `tests/test_tool_base.py` (append)

- [ ] **Step 1: Write failing tests for ToolLoader**

```python
# Append to tests/test_tool_base.py
from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolResult, ToolContext


class _FakeTool(BuiltinTool):
    name = "fake_tool"
    description = "A fake tool for testing"
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data=f"fake: {arguments.get('query')}", metadata={})


class TestToolLoader:
    def test_register_and_get(self):
        loader = ToolLoader()
        loader.register_class(_FakeTool)
        assert loader.get("fake_tool") is _FakeTool

    def test_get_unknown_returns_none(self):
        loader = ToolLoader()
        assert loader.get("nonexistent") is None

    def test_list_available(self):
        loader = ToolLoader()
        loader.register_class(_FakeTool)
        available = loader.list_available()
        assert "fake_tool" in available

    async def test_create_instance_with_config(self):
        loader = ToolLoader()
        loader.register_class(_FakeTool)
        instance = loader.create("fake_tool", config={"key": "val"})
        assert isinstance(instance, _FakeTool)
        assert instance.config == {"key": "val"}

    def test_create_unknown_raises(self):
        loader = ToolLoader()
        with pytest.raises(KeyError, match="nonexistent"):
            loader.create("nonexistent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_base.py::TestToolLoader -v`
Expected: FAIL — `ImportError: cannot import name 'ToolLoader'`

- [ ] **Step 3: Implement ToolLoader**

```python
# astromesh/tools/__init__.py
"""Built-in tools package for Astromesh."""
from astromesh.tools.base import BuiltinTool, ToolResult, ToolContext


class ToolLoader:
    """Discovers and instantiates built-in tools by name."""

    def __init__(self):
        self._registry: dict[str, type[BuiltinTool]] = {}

    def register_class(self, tool_cls: type[BuiltinTool]):
        self._registry[tool_cls.name] = tool_cls

    def get(self, name: str) -> type[BuiltinTool] | None:
        return self._registry.get(name)

    def list_available(self) -> list[str]:
        return list(self._registry.keys())

    def create(self, name: str, config: dict | None = None) -> BuiltinTool:
        cls = self._registry.get(name)
        if cls is None:
            raise KeyError(f"Built-in tool '{name}' not found. Available: {self.list_available()}")
        return cls(config=config)

    def auto_discover(self):
        """Import all builtin tool modules to trigger registration."""
        from astromesh.tools.builtin import ALL_TOOLS
        for tool_cls in ALL_TOOLS:
            self.register_class(tool_cls)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tool_base.py -v`
Expected: All tests PASS

- [ ] **Step 5: Add `register_builtin()` to ToolRegistry**

Modify `astromesh/core/tools.py` — add method and update `execute()` return type:

```python
# In ToolRegistry class, add:
    async def register_builtin(self, name: str, config: dict | None = None):
        """Register a built-in tool by name from the catalog."""
        from astromesh.tools import ToolLoader
        from astromesh.tools.base import ToolResult

        loader = ToolLoader()
        loader.auto_discover()
        instance = loader.create(name, config=config)
        await instance.validate_config(config or {})

        async def _handler(**arguments):
            from astromesh.tools.base import ToolContext
            ctx = ToolContext(
                agent_name="",
                session_id="",
                trace_span=None,
                cache={},
                secrets={},
            )
            result = await instance.execute(arguments, ctx)
            return result.to_dict()

        self.register_internal(
            name=instance.name,
            handler=_handler,
            description=instance.description,
            parameters=instance.parameters,
        )
```

- [ ] **Step 6: Commit**

```bash
git add astromesh/tools/__init__.py astromesh/core/tools.py tests/test_tool_base.py
git commit -m "feat: add ToolLoader with auto-discovery and ToolRegistry.register_builtin()"
```

### Task 3: Wire `type: builtin` in engine.py

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Create: `tests/test_engine_builtin.py`

- [ ] **Step 1: Write failing test for builtin tool loading using a fake tool**

Uses `ToolLoader.register_class()` directly to avoid dependency on `ALL_TOOLS` (populated in Task 17).

```python
# tests/test_engine_builtin.py
import pytest
from unittest.mock import patch
from astromesh.runtime.engine import AgentRuntime
from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolResult, ToolContext


class _FakeBuiltinTool(BuiltinTool):
    name = "fake_builtin"
    description = "A fake builtin tool for testing engine wiring"
    parameters = {"type": "object", "properties": {"input": {"type": "string"}}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data=f"fake: {arguments.get('input')}", metadata={})


class TestBuiltinToolLoading:
    def test_build_agent_resolves_builtin_type(self):
        """type: builtin in YAML should register the tool in the agent's ToolRegistry."""
        config = {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "test-agent", "version": "1.0.0"},
            "spec": {
                "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
                "orchestration": {"pattern": "react"},
                "tools": [
                    {"name": "fake_builtin", "type": "builtin"},
                ],
            },
        }
        # Patch auto_discover to register our fake tool instead
        def _fake_discover(self):
            self.register_class(_FakeBuiltinTool)

        with patch.object(ToolLoader, "auto_discover", _fake_discover):
            runtime = AgentRuntime(config_dir="./config")
            agent = runtime._build_agent(config)

        schemas = agent._tools.get_tool_schemas()
        tool_names = [s["function"]["name"] for s in schemas]
        assert "fake_builtin" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_builtin.py -v`
Expected: FAIL — engine doesn't handle `type: builtin` yet

- [ ] **Step 3: Update `_build_agent` in engine.py to handle `type: builtin`**

In `astromesh/runtime/engine.py`, inside `_build_agent()`, after `tools = ToolRegistry()`, add tool registration.

**Important:** `_build_agent` is synchronous. Use a sync factory function for the handler closure — do NOT use `asyncio.get_event_loop()`.

```python
# Module-level helper in engine.py:
def _make_builtin_handler(tool_instance, agent_name):
    """Create an async handler closure for a builtin tool instance."""
    async def _handler(**arguments):
        from astromesh.tools.base import ToolContext
        ctx = ToolContext(agent_name=agent_name, session_id="", trace_span=None)
        result = await tool_instance.execute(arguments, ctx)
        return result.to_dict()
    return _handler


# Inside _build_agent(), after: tools = ToolRegistry()
from astromesh.tools import ToolLoader
loader = ToolLoader()
loader.auto_discover()

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine_builtin.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_builtin.py
git commit -m "feat: resolve type: builtin tools in agent YAML via ToolLoader"
```

---

## Chunk 2: Observability — Tracing, Structured Logging, Collectors

### Task 4: TracingContext and Span

**Files:**
- Create: `astromesh/observability/tracing.py`
- Test: `tests/test_tracing.py`

- [ ] **Step 1: Write failing tests for TracingContext and Span**

```python
# tests/test_tracing.py
import pytest
import time
from astromesh.observability.tracing import TracingContext, Span, SpanStatus


class TestSpan:
    def test_span_creation(self):
        span = Span(name="test.span", trace_id="trace-1")
        assert span.name == "test.span"
        assert span.trace_id == "trace-1"
        assert span.parent_span_id is None
        assert span.status == SpanStatus.UNSET

    def test_span_finish(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.finish(status=SpanStatus.OK)
        assert span.status == SpanStatus.OK
        assert span.duration_ms >= 0

    def test_span_set_attribute(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_span_add_event(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.add_event("something.happened", {"detail": "info"})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "something.happened"

    def test_span_to_dict(self):
        span = Span(name="test.span", trace_id="trace-1")
        span.set_attribute("key", "val")
        span.finish(status=SpanStatus.OK)
        d = span.to_dict()
        assert d["name"] == "test.span"
        assert d["trace_id"] == "trace-1"
        assert d["status"] == "ok"
        assert "duration_ms" in d


class TestTracingContext:
    def test_create_trace(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        assert ctx.trace_id is not None
        assert ctx.agent_name == "test-agent"

    def test_start_and_finish_span(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        span = ctx.start_span("test.operation")
        assert span.trace_id == ctx.trace_id
        span.finish(status=SpanStatus.OK)
        assert len(ctx.spans) == 1

    def test_nested_spans(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        parent = ctx.start_span("parent")
        child = ctx.start_span("child")
        assert child.parent_span_id == parent.span_id
        child.finish(status=SpanStatus.OK)
        parent.finish(status=SpanStatus.OK)
        assert len(ctx.spans) == 2

    def test_to_dict(self):
        ctx = TracingContext(agent_name="test-agent", session_id="sess-1")
        span = ctx.start_span("op")
        span.finish(status=SpanStatus.OK)
        d = ctx.to_dict()
        assert d["trace_id"] == ctx.trace_id
        assert d["agent"] == "test-agent"
        assert len(d["spans"]) == 1

    def test_sample_rate_zero_disables_spans(self):
        ctx = TracingContext(
            agent_name="test-agent", session_id="sess-1", sample_rate=0.0
        )
        span = ctx.start_span("op")
        span.finish(status=SpanStatus.OK)
        assert ctx.is_sampled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tracing.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement TracingContext and Span**

```python
# astromesh/observability/tracing.py
import random
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpanStatus(str, Enum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration_ms: float | None = None

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict | None = None):
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def finish(self, status: SpanStatus = SpanStatus.OK):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
        }


# ContextVar for current active span
_current_span: ContextVar[Span | None] = ContextVar("_current_span", default=None)


class TracingContext:
    """Collects spans for a single agent run."""

    def __init__(
        self,
        agent_name: str,
        session_id: str,
        sample_rate: float = 1.0,
    ):
        self.trace_id = uuid.uuid4().hex
        self.agent_name = agent_name
        self.session_id = session_id
        self.spans: list[Span] = []
        self.is_sampled = random.random() < sample_rate
        self._span_stack: list[Span] = []

    def start_span(self, name: str, attributes: dict | None = None) -> Span:
        parent_id = self._span_stack[-1].span_id if self._span_stack else None
        span = Span(
            name=name,
            trace_id=self.trace_id,
            parent_span_id=parent_id,
        )
        if attributes:
            span.attributes.update(attributes)
        self._span_stack.append(span)
        self.spans.append(span)
        _current_span.set(span)
        return span

    def finish_span(self, span: Span, status: SpanStatus = SpanStatus.OK):
        span.finish(status=status)
        if self._span_stack and self._span_stack[-1] is span:
            self._span_stack.pop()
        parent = self._span_stack[-1] if self._span_stack else None
        _current_span.set(parent)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "agent": self.agent_name,
            "session_id": self.session_id,
            "is_sampled": self.is_sampled,
            "spans": [s.to_dict() for s in self.spans],
        }


def get_current_span() -> Span | None:
    return _current_span.get()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tracing.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/observability/tracing.py tests/test_tracing.py
git commit -m "feat: add TracingContext and Span for structured tracing"
```

### Task 5: Structured Logging

**Files:**
- Create: `astromesh/observability/logging.py`
- Test: `tests/test_tracing.py` (append)

- [ ] **Step 1: Write failing tests for StructuredLogger**

```python
# Append to tests/test_tracing.py
import json
from io import StringIO
from astromesh.observability.logging import StructuredLogger


class TestStructuredLogger:
    def test_log_event(self):
        output = StringIO()
        logger = StructuredLogger(stream=output)
        logger.info(
            "tool.executed",
            agent="test-agent",
            trace_id="trace-1",
            tool="web_search",
            duration_ms=150,
            status="success",
        )
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["level"] == "info"
        assert data["event"] == "tool.executed"
        assert data["agent"] == "test-agent"
        assert data["tool"] == "web_search"
        assert "timestamp" in data

    def test_log_error(self):
        output = StringIO()
        logger = StructuredLogger(stream=output)
        logger.error("tool.failed", tool="sql_query", error="Connection refused")
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["level"] == "error"
        assert data["error"] == "Connection refused"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tracing.py::TestStructuredLogger -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement StructuredLogger**

```python
# astromesh/observability/logging.py
import json
import sys
import time
from datetime import datetime, timezone
from typing import IO, Any


class StructuredLogger:
    """JSON structured logger for Astromesh events."""

    def __init__(self, stream: IO | None = None):
        self._stream = stream or sys.stdout

    def _emit(self, level: str, event: str, **kwargs: Any):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **kwargs,
        }
        self._stream.write(json.dumps(record, default=str) + "\n")
        self._stream.flush()

    def info(self, event: str, **kwargs):
        self._emit("info", event, **kwargs)

    def warning(self, event: str, **kwargs):
        self._emit("warning", event, **kwargs)

    def error(self, event: str, **kwargs):
        self._emit("error", event, **kwargs)

    def debug(self, event: str, **kwargs):
        self._emit("debug", event, **kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tracing.py::TestStructuredLogger -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/observability/logging.py tests/test_tracing.py
git commit -m "feat: add StructuredLogger for JSON-formatted observability logs"
```

### Task 6: Collector backends

**Files:**
- Create: `astromesh/observability/collector.py`
- Test: `tests/test_tracing.py` (append)

- [ ] **Step 1: Write failing tests for collectors**

```python
# Append to tests/test_tracing.py
from astromesh.observability.collector import StdoutCollector, InternalCollector


class TestStdoutCollector:
    async def test_emit_trace(self):
        output = StringIO()
        collector = StdoutCollector(stream=output)
        ctx = TracingContext(agent_name="test", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        await collector.emit_trace(ctx)
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["trace_id"] == ctx.trace_id


class TestInternalCollector:
    async def test_store_and_query_trace(self):
        collector = InternalCollector()
        ctx = TracingContext(agent_name="test-agent", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        await collector.emit_trace(ctx)
        traces = await collector.query_traces(agent="test-agent", limit=10)
        assert len(traces) == 1
        assert traces[0]["trace_id"] == ctx.trace_id

    async def test_query_by_trace_id(self):
        collector = InternalCollector()
        ctx = TracingContext(agent_name="test", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        await collector.emit_trace(ctx)
        trace = await collector.get_trace(ctx.trace_id)
        assert trace is not None
        assert trace["agent"] == "test"

    async def test_query_empty(self):
        collector = InternalCollector()
        traces = await collector.query_traces(agent="none", limit=10)
        assert traces == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tracing.py::TestStdoutCollector tests/test_tracing.py::TestInternalCollector -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement collectors**

```python
# astromesh/observability/collector.py
import json
import sys
from abc import ABC, abstractmethod
from collections import deque
from typing import IO, Any

from astromesh.observability.tracing import TracingContext


class Collector(ABC):
    @abstractmethod
    async def emit_trace(self, ctx: TracingContext) -> None: ...

    async def query_traces(self, agent: str | None = None, limit: int = 20) -> list[dict]:
        return []

    async def get_trace(self, trace_id: str) -> dict | None:
        return None


class StdoutCollector(Collector):
    def __init__(self, stream: IO | None = None):
        self._stream = stream or sys.stdout

    async def emit_trace(self, ctx: TracingContext) -> None:
        self._stream.write(json.dumps(ctx.to_dict(), default=str) + "\n")
        self._stream.flush()


class InternalCollector(Collector):
    """In-memory collector for development and small deployments."""

    def __init__(self, max_traces: int = 10000):
        self._traces: deque[dict] = deque(maxlen=max_traces)
        self._index: dict[str, dict] = {}  # trace_id -> trace dict

    async def emit_trace(self, ctx: TracingContext) -> None:
        trace_data = ctx.to_dict()
        self._traces.append(trace_data)
        self._index[ctx.trace_id] = trace_data

    async def query_traces(
        self, agent: str | None = None, limit: int = 20
    ) -> list[dict]:
        results = list(self._traces)
        if agent:
            results = [t for t in results if t.get("agent") == agent]
        return list(reversed(results))[:limit]

    async def get_trace(self, trace_id: str) -> dict | None:
        return self._index.get(trace_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tracing.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/observability/collector.py tests/test_tracing.py
git commit -m "feat: add StdoutCollector and InternalCollector for trace storage"
```

### Task 7: Trace and Metrics API routes

**Files:**
- Create: `astromesh/api/routes/traces.py`
- Modify: `astromesh/api/main.py`
- Modify: `astromesh/api/routes/tools.py`
- Test: `tests/test_traces_api.py`

- [ ] **Step 1: Write failing tests for trace API**

```python
# tests/test_traces_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from astromesh.api.main import app
from astromesh.observability.collector import InternalCollector
from astromesh.observability.tracing import TracingContext
from astromesh.api.routes.traces import set_collector


@pytest.fixture
async def collector():
    c = InternalCollector()
    set_collector(c)
    # Seed with a trace
    ctx = TracingContext(agent_name="test-agent", session_id="s1")
    span = ctx.start_span("agent.run")
    span.set_attribute("tokens", 100)
    span.finish()
    await c.emit_trace(ctx)
    return c, ctx.trace_id


class TestTracesAPI:
    async def test_list_traces(self, collector):
        c, trace_id = collector
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/traces/", params={"agent": "test-agent"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) == 1
        assert data["traces"][0]["trace_id"] == trace_id

    async def test_get_trace(self, collector):
        c, trace_id = collector
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/v1/traces/{trace_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == trace_id
        assert len(data["spans"]) == 1

    async def test_get_trace_not_found(self, collector):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/traces/nonexistent")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_traces_api.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement traces route**

```python
# astromesh/api/routes/traces.py
from fastapi import APIRouter, HTTPException, Query

from astromesh.observability.collector import Collector, InternalCollector

router = APIRouter(prefix="/traces", tags=["observability"])

_collector: Collector = InternalCollector()


def set_collector(collector: Collector):
    global _collector
    _collector = collector


def get_collector() -> Collector:
    return _collector


@router.get("/")
async def list_traces(
    agent: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    traces = await _collector.query_traces(agent=agent, limit=limit)
    return {"traces": traces}


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    trace = await _collector.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
```

- [ ] **Step 4: Mount route in main.py**

In `astromesh/api/main.py`, add:

```python
from astromesh.api.routes import traces
app.include_router(traces.router, prefix="/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_traces_api.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/routes/traces.py astromesh/api/main.py tests/test_traces_api.py
git commit -m "feat: add /v1/traces/ API endpoints for observability"
```

### Task 8: Wire tracing into AgentRuntime

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Test: `tests/test_engine_builtin.py` (append)

- [ ] **Step 1: Write failing test for tracing in agent run**

```python
# Append to tests/test_engine_builtin.py
from unittest.mock import AsyncMock, patch
from astromesh.observability.tracing import TracingContext


class TestAgentRunTracing:
    async def test_run_creates_trace(self):
        """Agent.run() should create a TracingContext and collect spans."""
        config = {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "trace-test", "version": "1.0.0"},
            "spec": {
                "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
                "orchestration": {"pattern": "react", "max_iterations": 1},
                "prompts": {"system": "You are a test agent."},
            },
        }
        runtime = AgentRuntime(config_dir="./config")
        agent = runtime._build_agent(config)

        # Mock the router to return a simple response
        mock_response = {
            "content": "Hello",
            "tool_calls": [],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        with patch.object(agent._router, "route", new_callable=AsyncMock, return_value=mock_response):
            result = await agent.run("test query", "session-1")

        # Verify trace was created (stored in result metadata)
        assert "trace" in result or result.get("answer") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_builtin.py::TestAgentRunTracing -v`
Expected: FAIL — no trace in result yet

- [ ] **Step 3: Integrate TracingContext into Agent.run()**

In `astromesh/runtime/engine.py`, modify `Agent.run()`:

```python
async def run(self, query, session_id, context=None):
    from datetime import datetime
    from astromesh.core.memory import ConversationTurn
    from astromesh.observability.tracing import TracingContext, SpanStatus

    # Create trace for this run
    tracing = TracingContext(agent_name=self.name, session_id=session_id)
    root_span = tracing.start_span("agent.run", {"agent": self.name})

    try:
        # Memory
        mem_span = tracing.start_span("agent.memory_build")
        query_text = (
            query if isinstance(query, str)
            else " ".join(p.get("text", "") for p in query if p.get("type") == "text")
        )
        memory_context = await self._memory.build_context(session_id, query_text, max_tokens=4096)
        tracing.finish_span(mem_span)

        # Prompt
        prompt_span = tracing.start_span("agent.prompt_render")
        rendered_prompt = self._prompt_engine.render(
            self._system_prompt, {**(context or {}), "memory": memory_context}
        )
        tracing.finish_span(prompt_span)

        tool_schemas = self._tools.get_tool_schemas(self._permissions.get("allowed_actions"))
        max_iterations = self._orchestration_config.get("max_iterations", 10)

        async def model_fn(messages, tools):
            span = tracing.start_span("llm.complete")
            try:
                full_messages = [{"role": "system", "content": rendered_prompt}] + messages
                resp = await self._router.route(full_messages, tools=tools)
                usage = resp.get("usage", {})
                span.set_attribute("tokens_in", usage.get("input_tokens", 0))
                span.set_attribute("tokens_out", usage.get("output_tokens", 0))
                tracing.finish_span(span)
                return resp
            except Exception as e:
                tracing.finish_span(span, status=SpanStatus.ERROR)
                raise

        async def tool_fn(name, args):
            span = tracing.start_span(f"tool.{name}")
            try:
                result = await self._tools.execute(name, args, {"agent": self.name, "session": session_id})
                span.set_attribute("success", result.get("success", True) if isinstance(result, dict) else True)
                tracing.finish_span(span)
                return result
            except Exception as e:
                tracing.finish_span(span, status=SpanStatus.ERROR)
                raise

        # Orchestration
        orch_span = tracing.start_span(f"orchestration.{self._orchestration_config.get('pattern', 'react')}")
        result = await self._pattern.execute(
            query=query, context=memory_context, model_fn=model_fn,
            tool_fn=tool_fn, tools=tool_schemas, max_iterations=max_iterations,
        )
        tracing.finish_span(orch_span)

        # Persist memory
        persist_span = tracing.start_span("agent.memory_persist")
        if isinstance(query, list):
            text_parts = [p.get("text", "") for p in query if p.get("type") == "text"]
            user_content = " ".join(text_parts)
            user_metadata = {"multimodal_content": query}
        else:
            user_content = query
            user_metadata = {}

        await self._memory.persist_turn(
            session_id,
            ConversationTurn(role="user", content=user_content, timestamp=datetime.utcnow(), metadata=user_metadata),
        )
        await self._memory.persist_turn(
            session_id,
            ConversationTurn(role="assistant", content=result.get("answer", ""), timestamp=datetime.utcnow()),
        )
        tracing.finish_span(persist_span)

        tracing.finish_span(root_span)
        result["trace"] = tracing.to_dict()
        return result

    except Exception as e:
        tracing.finish_span(root_span, status=SpanStatus.ERROR)
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine_builtin.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/test_engine.py tests/test_api.py -v`
Expected: All PASS (existing tests should still work since `trace` is added to result, not replacing anything)

- [ ] **Step 6: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_builtin.py
git commit -m "feat: wire TracingContext into Agent.run() for automatic span collection"
```

---

## Chunk 3: Built-in Tools — Utilities and HTTP

### Task 9: Utility tools (datetime_now, json_transform, cache_store)

**Files:**
- Create: `astromesh/tools/builtin/utilities.py`
- Test: `tests/test_builtin_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_builtin_tools.py
import pytest
import json
from astromesh.tools.base import ToolContext, ToolResult


def _ctx(**kwargs) -> ToolContext:
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestDatetimeNowTool:
    async def test_returns_current_time(self):
        from astromesh.tools.builtin.utilities import DatetimeNowTool
        tool = DatetimeNowTool()
        result = await tool.execute({"timezone": "UTC"}, _ctx())
        assert result.success is True
        assert "datetime" in result.data
        assert "UTC" in result.data["timezone"]

    async def test_default_timezone(self):
        from astromesh.tools.builtin.utilities import DatetimeNowTool
        tool = DatetimeNowTool()
        result = await tool.execute({}, _ctx())
        assert result.success is True


class TestJsonTransformTool:
    async def test_jinja2_transform(self):
        from astromesh.tools.builtin.utilities import JsonTransformTool
        tool = JsonTransformTool()
        result = await tool.execute({
            "data": {"name": "Alice", "scores": [90, 85]},
            "template": '{"greeting": "Hello {{ data.name }}", "top_score": {{ data.scores[0] }}}'
        }, _ctx())
        assert result.success is True
        assert result.data["greeting"] == "Hello Alice"
        assert result.data["top_score"] == 90

    async def test_invalid_template(self):
        from astromesh.tools.builtin.utilities import JsonTransformTool
        tool = JsonTransformTool()
        result = await tool.execute({
            "data": {},
            "template": "{{ invalid | no_such_filter }}"
        }, _ctx())
        assert result.success is False


class TestCacheStoreTool:
    async def test_set_and_get(self):
        from astromesh.tools.builtin.utilities import CacheStoreTool
        tool = CacheStoreTool()
        cache = {}
        ctx = _ctx(cache=cache)

        # Set
        result = await tool.execute({"action": "set", "key": "mykey", "value": "myval"}, ctx)
        assert result.success is True

        # Get
        result = await tool.execute({"action": "get", "key": "mykey"}, ctx)
        assert result.success is True
        assert result.data == "myval"

    async def test_get_missing_key(self):
        from astromesh.tools.builtin.utilities import CacheStoreTool
        tool = CacheStoreTool()
        result = await tool.execute({"action": "get", "key": "nope"}, _ctx(cache={}))
        assert result.success is True
        assert result.data is None

    async def test_delete(self):
        from astromesh.tools.builtin.utilities import CacheStoreTool
        tool = CacheStoreTool()
        cache = {"k": "v"}
        ctx = _ctx(cache=cache)
        result = await tool.execute({"action": "delete", "key": "k"}, ctx)
        assert result.success is True
        assert "k" not in cache
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement utility tools**

```python
# astromesh/tools/builtin/utilities.py
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class DatetimeNowTool(BuiltinTool):
    name = "datetime_now"
    description = "Get the current date and time with optional timezone"
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name (e.g. 'UTC', 'US/Eastern', 'Europe/London'). Defaults to UTC.",
            }
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        tz_name = arguments.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = timezone.utc
            tz_name = "UTC"
        now = datetime.now(tz)
        return ToolResult(
            success=True,
            data={
                "datetime": now.isoformat(),
                "timezone": tz_name,
                "unix_timestamp": now.timestamp(),
            },
            metadata={},
        )


class JsonTransformTool(BuiltinTool):
    name = "json_transform"
    description = "Transform JSON data using a Jinja2 template that outputs JSON"
    parameters = {
        "type": "object",
        "properties": {
            "data": {"description": "The input data to transform"},
            "template": {
                "type": "string",
                "description": "Jinja2 template that produces valid JSON",
            },
        },
        "required": ["data", "template"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        data = arguments["data"]
        template_str = arguments["template"]
        try:
            env = Environment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(data=data)
            parsed = json.loads(rendered)
            return ToolResult(success=True, data=parsed, metadata={})
        except (TemplateSyntaxError, UndefinedError, json.JSONDecodeError) as e:
            return ToolResult(success=False, data=None, metadata={}, error=str(e))


class CacheStoreTool(BuiltinTool):
    name = "cache_store"
    description = "Temporary key-value cache for sharing data between tool calls"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set", "delete"],
                "description": "Cache operation to perform",
            },
            "key": {"type": "string", "description": "Cache key"},
            "value": {"description": "Value to store (for set action)"},
        },
        "required": ["action", "key"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        action = arguments["action"]
        key = arguments["key"]
        cache = context.cache

        if action == "set":
            cache[key] = arguments.get("value")
            return ToolResult(success=True, data=None, metadata={"action": "set", "key": key})
        elif action == "get":
            value = cache.get(key)
            return ToolResult(success=True, data=value, metadata={"action": "get", "key": key})
        elif action == "delete":
            cache.pop(key, None)
            return ToolResult(success=True, data=None, metadata={"action": "delete", "key": key})
        else:
            return ToolResult(success=False, data=None, error=f"Unknown action: {action}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/utilities.py tests/test_builtin_tools.py
git commit -m "feat: add datetime_now, json_transform, cache_store built-in tools"
```

### Task 10: HTTP tools (http_request, graphql_query)

**Files:**
- Create: `astromesh/tools/builtin/http.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py
import respx
import httpx


class TestHttpRequestTool:
    @respx.mock
    async def test_get_request(self):
        from astromesh.tools.builtin.http import HttpRequestTool
        respx.get("https://api.example.com/data").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )
        tool = HttpRequestTool()
        result = await tool.execute({
            "method": "GET",
            "url": "https://api.example.com/data",
        }, _ctx())
        assert result.success is True
        assert result.data["status_code"] == 200
        assert result.data["body"]["result"] == "ok"

    @respx.mock
    async def test_post_with_body(self):
        from astromesh.tools.builtin.http import HttpRequestTool
        respx.post("https://api.example.com/submit").mock(
            return_value=httpx.Response(201, json={"id": 1})
        )
        tool = HttpRequestTool()
        result = await tool.execute({
            "method": "POST",
            "url": "https://api.example.com/submit",
            "body": {"name": "test"},
        }, _ctx())
        assert result.success is True
        assert result.data["status_code"] == 201

    async def test_blocks_localhost_by_default(self):
        from astromesh.tools.builtin.http import HttpRequestTool
        tool = HttpRequestTool()
        result = await tool.execute({
            "method": "GET",
            "url": "http://localhost:8080/secret",
        }, _ctx())
        assert result.success is False
        assert "localhost" in result.error.lower() or "blocked" in result.error.lower()

    @respx.mock
    async def test_timeout(self):
        from astromesh.tools.builtin.http import HttpRequestTool
        respx.get("https://slow.example.com").mock(side_effect=httpx.ReadTimeout("timeout"))
        tool = HttpRequestTool(config={"timeout_seconds": 1})
        result = await tool.execute({
            "method": "GET",
            "url": "https://slow.example.com",
        }, _ctx())
        assert result.success is False


class TestGraphQLQueryTool:
    @respx.mock
    async def test_graphql_query(self):
        from astromesh.tools.builtin.http import GraphQLQueryTool
        respx.post("https://api.example.com/graphql").mock(
            return_value=httpx.Response(200, json={"data": {"user": {"name": "Alice"}}})
        )
        tool = GraphQLQueryTool()
        result = await tool.execute({
            "endpoint": "https://api.example.com/graphql",
            "query": "query { user { name } }",
        }, _ctx())
        assert result.success is True
        assert result.data["data"]["user"]["name"] == "Alice"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestHttpRequestTool tests/test_builtin_tools.py::TestGraphQLQueryTool -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement HTTP tools**

```python
# astromesh/tools/builtin/http.py
from urllib.parse import urlparse

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}


class HttpRequestTool(BuiltinTool):
    name = "http_request"
    description = "Make HTTP requests (GET, POST, PUT, DELETE) to external APIs"
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "description": "HTTP method",
            },
            "url": {"type": "string", "description": "Request URL"},
            "headers": {
                "type": "object",
                "description": "Request headers",
            },
            "body": {"description": "Request body (for POST/PUT/PATCH)"},
        },
        "required": ["method", "url"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        url = arguments["url"]
        method = arguments["method"].upper()
        headers = arguments.get("headers", {})
        body = arguments.get("body")

        # Security: block localhost unless explicitly allowed
        allow_localhost = self.config.get("allow_localhost", False)
        if not allow_localhost:
            parsed = urlparse(url)
            if parsed.hostname in _BLOCKED_HOSTS:
                return ToolResult(
                    success=False, data=None,
                    error=f"Blocked: requests to localhost are not allowed",
                )

        timeout = self.config.get("timeout_seconds", 30)
        max_size = self.config.get("max_response_bytes", 5 * 1024 * 1024)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                kwargs = {"headers": headers}
                if body is not None and method in ("POST", "PUT", "PATCH"):
                    kwargs["json"] = body
                resp = await client.request(method, url, **kwargs)

                # Try to parse as JSON, fall back to text
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = resp.text[:max_size]

                return ToolResult(
                    success=True,
                    data={
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp_body,
                    },
                    metadata={"url": url, "method": method},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class GraphQLQueryTool(BuiltinTool):
    name = "graphql_query"
    description = "Execute GraphQL queries against an endpoint"
    parameters = {
        "type": "object",
        "properties": {
            "endpoint": {"type": "string", "description": "GraphQL endpoint URL"},
            "query": {"type": "string", "description": "GraphQL query string"},
            "variables": {
                "type": "object",
                "description": "Query variables",
            },
            "headers": {"type": "object", "description": "Request headers"},
        },
        "required": ["endpoint", "query"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        endpoint = arguments["endpoint"]
        query = arguments["query"]
        variables = arguments.get("variables", {})
        headers = arguments.get("headers", {})

        timeout = self.config.get("timeout_seconds", 30)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    endpoint,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                return ToolResult(
                    success=True,
                    data=resp.json(),
                    metadata={"endpoint": endpoint, "status_code": resp.status_code},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestHttpRequestTool tests/test_builtin_tools.py::TestGraphQLQueryTool -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/http.py tests/test_builtin_tools.py
git commit -m "feat: add http_request and graphql_query built-in tools"
```

---

## Chunk 4: Built-in Tools — Web, Files, Database

### Task 11: Web tools (web_search, web_scrape, wikipedia)

**Files:**
- Create: `astromesh/tools/builtin/web_search.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py

class TestWebSearchTool:
    @respx.mock
    async def test_tavily_search(self):
        from astromesh.tools.builtin.web_search import WebSearchTool
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={
                "results": [{"title": "Python", "url": "https://python.org", "content": "The Python language"}]
            })
        )
        tool = WebSearchTool(config={"provider": "tavily", "api_key": "test-key"})
        result = await tool.execute({"query": "Python programming"}, _ctx())
        assert result.success is True
        assert len(result.data["results"]) == 1

    async def test_missing_api_key(self):
        from astromesh.tools.builtin.web_search import WebSearchTool
        tool = WebSearchTool(config={"provider": "tavily"})
        result = await tool.execute({"query": "test"}, _ctx(secrets={}))
        assert result.success is False
        assert "api_key" in result.error.lower() or "key" in result.error.lower()


class TestWebScrapeTool:
    @respx.mock
    async def test_scrape_html(self):
        from astromesh.tools.builtin.web_search import WebScrapeTool
        respx.get("https://example.com").mock(
            return_value=httpx.Response(200, text="<html><body><h1>Hello</h1><p>World</p></body></html>")
        )
        tool = WebScrapeTool()
        result = await tool.execute({"url": "https://example.com"}, _ctx())
        assert result.success is True
        assert "Hello" in result.data["content"]


class TestWikipediaTool:
    @respx.mock
    async def test_wikipedia_search(self):
        from astromesh.tools.builtin.web_search import WikipediaTool
        respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Python_(programming_language)").mock(
            return_value=httpx.Response(200, json={
                "title": "Python (programming language)",
                "extract": "Python is a high-level programming language.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python"}},
            })
        )
        tool = WikipediaTool()
        result = await tool.execute({"topic": "Python_(programming_language)"}, _ctx())
        assert result.success is True
        assert "Python" in result.data["title"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestWebSearchTool tests/test_builtin_tools.py::TestWebScrapeTool tests/test_builtin_tools.py::TestWikipediaTool -v`
Expected: FAIL

- [ ] **Step 3: Implement web tools**

```python
# astromesh/tools/builtin/web_search.py
import re

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class WebSearchTool(BuiltinTool):
    name = "web_search"
    description = "Search the web using a search API (Tavily, Brave, or SearXNG)"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results to return", "default": 5},
        },
        "required": ["query"],
    }
    config_schema = {
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["tavily", "brave", "searxng"]},
            "api_key": {"type": "string"},
            "endpoint": {"type": "string", "description": "SearXNG instance URL"},
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        query = arguments["query"]
        max_results = arguments.get("max_results", 5)
        provider = self.config.get("provider", "tavily")
        api_key = self.config.get("api_key") or context.secrets.get("SEARCH_API_KEY")

        if provider == "tavily":
            return await self._tavily_search(query, max_results, api_key)
        elif provider == "brave":
            return await self._brave_search(query, max_results, api_key)
        elif provider == "searxng":
            return await self._searxng_search(query, max_results)
        return ToolResult(success=False, data=None, error=f"Unknown provider: {provider}")

    async def _tavily_search(self, query: str, max_results: int, api_key: str | None) -> ToolResult:
        if not api_key:
            return ToolResult(success=False, data=None, error="Tavily api_key is required")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "max_results": max_results, "api_key": api_key},
                )
                data = resp.json()
                return ToolResult(success=True, data={"results": data.get("results", [])}, metadata={"provider": "tavily"})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    async def _brave_search(self, query: str, max_results: int, api_key: str | None) -> ToolResult:
        if not api_key:
            return ToolResult(success=False, data=None, error="Brave api_key is required")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": max_results},
                    headers={"X-Subscription-Token": api_key},
                )
                data = resp.json()
                results = [{"title": r["title"], "url": r["url"], "content": r.get("description", "")}
                           for r in data.get("web", {}).get("results", [])]
                return ToolResult(success=True, data={"results": results}, metadata={"provider": "brave"})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    async def _searxng_search(self, query: str, max_results: int) -> ToolResult:
        endpoint = self.config.get("endpoint", "http://localhost:8888")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{endpoint}/search",
                    params={"q": query, "format": "json", "number_of_results": max_results},
                )
                data = resp.json()
                return ToolResult(success=True, data={"results": data.get("results", [])}, metadata={"provider": "searxng"})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WebScrapeTool(BuiltinTool):
    name = "web_scrape"
    description = "Extract text content from a URL (HTML converted to plain text)"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to scrape"},
            "max_length": {"type": "integer", "description": "Max characters to return", "default": 10000},
        },
        "required": ["url"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        url = arguments["url"]
        max_length = arguments.get("max_length", 10000)
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                html = resp.text
                # Simple HTML to text: strip tags
                text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                text = text[:max_length]
                return ToolResult(
                    success=True,
                    data={"content": text, "url": url, "length": len(text)},
                    metadata={"status_code": resp.status_code},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WikipediaTool(BuiltinTool):
    name = "wikipedia"
    description = "Get a summary of a Wikipedia article"
    parameters = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Wikipedia article title (use underscores for spaces)"},
            "language": {"type": "string", "description": "Language code (default: en)", "default": "en"},
        },
        "required": ["topic"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        topic = arguments["topic"]
        lang = arguments.get("language", "en")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{topic}"
                )
                if resp.status_code == 404:
                    return ToolResult(success=False, data=None, error=f"Article not found: {topic}")
                data = resp.json()
                return ToolResult(
                    success=True,
                    data={
                        "title": data.get("title"),
                        "extract": data.get("extract"),
                        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                    },
                    metadata={},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestWebSearchTool tests/test_builtin_tools.py::TestWebScrapeTool tests/test_builtin_tools.py::TestWikipediaTool -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/web_search.py tests/test_builtin_tools.py
git commit -m "feat: add web_search, web_scrape, wikipedia built-in tools"
```

### Task 12: File tools (read_file, write_file)

**Files:**
- Create: `astromesh/tools/builtin/files.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py
import tempfile
import os


class TestReadFileTool:
    async def test_read_text_file(self, tmp_path):
        from astromesh.tools.builtin.files import ReadFileTool
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        tool = ReadFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": str(f)}, _ctx())
        assert result.success is True
        assert result.data["content"] == "hello world"

    async def test_read_json_file(self, tmp_path):
        from astromesh.tools.builtin.files import ReadFileTool
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        tool = ReadFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": str(f)}, _ctx())
        assert result.success is True

    async def test_blocked_path(self):
        from astromesh.tools.builtin.files import ReadFileTool
        tool = ReadFileTool(config={"allowed_paths": ["/tmp/safe"]})
        result = await tool.execute({"path": "/etc/passwd"}, _ctx())
        assert result.success is False
        assert "not allowed" in result.error.lower() or "blocked" in result.error.lower()

    async def test_file_not_found(self, tmp_path):
        from astromesh.tools.builtin.files import ReadFileTool
        tool = ReadFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": str(tmp_path / "nope.txt")}, _ctx())
        assert result.success is False


class TestWriteFileTool:
    async def test_write_file(self, tmp_path):
        from astromesh.tools.builtin.files import WriteFileTool
        target = str(tmp_path / "output.txt")
        tool = WriteFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": target, "content": "hello"}, _ctx())
        assert result.success is True
        assert open(target).read() == "hello"

    async def test_blocked_write(self):
        from astromesh.tools.builtin.files import WriteFileTool
        tool = WriteFileTool(config={"allowed_paths": ["/tmp/safe"]})
        result = await tool.execute({"path": "/etc/hacked", "content": "bad"}, _ctx())
        assert result.success is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestReadFileTool tests/test_builtin_tools.py::TestWriteFileTool -v`
Expected: FAIL

- [ ] **Step 3: Implement file tools**

```python
# astromesh/tools/builtin/files.py
import os
from pathlib import Path

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


def _is_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    """Check if path is under one of the allowed directories."""
    if not allowed_paths:
        return True  # No restrictions if not configured
    resolved = os.path.realpath(path)
    return any(resolved.startswith(os.path.realpath(ap)) for ap in allowed_paths)


class ReadFileTool(BuiltinTool):
    name = "read_file"
    description = "Read the contents of a local file (text, CSV, JSON)"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
            "encoding": {"type": "string", "description": "File encoding (default: utf-8)", "default": "utf-8"},
        },
        "required": ["path"],
    }
    config_schema = {
        "type": "object",
        "properties": {
            "allowed_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Directories the tool is allowed to read from",
            },
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        path = arguments["path"]
        encoding = arguments.get("encoding", "utf-8")
        allowed = self.config.get("allowed_paths", [])

        if allowed and not _is_path_allowed(path, allowed):
            return ToolResult(success=False, data=None, error=f"Path not allowed: {path}")

        try:
            content = Path(path).read_text(encoding=encoding)
            return ToolResult(
                success=True,
                data={"content": content, "path": path, "size": len(content)},
                metadata={"encoding": encoding},
            )
        except FileNotFoundError:
            return ToolResult(success=False, data=None, error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WriteFileTool(BuiltinTool):
    name = "write_file"
    description = "Write content to a local file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to write to"},
            "content": {"type": "string", "description": "Content to write"},
            "encoding": {"type": "string", "description": "File encoding (default: utf-8)", "default": "utf-8"},
        },
        "required": ["path", "content"],
    }
    config_schema = {
        "type": "object",
        "properties": {
            "allowed_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Directories the tool is allowed to write to",
            },
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        path = arguments["path"]
        content = arguments["content"]
        encoding = arguments.get("encoding", "utf-8")
        allowed = self.config.get("allowed_paths", [])

        if allowed and not _is_path_allowed(path, allowed):
            return ToolResult(success=False, data=None, error=f"Path not allowed: {path}")

        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding=encoding)
            return ToolResult(
                success=True,
                data={"path": path, "bytes_written": len(content.encode(encoding))},
                metadata={},
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestReadFileTool tests/test_builtin_tools.py::TestWriteFileTool -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/files.py tests/test_builtin_tools.py
git commit -m "feat: add read_file and write_file built-in tools with path restrictions"
```

### Task 13: Database tool (sql_query)

**Files:**
- Create: `astromesh/tools/builtin/database.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py

class TestSqlQueryTool:
    async def test_sqlite_select(self, tmp_path):
        import sqlite3
        from astromesh.tools.builtin.database import SqlQueryTool

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.execute("INSERT INTO users VALUES (2, 'Bob')")
        conn.commit()
        conn.close()

        tool = SqlQueryTool(config={"connection_string": f"sqlite:///{db_path}"})
        result = await tool.execute({"query": "SELECT * FROM users"}, _ctx())
        assert result.success is True
        assert len(result.data["rows"]) == 2
        assert result.data["rows"][0]["name"] == "Alice"

    async def test_read_only_blocks_write(self, tmp_path):
        import sqlite3
        from astromesh.tools.builtin.database import SqlQueryTool

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.commit()
        conn.close()

        tool = SqlQueryTool(config={
            "connection_string": f"sqlite:///{db_path}",
            "read_only": True,
        })
        result = await tool.execute({
            "query": "INSERT INTO users VALUES (1, 'Hacker')"
        }, _ctx())
        assert result.success is False
        assert "read_only" in result.error.lower() or "read-only" in result.error.lower()

    async def test_missing_connection_string(self):
        from astromesh.tools.builtin.database import SqlQueryTool
        tool = SqlQueryTool(config={})
        result = await tool.execute({"query": "SELECT 1"}, _ctx())
        assert result.success is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestSqlQueryTool -v`
Expected: FAIL

- [ ] **Step 3: Implement sql_query tool**

```python
# astromesh/tools/builtin/database.py
import re
import sqlite3

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

_WRITE_PATTERNS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE)\s",
    re.IGNORECASE,
)


class SqlQueryTool(BuiltinTool):
    name = "sql_query"
    description = "Execute SQL queries against a database (SQLite, PostgreSQL, MySQL)"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SQL query to execute"},
            "params": {
                "type": "array",
                "description": "Query parameters for parameterized queries",
            },
        },
        "required": ["query"],
    }
    config_schema = {
        "type": "object",
        "properties": {
            "connection_string": {"type": "string"},
            "read_only": {"type": "boolean", "default": True},
            "max_rows": {"type": "integer", "default": 1000},
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        query = arguments["query"]
        params = arguments.get("params", [])
        conn_str = self.config.get("connection_string")
        read_only = self.config.get("read_only", True)
        max_rows = self.config.get("max_rows", 1000)

        if not conn_str:
            return ToolResult(success=False, data=None, error="connection_string is required in tool config")

        if read_only and _WRITE_PATTERNS.match(query):
            return ToolResult(success=False, data=None, error="Write operations blocked: read_only mode is enabled")

        if conn_str.startswith("sqlite:///"):
            return await self._execute_sqlite(conn_str[len("sqlite:///"):], query, params, max_rows)
        else:
            return ToolResult(success=False, data=None, error=f"Unsupported connection string format. Supported: sqlite:///path")

    async def _execute_sqlite(self, db_path: str, query: str, params: list, max_rows: int) -> ToolResult:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = [dict(row) for row in cursor.fetchmany(max_rows)]
                conn.close()
                return ToolResult(
                    success=True,
                    data={"columns": columns, "rows": rows, "row_count": len(rows)},
                    metadata={"db": db_path},
                )
            else:
                conn.commit()
                conn.close()
                return ToolResult(
                    success=True,
                    data={"affected_rows": cursor.rowcount},
                    metadata={"db": db_path},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestSqlQueryTool -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/database.py tests/test_builtin_tools.py
git commit -m "feat: add sql_query built-in tool with read_only security"
```

---

## Chunk 5: Built-in Tools — Communication, AI, RAG

### Task 14: Communication tools (send_email, send_slack, send_webhook)

**Files:**
- Create: `astromesh/tools/builtin/communication.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py

class TestSendWebhookTool:
    @respx.mock
    async def test_send_webhook(self):
        from astromesh.tools.builtin.communication import SendWebhookTool
        respx.post("https://hooks.example.com/trigger").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        tool = SendWebhookTool()
        result = await tool.execute({
            "url": "https://hooks.example.com/trigger",
            "payload": {"message": "Hello"},
        }, _ctx())
        assert result.success is True
        assert result.data["status_code"] == 200


class TestSendSlackTool:
    @respx.mock
    async def test_send_slack_webhook(self):
        from astromesh.tools.builtin.communication import SendSlackTool
        respx.post("https://hooks.slack.com/services/T/B/X").mock(
            return_value=httpx.Response(200, text="ok")
        )
        tool = SendSlackTool(config={"webhook_url": "https://hooks.slack.com/services/T/B/X"})
        result = await tool.execute({"message": "Hello Slack!"}, _ctx())
        assert result.success is True


class TestSendEmailTool:
    async def test_missing_smtp_config(self):
        from astromesh.tools.builtin.communication import SendEmailTool
        tool = SendEmailTool(config={})
        result = await tool.execute({
            "to": "user@example.com",
            "subject": "Test",
            "body": "Hello",
        }, _ctx())
        assert result.success is False
        assert "smtp" in result.error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestSendWebhookTool tests/test_builtin_tools.py::TestSendSlackTool tests/test_builtin_tools.py::TestSendEmailTool -v`
Expected: FAIL

- [ ] **Step 3: Implement communication tools**

```python
# astromesh/tools/builtin/communication.py
import smtplib
from email.mime.text import MIMEText

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class SendWebhookTool(BuiltinTool):
    name = "send_webhook"
    description = "Send an HTTP POST to a webhook URL with a JSON payload"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Webhook URL"},
            "payload": {"description": "JSON payload to send"},
            "headers": {"type": "object", "description": "Additional headers"},
        },
        "required": ["url", "payload"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        url = arguments["url"]
        payload = arguments["payload"]
        headers = arguments.get("headers", {})
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                return ToolResult(
                    success=True,
                    data={"status_code": resp.status_code, "response": resp.text},
                    metadata={"url": url},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class SendSlackTool(BuiltinTool):
    name = "send_slack"
    description = "Send a message to Slack via webhook or API"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message text"},
            "channel": {"type": "string", "description": "Channel (only for API mode)"},
        },
        "required": ["message"],
    }
    config_schema = {
        "type": "object",
        "properties": {
            "webhook_url": {"type": "string"},
            "api_token": {"type": "string"},
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        message = arguments["message"]
        webhook_url = self.config.get("webhook_url") or context.secrets.get("SLACK_WEBHOOK_URL")

        if webhook_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(webhook_url, json={"text": message})
                    return ToolResult(success=True, data={"response": resp.text}, metadata={"method": "webhook"})
            except Exception as e:
                return ToolResult(success=False, data=None, error=str(e))

        return ToolResult(success=False, data=None, error="No webhook_url or api_token configured")


class SendEmailTool(BuiltinTool):
    name = "send_email"
    description = "Send an email via SMTP"
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body (plain text)"},
        },
        "required": ["to", "subject", "body"],
    }
    config_schema = {
        "type": "object",
        "properties": {
            "smtp_host": {"type": "string"},
            "smtp_port": {"type": "integer", "default": 587},
            "smtp_user": {"type": "string"},
            "smtp_password": {"type": "string"},
            "from_address": {"type": "string"},
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        host = self.config.get("smtp_host") or context.secrets.get("SMTP_HOST")
        if not host:
            return ToolResult(success=False, data=None, error="SMTP host not configured (set smtp_host in config)")

        port = self.config.get("smtp_port", 587)
        user = self.config.get("smtp_user") or context.secrets.get("SMTP_USER")
        password = self.config.get("smtp_password") or context.secrets.get("SMTP_PASSWORD")
        from_addr = self.config.get("from_address", user)

        msg = MIMEText(arguments["body"])
        msg["Subject"] = arguments["subject"]
        msg["From"] = from_addr
        msg["To"] = arguments["to"]

        try:
            import asyncio

            def _send():
                with smtplib.SMTP(host, port) as server:
                    server.starttls()
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)

            await asyncio.to_thread(_send)
            return ToolResult(success=True, data={"to": arguments["to"], "subject": arguments["subject"]}, metadata={})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestSendWebhookTool tests/test_builtin_tools.py::TestSendSlackTool tests/test_builtin_tools.py::TestSendEmailTool -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/communication.py tests/test_builtin_tools.py
git commit -m "feat: add send_email, send_slack, send_webhook built-in tools"
```

### Task 15: AI tool (text_summarize)

**Files:**
- Create: `astromesh/tools/builtin/ai.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py
from unittest.mock import AsyncMock, patch


class TestTextSummarizeTool:
    async def test_summarize(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool
        tool = TextSummarizeTool()

        # Mock model_fn in context — the tool needs access to a model
        mock_model_fn = AsyncMock(return_value={
            "content": "This is a summary of the text.",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        })
        ctx = _ctx()
        ctx.model_fn = mock_model_fn

        result = await tool.execute({
            "text": "A very long text that needs summarizing..." * 50,
            "max_length": 100,
        }, ctx)
        assert result.success is True
        assert "summary" in result.data

    async def test_short_text_returned_as_is(self):
        from astromesh.tools.builtin.ai import TextSummarizeTool
        tool = TextSummarizeTool()
        ctx = _ctx()
        result = await tool.execute({
            "text": "Short text.",
        }, ctx)
        assert result.success is True
        assert result.data["summary"] == "Short text."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestTextSummarizeTool -v`
Expected: FAIL

- [ ] **Step 3: Implement text_summarize**

```python
# astromesh/tools/builtin/ai.py
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

_MIN_SUMMARIZE_LENGTH = 500  # Don't summarize texts shorter than this


class TextSummarizeTool(BuiltinTool):
    name = "text_summarize"
    description = "Summarize long text using the agent's language model"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to summarize"},
            "max_length": {
                "type": "integer",
                "description": "Approximate max length of summary in words",
                "default": 200,
            },
        },
        "required": ["text"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        text = arguments["text"]
        max_length = arguments.get("max_length", 200)

        # Short text: return as-is
        if len(text) < _MIN_SUMMARIZE_LENGTH:
            return ToolResult(
                success=True,
                data={"summary": text, "was_summarized": False},
                metadata={},
            )

        # Use model_fn from context if available
        model_fn = getattr(context, "model_fn", None)
        if model_fn is None:
            return ToolResult(
                success=False, data=None,
                error="text_summarize requires model access (model_fn not available in context)",
            )

        try:
            messages = [{"role": "user", "content": (
                f"Summarize the following text in approximately {max_length} words. "
                f"Be concise and capture the key points.\n\n{text}"
            )}]
            response = await model_fn(messages, [])
            summary = response.get("content", "")
            usage = response.get("usage", {})
            return ToolResult(
                success=True,
                data={"summary": summary, "was_summarized": True},
                metadata={
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                },
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Update ToolContext to support model_fn**

In `astromesh/tools/base.py`, add `model_fn` field:

```python
@dataclass
class ToolContext:
    """Context passed to tools during execution."""
    agent_name: str
    session_id: str
    trace_span: Any | None = None
    cache: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)
    model_fn: Any | None = None  # Optional: for tools that need LLM access (e.g. text_summarize)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestTextSummarizeTool -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh/tools/builtin/ai.py astromesh/tools/base.py tests/test_builtin_tools.py
git commit -m "feat: add text_summarize built-in tool with model access"
```

### Task 16: RAG wrapper tools (rag_query, rag_ingest)

**Files:**
- Create: `astromesh/tools/builtin/rag.py`
- Test: `tests/test_builtin_tools.py` (append)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_builtin_tools.py

class TestRagQueryTool:
    async def test_query_without_pipeline(self):
        from astromesh.tools.builtin.rag import RagQueryTool
        tool = RagQueryTool()
        result = await tool.execute({"query": "test"}, _ctx())
        assert result.success is False
        assert "pipeline" in result.error.lower()


class TestRagIngestTool:
    async def test_ingest_without_pipeline(self):
        from astromesh.tools.builtin.rag import RagIngestTool
        tool = RagIngestTool()
        result = await tool.execute({"document": "content", "metadata": {}}, _ctx())
        assert result.success is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builtin_tools.py::TestRagQueryTool tests/test_builtin_tools.py::TestRagIngestTool -v`
Expected: FAIL

- [ ] **Step 3: Implement RAG wrappers**

```python
# astromesh/tools/builtin/rag.py
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class RagQueryTool(BuiltinTool):
    name = "rag_query"
    description = "Query the RAG pipeline for relevant documents"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Number of results", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        pipeline = getattr(context, "rag_pipeline", None)
        if pipeline is None:
            return ToolResult(success=False, data=None, error="RAG pipeline not available in context")
        try:
            results = await pipeline.query(arguments["query"], top_k=arguments.get("top_k", 5))
            return ToolResult(success=True, data={"results": results}, metadata={})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class RagIngestTool(BuiltinTool):
    name = "rag_ingest"
    description = "Ingest a document into the RAG pipeline"
    parameters = {
        "type": "object",
        "properties": {
            "document": {"type": "string", "description": "Document content to ingest"},
            "metadata": {"type": "object", "description": "Document metadata"},
        },
        "required": ["document"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        pipeline = getattr(context, "rag_pipeline", None)
        if pipeline is None:
            return ToolResult(success=False, data=None, error="RAG pipeline not available in context")
        try:
            await pipeline.ingest(arguments["document"], metadata=arguments.get("metadata", {}))
            return ToolResult(success=True, data={"ingested": True}, metadata={})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_builtin_tools.py::TestRagQueryTool tests/test_builtin_tools.py::TestRagIngestTool -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/rag.py tests/test_builtin_tools.py
git commit -m "feat: add rag_query and rag_ingest built-in tool wrappers"
```

---

## Chunk 6: Tool Registry, Auto-discovery, and Integration

### Task 17: Register ALL_TOOLS and auto-discovery

**Files:**
- Modify: `astromesh/tools/builtin/__init__.py`
- Test: `tests/test_tool_base.py` (append)

- [ ] **Step 1: Write failing test for auto-discovery**

```python
# Append to tests/test_tool_base.py

class TestAutoDiscovery:
    def test_all_tools_registered(self):
        loader = ToolLoader()
        loader.auto_discover()
        available = loader.list_available()
        expected = [
            "datetime_now", "json_transform", "cache_store",
            "http_request", "graphql_query",
            "web_search", "web_scrape", "wikipedia",
            "read_file", "write_file",
            "sql_query",
            "send_email", "send_slack", "send_webhook",
            "text_summarize",
            "rag_query", "rag_ingest",
        ]
        for name in expected:
            assert name in available, f"{name} not found in auto-discovered tools"

    def test_all_tools_count(self):
        loader = ToolLoader()
        loader.auto_discover()
        # 17 builtin tools (text_summarize counts, generate_image is MCP)
        assert len(loader.list_available()) == 17
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_base.py::TestAutoDiscovery -v`
Expected: FAIL — `ALL_TOOLS` not defined yet

- [ ] **Step 3: Populate ALL_TOOLS in builtin/__init__.py**

```python
# astromesh/tools/builtin/__init__.py
"""Built-in tool implementations."""
from astromesh.tools.builtin.utilities import DatetimeNowTool, JsonTransformTool, CacheStoreTool
from astromesh.tools.builtin.http import HttpRequestTool, GraphQLQueryTool
from astromesh.tools.builtin.web_search import WebSearchTool, WebScrapeTool, WikipediaTool
from astromesh.tools.builtin.files import ReadFileTool, WriteFileTool
from astromesh.tools.builtin.database import SqlQueryTool
from astromesh.tools.builtin.communication import SendEmailTool, SendSlackTool, SendWebhookTool
from astromesh.tools.builtin.ai import TextSummarizeTool
from astromesh.tools.builtin.rag import RagQueryTool, RagIngestTool

ALL_TOOLS = [
    DatetimeNowTool,
    JsonTransformTool,
    CacheStoreTool,
    HttpRequestTool,
    GraphQLQueryTool,
    WebSearchTool,
    WebScrapeTool,
    WikipediaTool,
    ReadFileTool,
    WriteFileTool,
    SqlQueryTool,
    SendEmailTool,
    SendSlackTool,
    SendWebhookTool,
    TextSummarizeTool,
    RagQueryTool,
    RagIngestTool,
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tool_base.py::TestAutoDiscovery -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/tools/builtin/__init__.py tests/test_tool_base.py
git commit -m "feat: register all 17 built-in tools in ALL_TOOLS for auto-discovery"
```

### Task 18: Update existing tools API route

**Files:**
- Modify: `astromesh/api/routes/tools.py`
- Test: `tests/test_api.py` (verify existing tests still pass)

- [ ] **Step 1: Write test for tools list endpoint**

```python
# Append to tests/test_traces_api.py (or tests/test_tools_api.py)

class TestToolsAPI:
    async def test_list_builtin_tools(self):
        from astromesh.tools import ToolLoader
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
```

- [ ] **Step 2: Update tools route to list available built-in tools**

In `astromesh/api/routes/tools.py`, update the list endpoint:

```python
@router.get("")
async def list_tools():
    from astromesh.tools import ToolLoader
    loader = ToolLoader()
    loader.auto_discover()
    tools = []
    for name in loader.list_available():
        cls = loader.get(name)
        tools.append({
            "name": cls.name,
            "description": cls.description,
            "parameters": cls.parameters,
            "type": "builtin",
        })
    return {"tools": tools}
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_traces_api.py tests/test_api.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add astromesh/api/routes/tools.py tests/
git commit -m "feat: update /v1/tools endpoint to list built-in tools"
```

### Task 19: Enhanced metrics for observability

**Files:**
- Modify: `astromesh/observability/metrics.py`
- Test: `tests/test_observability.py` (verify no regression)

- [ ] **Step 1: Add tool-level duration histogram and cost counter**

In `astromesh/observability/metrics.py`, add to `_setup_metrics()`:

```python
self._histograms["tool_latency"] = Histogram(
    f"{prefix}_tool_latency_seconds",
    "Tool execution latency",
    ["tool_name"],
)
self._counters["cost_usd"] = Counter(
    f"{prefix}_cost_usd_total",
    "Estimated cost in USD",
    ["agent_name", "model"],
)
```

Add method:

```python
def record_tool_latency(self, tool_name: str, latency_s: float):
    if "tool_latency" in self._histograms:
        self._histograms["tool_latency"].labels(tool_name=tool_name).observe(latency_s)

def record_cost(self, agent_name: str, model: str, cost_usd: float):
    if "cost_usd" in self._counters:
        self._counters["cost_usd"].labels(agent_name=agent_name, model=model).inc(cost_usd)
```

- [ ] **Step 2: Run existing observability tests**

Run: `uv run pytest tests/test_observability.py -v`
Expected: All PASS

- [ ] **Step 3: Also add orchestration iterations and memory operations metrics**

```python
# In _setup_metrics():
self._histograms["orchestration_iterations"] = Histogram(
    f"{prefix}_orchestration_iterations",
    "Orchestration iterations per run",
    ["agent_name", "pattern"],
)
self._counters["memory_operations"] = Counter(
    f"{prefix}_memory_operations_total",
    "Memory read/write operations",
    ["agent_name", "backend", "operation"],  # operation: read/write
)
```

Add methods:

```python
def record_orchestration_iterations(self, agent_name: str, pattern: str, iterations: int):
    if "orchestration_iterations" in self._histograms:
        self._histograms["orchestration_iterations"].labels(
            agent_name=agent_name, pattern=pattern
        ).observe(iterations)

def record_memory_operation(self, agent_name: str, backend: str, operation: str):
    if "memory_operations" in self._counters:
        self._counters["memory_operations"].labels(
            agent_name=agent_name, backend=backend, operation=operation
        ).inc()
```

- [ ] **Step 4: Run existing observability tests**

Run: `uv run pytest tests/test_observability.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/observability/metrics.py
git commit -m "feat: add tool latency, cost, orchestration, and memory metrics"
```

### Task 20: Metrics REST API

**Files:**
- Create: `astromesh/api/routes/metrics_api.py`
- Modify: `astromesh/api/main.py`
- Test: `tests/test_traces_api.py` (append)

- [ ] **Step 1: Write failing tests for metrics API**

```python
# Append to tests/test_traces_api.py

class TestMetricsAPI:
    async def test_get_metrics(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/metrics/", params={"agent": "test-agent", "window": "1h"})
        assert resp.status_code == 200

    async def test_get_cost_metrics(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/metrics/cost", params={"group_by": "agent", "window": "24h"})
        assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_traces_api.py::TestMetricsAPI -v`
Expected: FAIL

- [ ] **Step 3: Implement metrics API route**

```python
# astromesh/api/routes/metrics_api.py
from fastapi import APIRouter, Query

from astromesh.observability.cost_tracker import CostTracker

router = APIRouter(prefix="/metrics", tags=["observability"])

_cost_tracker: CostTracker | None = None


def set_cost_tracker(tracker: CostTracker):
    global _cost_tracker
    _cost_tracker = tracker


@router.get("/")
async def get_metrics(
    agent: str | None = Query(None),
    window: str = Query("1h"),
):
    """Return aggregated metrics. Wraps CostTracker usage summary."""
    if _cost_tracker is None:
        return {"metrics": {}, "window": window}
    summary = _cost_tracker.get_usage_summary(agent_name=agent)
    return {"metrics": summary, "window": window, "agent": agent}


@router.get("/cost")
async def get_cost_metrics(
    group_by: str = Query("agent"),
    window: str = Query("24h"),
):
    """Return cost breakdown."""
    if _cost_tracker is None:
        return {"costs": {}, "group_by": group_by, "window": window}
    summary = _cost_tracker.get_usage_summary()
    return {
        "costs": summary.get(f"by_{group_by}", {}),
        "total_cost": summary.get("total_cost", 0.0),
        "group_by": group_by,
        "window": window,
    }
```

- [ ] **Step 4: Mount in main.py**

```python
from astromesh.api.routes import metrics_api
app.include_router(metrics_api.router, prefix="/v1")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_traces_api.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/routes/metrics_api.py astromesh/api/main.py tests/test_traces_api.py
git commit -m "feat: add /v1/metrics/ and /v1/metrics/cost API endpoints"
```

### Task 21: Wire StructuredLogger and observability config into runtime

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Test: `tests/test_engine_builtin.py` (append)

- [ ] **Step 1: Write failing test for observability config parsing**

```python
# Append to tests/test_engine_builtin.py

class TestObservabilityConfig:
    def test_agent_reads_observability_config(self):
        config = {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "obs-test", "version": "1.0.0"},
            "spec": {
                "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
                "orchestration": {"pattern": "react"},
                "observability": {
                    "tracing": True,
                    "metrics": True,
                    "collector": "internal",
                    "sample_rate": 0.5,
                },
            },
        }
        runtime = AgentRuntime(config_dir="./config")
        agent = runtime._build_agent(config)
        assert agent._observability_config["sample_rate"] == 0.5
        assert agent._observability_config["collector"] == "internal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_builtin.py::TestObservabilityConfig -v`
Expected: FAIL — `_observability_config` doesn't exist

- [ ] **Step 3: Parse observability config in _build_agent and Agent.__init__**

In `_build_agent()`, extract observability config and pass to Agent:

```python
obs_config = spec.get("observability", {
    "tracing": True,
    "metrics": True,
    "collector": "stdout",
    "sample_rate": 1.0,
})
```

In `Agent.__init__`, add `self._observability_config = observability_config`.

In `Agent.run()`, use `sample_rate` from config:

```python
tracing = TracingContext(
    agent_name=self.name,
    session_id=session_id,
    sample_rate=self._observability_config.get("sample_rate", 1.0),
)
```

Also wire StructuredLogger into Agent.run() — emit log events for key operations:

```python
from astromesh.observability.logging import StructuredLogger
logger = StructuredLogger()

# After tool execution:
logger.info("tool.executed", agent=self.name, trace_id=tracing.trace_id,
            tool=name, duration_ms=span.duration_ms, status="success")

# After LLM call:
logger.info("llm.completed", agent=self.name, trace_id=tracing.trace_id,
            tokens_in=usage.get("input_tokens", 0), tokens_out=usage.get("output_tokens", 0))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_engine_builtin.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_builtin.py
git commit -m "feat: parse observability config, wire StructuredLogger into agent runtime"
```

### Task 22: OTLPCollector bridge to existing TelemetryManager

**Files:**
- Modify: `astromesh/observability/collector.py`
- Test: `tests/test_tracing.py` (append)

- [ ] **Step 1: Write test for OTLPCollector**

```python
# Append to tests/test_tracing.py

class TestOTLPCollector:
    async def test_emit_delegates_to_telemetry_manager(self):
        from astromesh.observability.collector import OTLPCollector
        collector = OTLPCollector(enabled=False)  # disabled = no-op, just verify interface
        ctx = TracingContext(agent_name="test", session_id="s1")
        span = ctx.start_span("op")
        span.finish()
        # Should not raise even when OTLP is disabled
        await collector.emit_trace(ctx)
```

- [ ] **Step 2: Implement OTLPCollector**

```python
# Append to astromesh/observability/collector.py

class OTLPCollector(Collector):
    """Bridges to existing TelemetryManager for OTLP export."""

    def __init__(self, endpoint: str = "http://localhost:4317", enabled: bool = True):
        self._enabled = enabled
        self._telemetry = None
        if enabled:
            try:
                from astromesh.observability.telemetry import TelemetryManager, TelemetryConfig
                config = TelemetryConfig(otlp_endpoint=endpoint, enabled=True)
                self._telemetry = TelemetryManager(config)
                self._telemetry.setup()
            except ImportError:
                self._enabled = False

    async def emit_trace(self, ctx: TracingContext) -> None:
        if not self._enabled or not self._telemetry:
            return
        tracer = self._telemetry.get_tracer()
        if not tracer:
            return
        # Re-emit spans through OpenTelemetry
        for span_data in ctx.spans:
            with tracer.start_as_current_span(
                span_data.name,
                attributes=span_data.attributes,
            ) as otel_span:
                for event in span_data.events:
                    otel_span.add_event(event["name"], attributes=event.get("attributes", {}))
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_tracing.py::TestOTLPCollector -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add astromesh/observability/collector.py tests/test_tracing.py
git commit -m "feat: add OTLPCollector bridging to existing TelemetryManager"
```

### Task 23: Full integration test

**Files:**
- Test: `tests/test_integration_builtin.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration_builtin.py
import pytest
from unittest.mock import AsyncMock, patch
from astromesh.runtime.engine import AgentRuntime


class TestBuiltinToolIntegration:
    async def test_agent_with_builtin_datetime_tool(self):
        """End-to-end: agent with builtin datetime_now tool produces a trace."""
        config = {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "integration-test", "version": "1.0.0"},
            "spec": {
                "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
                "orchestration": {"pattern": "react", "max_iterations": 1},
                "prompts": {"system": "You are a helpful assistant."},
                "tools": [
                    {"name": "datetime_now", "type": "builtin"},
                ],
            },
        }
        runtime = AgentRuntime(config_dir="./config")
        agent = runtime._build_agent(config)

        # Verify tool is registered
        schemas = agent._tools.get_tool_schemas()
        tool_names = [s["function"]["name"] for s in schemas]
        assert "datetime_now" in tool_names

        # Mock model response (no tool call, just answer)
        mock_response = {
            "content": "The current time is 2026-03-10T14:00:00.",
            "tool_calls": [],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        }
        with patch.object(agent._router, "route", new_callable=AsyncMock, return_value=mock_response):
            result = await agent.run("What time is it?", "sess-integration")

        assert result.get("answer") is not None or result.get("content") is not None
        assert "trace" in result
        assert len(result["trace"]["spans"]) > 0
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/test_integration_builtin.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: All existing + new tests PASS. No regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_builtin.py
git commit -m "test: add end-to-end integration test for builtin tools + tracing"
```

- [ ] **Step 5: Final lint check**

Run: `uv run ruff check astromesh/tools/ astromesh/observability/ tests/test_builtin_tools.py tests/test_tool_base.py tests/test_tracing.py tests/test_traces_api.py tests/test_integration_builtin.py --fix`

Run: `uv run ruff format astromesh/tools/ astromesh/observability/ tests/test_builtin_tools.py tests/test_tool_base.py tests/test_tracing.py tests/test_traces_api.py tests/test_integration_builtin.py`

- [ ] **Step 6: Commit any lint fixes**

```bash
git add -A
git commit -m "style: lint and format builtin tools + observability code"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|------------------|
| 1: Foundation | 1-3 | ToolResult, ToolContext, BuiltinTool ABC, ToolLoader, engine wiring |
| 2: Observability | 4-8 | TracingContext, StructuredLogger, Collectors, /v1/traces/ API, runtime tracing |
| 3: Utilities & HTTP | 9-10 | datetime_now, json_transform, cache_store, http_request, graphql_query |
| 4: Web, Files, DB | 11-13 | web_search, web_scrape, wikipedia, read_file, write_file, sql_query |
| 5: Comms, AI, RAG | 14-16 | send_email, send_slack, send_webhook, text_summarize, rag_query, rag_ingest |
| 6: Integration | 17-23 | ALL_TOOLS registry, API updates, enhanced metrics, /v1/metrics/ API, StructuredLogger wiring, observability config, OTLPCollector bridge, full integration test |

**Total: 23 tasks, ~115 steps, 17 built-in tools + full observability stack**
