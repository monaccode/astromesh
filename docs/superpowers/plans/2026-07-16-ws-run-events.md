# WebSocket Run Events — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `/v1/ws/agent/{agent_name}` to the runtime and make a run observable while it happens, by adding an optional `on_event` callback to `run()`.

**Architecture:** All six orchestration patterns reach tools through a single `tool_fn` closure built once in `Agent.run()` (`engine.py:684`), and every model call goes through a single `model_fn` closure (`engine.py:626`). Wrapping those two closures emits `tool_call`/`tool_result`/`token` for every pattern without touching a single pattern file or the shared `ModelRouter`. The WebSocket handler passes a callback that only enqueues — never awaits — so a slow client can't stall the agent; it runs the agent as a task and forwards events while that task is in flight, exiting only once the run has finished *and* the queue is empty.

**Tech Stack:** Python 3.12, FastAPI/Starlette WebSockets, asyncio, pytest (`asyncio_mode = "auto"`), uv.

**Spec:** `docs/superpowers/specs/2026-07-16-ws-run-events-design.md`

## Global Constraints

- **`on_event=None` must be byte-for-byte today's behavior.** Every existing caller (`api/routes/agents.py`, `api/routes/agent_channels.py`, the ADK) passes nothing. This is the regression that matters most.
- **Emitting must never break a run.** A callback that raises is logged and swallowed — an observer that breaks what it observes is worse than no observer.
- **`on_event` is synchronous:** `Callable[[dict], None]`. It mirrors `ChannelEventBus.emit()`, the established shape in this repo. It must not be awaited.
- **The engine emits only `token`, `tool_call`, `tool_result`.** `status`, `done` and `error` are the transport's — they carry information only across a wire.
- **Do not touch** `astromesh/core/model_router.py`, `astromesh/orchestration/*`, or `POST /v1/agents/{name}/run`'s behavior.
- **No auth is added.** Abuse is the deployment's problem (spec §9).
- Tests: `uv run pytest -v`. There is **no** `--cov-fail-under` in this repo. `asyncio_mode = "auto"` — do NOT add `@pytest.mark.asyncio`.
- Tests live flat in `tests/`. Commits in Spanish, conventional format.

## File Structure

| File | Responsibility |
|---|---|
| `astromesh/api/usage.py` | **Create.** `usage_from_trace()` — token usage from a trace's spans, shared by both routes that report it |
| `astromesh/api/routes/agents.py` | **Modify.** Use the shared helper instead of its inline copy |
| `astromesh/runtime/engine.py` | **Modify.** `on_event` param + `_emit` helper + two wrapped closures |
| `astromesh/api/ws.py` | **Modify.** `set_runtime` + a handler that runs the agent and streams events |
| `astromesh/api/main.py` | **Modify.** Wire `ws.set_runtime` into the lifespan, in all three places |
| `tests/test_usage_from_trace.py` | **Create.** |
| `tests/test_run_events.py` | **Create.** `on_event` at the engine level, no HTTP |
| `tests/test_ws_agent.py` | **Create.** The repo's first WebSocket test |

---

## Task 1: `usage_from_trace` — extract before duplicating

**Files:**
- Create: `astromesh/api/usage.py`
- Modify: `astromesh/api/routes/agents.py:191-212` (the inline usage block) and its imports
- Test: `tests/test_usage_from_trace.py`

**Interfaces:**
- Produces: `usage_from_trace(trace: dict | None) -> dict | None`, returning `{"tokens_in": int, "tokens_out": int, "model": str}` or `None`.

**Context:** `POST /v1/agents/{name}/run` computes token usage by walking `result["trace"]["spans"]` — 25 lines that also handle a legacy nested `metadata.usage` shape from external providers. Task 3's WebSocket handler must report the same `usage` in its `done` event. Copying those 25 lines would guarantee the two drift: one gets a fix, the other doesn't. Extract first, then both call it.

This task must not change `/v1/agents/{name}/run`'s behavior at all — it is a pure refactor plus its first test.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_usage_from_trace.py
"""Token usage derived from a trace, shared by the REST and WebSocket surfaces."""

from astromesh.api.usage import usage_from_trace


def test_sums_input_and_output_tokens_across_spans():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 10, "output_tokens": 5}},
            {"attributes": {"input_tokens": 3, "output_tokens": 7}},
        ]
    }
    assert usage_from_trace(trace) == {"tokens_in": 13, "tokens_out": 12, "model": ""}


def test_reads_legacy_nested_metadata_usage():
    trace = {
        "spans": [
            {
                "attributes": {
                    "metadata": {
                        "usage": {"prompt_tokens": 4, "completion_tokens": 6},
                        "model": "gpt-4o-mini",
                    }
                }
            }
        ]
    }
    assert usage_from_trace(trace) == {"tokens_in": 4, "tokens_out": 6, "model": "gpt-4o-mini"}


def test_takes_the_first_model_it_sees():
    trace = {
        "spans": [
            {"attributes": {"input_tokens": 1, "metadata": {"model": "first"}}},
            {"attributes": {"input_tokens": 1, "metadata": {"model": "second"}}},
        ]
    }
    assert usage_from_trace(trace)["model"] == "first"


def test_adds_direct_and_legacy_tokens_from_the_same_span():
    trace = {
        "spans": [
            {
                "attributes": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "metadata": {"usage": {"prompt_tokens": 1, "completion_tokens": 2}},
                }
            }
        ]
    }
    assert usage_from_trace(trace) == {"tokens_in": 11, "tokens_out": 7, "model": ""}


def test_returns_none_when_no_tokens_were_reported():
    assert usage_from_trace({"spans": [{"attributes": {"tool": "search"}}]}) is None


def test_returns_none_for_empty_or_missing_traces():
    assert usage_from_trace(None) is None
    assert usage_from_trace({}) is None
    assert usage_from_trace({"spans": []}) is None


def test_tolerates_malformed_traces_without_raising():
    # A trace comes from the runtime, but nothing enforces its shape here.
    assert usage_from_trace({"spans": "not-a-list"}) is None
    assert usage_from_trace({"spans": ["not-a-dict"]}) is None
    assert usage_from_trace({"spans": [{"attributes": None}]}) is None
    assert usage_from_trace("not-a-dict") is None
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_usage_from_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.api.usage'`.

- [ ] **Step 3: Implement the helper**

```python
# astromesh/api/usage.py
"""Token usage derived from a run's trace.

Both POST /v1/agents/{name}/run and the WebSocket handler report usage, and both
derive it the same way: walk the trace's spans and sum what the providers
reported. It lives here so the two can't drift — the legacy metadata.usage
branch below is exactly the kind of detail that gets fixed in one copy and
forgotten in the other.
"""


def usage_from_trace(trace: dict | None) -> dict | None:
    """Sum token usage across a trace's spans.

    Returns {"tokens_in", "tokens_out", "model"}, or None when the trace reports
    no tokens at all (a run that never reached a provider, or a malformed trace).
    Never raises: a trace is data from the runtime, not a validated contract.
    """
    spans = trace.get("spans", []) if isinstance(trace, dict) else []
    if not isinstance(spans, list):
        return None

    total_in = 0
    total_out = 0
    model_used = ""

    for span in spans:
        attrs = span.get("attributes", {}) if isinstance(span, dict) else {}
        if not isinstance(attrs, dict):
            continue

        # The runtime stores tokens as input_tokens / output_tokens.
        total_in += attrs.get("input_tokens", 0)
        total_out += attrs.get("output_tokens", 0)

        # Legacy / external providers nest them under metadata.usage.
        span_meta = attrs.get("metadata", {})
        if isinstance(span_meta, dict) and "usage" in span_meta:
            u = span_meta["usage"]
            total_in += u.get("prompt_tokens", 0)
            total_out += u.get("completion_tokens", 0)
        if isinstance(span_meta, dict) and "model" in span_meta and not model_used:
            model_used = span_meta["model"]

    if total_in or total_out:
        return {"tokens_in": total_in, "tokens_out": total_out, "model": model_used}
    return None
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_usage_from_trace.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Make the REST route use it**

In `astromesh/api/routes/agents.py`, add to the imports near the top (after `from astromesh.errors import ...`):

```python
from astromesh.api.usage import usage_from_trace
```

Then replace the inline block — everything from `usage = None` through the `if total_in or total_out:` assignment (currently lines ~191-212) — with:

```python
        trace = result.get("trace", {})
        usage_data = usage_from_trace(trace)
        usage = UsageInfo(**usage_data) if usage_data else None
```

Leave the `return AgentRunResponse(...)` below it exactly as it is. `UsageInfo` stays defined in `agents.py` — it is that route's response model, and the helper deliberately returns a plain dict so the WebSocket handler (Task 3) doesn't have to import a pydantic model from a route.

- [ ] **Step 6: Verify the route is unchanged**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_api.py tests/test_api_agents_extended.py tests/test_usage_from_trace.py -v`
Expected: PASS. These cover the run route; they must be green without modification — if one fails, the refactor changed behavior and is wrong.

- [ ] **Step 7: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/api/usage.py astromesh/api/routes/agents.py tests/test_usage_from_trace.py
git commit -m "refactor(api): extraer usage_from_trace para compartirlo entre REST y WS"
```

---

## Task 2: `on_event` in the engine

**Files:**
- Modify: `astromesh/runtime/engine.py` — `AgentRuntime.run:416`, `Agent.run:569`, `model_fn:626`, `tool_fn:684`
- Test: `tests/test_run_events.py`

**Interfaces:**
- Produces:
  ```python
  AgentRuntime.run(agent_name, query, session_id, context=None, parent_trace_id=None, on_event=None)
  Agent.run(query, session_id, context=None, parent_trace_id=None, on_event=None)
  # on_event: Callable[[dict], None] | None
  ```
  Events emitted by the engine, and only these:
  ```python
  {"type": "token", "content": str}
  {"type": "tool_call", "id": str, "name": str, "arguments": dict}
  {"type": "tool_result", "id": str, "ok": bool}
  ```

**Context:** This is the whole feature. Everything else is plumbing.

`Agent.run()` builds two closures and hands them to `self._pattern.execute(...)`. **Every** orchestration pattern receives those same two closures — verified across all six: `patterns.py`'s `ReActPattern:38`, `PlanAndExecutePattern:99`, `ParallelFanOutPattern:152`, `PipelinePattern:191`, plus `orchestration/supervisor.py:11` and `orchestration/swarm.py:11`. They all share `execute(query, context, model_fn, tool_fn, tools, max_iterations=10)` and all reach tools via `await tool_fn(name, args)`. So wrapping the closures covers every pattern, and no pattern file is touched.

**Do not add a global bus.** The runtime is multi-tenant (Cloud namespaces agents `{org_slug}__{agent_name}`); a callback passed into the call it belongs to has no cross-run visibility by construction.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_events.py
"""on_event: observing a run while it happens, at the engine level (no HTTP)."""

from __future__ import annotations

import pytest

from astromesh.runtime.engine import Agent, _emit


class FakeResponse:
    """Shaped like the providers' CompletionResponse, minus what the engine ignores."""

    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.model = "fake-model"
        self.provider = "fake"
        self.latency_ms = 1
        self.cost = 0.0
        self.usage = {"input_tokens": 1, "output_tokens": 1}


def test_emit_is_a_noop_without_a_callback():
    _emit(None, {"type": "token", "content": "hi"})  # must not raise


def test_emit_delivers_the_event():
    seen = []
    _emit(seen.append, {"type": "token", "content": "hi"})
    assert seen == [{"type": "token", "content": "hi"}]


def test_emit_swallows_a_raising_callback():
    def boom(_event):
        raise RuntimeError("observer is broken")

    # An observer must never be able to break the run it observes.
    _emit(boom, {"type": "token", "content": "hi"})


def test_emit_swallows_a_raising_callback_and_logs_it(caplog):
    def boom(_event):
        raise RuntimeError("observer is broken")

    with caplog.at_level("ERROR"):
        _emit(boom, {"type": "token", "content": "hi"})
    assert "on_event" in caplog.text
```

Note: the pattern-level tests (a real `Agent.run()` with a fake pattern) come in Step 5 — this step pins `_emit`'s contract first because everything else depends on it.

- [ ] **Step 2: Run the test and watch it fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_run_events.py -v`
Expected: FAIL — `ImportError: cannot import name '_emit' from 'astromesh.runtime.engine'`.

- [ ] **Step 3: Add the `_emit` helper**

In `astromesh/runtime/engine.py`, add at module level, right after `logger = logging.getLogger(__name__)` (line 22):

```python
def _emit(on_event, event: dict) -> None:
    """Hand one event to the caller's observer, if there is one.

    An observer that raises is logged and ignored: watching a run must never be
    able to break it. This mirrors ChannelEventBus.emit(), which likewise
    swallows a subscriber's failure rather than propagating it into the producer.
    """
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        logger.exception("on_event callback raised; ignoring")
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_run_events.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the failing tests for the wired closures**

Append to `tests/test_run_events.py`:

```python
class RecordingPattern:
    """A pattern that drives model_fn/tool_fn the way the real ones do.

    Every real pattern receives exactly these two closures and calls
    `await tool_fn(name, args)` — so exercising them here exercises what all six
    patterns will do.
    """

    def __init__(self, script=None):
        self.script = script or []
        self.tool_ran_after = []

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        for item in self.script:
            if item[0] == "model":
                await model_fn([{"role": "user", "content": query}], tools)
            elif item[0] == "tool":
                await tool_fn(item[1], item[2])
        return {"answer": "done", "steps": []}


def _make_agent(pattern, tool_impl=None, model_content="thinking"):
    """Build an Agent with everything the run loop touches stubbed out."""
    from unittest.mock import AsyncMock, MagicMock

    agent = Agent.__new__(Agent)  # bypass __init__: we only exercise run()
    agent.name = "test-agent"
    agent._pattern = pattern
    agent._role_map = {}
    agent._orchestration_config = {"pattern": "recording"}
    agent._permissions = {}
    agent._guardrails = {}
    agent._rag = None
    agent._knowledge = None

    router = MagicMock()
    router.route = AsyncMock(return_value=FakeResponse(content=model_content))
    agent._routers = {"default": router}

    tools = MagicMock()
    tools.execute = AsyncMock(side_effect=tool_impl or (lambda n, a, c: "observation"))
    tools.get_schemas = MagicMock(return_value=[])
    agent._tools = tools

    memory = MagicMock()
    memory.get_context = AsyncMock(return_value=[])
    memory.add_turn = AsyncMock()
    agent._memory = memory

    prompt = MagicMock()
    prompt.render = MagicMock(return_value="you are a test agent")
    agent._prompt_engine = prompt

    return agent


async def test_tool_call_is_emitted_before_the_tool_runs():
    order = []

    async def tool_impl(name, args, ctx):
        order.append("tool-executed")
        return "observation"

    events = []

    def on_event(e):
        order.append(e["type"])
        events.append(e)

    agent = _make_agent(RecordingPattern([("tool", "search", {"q": "x"})]), tool_impl=tool_impl)
    await agent.run("hola", "s1", on_event=on_event)

    assert order == ["tool_call", "tool-executed", "tool_result"]
    assert events[0]["name"] == "search"
    assert events[0]["arguments"] == {"q": "x"}
    assert events[1]["ok"] is True


async def test_tool_call_and_tool_result_share_an_id():
    events = []
    agent = _make_agent(RecordingPattern([("tool", "search", {"q": "x"})]))
    await agent.run("hola", "s1", on_event=events.append)

    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    assert call["id"] == result["id"]
    assert call["id"]


async def test_ids_differ_across_calls():
    events = []
    agent = _make_agent(
        RecordingPattern([("tool", "a", {}), ("tool", "b", {})])
    )
    await agent.run("hola", "s1", on_event=events.append)

    ids = [e["id"] for e in events if e["type"] == "tool_call"]
    assert len(ids) == 2 and ids[0] != ids[1]


async def test_a_raising_tool_emits_ok_false_and_still_propagates():
    async def boom(name, args, ctx):
        raise RuntimeError("tool exploded")

    events = []
    agent = _make_agent(RecordingPattern([("tool", "search", {})]), tool_impl=boom)

    with pytest.raises(RuntimeError, match="tool exploded"):
        await agent.run("hola", "s1", on_event=events.append)

    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ok"] is False


async def test_model_content_is_emitted_as_a_token():
    events = []
    agent = _make_agent(RecordingPattern([("model",)]), model_content="pensando en voz alta")
    await agent.run("hola", "s1", on_event=events.append)

    tokens = [e for e in events if e["type"] == "token"]
    assert tokens == [{"type": "token", "content": "pensando en voz alta"}]


async def test_empty_model_content_emits_no_token():
    events = []
    agent = _make_agent(RecordingPattern([("model",)]), model_content="")
    await agent.run("hola", "s1", on_event=events.append)

    assert [e for e in events if e["type"] == "token"] == []


async def test_the_engine_emits_no_status_or_done():
    """Those belong to the transport — a direct caller sees run() return."""
    events = []
    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {})]))
    await agent.run("hola", "s1", on_event=events.append)

    assert {e["type"] for e in events} == {"token", "tool_call", "tool_result"}


async def test_events_arrive_in_run_order():
    events = []
    agent = _make_agent(
        RecordingPattern([("model",), ("tool", "a", {}), ("model",)])
    )
    await agent.run("hola", "s1", on_event=events.append)

    assert [e["type"] for e in events] == [
        "token",
        "tool_call",
        "tool_result",
        "token",
    ]


async def test_without_on_event_the_run_behaves_exactly_as_before():
    """The regression that matters: every existing caller passes nothing."""
    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {})]))
    result = await agent.run("hola", "s1")
    assert result["answer"] == "done"


async def test_a_raising_observer_does_not_break_the_run():
    def boom(_event):
        raise RuntimeError("observer is broken")

    agent = _make_agent(RecordingPattern([("model",), ("tool", "a", {})]))
    result = await agent.run("hola", "s1", on_event=boom)
    assert result["answer"] == "done"
```

- [ ] **Step 6: Run and watch them fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_run_events.py -v`
Expected: FAIL — `Agent.run()` doesn't accept `on_event`.

If `_make_agent` fails on an attribute the run loop needs that isn't stubbed here, add the stub — do not change `engine.py` to accommodate the test.

- [ ] **Step 7: Thread `on_event` through both `run()` methods**

In `astromesh/runtime/engine.py`, `AgentRuntime.run` (line 416):

```python
    async def run(
        self, agent_name, query, session_id, context=None, parent_trace_id=None, on_event=None
    ):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(
            query, session_id, context, parent_trace_id=parent_trace_id, on_event=on_event
        )
```

And `Agent.run` (line 569) — signature only:

```python
    async def run(self, query, session_id, context=None, parent_trace_id=None, on_event=None):
```

- [ ] **Step 8: Emit `token` from `model_fn`**

In `Agent.run`'s `model_fn` closure, find the end of the `try:` block where it currently reads:

```python
                    llm_span.set_attribute("response", _truncate(response.content, 10_000))
                    tracing.finish_span(llm_span)
                    return response
```

Replace with:

```python
                    llm_span.set_attribute("response", _truncate(response.content, 10_000))
                    tracing.finish_span(llm_span)
                    if response.content:
                        _emit(on_event, {"type": "token", "content": response.content})
                    return response
```

- [ ] **Step 9: Emit `tool_call` / `tool_result` from `tool_fn`**

Add `import uuid` to the imports at the top of `engine.py` (after `import os`).

Replace the whole `tool_fn` closure (line ~684) with:

```python
            async def tool_fn(name, args):
                # One id per call so a consumer can pair the result with its call.
                call_id = str(uuid.uuid4())
                _emit(
                    on_event,
                    {"type": "tool_call", "id": call_id, "name": name, "arguments": args},
                )
                tool_span = tracing.start_span(
                    "tool.call", {"tool": name}, parent_span_id=root_span.span_id
                )
                try:
                    observation = await self._tools.execute(
                        name, args, {"agent": self.name, "session": session_id}
                    )
                    tool_span.set_attribute("tool_args", args)
                    tool_span.set_attribute("tool_result", _truncate(str(observation), 5_000))
                    tracing.finish_span(tool_span)
                    _emit(on_event, {"type": "tool_result", "id": call_id, "ok": True})
                    return observation
                except Exception as e:
                    tool_span.set_attribute("error_message", str(e))
                    tracing.finish_span(tool_span, status=SpanStatus.ERROR)
                    _emit(on_event, {"type": "tool_result", "id": call_id, "ok": False})
                    raise
```

Note the ordering: `tool_call` is emitted **before** the span opens and before `execute` — that's the whole point, a consumer mounts UI while the tool runs. And `tool_result {ok: False}` is emitted **before** the existing `raise`, so a failing tool still reports.

- [ ] **Step 10: Run and watch them pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_run_events.py -v`
Expected: PASS (14 tests).

- [ ] **Step 11: Verify nothing else regressed**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -v`
Expected: PASS. `on_event` defaults to `None` everywhere, so the whole suite must be green with no test modified.

- [ ] **Step 12: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/runtime/engine.py tests/test_run_events.py
git commit -m "feat(runtime): on_event opcional en run() para observar tools y texto en vivo"
```

---

## Task 3: The WebSocket handler, wired

**Files:**
- Modify: `astromesh/api/ws.py` (the whole handler)
- Modify: `astromesh/api/main.py:80-83`, `:103-107`, `:112-116` (lifespan wiring)
- Test: `tests/test_ws_agent.py`

**Interfaces:**
- Consumes: `usage_from_trace(trace) -> dict | None` (Task 1); `AgentRuntime.run(..., on_event=...)` (Task 2)
- Produces: `set_runtime(runtime)` in `astromesh/api/ws.py`, matching every other route module's shape

**Context:** `ws.py` today never imports the runtime; it echoes `f"[WebSocket] Received: {query}"` (line 49). It also has no `set_runtime`, and `main.py`'s lifespan doesn't wire it — both need adding.

Three things to get right, in order of how badly they bite:

1. **Events must reach the client during the run.** Draining the queue only after `await run(...)` returns delivers everything at once at the end, which defeats the entire feature. The run goes in a task and events are forwarded while it's in flight.
2. **The queue must be flushed before `done`.** When the run finishes, events may still be queued. Send `done` first and the last `tool_result` — sometimes the last `tool_call` — is lost, and the consumer renders a run that never finished. The loop's exit condition makes this structural instead of something to remember.
3. **A client that vanishes mid-run must cancel the run**, or an agent keeps burning model calls writing to a dead socket.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ws_agent.py
"""The WebSocket agent endpoint: runs the agent and streams its events."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from astromesh.api.ws import router, set_runtime


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router, prefix="/v1")
    return application


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt.run = AsyncMock(return_value={"answer": "Hola!", "steps": [], "trace": {}})
    return rt


@pytest.fixture
def client(app, mock_runtime):
    set_runtime(mock_runtime)
    yield TestClient(app)
    set_runtime(None)


def _drain(ws, until="done"):
    """Collect events until the terminal one. Fails loudly rather than hanging."""
    out = []
    for _ in range(50):
        event = ws.receive_json()
        out.append(event)
        if event["type"] in (until, "error"):
            return out
    raise AssertionError(f"no {until!r} after 50 events: {out}")


def test_runs_the_agent_and_returns_its_answer(client, mock_runtime):
    with client.websocket_connect("/v1/ws/agent/demo?session_id=s1") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    assert events[0]["type"] == "status"
    assert events[-1]["type"] == "done"
    assert events[-1]["answer"] == "Hola!"
    assert events[-1]["session_id"] == "s1"
    # The old stub echoed the query back; the real runtime must be called.
    assert "[WebSocket] Received" not in events[-1]["answer"]
    mock_runtime.run.assert_awaited_once()
    assert mock_runtime.run.await_args.args[0] == "demo"
    assert mock_runtime.run.await_args.args[1] == "hola"


def test_forwards_events_the_runtime_emits_during_the_run(app, client, mock_runtime):
    async def run_with_events(agent_name, query, session_id, context=None, on_event=None, **kw):
        on_event({"type": "token", "content": "pensando"})
        on_event({"type": "tool_call", "id": "t1", "name": "search", "arguments": {"q": "x"}})
        on_event({"type": "tool_result", "id": "t1", "ok": True})
        return {"answer": "listo", "steps": [], "trace": {}}

    mock_runtime.run = AsyncMock(side_effect=run_with_events)

    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    types = [e["type"] for e in events]
    assert types == ["status", "token", "tool_call", "tool_result", "done"]
    assert events[2]["name"] == "search"


def test_every_queued_event_is_delivered_before_done(client, mock_runtime):
    """The flush: the run finishing must not cut the loop off with events still queued."""

    async def run_with_many(agent_name, query, session_id, context=None, on_event=None, **kw):
        for i in range(20):
            on_event({"type": "token", "content": str(i)})
        return {"answer": "listo", "steps": [], "trace": {}}

    mock_runtime.run = AsyncMock(side_effect=run_with_many)

    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert tokens == [str(i) for i in range(20)]
    assert events[-1]["type"] == "done"


def test_includes_usage_when_the_trace_reports_tokens(client, mock_runtime):
    mock_runtime.run = AsyncMock(
        return_value={
            "answer": "listo",
            "steps": [],
            "trace": {"spans": [{"attributes": {"input_tokens": 10, "output_tokens": 5}}]},
        }
    )

    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    assert events[-1]["usage"] == {"tokens_in": 10, "tokens_out": 5, "model": ""}


def test_usage_is_none_when_the_trace_reports_nothing(client, mock_runtime):
    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    assert events[-1]["usage"] is None


def test_a_failing_run_sends_error_not_silence(client, mock_runtime):
    """A consumer that gets silence hangs forever waiting to be told."""
    mock_runtime.run = AsyncMock(side_effect=RuntimeError("el modelo explotó"))

    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    assert events[-1]["type"] == "error"
    assert "explotó" in events[-1]["message"]


def test_an_unknown_agent_sends_error(client, mock_runtime):
    mock_runtime.run = AsyncMock(side_effect=ValueError("Agent 'nope' not found"))

    with client.websocket_connect("/v1/ws/agent/nope") as ws:
        ws.send_json({"query": "hola"})
        events = _drain(ws)

    assert events[-1]["type"] == "error"
    assert "not found" in events[-1]["message"]


def test_malformed_json_sends_error_and_keeps_the_connection(client, mock_runtime):
    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_text("no soy json")
        first = ws.receive_json()
        assert first["type"] == "error"

        # The connection survives: a second, valid query still works.
        ws.send_json({"query": "hola"})
        events = _drain(ws)
        assert events[-1]["type"] == "done"


def test_without_a_runtime_it_sends_error(app):
    set_runtime(None)
    with TestClient(app).websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "hola"})
        event = ws.receive_json()
        assert event["type"] == "error"


def test_two_queries_on_one_connection_both_run(client, mock_runtime):
    with client.websocket_connect("/v1/ws/agent/demo") as ws:
        ws.send_json({"query": "una"})
        _drain(ws)
        ws.send_json({"query": "dos"})
        _drain(ws)

    assert mock_runtime.run.await_count == 2


async def test_a_client_that_vanishes_mid_run_cancels_the_run():
    """A dead socket must not leave an agent burning model calls for nobody.

    Driven directly rather than through TestClient: TestClient runs the app in a
    worker thread, so a disconnect racing an in-flight run isn't expressible there.
    A fake socket that dies on its second send is.
    """
    import asyncio

    from fastapi import WebSocketDisconnect

    from astromesh.api.ws import _run_and_stream, set_runtime as set_ws_runtime

    cancelled = asyncio.Event()

    async def slow_run(agent_name, query, session_id, context=None, on_event=None, **kw):
        on_event({"type": "token", "content": "uno"})
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"answer": "nunca llega", "steps": [], "trace": {}}

    rt = MagicMock()
    rt.run = AsyncMock(side_effect=slow_run)
    set_ws_runtime(rt)

    class DyingSocket:
        def __init__(self):
            self.sends = 0

        async def send_json(self, message):
            self.sends += 1
            # status goes out; the first forwarded event finds a dead socket.
            if self.sends >= 2:
                raise WebSocketDisconnect()

    try:
        with pytest.raises(WebSocketDisconnect):
            await _run_and_stream(DyingSocket(), "demo", "s1", "hola")
        await asyncio.wait_for(cancelled.wait(), timeout=2)
    finally:
        set_ws_runtime(None)
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_ws_agent.py -v`
Expected: FAIL — `ImportError: cannot import name 'set_runtime' from 'astromesh.api.ws'`.

- [ ] **Step 3: Rewrite `astromesh/api/ws.py`**

```python
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from astromesh.api.usage import usage_from_trace

router = APIRouter()
logger = logging.getLogger(__name__)

# Generous: one run emits a handful of events. A full queue means something is
# very wrong (a runaway loop), which is why it's logged rather than ignored.
_EVENT_QUEUE_MAX = 1000

# How long to wait on the queue before re-checking whether the run has finished.
# Same shape as ASTROMESH_SSE_POLL_INTERVAL in api/routes/agent_channels.py.
_POLL_INTERVAL = 0.05

_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)


manager = ConnectionManager()


async def _run_and_stream(websocket: WebSocket, agent_name: str, session_id: str, query: str):
    """Run the agent, streaming its events to the socket as they happen.

    The callback only enqueues, so a slow socket can never stall the agent. The
    run itself is a task, so this coroutine can forward events *while* it is in
    flight rather than all at once at the end.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=_EVENT_QUEUE_MAX)

    def on_event(event: dict) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Dropping a tool_call means a consumer's UI never mounts that
            # component — worth a loud line rather than silent truncation.
            logger.warning(
                "run event queue full for agent=%s session=%s; dropping %s",
                agent_name,
                session_id,
                event.get("type"),
            )

    await manager.send_message(
        {"type": "status", "status": "processing", "agent": agent_name}, websocket
    )

    run_task = asyncio.create_task(
        _runtime.run(agent_name, query, session_id, on_event=on_event)
    )

    try:
        # The exit condition is the whole trick: the run must be finished AND the
        # queue drained. That makes "flush before done" structural rather than a
        # race someone has to remember to win — sending done with events still
        # queued would render a run that never finished.
        # The short poll mirrors the SSE route in api/routes/agent_channels.py,
        # which documents the same approach.
        while not run_task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_POLL_INTERVAL)
            except asyncio.TimeoutError:
                continue
            await websocket.send_json(event)
    finally:
        # If we leave this loop by exception — the client vanished mid-run — do not
        # leave an agent burning model calls for a socket nobody is reading.
        if not run_task.done():
            run_task.cancel()

    try:
        result = await run_task
    except Exception as e:
        logger.exception("agent run failed agent=%s session=%s", agent_name, session_id)
        await manager.send_message({"type": "error", "message": str(e)}, websocket)
        return

    await manager.send_message(
        {
            "type": "done",
            "answer": result.get("answer", ""),
            "session_id": session_id,
            "usage": usage_from_trace(result.get("trace")),
        },
        websocket,
    )


@router.websocket("/ws/agent/{agent_name}")
async def agent_websocket(websocket: WebSocket, agent_name: str):
    session_id = websocket.query_params.get("session_id", "default")
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                query = message.get("query", "")
            except (ValueError, AttributeError) as e:
                # Previously an unparseable payload killed the connection.
                await manager.send_message(
                    {"type": "error", "message": f"invalid JSON: {e}"}, websocket
                )
                continue

            if not _runtime:
                await manager.send_message(
                    {"type": "error", "message": "Runtime not initialized"}, websocket
                )
                continue

            await _run_and_stream(websocket, agent_name, session_id, query)
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
```

- [ ] **Step 4: Run and watch them pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_ws_agent.py -v`
Expected: PASS (12 tests).

If `test_every_queued_event_is_delivered_before_done` fails, the loop's exit condition is wrong — do not weaken the test, fix the condition.

- [ ] **Step 5: Write the failing test for the lifespan wiring**

Without this, `ws._runtime` is never set in production and every query answers `"Runtime not initialized"` — while every test above still passes, because they call `set_runtime` themselves. Append to `tests/test_ws_agent.py`:

```python
async def test_the_app_lifespan_wires_the_ws_runtime():
    """ws._runtime is set by main.py's lifespan, not just by tests calling set_runtime."""
    from asgi_lifespan import LifespanManager

    from astromesh.api import ws as ws_module
    from astromesh.api.routes import agents as agents_route
    from astromesh.api.main import app

    sentinel = MagicMock()
    agents_route.set_runtime(sentinel)  # take main.py's pre-injected branch
    ws_module.set_runtime(None)
    try:
        async with LifespanManager(app):
            assert ws_module._runtime is sentinel
    finally:
        agents_route.set_runtime(None)
        ws_module.set_runtime(None)
```

- [ ] **Step 6: Run and watch it fail**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_ws_agent.py::test_the_app_lifespan_wires_the_ws_runtime -v`
Expected: FAIL — `assert None is sentinel`.

- [ ] **Step 7: Wire `ws.set_runtime` into the lifespan**

`astromesh/api/main.py` already imports `ws` (line 11: `from astromesh.api import ws`). Add it to all **three** places the other route modules are wired — missing one leaves a hole that only shows up in production:

In the pre-injected branch (after `agent_channels_route.set_runtime(r)`, ~line 83):
```python
        ws.set_runtime(r)
```

In normal startup (after `agent_channels_route.set_runtime(runtime)`, ~line 107):
```python
    ws.set_runtime(runtime)
```

In teardown (after `agent_channels_route.set_runtime(None)`, ~line 116):
```python
        ws.set_runtime(None)
```

- [ ] **Step 8: Run and watch it pass**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest tests/test_ws_agent.py -v`
Expected: PASS (12 tests).

- [ ] **Step 9: Verify the whole suite**

Run: `cd /Users/fulfaro/monaccode/astromesh && uv run pytest -v`
Expected: PASS. Nothing outside these three files changed behavior.

- [ ] **Step 10: Drive it against a real agent**

Unit tests all mock the runtime; this is the first time the real thing runs end to end.

```bash
cd /Users/fulfaro/monaccode/astromesh
uv run uvicorn astromesh.api.main:app --port 8000
```

In another shell, with an agent from `config/agents/` (e.g. `sales-qualifier`) and a query that makes it call a tool:

```bash
uv run python - <<'EOF'
import asyncio, json, websockets

async def main():
    uri = "ws://localhost:8000/v1/ws/agent/sales-qualifier?session_id=smoke"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"query": "Look up Acme Corp"}))
        while True:
            event = json.loads(await ws.recv())
            print(event["type"], {k: v for k, v in event.items() if k != "type"})
            if event["type"] in ("done", "error"):
                break

asyncio.run(main())
EOF
```

Confirm, and report what you actually saw: `status` arrives first; `tool_call` arrives **before** the tool's work finishes (not batched at the end); `tool_result` pairs by `id`; `done.answer` is the agent's real answer, not an echo. If the provider isn't reachable, report that you got `error` instead of silence — that is also a passing observation for this step.

- [ ] **Step 11: Commit**

```bash
cd /Users/fulfaro/monaccode/astromesh
git add astromesh/api/ws.py astromesh/api/main.py tests/test_ws_agent.py
git commit -m "feat(api): cablear el WS al runtime y transmitir los eventos de la corrida"
```

---

## Notes for whoever executes this

**The spec's §7 is a requirement on consumers, not on this code.** Emitting each iteration's `content` as `token` exposes the model's per-iteration reasoning to whoever is watching. That is unavoidable — without it, all text arrives at the end and every tool event precedes it. Any agent whose run is streamed to end users must be prompted so that `content` is narration, not private deliberation. Out of scope here; recorded so it isn't discovered by a visitor.

**The spec's §9 stands: this makes the endpoint live.** After Task 3, anyone who can reach the port can run agents and spend money on model calls. No auth is added, deliberately — a credential shipped to a browser is not a credential. Whoever deploys this owns reachability, rate limiting and quotas.

**What this does not do:** token-level streaming. `token` carries one whole completion. Providers implement `stream()` but `ModelRouter.route()` only calls `complete()`; wiring that touches the router the whole platform shares, and belongs in its own spec. The contract doesn't change when it happens — `token` appends, so real streaming just subdivides these chunks.
