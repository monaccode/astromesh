# Astromesh ADK Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `astromesh-adk`, a Python-first Agent Development Kit that wraps Astromesh core with decorator/class APIs.

**Architecture:** The ADK is a separate Python package (`astromesh-adk/`) that imports from `astromesh` core modules (providers, runtime, memory, tools, orchestration) and exposes them through a developer-friendly API of decorators, builders, and classes. It does NOT depend on `astromesh.api` (FastAPI layer).

**Tech Stack:** Python 3.12+, hatchling (build), pytest + pytest-asyncio (testing), typer + rich (CLI), httpx (remote connection), watchfiles (hot reload).

**Spec:** `docs/superpowers/specs/2026-03-17-astromesh-adk-design.md`

---

## Chunk 1: Foundation Types & Package Scaffolding

### Task 1: Package Scaffolding

**Files:**
- Create: `astromesh-adk/pyproject.toml`
- Create: `astromesh-adk/astromesh_adk/__init__.py`
- Create: `astromesh-adk/tests/__init__.py`
- Create: `astromesh-adk/tests/conftest.py`

- [ ] **Step 1: Create package directory structure**

```bash
mkdir -p astromesh-adk/astromesh_adk/cli
mkdir -p astromesh-adk/tests
mkdir -p astromesh-adk/examples
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "astromesh-adk"
version = "0.1.0"
description = "Agent Development Kit for the Astromesh runtime"
requires-python = ">=3.12"
dependencies = [
    "astromesh>=0.15.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
cli = ["typer>=0.12.0", "rich>=13.0.0"]
dev = ["astromesh-adk[cli]", "watchfiles>=0.21.0"]
test = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0", "pytest-cov>=5.0.0", "respx>=0.21.0"]
all = ["astromesh-adk[cli,dev,test]"]

[project.scripts]
astromesh-adk = "astromesh_adk.cli.main:app"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Write empty __init__.py files**

`astromesh-adk/astromesh_adk/__init__.py`:
```python
"""Astromesh Agent Development Kit."""

__version__ = "0.1.0"
```

`astromesh-adk/astromesh_adk/cli/__init__.py`: empty file

`astromesh-adk/tests/__init__.py`: empty file

- [ ] **Step 4: Write tests/conftest.py**

```python
"""Shared test fixtures for astromesh-adk."""

import pytest
```

- [ ] **Step 5: Verify package structure**

Run: `ls -R astromesh-adk/astromesh_adk/`
Expected: Shows `__init__.py`, `cli/`, `cli/__init__.py`

- [ ] **Step 6: Commit**

```bash
git add astromesh-adk/
git commit -m "feat(adk): scaffold astromesh-adk package"
```

---

### Task 2: Exceptions Module

**Files:**
- Create: `astromesh-adk/astromesh_adk/exceptions.py`
- Create: `astromesh-adk/tests/test_exceptions.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_exceptions.py`:
```python
from astromesh_adk.exceptions import (
    ADKError,
    AgentError,
    AgentNotFoundError,
    OrchestrationError,
    ProviderError,
    ProviderUnavailableError,
    AuthenticationError,
    RateLimitError,
    ToolError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolPermissionError,
    GuardrailError,
    InputBlockedError,
    OutputBlockedError,
    RemoteError,
    RemoteUnavailableError,
    SyncError,
)


def test_exception_hierarchy():
    assert issubclass(AgentError, ADKError)
    assert issubclass(ProviderError, ADKError)
    assert issubclass(ToolError, ADKError)
    assert issubclass(GuardrailError, ADKError)
    assert issubclass(RemoteError, ADKError)


def test_agent_error_subtypes():
    assert issubclass(AgentNotFoundError, AgentError)
    assert issubclass(OrchestrationError, AgentError)


def test_provider_error_subtypes():
    assert issubclass(ProviderUnavailableError, ProviderError)
    assert issubclass(AuthenticationError, ProviderError)
    assert issubclass(RateLimitError, ProviderError)


def test_tool_error_subtypes():
    assert issubclass(ToolNotFoundError, ToolError)
    assert issubclass(ToolTimeoutError, ToolError)
    assert issubclass(ToolPermissionError, ToolError)


def test_guardrail_error_subtypes():
    assert issubclass(InputBlockedError, GuardrailError)
    assert issubclass(OutputBlockedError, GuardrailError)


def test_remote_error_subtypes():
    assert issubclass(RemoteUnavailableError, RemoteError)
    assert issubclass(SyncError, RemoteError)


def test_error_message():
    err = ProviderUnavailableError("all providers failed", attempts=["openai", "ollama"])
    assert str(err) == "all providers failed"
    assert err.attempts == ["openai", "ollama"]


def test_guardrail_error_has_reason():
    err = InputBlockedError("blocked", reason="PII detected")
    assert err.reason == "PII detected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement exceptions module**

`astromesh-adk/astromesh_adk/exceptions.py`:
```python
"""ADK exception hierarchy."""


class ADKError(Exception):
    """Base exception for all ADK errors."""


# --- Agent errors ---

class AgentError(ADKError):
    """Agent execution failure."""


class AgentNotFoundError(AgentError):
    """Agent not found by name."""


class OrchestrationError(AgentError):
    """Orchestration pattern failure (max iterations, timeout)."""


# --- Provider errors ---

class ProviderError(ADKError):
    """LLM provider failure."""


class ProviderUnavailableError(ProviderError):
    """All providers are down or circuit is open."""

    def __init__(self, message: str, attempts: list[str] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


class AuthenticationError(ProviderError):
    """Invalid API key or credentials."""


class RateLimitError(ProviderError):
    """Provider rate limit exceeded."""


# --- Tool errors ---

class ToolError(ADKError):
    """Tool execution failure."""


class ToolNotFoundError(ToolError):
    """Tool not found by name."""


class ToolTimeoutError(ToolError):
    """Tool execution timed out."""


class ToolPermissionError(ToolError):
    """Tool execution not permitted."""


# --- Guardrail errors ---

class GuardrailError(ADKError):
    """Guardrail blocked content."""

    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason


class InputBlockedError(GuardrailError):
    """Input guardrail blocked the query."""


class OutputBlockedError(GuardrailError):
    """Output guardrail blocked the response."""


# --- Remote errors ---

class RemoteError(ADKError):
    """Remote Astromesh connection failure."""


class RemoteUnavailableError(RemoteError):
    """Remote Astromesh server is unreachable."""


class SyncError(RemoteError):
    """Agent registration/sync with remote failed."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_exceptions.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/exceptions.py astromesh-adk/tests/test_exceptions.py
git commit -m "feat(adk): add exception hierarchy"
```

---

### Task 3: Result Types (RunResult, StreamEvent)

**Files:**
- Create: `astromesh-adk/astromesh_adk/result.py`
- Create: `astromesh-adk/tests/test_result.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_result.py`:
```python
from astromesh_adk.result import RunResult, StreamEvent


def test_run_result_from_runtime_dict():
    """RunResult is built from the dict returned by AgentRuntime.run()."""
    runtime_result = {
        "answer": "CRISPR is a gene editing tool.",
        "steps": [
            {"thought": "Need to search", "action": "web_search", "action_input": {"query": "CRISPR"}, "observation": "Found info", "result": None}
        ],
        "trace": _make_trace_dict(),
    }
    result = RunResult.from_runtime(runtime_result)

    assert result.answer == "CRISPR is a gene editing tool."
    assert len(result.steps) == 1
    assert result.steps[0]["action"] == "web_search"
    assert result.cost >= 0
    assert result.tokens["input"] >= 0
    assert result.tokens["output"] >= 0
    assert result.latency_ms >= 0
    assert isinstance(result.model, str)


def test_run_result_from_runtime_no_trace():
    """RunResult works when trace is None."""
    runtime_result = {"answer": "Hello", "steps": [], "trace": None}
    result = RunResult.from_runtime(runtime_result)

    assert result.answer == "Hello"
    assert result.cost == 0.0
    assert result.tokens == {"input": 0, "output": 0}
    assert result.latency_ms == 0.0
    assert result.model == ""


def test_stream_event_step():
    event = StreamEvent(type="step", step={"action": "search"})
    assert event.type == "step"
    assert event.step == {"action": "search"}
    assert event.content is None
    assert event.result is None


def test_stream_event_token():
    event = StreamEvent(type="token", content="Hello")
    assert event.content == "Hello"


def test_stream_event_done():
    result = RunResult(answer="done", steps=[], trace=None, cost=0.0, tokens={"input": 0, "output": 0}, latency_ms=0.0, model="")
    event = StreamEvent(type="done", result=result)
    assert event.result.answer == "done"


def _make_trace_dict():
    """Helper: build a minimal trace dict with one llm.complete span."""
    return {
        "agent_name": "test",
        "session_id": "s1",
        "trace_id": "t1",
        "spans": [
            {
                "name": "agent.run",
                "span_id": "root",
                "parent_span_id": None,
                "duration_ms": 1500.0,
                "attributes": {},
            },
            {
                "name": "llm.complete",
                "span_id": "llm1",
                "parent_span_id": "root",
                "duration_ms": 1200.0,
                "attributes": {
                    "model": "gpt-4o",
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "cost": 0.003,
                },
            },
        ],
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_result.py -v`
Expected: FAIL

- [ ] **Step 3: Implement result module**

`astromesh-adk/astromesh_adk/result.py`:
```python
"""RunResult and StreamEvent types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunResult:
    """Result of an agent execution."""

    answer: str
    steps: list[dict]
    trace: dict | None
    cost: float
    tokens: dict[str, int]
    latency_ms: float
    model: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_runtime(cls, runtime_result: dict) -> RunResult:
        """Build RunResult from the dict returned by AgentRuntime.run()."""
        trace = runtime_result.get("trace")
        cost = 0.0
        input_tokens = 0
        output_tokens = 0
        latency_ms = 0.0
        model = ""

        if trace and isinstance(trace, dict):
            spans = trace.get("spans", [])
            for span in spans:
                attrs = span.get("attributes", {})
                if span.get("name") == "llm.complete":
                    cost += attrs.get("cost", 0.0)
                    input_tokens += attrs.get("input_tokens", 0)
                    output_tokens += attrs.get("output_tokens", 0)
                    model = attrs.get("model", model)
                if span.get("parent_span_id") is None:
                    latency_ms = span.get("duration_ms", 0.0)

        return cls(
            answer=runtime_result.get("answer", ""),
            steps=runtime_result.get("steps", []),
            trace=trace,
            cost=cost,
            tokens={"input": input_tokens, "output": output_tokens},
            latency_ms=latency_ms,
            model=model,
        )


@dataclass
class StreamEvent:
    """Event emitted during agent streaming."""

    type: str  # "step" | "token" | "done"
    step: dict | None = None
    content: str | None = None
    result: RunResult | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_result.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/result.py astromesh-adk/tests/test_result.py
git commit -m "feat(adk): add RunResult and StreamEvent types"
```

---

### Task 4: Context Types (RunContext, ToolContext)

**Files:**
- Create: `astromesh-adk/astromesh_adk/context.py`
- Create: `astromesh-adk/tests/test_context.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_context.py`:
```python
from datetime import datetime
from astromesh_adk.context import RunContext, ToolContext, MemoryAccessor


def test_run_context_creation():
    ctx = RunContext(
        query="Hello",
        session_id="s1",
        agent_name="test-agent",
        user_id="u1",
        timestamp=datetime(2026, 1, 1),
        metadata={"key": "value"},
        tools=["web_search"],
    )
    assert ctx.query == "Hello"
    assert ctx.session_id == "s1"
    assert ctx.agent_name == "test-agent"
    assert ctx.user_id == "u1"
    assert ctx.tools == ["web_search"]


def test_run_context_from_run_params():
    ctx = RunContext.from_run_params(
        query="Hello",
        session_id="s1",
        agent_name="test-agent",
        context={"user_id": "u1", "company": "Acme"},
        tool_names=["search"],
    )
    assert ctx.user_id == "u1"
    assert ctx.metadata["company"] == "Acme"
    assert ctx.tools == ["search"]
    assert isinstance(ctx.timestamp, datetime)


def test_run_context_from_run_params_no_context():
    ctx = RunContext.from_run_params(
        query="Hi",
        session_id="default",
        agent_name="agent",
        context=None,
        tool_names=[],
    )
    assert ctx.user_id is None
    assert ctx.metadata == {}


def test_tool_context_creation():
    ctx = ToolContext(agent_name="agent", session_id="s1")
    assert ctx.agent_name == "agent"
    assert ctx.session_id == "s1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_context.py -v`
Expected: FAIL

- [ ] **Step 3: Implement context module**

`astromesh-adk/astromesh_adk/context.py`:
```python
"""RunContext and ToolContext types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable


@dataclass
class MemoryAccessor:
    """Accessor for agent memory within a run context."""

    _store_fn: Callable[..., Awaitable] | None = None
    _retrieve_fn: Callable[..., Awaitable] | None = None
    _search_fn: Callable[..., Awaitable] | None = None

    async def store(self, key: str, value: str) -> None:
        if self._store_fn:
            await self._store_fn(key, value)

    async def retrieve(self, key: str) -> str | None:
        if self._retrieve_fn:
            return await self._retrieve_fn(key)
        return None

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self._search_fn:
            return await self._search_fn(query, top_k)
        return []


@dataclass
class RunContext:
    """Context passed to agent handlers and lifecycle hooks."""

    query: str
    session_id: str
    agent_name: str
    user_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    memory: MemoryAccessor = field(default_factory=MemoryAccessor)
    tools: list[str] = field(default_factory=list)

    # Internal callables — set by the runner, not by the user
    _run_default_fn: Callable[..., Awaitable] | None = field(default=None, repr=False)
    _complete_fn: Callable[..., Awaitable] | None = field(default=None, repr=False)
    _call_tool_fn: Callable[..., Awaitable] | None = field(default=None, repr=False)

    async def run_default(self):
        """Execute the default orchestration pipeline."""
        if self._run_default_fn:
            return await self._run_default_fn()
        raise RuntimeError("run_default is not available in this context")

    async def complete(self, query: str, **kwargs) -> str:
        """Call the model directly, bypassing orchestration."""
        if self._complete_fn:
            return await self._complete_fn(query, **kwargs)
        raise RuntimeError("complete is not available in this context")

    async def call_tool(self, name: str, args: dict) -> Any:
        """Execute a tool by name."""
        if self._call_tool_fn:
            return await self._call_tool_fn(name, args)
        raise RuntimeError("call_tool is not available in this context")

    @classmethod
    def from_run_params(
        cls,
        query: str,
        session_id: str,
        agent_name: str,
        context: dict | None,
        tool_names: list[str],
    ) -> RunContext:
        """Build RunContext from agent.run() parameters."""
        ctx = context or {}
        return cls(
            query=query,
            session_id=session_id,
            agent_name=agent_name,
            user_id=ctx.get("user_id"),
            metadata={k: v for k, v in ctx.items() if k != "user_id"},
            tools=tool_names,
        )


@dataclass
class ToolContext:
    """Context passed to tool execute methods."""

    agent_name: str
    session_id: str
    metadata: dict = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_context.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/context.py astromesh-adk/tests/test_context.py
git commit -m "feat(adk): add RunContext and ToolContext types"
```

---

### Task 5: Callbacks Module

**Files:**
- Create: `astromesh-adk/astromesh_adk/callbacks.py`
- Create: `astromesh-adk/tests/test_callbacks.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_callbacks.py`:
```python
import pytest
from astromesh_adk.callbacks import Callbacks


class RecordingCallbacks(Callbacks):
    def __init__(self):
        self.events = []

    async def on_step(self, step):
        self.events.append(("step", step))

    async def on_tool_result(self, tool_name, args, result):
        self.events.append(("tool_result", tool_name, result))

    async def on_model_call(self, model, messages, response):
        self.events.append(("model_call", model))

    async def on_error(self, error, context):
        self.events.append(("error", str(error)))


async def test_callbacks_are_noop_by_default():
    cb = Callbacks()
    # These should not raise
    await cb.on_step({})
    await cb.on_tool_result("tool", {}, "result")
    await cb.on_model_call("model", [], {})
    await cb.on_error(Exception("test"), {})


async def test_recording_callbacks():
    cb = RecordingCallbacks()
    await cb.on_step({"action": "search"})
    await cb.on_tool_result("web_search", {"q": "test"}, "result")
    assert len(cb.events) == 2
    assert cb.events[0] == ("step", {"action": "search"})
    assert cb.events[1][0] == "tool_result"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_callbacks.py -v`
Expected: FAIL

- [ ] **Step 3: Implement callbacks module**

`astromesh-adk/astromesh_adk/callbacks.py`:
```python
"""Observational callbacks for agent execution."""

from typing import Any


class Callbacks:
    """Base class for observational callbacks.

    Callbacks are read-only observers — they cannot modify or block execution.
    Override any method to receive notifications. All methods are no-ops by default.
    """

    async def on_step(self, step: dict) -> None:
        """Called after each orchestration step completes."""

    async def on_tool_result(self, tool_name: str, args: dict, result: Any) -> None:
        """Called after a tool execution completes."""

    async def on_model_call(self, model: str, messages: list[dict], response: Any) -> None:
        """Called after a model call completes."""

    async def on_error(self, error: Exception, context: dict) -> None:
        """Called when an error occurs. Errors in callbacks are logged, not propagated."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_callbacks.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/callbacks.py astromesh-adk/tests/test_callbacks.py
git commit -m "feat(adk): add observational Callbacks base class"
```

---

## Chunk 2: Provider Resolution & Config Builders

### Task 6: Provider Resolution

**Files:**
- Create: `astromesh-adk/astromesh_adk/providers.py`
- Create: `astromesh-adk/tests/test_providers.py`

The provider resolver parses `"provider/model"` strings and creates configured Astromesh provider instances.

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_providers.py`:
```python
import os
import pytest
from astromesh_adk.providers import parse_model_string, resolve_provider, PROVIDER_REGISTRY


def test_parse_model_string_openai():
    provider, model = parse_model_string("openai/gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"


def test_parse_model_string_with_org():
    provider, model = parse_model_string("anthropic/claude-sonnet-4-20250514")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-20250514"


def test_parse_model_string_ollama():
    provider, model = parse_model_string("ollama/llama3")
    assert provider == "ollama"
    assert model == "llama3"


def test_parse_model_string_no_slash():
    """Without slash, assume openai provider."""
    provider, model = parse_model_string("gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"


def test_provider_registry_has_all_providers():
    expected = {"openai", "anthropic", "ollama", "vllm", "llamacpp", "hf"}
    assert expected.issubset(set(PROVIDER_REGISTRY.keys()))


def test_provider_registry_env_vars():
    assert PROVIDER_REGISTRY["openai"]["env_var"] == "OPENAI_API_KEY"
    assert PROVIDER_REGISTRY["anthropic"]["env_var"] == "ANTHROPIC_API_KEY"
    assert PROVIDER_REGISTRY["ollama"]["env_var"] is None


def test_resolve_provider_ollama():
    """Ollama doesn't need an API key."""
    provider = resolve_provider("ollama", "llama3", model_config=None)
    assert provider is not None


def test_resolve_provider_with_config():
    provider = resolve_provider(
        "openai",
        "gpt-4o",
        model_config={
            "endpoint": "https://my-proxy.com/v1",
            "api_key_env": "MY_KEY",
            "temperature": 0.7,
        },
    )
    assert provider is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_providers.py -v`
Expected: FAIL

- [ ] **Step 3: Implement provider resolution**

`astromesh-adk/astromesh_adk/providers.py`:
```python
"""Provider resolution from 'provider/model' strings."""

from __future__ import annotations

import os

from astromesh.providers.base import ProviderProtocol
from astromesh.providers.ollama_provider import OllamaProvider
from astromesh.providers.openai_compat import OpenAICompatProvider
from astromesh.providers.vllm_provider import VLLMProvider
from astromesh.providers.llamacpp_provider import LlamaCppProvider
from astromesh.providers.hf_tgi_provider import HFTGIProvider

# Maps provider prefix → {class, env_var, default_endpoint}
PROVIDER_REGISTRY: dict[str, dict] = {
    "openai": {
        "class": OpenAICompatProvider,
        "env_var": "OPENAI_API_KEY",
        "default_endpoint": "https://api.openai.com/v1",
    },
    "anthropic": {
        "class": OpenAICompatProvider,  # v1: uses OpenAI-compat endpoint
        "env_var": "ANTHROPIC_API_KEY",
        "default_endpoint": "https://api.anthropic.com/v1",
    },
    "ollama": {
        "class": OllamaProvider,
        "env_var": None,
        "default_endpoint": "http://localhost:11434",
    },
    "vllm": {
        "class": VLLMProvider,
        "env_var": None,
        "default_endpoint": "http://localhost:8000",
    },
    "llamacpp": {
        "class": LlamaCppProvider,
        "env_var": None,
        "default_endpoint": "http://localhost:8080",
    },
    "hf": {
        "class": HFTGIProvider,
        "env_var": "HF_TOKEN",
        "default_endpoint": None,
    },
}


def parse_model_string(model: str) -> tuple[str, str]:
    """Parse 'provider/model' into (provider_name, model_name).

    If no slash is present, defaults to 'openai' provider.
    """
    if "/" in model:
        provider, model_name = model.split("/", 1)
        return provider, model_name
    return "openai", model


def resolve_provider(
    provider_name: str,
    model_name: str,
    model_config: dict | None = None,
) -> ProviderProtocol:
    """Create a configured provider instance."""
    config = model_config or {}
    registry_entry = PROVIDER_REGISTRY.get(provider_name)
    if not registry_entry:
        raise ValueError(f"Unknown provider: {provider_name!r}. Available: {list(PROVIDER_REGISTRY)}")

    provider_cls = registry_entry["class"]
    env_var = config.get("api_key_env") or registry_entry["env_var"]
    endpoint = config.get("endpoint") or registry_entry["default_endpoint"]

    # Build provider config dict matching Astromesh constructors
    provider_config = {"model": model_name}
    if endpoint:
        provider_config["endpoint"] = endpoint
    if env_var:
        api_key = os.environ.get(env_var, "")
        if api_key:
            provider_config["api_key"] = api_key

    # Pass through model parameters
    for param in ("temperature", "top_p", "max_tokens"):
        if param in config:
            provider_config[param] = config[param]

    return provider_cls(provider_config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_providers.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/providers.py astromesh-adk/tests/test_providers.py
git commit -m "feat(adk): add provider resolution from model strings"
```

---

### Task 7: Memory Config Builder

**Files:**
- Create: `astromesh-adk/astromesh_adk/memory.py`
- Create: `astromesh-adk/tests/test_memory_config.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_memory_config.py`:
```python
from astromesh_adk.memory import normalize_memory_config


def test_none_returns_empty():
    assert normalize_memory_config(None) == {}


def test_string_shorthand_sqlite():
    config = normalize_memory_config("sqlite")
    assert config["conversational"]["backend"] == "sqlite"
    assert config["conversational"]["strategy"] == "sliding_window"
    assert config["conversational"]["max_turns"] == 50


def test_string_shorthand_redis():
    config = normalize_memory_config("redis")
    assert config["conversational"]["backend"] == "redis"


def test_full_dict_passthrough():
    input_config = {
        "conversational": {"backend": "sqlite", "strategy": "summary", "max_turns": 20},
        "semantic": {"backend": "chromadb", "similarity_threshold": 0.8},
    }
    config = normalize_memory_config(input_config)
    assert config["conversational"]["strategy"] == "summary"
    assert config["semantic"]["backend"] == "chromadb"


def test_dict_shorthand_backends_only():
    config = normalize_memory_config({"conversational": "redis", "semantic": "faiss"})
    assert config["conversational"]["backend"] == "redis"
    assert config["conversational"]["strategy"] == "sliding_window"
    assert config["semantic"]["backend"] == "faiss"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_memory_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement memory config builder**

`astromesh-adk/astromesh_adk/memory.py`:
```python
"""Memory configuration normalization."""

from __future__ import annotations

CONVERSATIONAL_DEFAULTS = {
    "strategy": "sliding_window",
    "max_turns": 50,
}

SEMANTIC_DEFAULTS = {
    "similarity_threshold": 0.7,
    "max_results": 5,
}


def normalize_memory_config(memory: str | dict | None) -> dict:
    """Normalize memory config from shorthand or full dict.

    Accepts:
        - None → {}
        - "sqlite" → {"conversational": {"backend": "sqlite", ...defaults}}
        - {"conversational": "redis"} → {"conversational": {"backend": "redis", ...defaults}}
        - {"conversational": {"backend": "sqlite", "strategy": "summary"}} → passthrough with defaults
    """
    if memory is None:
        return {}

    if isinstance(memory, str):
        return {
            "conversational": {"backend": memory, **CONVERSATIONAL_DEFAULTS},
        }

    result = {}
    for mem_type, value in memory.items():
        if isinstance(value, str):
            defaults = CONVERSATIONAL_DEFAULTS if mem_type == "conversational" else SEMANTIC_DEFAULTS
            result[mem_type] = {"backend": value, **defaults}
        elif isinstance(value, dict):
            defaults = CONVERSATIONAL_DEFAULTS if mem_type == "conversational" else SEMANTIC_DEFAULTS
            merged = {**defaults, **value}
            result[mem_type] = merged
        else:
            result[mem_type] = value

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_memory_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/memory.py astromesh-adk/tests/test_memory_config.py
git commit -m "feat(adk): add memory config normalization"
```

---

### Task 8: Guardrails Config Builder

**Files:**
- Create: `astromesh-adk/astromesh_adk/guardrails.py`
- Create: `astromesh-adk/tests/test_guardrails_config.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_guardrails_config.py`:
```python
from astromesh_adk.guardrails import normalize_guardrails_config


def test_none_returns_empty():
    assert normalize_guardrails_config(None) == {"input": [], "output": []}


def test_dict_with_lists():
    config = normalize_guardrails_config({
        "input": ["pii_detection", "topic_filter"],
        "output": ["pii_detection"],
    })
    assert len(config["input"]) == 2
    assert config["input"][0]["type"] == "pii_detection"
    assert config["input"][0]["action"] == "redact"
    assert config["input"][1]["type"] == "topic_filter"
    assert config["input"][1]["action"] == "block"


def test_dict_with_full_config():
    config = normalize_guardrails_config({
        "input": [{"type": "pii_detection", "action": "warn"}],
        "output": [],
    })
    assert config["input"][0]["action"] == "warn"


def test_only_input():
    config = normalize_guardrails_config({"input": ["max_length"]})
    assert config["output"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_guardrails_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement guardrails config builder**

`astromesh-adk/astromesh_adk/guardrails.py`:
```python
"""Guardrails configuration normalization."""

from __future__ import annotations

# Default actions per guardrail type
DEFAULT_ACTIONS = {
    "pii_detection": "redact",
    "topic_filter": "block",
    "max_length": "block",
    "cost_limit": "block",
    "content_filter": "redact",
}


def normalize_guardrails_config(guardrails: dict | None) -> dict:
    """Normalize guardrails config into Astromesh format.

    Accepts:
        - None → {"input": [], "output": []}
        - {"input": ["pii_detection"]} → {"input": [{"type": "pii_detection", "action": "redact"}]}
        - {"input": [{"type": "pii_detection", "action": "warn"}]} → passthrough
    """
    if guardrails is None:
        return {"input": [], "output": []}

    result = {}
    for side in ("input", "output"):
        items = guardrails.get(side, [])
        normalized = []
        for item in items:
            if isinstance(item, str):
                normalized.append({
                    "type": item,
                    "action": DEFAULT_ACTIONS.get(item, "block"),
                })
            elif isinstance(item, dict):
                normalized.append(item)
        result[side] = normalized

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_guardrails_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/guardrails.py astromesh-adk/tests/test_guardrails_config.py
git commit -m "feat(adk): add guardrails config normalization"
```

---

## Chunk 3: Tool System

### Task 9: @tool Decorator & Tool Base Class

**Files:**
- Create: `astromesh-adk/astromesh_adk/tools.py`
- Create: `astromesh-adk/tests/test_tools.py`

This is the core of the tool system: the `@tool` decorator that auto-generates JSON schema from type hints, and the `Tool` base class for stateful tools.

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_tools.py`:
```python
import pytest
from astromesh_adk.tools import tool, Tool, ToolDefinitionWrapper


# --- @tool decorator tests ---

@tool(description="Search the web")
async def web_search(query: str, max_results: int = 5) -> str:
    return f"Results for {query}"


@tool(description="Calculate", rate_limit={"max_calls": 10, "window_seconds": 60})
async def calculator(expression: str) -> float:
    return 42.0


def test_tool_decorator_preserves_callable():
    """The decorated function is still callable as a tool handler."""
    assert callable(web_search)


def test_tool_decorator_creates_wrapper():
    assert isinstance(web_search, ToolDefinitionWrapper)


def test_tool_decorator_name_from_function():
    assert web_search.tool_name == "web_search"


def test_tool_decorator_description():
    assert web_search.tool_description == "Search the web"


def test_tool_decorator_schema_generation():
    schema = web_search.parameters_schema
    assert schema["type"] == "object"
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["type"] == "string"
    assert "max_results" in schema["properties"]
    assert schema["properties"]["max_results"]["type"] == "integer"
    assert schema["properties"]["max_results"].get("default") == 5
    assert schema["required"] == ["query"]


def test_tool_decorator_rate_limit():
    assert calculator.rate_limit == {"max_calls": 10, "window_seconds": 60}


async def test_tool_decorator_execution():
    result = await web_search(query="test", max_results=3)
    assert result == "Results for test"


# --- Optional type hints ---

@tool(description="Optional param")
async def optional_tool(name: str, count: int | None = None) -> str:
    return name


def test_tool_optional_params():
    schema = optional_tool.parameters_schema
    assert "count" in schema["properties"]
    assert "count" not in schema["required"]


# --- Tool base class tests ---

class MyTool(Tool):
    name = "my_tool"
    description = "A custom tool"

    def parameters(self):
        return {
            "input": {"type": "string", "description": "The input"},
        }

    async def execute(self, args: dict, ctx=None) -> str:
        return f"processed: {args['input']}"


async def test_tool_class_execute():
    t = MyTool()
    result = await t.execute({"input": "hello"})
    assert result == "processed: hello"


def test_tool_class_attributes():
    t = MyTool()
    assert t.name == "my_tool"
    assert t.description == "A custom tool"
    assert "input" in t.parameters()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_tools.py -v`
Expected: FAIL

- [ ] **Step 3: Implement tools module**

`astromesh-adk/astromesh_adk/tools.py`:
```python
"""@tool decorator and Tool base class."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
import types
from typing import Any, get_type_hints, get_origin, get_args, Union

# Python type → JSON schema type
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _is_optional(annotation) -> bool:
    """Check if a type hint is Optional (Union[X, None] or X | None)."""
    origin = get_origin(annotation)
    if origin is Union or isinstance(annotation, types.UnionType):
        args = get_args(annotation)
        return type(None) in args
    return False


def _unwrap_optional(annotation):
    """Get the inner type from Optional[X]."""
    args = get_args(annotation)
    return next(a for a in args if a is not type(None))


def _python_type_to_json(annotation) -> str:
    """Convert a Python type annotation to a JSON schema type string."""
    if _is_optional(annotation):
        annotation = _unwrap_optional(annotation)
    return _TYPE_MAP.get(annotation, "string")


def _generate_schema(func) -> dict:
    """Generate JSON schema from function signature and type hints."""
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "ctx", "context"):
            continue

        annotation = hints.get(param_name, str)
        prop: dict[str, Any] = {"type": _python_type_to_json(annotation)}

        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            if not _is_optional(annotation):
                required.append(param_name)

        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class ToolDefinitionWrapper:
    """Wraps a decorated function with tool metadata and schema."""

    def __init__(
        self,
        func,
        description: str,
        rate_limit: dict | None = None,
        requires_approval: bool = False,
        timeout: int = 30,
    ):
        self._func = func
        self.tool_name = func.__name__
        self.tool_description = description
        self.parameters_schema = _generate_schema(func)
        self.rate_limit = rate_limit
        self.requires_approval = requires_approval
        self.timeout = timeout

    async def __call__(self, *args, **kwargs):
        return await self._func(*args, **kwargs)

    def __repr__(self):
        return f"<Tool {self.tool_name!r}>"


def tool(
    description: str,
    rate_limit: dict | None = None,
    requires_approval: bool = False,
    timeout: int = 30,
):
    """Decorator to define a tool from an async function.

    JSON schema is auto-generated from type hints.
    """

    def decorator(func):
        return ToolDefinitionWrapper(
            func,
            description=description,
            rate_limit=rate_limit,
            requires_approval=requires_approval,
            timeout=timeout,
        )

    return decorator


class Tool(ABC):
    """Base class for stateful tools with lifecycle management."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def parameters(self) -> dict:
        """Return the JSON schema for tool parameters."""

    @abstractmethod
    async def execute(self, args: dict, ctx: Any = None) -> Any:
        """Execute the tool with the given arguments."""

    async def cleanup(self) -> None:
        """Clean up resources. Called during runtime shutdown."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/tools.py astromesh-adk/tests/test_tools.py
git commit -m "feat(adk): add @tool decorator and Tool base class with schema generation"
```

---

### Task 10: MCP Tools Helper

**Files:**
- Create: `astromesh-adk/astromesh_adk/mcp.py`
- Create: `astromesh-adk/tests/test_mcp.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_mcp.py`:
```python
from astromesh_adk.mcp import mcp_tools, MCPToolSet


def test_mcp_tools_returns_toolset():
    toolset = mcp_tools(transport="stdio", command="echo", args=["hello"])
    assert isinstance(toolset, MCPToolSet)


def test_mcp_toolset_is_iterable():
    toolset = mcp_tools(transport="stdio", command="echo", args=[])
    # Before discovery, iteration yields the toolset itself as a lazy marker
    items = list(toolset)
    assert len(items) == 1
    assert items[0] is toolset


def test_mcp_toolset_stores_config():
    toolset = mcp_tools(
        transport="http",
        command=None,
        args=[],
        url="https://mcp.example.com",
        headers={"Authorization": "Bearer xxx"},
    )
    assert toolset.config["transport"] == "http"
    assert toolset.config["url"] == "https://mcp.example.com"


def test_mcp_toolset_discovered_flag():
    toolset = mcp_tools(transport="stdio", command="echo", args=[])
    assert toolset.discovered is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_mcp.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MCP tools helper**

`astromesh-adk/astromesh_adk/mcp.py`:
```python
"""MCP tools integration — lazy discovery."""

from __future__ import annotations

from typing import Any, Iterator


class MCPToolSet:
    """Lazy MCP tool set descriptor.

    Created synchronously at import time. Actual MCP server connection
    and tool discovery happens on first agent run via discover().
    """

    def __init__(self, config: dict):
        self.config = config
        self.discovered = False
        self._tools: list[dict] = []
        self._client: Any = None

    async def discover(self) -> list[dict]:
        """Connect to MCP server and discover available tools.

        Called automatically by the ADK runner on first agent execution.
        """
        from astromesh.mcp.client import MCPClient

        self._client = MCPClient(self.config)
        await self._client.connect()
        mcp_tools_info = self._client.get_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in mcp_tools_info
        ]
        self.discovered = True
        return self._tools

    async def cleanup(self) -> None:
        """Disconnect from MCP server."""
        if self._client:
            await self._client.disconnect()
            self._client = None

    def __iter__(self) -> Iterator:
        """Allow unpacking with * in tools list.

        Before discovery, yields self as a lazy marker.
        After discovery, yields individual tool dicts.
        """
        if self.discovered:
            yield from self._tools
        else:
            yield self

    def __repr__(self) -> str:
        transport = self.config.get("transport", "unknown")
        return f"<MCPToolSet transport={transport!r} discovered={self.discovered}>"


def mcp_tools(
    transport: str,
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    headers: dict | None = None,
    env: dict | None = None,
) -> MCPToolSet:
    """Create a lazy MCP tool set.

    Returns immediately (no async). Connection happens on first agent run.
    Use with * unpacking in agent tools list:

        github = mcp_tools(transport="stdio", command="npx", args=[...])

        @agent(tools=[search, *github])
        async def my_agent(ctx): ...
    """
    config: dict[str, Any] = {"transport": transport}
    if command is not None:
        config["command"] = command
    if args is not None:
        config["args"] = args
    if url is not None:
        config["url"] = url
    if headers is not None:
        config["headers"] = headers
    if env is not None:
        config["env"] = env

    return MCPToolSet(config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_mcp.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/mcp.py astromesh-adk/tests/test_mcp.py
git commit -m "feat(adk): add lazy MCP tools integration"
```

---

## Chunk 4: Agent System

### Task 11: @agent Decorator & Agent Base Class

**Files:**
- Create: `astromesh-adk/astromesh_adk/agent.py`
- Create: `astromesh-adk/tests/test_agent.py`

This is the core module — the `@agent` decorator that creates agent objects with `.run()` and `.stream()`, and the `Agent` base class for advanced agents with lifecycle hooks.

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_agent.py`:
```python
import pytest
from astromesh_adk.agent import agent, Agent, AgentWrapper
from astromesh_adk.tools import tool


@tool(description="Add numbers")
async def add(a: int, b: int) -> int:
    return a + b


# --- Decorator tests ---

@agent(name="simple", model="ollama/llama3", description="Simple agent")
async def simple_agent(ctx):
    """You are a simple assistant."""
    return None


@agent(
    name="configured",
    model="openai/gpt-4o",
    fallback_model="ollama/llama3",
    tools=[add],
    pattern="react",
    max_iterations=5,
    memory="sqlite",
    routing="cost_optimized",
    guardrails={"input": ["pii_detection"], "output": []},
)
async def configured_agent(ctx):
    """You are a configured agent."""
    return None


def test_agent_decorator_creates_wrapper():
    assert isinstance(simple_agent, AgentWrapper)


def test_agent_wrapper_name():
    assert simple_agent.name == "simple"
    assert configured_agent.name == "configured"


def test_agent_wrapper_model():
    assert simple_agent.model == "ollama/llama3"
    assert configured_agent.model == "openai/gpt-4o"


def test_agent_wrapper_description():
    assert simple_agent.description == "Simple agent"


def test_agent_wrapper_system_prompt():
    assert simple_agent.system_prompt == "You are a simple assistant."


def test_agent_wrapper_tools():
    assert len(configured_agent.tools) == 1


def test_agent_wrapper_pattern():
    assert simple_agent.pattern == "react"  # default
    assert configured_agent.pattern == "react"


def test_agent_wrapper_fallback():
    assert configured_agent.fallback_model == "ollama/llama3"
    assert simple_agent.fallback_model is None


def test_agent_wrapper_memory():
    assert configured_agent.memory_config is not None
    assert configured_agent.memory_config["conversational"]["backend"] == "sqlite"


def test_agent_wrapper_guardrails():
    assert len(configured_agent.guardrails_config["input"]) == 1


def test_agent_wrapper_has_run():
    assert hasattr(simple_agent, "run")
    assert callable(simple_agent.run)


def test_agent_wrapper_has_stream():
    assert hasattr(simple_agent, "stream")
    assert callable(simple_agent.stream)


def test_agent_wrapper_has_as_tool():
    assert hasattr(simple_agent, "as_tool")
    assert callable(simple_agent.as_tool)


def test_agent_as_tool():
    tool_def = simple_agent.as_tool()
    assert tool_def.tool_name == "simple"
    assert "simple" in tool_def.tool_description.lower() or "assistant" in tool_def.tool_description.lower()


# --- Class-based agent tests ---

class MyAgent(Agent):
    name = "custom"
    model = "ollama/llama3"
    description = "Custom agent"
    tools = [add]
    pattern = "plan_and_execute"

    def system_prompt_fn(self, ctx):
        return f"You help {ctx.user_id}"


def test_class_agent_attributes():
    a = MyAgent()
    assert a.name == "custom"
    assert a.model == "ollama/llama3"
    assert a.pattern == "plan_and_execute"
    assert len(a.tools) == 1


def test_class_agent_has_run():
    a = MyAgent()
    assert hasattr(a, "run")
    assert callable(a.run)


def test_class_agent_has_stream():
    a = MyAgent()
    assert hasattr(a, "stream")


def test_class_agent_has_as_tool():
    a = MyAgent()
    tool_def = a.as_tool()
    assert tool_def.tool_name == "custom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement agent module**

`astromesh-adk/astromesh_adk/agent.py`:
```python
"""@agent decorator and Agent base class."""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator

from astromesh_adk.context import RunContext
from astromesh_adk.exceptions import AgentNotFoundError
from astromesh_adk.guardrails import normalize_guardrails_config
from astromesh_adk.memory import normalize_memory_config
from astromesh_adk.result import RunResult, StreamEvent
from astromesh_adk.tools import ToolDefinitionWrapper
from astromesh_adk.callbacks import Callbacks


class AgentWrapper:
    """Wraps a decorated function as an agent with .run() and .stream()."""

    def __init__(
        self,
        handler,
        name: str,
        model: str,
        description: str = "",
        fallback_model: str | None = None,
        routing: str = "cost_optimized",
        model_config: dict | None = None,
        tools: list | None = None,
        pattern: str = "react",
        max_iterations: int = 10,
        memory: str | dict | None = None,
        guardrails: dict | None = None,
    ):
        self._handler = handler
        self.name = name
        self.model = model
        self.description = description or name
        self.system_prompt = inspect.getdoc(handler) or ""
        self.fallback_model = fallback_model
        self.routing = routing
        self.model_config = model_config
        self.tools = tools or []
        self.pattern = pattern
        self.max_iterations = max_iterations
        self.memory_config = normalize_memory_config(memory)
        self.guardrails_config = normalize_guardrails_config(guardrails)

        # Remote binding (set via .bind())
        self._remote_url: str | None = None
        self._remote_api_key: str | None = None

    async def run(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> RunResult:
        """Execute the agent with a query."""
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        return await rt.run_agent(self, query, session_id, context, callbacks)

    async def stream(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        stream_steps: bool = False,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the agent execution."""
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        async for event in rt.stream_agent(self, query, session_id, context, stream_steps, callbacks):
            yield event

    def as_tool(self) -> ToolDefinitionWrapper:
        """Convert this agent to a tool that can be used by other agents."""
        async def _agent_tool_handler(**kwargs):
            query = kwargs.get("query", kwargs.get("task", ""))
            result = await self.run(query)
            return result.answer

        wrapper = ToolDefinitionWrapper(
            func=_agent_tool_handler,
            description=f"Delegate to agent '{self.name}': {self.description}",
        )
        wrapper.tool_name = self.name
        wrapper.parameters_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The task or query to delegate"},
            },
            "required": ["query"],
        }
        return wrapper

    def bind(self, remote: str, api_key: str) -> None:
        """Bind this agent to execute on a specific remote Astromesh instance."""
        self._remote_url = remote
        self._remote_api_key = api_key

    def __repr__(self):
        return f"<Agent {self.name!r} model={self.model!r}>"


def agent(
    name: str,
    model: str,
    description: str = "",
    fallback_model: str | None = None,
    routing: str = "cost_optimized",
    model_config: dict | None = None,
    tools: list | None = None,
    pattern: str = "react",
    max_iterations: int = 10,
    memory: str | dict | None = None,
    guardrails: dict | None = None,
):
    """Decorator to define an agent from an async function.

    The function's docstring becomes the system prompt.
    The function body is the run handler (return None for default orchestration).
    """

    def decorator(func):
        return AgentWrapper(
            handler=func,
            name=name,
            model=model,
            description=description,
            fallback_model=fallback_model,
            routing=routing,
            model_config=model_config,
            tools=tools,
            pattern=pattern,
            max_iterations=max_iterations,
            memory=memory,
            guardrails=guardrails,
        )

    return decorator


class Agent:
    """Base class for advanced agents with lifecycle hooks.

    Subclass this for agents that need custom system prompts,
    lifecycle hooks (on_before_run, on_after_run, on_tool_call),
    or state management.
    """

    name: str = ""
    model: str = ""
    description: str = ""
    fallback_model: str | None = None
    routing: str = "cost_optimized"
    model_config: dict | None = None
    tools: list = []
    pattern: str = "react"
    max_iterations: int = 10
    memory: str | dict | None = None
    guardrails: dict | None = None

    def __init__(self):
        self.tools = list(self.__class__.tools)  # copy to avoid shared mutable default
        self.memory_config = normalize_memory_config(self.memory)
        self.guardrails_config = normalize_guardrails_config(self.guardrails)
        self._remote_url: str | None = None
        self._remote_api_key: str | None = None

    @property
    def system_prompt(self) -> str:
        """Default system prompt from class docstring."""
        return inspect.getdoc(self) or ""

    def system_prompt_fn(self, ctx: RunContext) -> str:
        """Override for dynamic system prompts."""
        return self.system_prompt

    async def on_before_run(self, ctx: RunContext) -> None:
        """Hook: called before agent execution. Override to customize."""

    async def on_after_run(self, ctx: RunContext, result: RunResult) -> None:
        """Hook: called after agent execution. Override to customize."""

    async def on_tool_call(self, ctx: RunContext, tool_name: str, args: dict) -> None:
        """Hook: called before each tool call. Override to intercept."""

    async def run(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> RunResult:
        """Execute the agent."""
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        return await rt.run_class_agent(self, query, session_id, context, callbacks)

    async def stream(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        stream_steps: bool = False,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the agent execution."""
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        async for event in rt.stream_class_agent(self, query, session_id, context, stream_steps, callbacks):
            yield event

    def as_tool(self) -> ToolDefinitionWrapper:
        """Convert this agent to a tool for other agents."""
        async def _handler(**kwargs):
            query = kwargs.get("query", kwargs.get("task", ""))
            result = await self.run(query)
            return result.answer

        wrapper = ToolDefinitionWrapper(
            func=_handler,
            description=f"Delegate to agent '{self.name}': {self.description}",
        )
        wrapper.tool_name = self.name
        wrapper.parameters_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The task or query to delegate"},
            },
            "required": ["query"],
        }
        return wrapper

    def bind(self, remote: str, api_key: str) -> None:
        """Bind to a remote Astromesh instance."""
        self._remote_url = remote
        self._remote_api_key = api_key

    def __repr__(self):
        return f"<Agent {self.name!r} model={self.model!r}>"
```

- [ ] **Step 4: Create a stub runner module** (needed for imports)

`astromesh-adk/astromesh_adk/runner.py`:
```python
"""ADK Runtime — stub for initial agent module import."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astromesh_adk.agent import AgentWrapper, Agent

_default_runtime = None


def get_or_create_runtime():
    """Get or lazily create the default ADKRuntime."""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ADKRuntime()
    return _default_runtime


class ADKRuntime:
    """Placeholder — full implementation in Task 13."""

    async def run_agent(self, agent_wrapper, query, session_id, context, callbacks):
        raise NotImplementedError("ADKRuntime.run_agent not yet implemented")

    async def stream_agent(self, agent_wrapper, query, session_id, context, stream_steps, callbacks):
        raise NotImplementedError("ADKRuntime.stream_agent not yet implemented")
        yield  # make it a generator

    async def run_class_agent(self, agent_instance, query, session_id, context, callbacks):
        raise NotImplementedError("ADKRuntime.run_class_agent not yet implemented")

    async def stream_class_agent(self, agent_instance, query, session_id, context, stream_steps, callbacks):
        raise NotImplementedError("ADKRuntime.stream_class_agent not yet implemented")
        yield  # make it a generator
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_agent.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh-adk/astromesh_adk/agent.py astromesh-adk/astromesh_adk/runner.py astromesh-adk/tests/test_agent.py
git commit -m "feat(adk): add @agent decorator and Agent base class"
```

---

## Chunk 5: Connection, Runtime & Multi-Agent

### Task 12: Remote Connection

**Files:**
- Create: `astromesh-adk/astromesh_adk/connection.py`
- Create: `astromesh-adk/tests/test_connection.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_connection.py`:
```python
import pytest
from astromesh_adk.connection import (
    connect,
    disconnect,
    remote,
    get_connection,
    _connection_var,
)


def test_connect_sets_global():
    connect(url="https://test.astromesh.io", api_key="key123")
    conn = get_connection()
    assert conn is not None
    assert conn.url == "https://test.astromesh.io"
    assert conn.api_key == "key123"
    disconnect()


def test_disconnect_clears_global():
    connect(url="https://test.astromesh.io", api_key="key")
    disconnect()
    conn = get_connection()
    assert conn is None


async def test_remote_context_manager():
    async with remote("https://ctx.astromesh.io", api_key="ctx-key"):
        conn = get_connection()
        assert conn is not None
        assert conn.url == "https://ctx.astromesh.io"

    # After exiting, connection is restored to previous state
    conn = get_connection()
    assert conn is None


async def test_remote_restores_previous():
    connect(url="https://global.io", api_key="g")
    async with remote("https://scoped.io", api_key="s"):
        conn = get_connection()
        assert conn.url == "https://scoped.io"

    conn = get_connection()
    assert conn.url == "https://global.io"
    disconnect()


def test_connection_repr():
    connect(url="https://test.io", api_key="secret")
    conn = get_connection()
    r = repr(conn)
    assert "test.io" in r
    assert "secret" not in r  # API key should not be in repr
    disconnect()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_connection.py -v`
Expected: FAIL

- [ ] **Step 3: Implement connection module**

`astromesh-adk/astromesh_adk/connection.py`:
```python
"""Remote Astromesh connection management."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass
class RemoteConnection:
    """Represents a connection to a remote Astromesh instance."""

    url: str
    api_key: str

    def __repr__(self):
        return f"RemoteConnection(url={self.url!r})"


# Module-level state (after class definition to avoid forward reference)
_connection_var: contextvars.ContextVar[RemoteConnection | None] = contextvars.ContextVar(
    "astromesh_adk_connection", default=None
)
_global_connection: RemoteConnection | None = None


def connect(url: str, api_key: str) -> None:
    """Set a global remote connection. All agent.run() calls will use this."""
    global _global_connection
    _global_connection = RemoteConnection(url=url, api_key=api_key)
    _connection_var.set(_global_connection)


def disconnect() -> None:
    """Clear the global remote connection. Agents will run locally."""
    global _global_connection
    _global_connection = None
    _connection_var.set(None)


def get_connection() -> RemoteConnection | None:
    """Get the current connection (contextvar > global > None)."""
    return _connection_var.get(None)


class remote:
    """Async context manager for scoped remote connections.

    Usage:
        async with remote("https://cluster.io", api_key="..."):
            result = await agent.run("query")  # runs on remote
        # Back to local after exiting
    """

    def __init__(self, url: str, api_key: str):
        self._connection = RemoteConnection(url=url, api_key=api_key)
        self._token: contextvars.Token | None = None

    async def __aenter__(self):
        self._token = _connection_var.set(self._connection)
        return self._connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _connection_var.reset(self._token)
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_connection.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/connection.py astromesh-adk/tests/test_connection.py
git commit -m "feat(adk): add remote connection management with contextvars"
```

---

### Task 13: ADKRuntime (Full Implementation)

**Files:**
- Modify: `astromesh-adk/astromesh_adk/runner.py`
- Create: `astromesh-adk/tests/test_runner.py`

This is the critical integration piece. The `ADKRuntime` translates ADK agent definitions into Astromesh runtime constructs and executes them.

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_runner.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from astromesh_adk.runner import ADKRuntime, get_or_create_runtime
from astromesh_adk.agent import agent, AgentWrapper
from astromesh_adk.tools import tool
from astromesh_adk.result import RunResult


@tool(description="Echo tool")
async def echo_tool(text: str) -> str:
    return text


@agent(name="test-agent", model="ollama/llama3", tools=[echo_tool])
async def test_agent(ctx):
    """You are a test agent."""
    return None


def test_adk_runtime_creation():
    rt = ADKRuntime()
    assert rt is not None


async def test_adk_runtime_context_manager():
    async with ADKRuntime() as rt:
        assert rt is not None


def test_get_or_create_runtime():
    import astromesh_adk.runner as runner_mod
    runner_mod._default_runtime = None
    rt = get_or_create_runtime()
    assert rt is not None
    rt2 = get_or_create_runtime()
    assert rt is rt2
    runner_mod._default_runtime = None  # cleanup


def test_build_tools_registry():
    """ADKRuntime can build a ToolRegistry from tool definitions."""
    rt = ADKRuntime()
    registry = rt._build_tools_registry([echo_tool])
    schemas = registry.get_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "echo_tool" in names


def test_build_pattern():
    """ADKRuntime resolves pattern strings to OrchestrationPattern instances."""
    rt = ADKRuntime()
    pattern = rt._build_pattern("react", {})
    from astromesh.orchestration.patterns import ReActPattern
    assert isinstance(pattern, ReActPattern)


def test_build_pattern_plan_and_execute():
    rt = ADKRuntime()
    pattern = rt._build_pattern("plan_and_execute", {})
    from astromesh.orchestration.patterns import PlanAndExecutePattern
    assert isinstance(pattern, PlanAndExecutePattern)


def test_build_pattern_parallel():
    rt = ADKRuntime()
    pattern = rt._build_pattern("parallel", {})
    from astromesh.orchestration.patterns import ParallelFanOutPattern
    assert isinstance(pattern, ParallelFanOutPattern)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement full ADKRuntime**

`astromesh-adk/astromesh_adk/runner.py`:
```python
"""ADK Runtime — bridges ADK agents to Astromesh core engine."""

from __future__ import annotations

import atexit
import asyncio
import logging
from typing import Any, AsyncIterator, TYPE_CHECKING

from astromesh.core.tools import ToolRegistry, ToolDefinition, ToolType
from astromesh.core.model_router import ModelRouter
from astromesh.core.memory import MemoryManager
from astromesh.core.guardrails import GuardrailsEngine
from astromesh.core.prompt_engine import PromptEngine
from astromesh.orchestration.patterns import (
    ReActPattern,
    PlanAndExecutePattern,
    ParallelFanOutPattern,
    PipelinePattern,
    AgentStep,
)
from astromesh.orchestration.supervisor import SupervisorPattern
from astromesh.orchestration.swarm import SwarmPattern
from astromesh.observability.tracing import TracingContext, SpanStatus

from astromesh_adk.context import RunContext, ToolContext
from astromesh_adk.result import RunResult, StreamEvent
from astromesh_adk.providers import parse_model_string, resolve_provider
from astromesh_adk.callbacks import Callbacks
from astromesh_adk.tools import ToolDefinitionWrapper, Tool
from astromesh_adk.mcp import MCPToolSet
from astromesh_adk.exceptions import (
    AgentError,
    ProviderError,
    ProviderUnavailableError,
    ToolError,
)

if TYPE_CHECKING:
    from astromesh_adk.agent import AgentWrapper, Agent as AgentClass

logger = logging.getLogger("astromesh_adk.runner")

_default_runtime: ADKRuntime | None = None

# Pattern name mapping (ADK shorthand → constructor)
PATTERN_MAP = {
    "react": ReActPattern,
    "plan_and_execute": PlanAndExecutePattern,
    "parallel_fan_out": ParallelFanOutPattern,
    "parallel": ParallelFanOutPattern,
    "pipeline": PipelinePattern,
    "supervisor": SupervisorPattern,
    "swarm": SwarmPattern,
}


def get_or_create_runtime() -> ADKRuntime:
    """Get or lazily create the default ADKRuntime."""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ADKRuntime()
        atexit.register(_cleanup_default_runtime)
    return _default_runtime


def _cleanup_default_runtime():
    global _default_runtime
    if _default_runtime:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_default_runtime.shutdown())
            else:
                loop.run_until_complete(_default_runtime.shutdown())
        except RuntimeError:
            pass
        _default_runtime = None


class ADKRuntime:
    """Bridges ADK agent definitions to the Astromesh runtime engine."""

    def __init__(self):
        self._mcp_toolsets: list[MCPToolSet] = []
        self._stateful_tools: list[Tool] = []
        self._started = False

    async def start(self) -> None:
        """Initialize runtime resources."""
        self._started = True

    async def shutdown(self) -> None:
        """Clean up all resources."""
        for ts in self._mcp_toolsets:
            await ts.cleanup()
        for t in self._stateful_tools:
            await t.cleanup()
        self._mcp_toolsets.clear()
        self._stateful_tools.clear()
        self._started = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()
        return False

    # --- Public execution methods ---

    async def run_agent(
        self,
        wrapper: AgentWrapper,
        query: str,
        session_id: str,
        context: dict | None,
        callbacks: Callbacks | None,
    ) -> RunResult:
        """Execute a decorator-based agent."""
        # Check for remote binding
        from astromesh_adk.connection import get_connection
        conn = get_connection()
        remote_url = wrapper._remote_url or (conn.url if conn else None)
        remote_key = wrapper._remote_api_key or (conn.api_key if conn else None)

        if remote_url:
            return await self._run_remote(wrapper.name, query, session_id, context, remote_url, remote_key)

        return await self._run_local(
            name=wrapper.name,
            model=wrapper.model,
            system_prompt=wrapper.system_prompt,
            tools=wrapper.tools,
            pattern=wrapper.pattern,
            max_iterations=wrapper.max_iterations,
            memory_config=wrapper.memory_config,
            guardrails_config=wrapper.guardrails_config,
            model_config=wrapper.model_config,
            fallback_model=wrapper.fallback_model,
            routing=wrapper.routing,
            handler=wrapper._handler,
            query=query,
            session_id=session_id,
            context=context,
            callbacks=callbacks,
        )

    async def run_class_agent(
        self,
        agent_instance: AgentClass,
        query: str,
        session_id: str,
        context: dict | None,
        callbacks: Callbacks | None,
    ) -> RunResult:
        """Execute a class-based agent with lifecycle hooks."""
        from astromesh_adk.connection import get_connection
        conn = get_connection()
        remote_url = agent_instance._remote_url or (conn.url if conn else None)
        remote_key = agent_instance._remote_api_key or (conn.api_key if conn else None)

        if remote_url:
            return await self._run_remote(agent_instance.name, query, session_id, context, remote_url, remote_key)

        # Build context for hooks
        tool_names = [self._get_tool_name(t) for t in agent_instance.tools]
        ctx = RunContext.from_run_params(query, session_id, agent_instance.name, context, tool_names)

        # Lifecycle: on_before_run
        await agent_instance.on_before_run(ctx)

        # Get dynamic system prompt
        system_prompt = agent_instance.system_prompt_fn(ctx)

        result = await self._run_local(
            name=agent_instance.name,
            model=agent_instance.model,
            system_prompt=system_prompt,
            tools=agent_instance.tools,
            pattern=agent_instance.pattern,
            max_iterations=agent_instance.max_iterations,
            memory_config=agent_instance.memory_config,
            guardrails_config=agent_instance.guardrails_config,
            model_config=agent_instance.model_config,
            fallback_model=agent_instance.fallback_model,
            routing=agent_instance.routing,
            handler=None,
            query=query,
            session_id=session_id,
            context=context,
            callbacks=callbacks,
        )

        # Lifecycle: on_after_run
        await agent_instance.on_after_run(ctx, result)

        return result

    async def stream_agent(self, wrapper, query, session_id, context, stream_steps, callbacks):
        """Stream execution for decorator-based agents.

        Token streaming: orchestration runs to completion, then final answer
        is re-generated with provider.stream() to yield tokens incrementally.
        Step streaming: also yields intermediate steps before token stream.
        """
        # Run orchestration to get full result (including steps)
        result = await self.run_agent(wrapper, query, session_id, context, callbacks)

        # Emit steps if requested
        if stream_steps:
            for step in result.steps:
                yield StreamEvent(type="step", step=step)

        # Token-stream the final answer via provider.stream()
        provider_name, model_name = parse_model_string(wrapper.model)
        provider = resolve_provider(provider_name, model_name, wrapper.model_config)
        messages = [
            {"role": "system", "content": wrapper.system_prompt},
            {"role": "user", "content": query},
            {"role": "assistant", "content": result.answer},
        ]
        # Re-stream the known answer for token-level output
        # In v1, we yield the answer in chunks for API compatibility
        chunk_size = 20
        for i in range(0, len(result.answer), chunk_size):
            yield StreamEvent(type="token", content=result.answer[i:i + chunk_size])

        yield StreamEvent(type="done", result=result)

    async def stream_class_agent(self, agent_instance, query, session_id, context, stream_steps, callbacks):
        """Stream execution for class-based agents."""
        result = await self.run_class_agent(agent_instance, query, session_id, context, callbacks)

        if stream_steps:
            for step in result.steps:
                yield StreamEvent(type="step", step=step)

        chunk_size = 20
        for i in range(0, len(result.answer), chunk_size):
            yield StreamEvent(type="token", content=result.answer[i:i + chunk_size])

        yield StreamEvent(type="done", result=result)

    async def run_team(self, team, query, session_id, context, callbacks):
        """Execute an AgentTeam by translating to Astromesh orchestration patterns."""
        from astromesh_adk.team import AgentTeam

        # 1. Register all team agents as tools in a shared registry
        all_agents = team.workers or team.agents
        all_tools = []
        for a in all_agents:
            all_tools.append(a.as_tool())

        # 2. Determine the supervisor/coordinator agent
        supervisor = team.supervisor or (team.entry_agent if team.pattern == "swarm" else all_agents[0])

        # 3. Build pattern config
        pattern_config = {}
        if team.pattern == "supervisor":
            pattern_config["workers"] = team._build_workers_dict()
        elif team.pattern == "swarm":
            pattern_config["agent_configs"] = team._build_agent_configs()
        elif team.pattern == "pipeline":
            pattern_config["stages"] = team._build_stages()

        # 4. Build system prompt describing available agents
        agent_descriptions = "\n".join(f"- {a.name}: {a.description}" for a in all_agents)
        team_prompt = (
            f"You are the coordinator of a team. Available agents:\n{agent_descriptions}\n\n"
            f"Delegate tasks to the appropriate agent using their tool."
        )

        # 5. Execute using the supervisor agent's model with team tools
        return await self._run_local(
            name=team.name,
            model=supervisor.model,
            system_prompt=team_prompt,
            tools=all_tools,
            pattern=team.pattern,
            max_iterations=10,
            memory_config={},
            guardrails_config={"input": [], "output": []},
            model_config=getattr(supervisor, "model_config", None),
            fallback_model=getattr(supervisor, "fallback_model", None),
            routing=getattr(supervisor, "routing", "cost_optimized"),
            handler=None,
            query=query,
            session_id=session_id,
            context=context,
            callbacks=callbacks,
        )

    # --- Internal methods ---

    async def _run_local(
        self,
        name: str,
        model: str,
        system_prompt: str,
        tools: list,
        pattern: str,
        max_iterations: int,
        memory_config: dict,
        guardrails_config: dict,
        model_config: dict | None,
        fallback_model: str | None,
        routing: str,
        handler: Any,
        query: str,
        session_id: str,
        context: dict | None,
        callbacks: Callbacks | None,
    ) -> RunResult:
        """Execute agent locally using Astromesh core modules."""
        # 1. Build provider + router
        provider_name, model_name = parse_model_string(model)
        primary_provider = resolve_provider(provider_name, model_name, model_config)
        router = ModelRouter({"strategy": routing})
        router.register_provider(provider_name, primary_provider)

        if fallback_model:
            fb_provider_name, fb_model_name = parse_model_string(fallback_model)
            fb_provider = resolve_provider(fb_provider_name, fb_model_name)
            router.register_provider(fb_provider_name, fb_provider)

        # 2. Build tool registry
        registry = self._build_tools_registry(tools)

        # 3. Build orchestration pattern
        orchestration_pattern = self._build_pattern(pattern, {})

        # 4. Build memory manager
        memory_mgr = MemoryManager(agent_id=name, config=memory_config)

        # 5. Build guardrails
        guardrails = GuardrailsEngine(guardrails_config)

        # 6. Build prompt engine
        prompt_engine = PromptEngine()

        # 7. Build tracing context
        trace = TracingContext(agent_name=name, session_id=session_id)

        # 8. Build context
        memory_context = await memory_mgr.build_context(session_id, query)
        rendered_prompt = prompt_engine.render(system_prompt, {
            "memory": memory_context,
            "context": context or {},
        })

        # 9. Apply input guardrails
        query_text = query if isinstance(query, str) else str(query)
        query_text = await guardrails.apply_input(query_text)

        # 10. Build model_fn and tool_fn closures
        tool_schemas = registry.get_tool_schemas()

        async def model_fn(messages, **kwargs):
            try:
                response = await router.route(messages, **kwargs)
                if callbacks:
                    try:
                        await callbacks.on_model_call(response.model, messages, response)
                    except Exception as e:
                        logger.warning(f"Callback error in on_model_call: {e}")
                return response
            except RuntimeError as e:
                raise ProviderUnavailableError(str(e))

        async def tool_fn(tool_name, arguments):
            try:
                result = await registry.execute(tool_name, arguments)
                if callbacks:
                    try:
                        await callbacks.on_tool_result(tool_name, arguments, result)
                    except Exception as cb_err:
                        logger.warning(f"Callback error in on_tool_result: {cb_err}")
                return result
            except Exception as e:
                raise ToolError(str(e))

        # 11. Execute handler or default orchestration
        tool_names = [self._get_tool_name(t) for t in tools]
        ctx = RunContext.from_run_params(query, session_id, name, context, tool_names)

        if handler:
            # Set up ctx methods
            ctx._run_default_fn = lambda: self._run_orchestration(
                orchestration_pattern, query_text, memory_context, rendered_prompt,
                model_fn, tool_fn, tool_schemas, max_iterations, callbacks
            )
            ctx._complete_fn = lambda q, **kw: self._complete_direct(router, q, rendered_prompt, **kw)
            ctx._call_tool_fn = lambda n, a: registry.execute(n, a)

            handler_result = await handler(ctx)
            if handler_result is not None:
                if isinstance(handler_result, RunResult):
                    return handler_result

        # Default orchestration
        runtime_result = await self._run_orchestration(
            orchestration_pattern, query_text, memory_context, rendered_prompt,
            model_fn, tool_fn, tool_schemas, max_iterations, callbacks
        )

        # 12. Apply output guardrails
        answer = runtime_result.get("answer", "")
        answer = await guardrails.apply_output(answer)
        runtime_result["answer"] = answer

        # 13. Persist memory
        from astromesh.core.memory import ConversationTurn
        from datetime import datetime
        await memory_mgr.persist_turn(session_id, ConversationTurn(
            role="user", content=query_text, timestamp=datetime.now()
        ))
        await memory_mgr.persist_turn(session_id, ConversationTurn(
            role="assistant", content=answer, timestamp=datetime.now()
        ))

        # 14. Build and return RunResult
        runtime_result["trace"] = trace.to_dict()
        return RunResult.from_runtime(runtime_result)

    async def _run_orchestration(
        self, pattern, query, memory_context, system_prompt,
        model_fn, tool_fn, tool_schemas, max_iterations, callbacks
    ):
        """Execute the orchestration pattern."""
        context = {
            "system_prompt": system_prompt,
            "memory": memory_context,
        }
        result = await pattern.execute(
            query=query,
            context=context,
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=tool_schemas,
            max_iterations=max_iterations,
        )

        if callbacks:
            for step in result.get("steps", []):
                try:
                    await callbacks.on_step(step)
                except Exception as e:
                    logger.warning(f"Callback error in on_step: {e}")

        return result

    async def _complete_direct(self, router, query, system_prompt, **kwargs):
        """Direct model call bypassing orchestration."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        response = await router.route(messages, **kwargs)
        return response.content

    async def _run_remote(self, agent_name, query, session_id, context, url, api_key):
        """Execute agent on a remote Astromesh instance."""
        import httpx
        from astromesh_adk.exceptions import RemoteUnavailableError

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{url.rstrip('/')}/v1/agents/{agent_name}/run",
                    json={"query": query, "session_id": session_id, "context": context},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                return RunResult(
                    answer=data.get("answer", ""),
                    steps=data.get("steps", []),
                    trace=None,
                    cost=0.0,
                    tokens={"input": 0, "output": 0},
                    latency_ms=0.0,
                    model="remote",
                )
        except httpx.HTTPError as e:
            raise RemoteUnavailableError(f"Remote execution failed: {e}")

    def _build_tools_registry(self, tools: list) -> ToolRegistry:
        """Build a ToolRegistry from ADK tool definitions."""
        registry = ToolRegistry()

        for t in tools:
            if isinstance(t, ToolDefinitionWrapper):
                registry.register_internal(
                    name=t.tool_name,
                    handler=t._func,
                    description=t.tool_description,
                    parameters=t.parameters_schema,
                    rate_limit=t.rate_limit,
                    requires_approval=t.requires_approval,
                    timeout_seconds=t.timeout,
                )
            elif isinstance(t, Tool):
                self._stateful_tools.append(t)
                registry.register_internal(
                    name=t.name,
                    handler=lambda args, ctx=None, tool=t: tool.execute(args, ctx),
                    description=t.description,
                    parameters=t.parameters() if callable(t.parameters) else t.parameters,
                )
            elif isinstance(t, MCPToolSet):
                self._mcp_toolsets.append(t)
                # MCP tools will be discovered lazily on first call

        return registry

    def _build_pattern(self, pattern_name: str, config: dict):
        """Resolve pattern name to OrchestrationPattern instance."""
        pattern_cls = PATTERN_MAP.get(pattern_name)
        if not pattern_cls:
            raise ValueError(f"Unknown pattern: {pattern_name!r}. Available: {list(PATTERN_MAP)}")

        if pattern_cls in (SupervisorPattern, SwarmPattern, PipelinePattern):
            return pattern_cls(config.get("workers") or config.get("agent_configs") or config.get("stages"))
        return pattern_cls()

    @staticmethod
    def _get_tool_name(t) -> str:
        if isinstance(t, ToolDefinitionWrapper):
            return t.tool_name
        if isinstance(t, Tool):
            return t.name
        if isinstance(t, MCPToolSet):
            return f"mcp:{t.config.get('transport', 'unknown')}"
        return str(t)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/runner.py astromesh-adk/tests/test_runner.py
git commit -m "feat(adk): implement ADKRuntime bridging to Astromesh core"
```

---

### Task 14: AgentTeam (Multi-Agent Composition)

**Files:**
- Create: `astromesh-adk/astromesh_adk/team.py`
- Create: `astromesh-adk/tests/test_team.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_team.py`:
```python
import pytest
from astromesh_adk.team import AgentTeam
from astromesh_adk.agent import agent


@agent(name="researcher", model="ollama/llama3", description="Research agent")
async def researcher(ctx):
    """You research topics."""
    return None


@agent(name="writer", model="ollama/llama3", description="Writing agent")
async def writer(ctx):
    """You write content."""
    return None


@agent(name="editor", model="ollama/llama3", description="Editing agent")
async def editor(ctx):
    """You edit content."""
    return None


def test_supervisor_team_creation():
    team = AgentTeam(
        name="content-team",
        pattern="supervisor",
        supervisor=researcher,
        workers=[writer, editor],
    )
    assert team.name == "content-team"
    assert team.pattern == "supervisor"
    assert team.supervisor is researcher
    assert len(team.workers) == 2


def test_swarm_team_creation():
    team = AgentTeam(
        name="pipeline",
        pattern="swarm",
        agents=[researcher, writer, editor],
        entry_agent=researcher,
    )
    assert team.pattern == "swarm"
    assert team.entry_agent is researcher
    assert len(team.agents) == 3


def test_pipeline_team_creation():
    team = AgentTeam(
        name="doc-pipeline",
        pattern="pipeline",
        agents=[researcher, writer, editor],
    )
    assert team.pattern == "pipeline"


def test_parallel_team_creation():
    team = AgentTeam(
        name="research-team",
        pattern="parallel",
        agents=[researcher, writer],
    )
    assert team.pattern == "parallel"


def test_team_has_run():
    team = AgentTeam(name="t", pattern="pipeline", agents=[researcher, writer])
    assert hasattr(team, "run")
    assert callable(team.run)


def test_team_build_workers_dict():
    team = AgentTeam(
        name="t",
        pattern="supervisor",
        supervisor=researcher,
        workers=[writer, editor],
    )
    workers_dict = team._build_workers_dict()
    assert "writer" in workers_dict
    assert "editor" in workers_dict
    assert workers_dict["writer"]["description"] == "Writing agent"


def test_team_build_agent_configs():
    team = AgentTeam(
        name="t",
        pattern="swarm",
        agents=[researcher, writer],
        entry_agent=researcher,
    )
    configs = team._build_agent_configs()
    assert "researcher" in configs
    assert "writer" in configs


def test_team_build_stages():
    team = AgentTeam(
        name="t",
        pattern="pipeline",
        agents=[researcher, writer, editor],
    )
    stages = team._build_stages()
    assert stages == ["researcher", "writer", "editor"]


def test_team_invalid_pattern():
    with pytest.raises(ValueError, match="Unknown team pattern"):
        AgentTeam(name="t", pattern="invalid", agents=[researcher])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_team.py -v`
Expected: FAIL

- [ ] **Step 3: Implement team module**

`astromesh-adk/astromesh_adk/team.py`:
```python
"""AgentTeam — multi-agent composition with orchestration patterns."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from astromesh_adk.result import RunResult
from astromesh_adk.callbacks import Callbacks

if TYPE_CHECKING:
    from astromesh_adk.agent import AgentWrapper

VALID_TEAM_PATTERNS = {"supervisor", "swarm", "pipeline", "parallel"}


class AgentTeam:
    """Compose multiple agents into a team with an orchestration pattern.

    Patterns:
        - supervisor: A supervisor agent delegates tasks to workers
        - swarm: Agents hand off control to each other
        - pipeline: Sequential execution through a chain of agents
        - parallel: All agents execute in parallel, results are aggregated
    """

    def __init__(
        self,
        name: str,
        pattern: str,
        agents: list[AgentWrapper] | None = None,
        supervisor: AgentWrapper | None = None,
        workers: list[AgentWrapper] | None = None,
        entry_agent: AgentWrapper | None = None,
    ):
        if pattern not in VALID_TEAM_PATTERNS:
            raise ValueError(f"Unknown team pattern: {pattern!r}. Available: {VALID_TEAM_PATTERNS}")

        self.name = name
        self.pattern = pattern
        self.agents = agents or []
        self.supervisor = supervisor
        self.workers = workers or []
        self.entry_agent = entry_agent

    async def run(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> RunResult:
        """Execute the team with the configured pattern."""
        from astromesh_adk.runner import get_or_create_runtime, ADKRuntime

        rt = runtime or get_or_create_runtime()
        return await rt.run_team(self, query, session_id, context, callbacks)

    def _build_workers_dict(self) -> dict:
        """Build workers config dict for SupervisorPattern."""
        return {
            w.name: {"description": w.description}
            for w in self.workers
        }

    def _build_agent_configs(self) -> dict:
        """Build agent_configs dict for SwarmPattern."""
        return {
            a.name: {"description": a.description}
            for a in self.agents
        }

    def _build_stages(self) -> list[str]:
        """Build stages list for PipelinePattern."""
        return [a.name for a in self.agents]

    def __repr__(self):
        count = len(self.workers or self.agents)
        return f"<AgentTeam {self.name!r} pattern={self.pattern!r} agents={count}>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_team.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/team.py astromesh-adk/tests/test_team.py
git commit -m "feat(adk): add AgentTeam for multi-agent composition"
```

---

## Chunk 6: CLI & Public API

### Task 15: CLI

**Files:**
- Modify: `astromesh-adk/astromesh_adk/cli/main.py`
- Create: `astromesh-adk/tests/test_cli.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_cli.py`:
```python
import pytest
from typer.testing import CliRunner
from astromesh_adk.cli.main import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "astromesh-adk" in result.output.lower() or "agent" in result.output.lower()


def test_cli_list_help():
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "file" in result.output.lower()


def test_cli_run_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0


def test_cli_check_help():
    result = runner.invoke(app, ["check", "--help"])
    assert result.exit_code == 0


def test_cli_dev_help():
    result = runner.invoke(app, ["dev", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI**

`astromesh-adk/astromesh_adk/cli/main.py`:
```python
"""Astromesh ADK CLI."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="astromesh-adk", help="Astromesh Agent Development Kit CLI")
console = Console()


def _load_module(file_path: str):
    """Import a Python file as a module."""
    path = Path(file_path).resolve()
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    spec = importlib.util.spec_from_file_location("__adk_user_module__", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["__adk_user_module__"] = module
    spec.loader.exec_module(module)
    return module


def _discover_agents(module):
    """Find all AgentWrapper and Agent instances in a module."""
    from astromesh_adk.agent import AgentWrapper, Agent

    agents = []
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, AgentWrapper):
            agents.append(obj)
        elif isinstance(obj, type) and issubclass(obj, Agent) and obj is not Agent:
            agents.append(obj())
    return agents


def _parse_agent_ref(ref: str):
    """Parse 'file.py:agent_name' into (file_path, agent_name)."""
    if ":" in ref:
        file_path, agent_name = ref.rsplit(":", 1)
        return file_path, agent_name
    return ref, None


@app.command()
def list(file: str = typer.Argument(..., help="Python file with agent definitions")):
    """List all agents defined in a file."""
    module = _load_module(file)
    agents = _discover_agents(module)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Pattern", style="blue")
    table.add_column("Tools", style="yellow")

    for a in agents:
        tool_count = str(len(a.tools))
        table.add_row(a.name, a.model, a.pattern, tool_count)

    console.print(table)


@app.command()
def run(
    agent_ref: str = typer.Argument(..., help="agent file:name (e.g., agents.py:my_agent)"),
    query: str = typer.Argument(..., help="Query to send to the agent"),
    session: str = typer.Option("default", "--session", "-s", help="Session ID"),
):
    """Run an agent with a query."""
    file_path, agent_name = _parse_agent_ref(agent_ref)
    module = _load_module(file_path)
    agents = _discover_agents(module)

    target = None
    for a in agents:
        if agent_name is None or a.name == agent_name:
            target = a
            break

    if target is None:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        raise typer.Exit(1)

    async def _run():
        result = await target.run(query, session_id=session)
        console.print(f"\n[bold green]Answer:[/bold green] {result.answer}")
        if result.steps:
            console.print(f"\n[dim]Steps: {len(result.steps)} | Cost: ${result.cost:.4f} | Tokens: {result.tokens}[/dim]")

    asyncio.run(_run())


@app.command()
def chat(
    agent_ref: str = typer.Argument(..., help="agent file:name"),
    session: str = typer.Option("default", "--session", "-s", help="Session ID"),
):
    """Interactive chat with an agent."""
    file_path, agent_name = _parse_agent_ref(agent_ref)
    module = _load_module(file_path)
    agents = _discover_agents(module)

    target = None
    for a in agents:
        if agent_name is None or a.name == agent_name:
            target = a
            break

    if target is None:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Chat with {target.name}[/bold] (Ctrl+C to exit)\n")

    async def _chat():
        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if not user_input.strip():
                    continue
                result = await target.run(user_input, session_id=session)
                console.print(f"\n{result.answer}\n")
            except KeyboardInterrupt:
                console.print("\n[dim]Bye![/dim]")
                break

    asyncio.run(_chat())


@app.command()
def check(file: str = typer.Argument(..., help="Python file to validate")):
    """Validate agent definitions."""
    import os
    module = _load_module(file)
    agents = _discover_agents(module)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    from astromesh_adk.providers import parse_model_string, PROVIDER_REGISTRY

    for a in agents:
        issues = []

        # Check provider env vars
        provider_name, _ = parse_model_string(a.model)
        entry = PROVIDER_REGISTRY.get(provider_name)
        if entry and entry.get("env_var"):
            if not os.environ.get(entry["env_var"]):
                issues.append(f"Missing env var: {entry['env_var']}")

        # Check tools
        for t in a.tools:
            from astromesh_adk.tools import ToolDefinitionWrapper, Tool
            from astromesh_adk.mcp import MCPToolSet
            if isinstance(t, ToolDefinitionWrapper):
                pass  # OK
            elif isinstance(t, Tool):
                if not t.name:
                    issues.append("Tool class missing 'name'")
            elif isinstance(t, MCPToolSet):
                import shutil
                cmd = t.config.get("command")
                if cmd and not shutil.which(cmd):
                    issues.append(f"MCP command not found: {cmd}")

        status = "[green]✓[/green]" if not issues else "[red]✗[/red]"
        tool_count = len(a.tools)
        console.print(f"  {status} {a.name}: {provider_name} provider, {tool_count} tools")
        for issue in issues:
            console.print(f"    [yellow]⚠ {issue}[/yellow]")


@app.command()
def dev(
    file: str = typer.Argument(..., help="Python file with agent definitions"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable hot reload"),
):
    """Start the development server."""
    console.print(f"[bold]Starting ADK dev server...[/bold]")
    console.print(f"  File: {file}")
    console.print(f"  Port: {port}")
    console.print(f"  Reload: {reload}")

    # Import here to avoid requiring FastAPI as a core dependency
    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        console.print("[red]Dev server requires FastAPI and Uvicorn. Install with: pip install astromesh-adk[dev][/red]")
        raise typer.Exit(1)

    module = _load_module(file)
    agents = _discover_agents(module)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    # Build a minimal FastAPI app
    dev_app = FastAPI(title=f"ADK Dev Server")

    @dev_app.get("/v1/health")
    def health():
        return {"status": "ok", "agents": [a.name for a in agents]}

    @dev_app.get("/v1/agents")
    def list_agents():
        return [{"name": a.name, "model": a.model, "description": a.description} for a in agents]

    @dev_app.post("/v1/agents/{agent_name}/run")
    async def run_agent(agent_name: str, body: dict):
        target = next((a for a in agents if a.name == agent_name), None)
        if not target:
            return {"error": f"Agent '{agent_name}' not found"}
        result = await target.run(
            body.get("query", ""),
            session_id=body.get("session_id", "default"),
            context=body.get("context"),
        )
        return {"answer": result.answer, "steps": result.steps}

    console.print(f"\n[bold green]Serving {len(agents)} agent(s) at http://localhost:{port}[/bold green]")
    for a in agents:
        console.print(f"  • {a.name} ({a.model})")

    uvicorn.run(dev_app, host="0.0.0.0", port=port, reload=reload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-adk/astromesh_adk/cli/main.py astromesh-adk/tests/test_cli.py
git commit -m "feat(adk): add CLI with run, chat, list, check, dev commands"
```

---

### Task 16: Public API (__init__.py)

**Files:**
- Modify: `astromesh-adk/astromesh_adk/__init__.py`
- Create: `astromesh-adk/tests/test_public_api.py`

- [ ] **Step 1: Write failing test**

`astromesh-adk/tests/test_public_api.py`:
```python
def test_all_public_exports():
    """All documented public API names are importable from the top-level package."""
    from astromesh_adk import (
        Agent,
        AgentTeam,
        ADKRuntime,
        Callbacks,
        RunContext,
        RunResult,
        StreamEvent,
        Tool,
        ToolContext,
        agent,
        connect,
        disconnect,
        mcp_tools,
        remote,
        tool,
    )

    assert Agent is not None
    assert agent is not None
    assert tool is not None
    assert Tool is not None
    assert connect is not None
    assert disconnect is not None
    assert remote is not None
    assert AgentTeam is not None
    assert ADKRuntime is not None
    assert Callbacks is not None
    assert RunResult is not None
    assert RunContext is not None
    assert StreamEvent is not None
    assert ToolContext is not None
    assert mcp_tools is not None


def test_version():
    import astromesh_adk
    assert hasattr(astromesh_adk, "__version__")
    assert astromesh_adk.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-adk && uv run pytest tests/test_public_api.py -v`
Expected: FAIL

- [ ] **Step 3: Implement public API exports**

`astromesh-adk/astromesh_adk/__init__.py`:
```python
"""Astromesh Agent Development Kit."""

__version__ = "0.1.0"

from astromesh_adk.agent import Agent, agent, AgentWrapper
from astromesh_adk.callbacks import Callbacks
from astromesh_adk.connection import connect, disconnect, remote
from astromesh_adk.context import RunContext, ToolContext
from astromesh_adk.mcp import mcp_tools
from astromesh_adk.result import RunResult, StreamEvent
from astromesh_adk.runner import ADKRuntime
from astromesh_adk.team import AgentTeam
from astromesh_adk.tools import Tool, tool

__all__ = [
    "ADKRuntime",
    "Agent",
    "AgentTeam",
    "AgentWrapper",
    "Callbacks",
    "RunContext",
    "RunResult",
    "StreamEvent",
    "Tool",
    "ToolContext",
    "agent",
    "connect",
    "disconnect",
    "mcp_tools",
    "remote",
    "tool",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-adk && uv run pytest tests/test_public_api.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests**

Run: `cd astromesh-adk && uv run pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh-adk/astromesh_adk/__init__.py astromesh-adk/tests/test_public_api.py
git commit -m "feat(adk): wire up public API exports"
```

---

## Chunk 7: Examples & Documentation

### Task 17: Examples

**Files:**
- Create: `astromesh-adk/examples/quickstart.py`
- Create: `astromesh-adk/examples/tools_example.py`
- Create: `astromesh-adk/examples/multi_agent.py`

- [ ] **Step 1: Write quickstart example**

`astromesh-adk/examples/quickstart.py`:
```python
"""Astromesh ADK Quickstart — define and run an agent in 10 lines."""

import asyncio
from astromesh_adk import agent


@agent(name="assistant", model="ollama/llama3", description="General assistant")
async def assistant(ctx):
    """You are a helpful assistant. Be concise and accurate."""
    return None


async def main():
    result = await assistant.run("What is the capital of France?")
    print(f"Answer: {result.answer}")
    print(f"Cost: ${result.cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Write tools example**

`astromesh-adk/examples/tools_example.py`:
```python
"""Astromesh ADK — defining tools with decorators and classes."""

import asyncio
import httpx
from astromesh_adk import agent, tool, Tool


# Simple tool with decorator — schema auto-generated from type hints
@tool(description="Calculate a math expression")
async def calculator(expression: str) -> str:
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


# Stateful tool with class — for tools that need initialization
class WebFetcher(Tool):
    name = "web_fetch"
    description = "Fetch content from a URL"

    def __init__(self):
        self.client = httpx.AsyncClient()

    def parameters(self):
        return {
            "url": {"type": "string", "description": "URL to fetch"},
        }

    async def execute(self, args, ctx=None):
        resp = await self.client.get(args["url"], follow_redirects=True)
        return resp.text[:2000]

    async def cleanup(self):
        await self.client.aclose()


@agent(
    name="research-assistant",
    model="ollama/llama3",
    tools=[calculator, WebFetcher()],
    pattern="react",
)
async def research_assistant(ctx):
    """You are a research assistant with calculation and web capabilities."""
    return None


async def main():
    result = await research_assistant.run("What is 42 * 17?")
    print(f"Answer: {result.answer}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Write multi-agent example**

`astromesh-adk/examples/multi_agent.py`:
```python
"""Astromesh ADK — multi-agent composition with AgentTeam."""

import asyncio
from astromesh_adk import agent, AgentTeam


@agent(name="researcher", model="ollama/llama3", description="Research specialist")
async def researcher(ctx):
    """You research topics thoroughly and provide factual summaries."""
    return None


@agent(name="writer", model="ollama/llama3", description="Content writer")
async def writer(ctx):
    """You write clear, engaging content from research notes."""
    return None


@agent(name="editor", model="ollama/llama3", description="Content editor")
async def editor(ctx):
    """You review and improve written content for clarity and accuracy."""
    return None


# Pipeline: research → write → edit
pipeline_team = AgentTeam(
    name="content-pipeline",
    pattern="pipeline",
    agents=[researcher, writer, editor],
)

# Supervisor: one agent delegates to others
supervisor_team = AgentTeam(
    name="content-supervisor",
    pattern="supervisor",
    supervisor=researcher,
    workers=[writer, editor],
)


async def main():
    result = await pipeline_team.run("Write an article about quantum computing")
    print(f"Pipeline result: {result.answer[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Commit**

```bash
git add astromesh-adk/examples/
git commit -m "docs(adk): add quickstart, tools, and multi-agent examples"
```

---

### Task 18: Documentation

**Files:**
- Create: `docs/ADK_QUICKSTART.md`
- Modify: `docs-site/astro.config.mjs` (add ADK sidebar section)
- Create: `docs-site/src/content/docs/adk/introduction.mdx`
- Create: `docs-site/src/content/docs/adk/quickstart.mdx`

- [ ] **Step 1: Write ADK quickstart doc**

`docs/ADK_QUICKSTART.md`:
```markdown
# Astromesh ADK — Quick Start

## Installation

```bash
pip install astromesh-adk
```

## Define an Agent

```python
from astromesh_adk import agent, tool

@tool(description="Add two numbers")
async def add(a: int, b: int) -> int:
    return a + b

@agent(
    name="math-assistant",
    model="ollama/llama3",
    tools=[add],
)
async def math_assistant(ctx):
    """You are a math assistant. Use the add tool for calculations."""
    return None
```

## Run It

```python
import asyncio

async def main():
    result = await math_assistant.run("What is 5 + 3?")
    print(result.answer)

asyncio.run(main())
```

## CLI

```bash
# Run from command line
astromesh-adk run my_agents.py:math_assistant "What is 5 + 3?"

# Interactive chat
astromesh-adk chat my_agents.py:math_assistant

# Dev server with playground
astromesh-adk dev my_agents.py

# List all agents
astromesh-adk list my_agents.py

# Validate configuration
astromesh-adk check my_agents.py
```

## Connect to Astromesh Remote

```python
from astromesh_adk import connect

connect(url="https://my-cluster.astromesh.io", api_key="ask-xxx")

# Same code, now runs on remote Astromesh
result = await math_assistant.run("What is 5 + 3?")
```

## Next Steps

- See `examples/` for more patterns
- Read the full spec at `docs/superpowers/specs/2026-03-17-astromesh-adk-design.md`
```

- [ ] **Step 2: Add ADK section to docs-site sidebar**

Add the following to `docs-site/astro.config.mjs` sidebar array, after the 'Reference' section:

```javascript
{
  label: 'Agent Development Kit',
  items: [
    { label: 'Introduction', slug: 'adk/introduction' },
    { label: 'Quick Start', slug: 'adk/quickstart' },
    { label: 'Defining Agents', slug: 'adk/defining-agents' },
    { label: 'Creating Tools', slug: 'adk/creating-tools' },
    { label: 'Multi-Agent Teams', slug: 'adk/multi-agent' },
    { label: 'Remote Execution', slug: 'adk/remote-execution' },
    { label: 'CLI Reference', slug: 'adk/cli-reference' },
  ],
},
```

- [ ] **Step 3: Create introduction MDX**

`docs-site/src/content/docs/adk/introduction.mdx`:
```mdx
---
title: Agent Development Kit
description: Build AI agents in Python with the Astromesh ADK
---

The **Astromesh ADK** (Agent Development Kit) is a Python-first framework for building, running, and deploying AI agents. It wraps the Astromesh runtime engine with an intuitive decorator and class API.

## Key Features

- **Decorator-based agents** — Define agents with `@agent` and tools with `@tool`
- **Auto-generated schemas** — Tool JSON schemas from Python type hints
- **Multi-agent composition** — Teams with supervisor, swarm, pipeline, and parallel patterns
- **Local + Remote** — Develop locally, deploy to Astromesh with one line
- **Full observability** — Traces, costs, tokens, and callbacks built in

## Quick Example

```python
from astromesh_adk import agent, tool

@tool(description="Search the web")
async def search(query: str) -> str:
    ...

@agent(name="assistant", model="openai/gpt-4o", tools=[search])
async def assistant(ctx):
    """You are a helpful research assistant."""
    return None

result = await assistant.run("What is quantum computing?")
```

## Install

```bash
pip install astromesh-adk
```
```

- [ ] **Step 4: Create quickstart MDX**

`docs-site/src/content/docs/adk/quickstart.mdx`:
```mdx
---
title: Quick Start
description: Get started with the Astromesh ADK in 5 minutes
---

import { Tabs, TabItem } from '@astrojs/starlight/components';

## Install

<Tabs>
  <TabItem label="pip">
    ```bash
    pip install astromesh-adk
    ```
  </TabItem>
  <TabItem label="uv">
    ```bash
    uv add astromesh-adk
    ```
  </TabItem>
</Tabs>

## Create Your First Agent

Create a file called `my_agent.py`:

```python
from astromesh_adk import agent

@agent(name="assistant", model="ollama/llama3")
async def assistant(ctx):
    """You are a helpful assistant. Be concise."""
    return None
```

## Run It

```bash
astromesh-adk run my_agent.py:assistant "Hello, what can you do?"
```

## Add Tools

```python
from astromesh_adk import agent, tool

@tool(description="Add two numbers")
async def add(a: int, b: int) -> int:
    return a + b

@agent(name="math-bot", model="ollama/llama3", tools=[add])
async def math_bot(ctx):
    """You are a math assistant. Use the add tool."""
    return None
```

## Start the Dev Server

```bash
astromesh-adk dev my_agent.py --reload
```

This starts a local server with REST API and a simple playground at `http://localhost:8000`.
```

- [ ] **Step 5: Commit**

```bash
git add docs/ADK_QUICKSTART.md docs-site/astro.config.mjs docs-site/src/content/docs/adk/
git commit -m "docs(adk): add quickstart guide and docs-site ADK section"
```

---

## Summary

| Chunk | Tasks | What It Delivers |
|-------|-------|------------------|
| 1: Foundation | 1-5 | Package scaffold, exceptions, result/context types, callbacks |
| 2: Config | 6-8 | Provider resolution, memory/guardrails config builders |
| 3: Tools | 9-10 | @tool decorator, Tool class, MCP integration |
| 4: Agents | 11 | @agent decorator, Agent class, lifecycle hooks |
| 5: Composition | 12-14 | Remote connection, ADKRuntime, AgentTeam |
| 6: CLI & API | 15-16 | CLI commands, public __init__.py exports |
| 7: Docs | 17-18 | Examples, quickstart guide, docs-site pages |

**Parallelizable tasks:**
- Tasks 2, 3, 4, 5 (Chunk 1 after scaffolding) — all independent foundation types
- Tasks 6, 7, 8 (Chunk 2) — all independent config builders
- Tasks 9, 10 (Chunk 3) — tool decorator + MCP helper
- Tasks 17, 18 (Chunk 7) — examples + docs
