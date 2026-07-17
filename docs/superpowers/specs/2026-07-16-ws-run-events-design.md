# WebSocket wired to the runtime, with live run events — Design

**Date:** 2026-07-16
**Branch:** `feature/ws-run-events`
**Status:** approved

---

## 1. Goal

Two things, one change:

1. **Wire `/v1/ws/agent/{agent_name}` to the runtime.** Today it is a stub that never touches the agent — it echoes `f"[WebSocket] Received: {query}"` back (`astromesh/api/ws.py:49`, comment: *"Placeholder response — will be wired to runtime"*).
2. **Make a run observable while it happens.** Today tool calls are only visible *after* `run()` returns, in `AgentRunResponse.steps` / the trace. Nothing can watch a run in progress.

**Why now:** a consumer exists. The FAiNANSU marketing site (`fainansu-marketing`, live) is built against the event contract in §3 and currently runs on a local mock because this endpoint doesn't work. But the feature stands on its own — a runtime that can't be watched while it runs is a gap in AstroMesh regardless of who asked.

**Non-goal:** this is not a marketing-site feature. The contract is generic; nothing about FAiNANSU enters the runtime.

---

## 2. What changes

| File | Change |
|---|---|
| `astromesh/runtime/engine.py` | `AgentRuntime.run()` and `Agent.run()` take `on_event=None`; two closures wrapped |
| `astromesh/api/ws.py` | Handler calls the runtime and streams events |
| `tests/test_ws_agent.py` | New — the repo's first WebSocket test |
| `tests/test_run_events.py` | New — `on_event` emission and ordering |

### What deliberately does NOT change

- **`astromesh/orchestration/patterns.py`.** All four patterns (`ReActPattern:38`, `PlanAndExecutePattern:99`, `ParallelFanOutPattern:152`, `PipelinePattern:191`) share the signature `execute(query, context, model_fn, tool_fn, tools, max_iterations=10)` and every one that calls a tool calls it as `await tool_fn(tc["name"], tc["arguments"])`. The closure is built **once**, in `Agent.run()` (`engine.py:684`). Wrapping it there covers every pattern — including patterns added later — without touching this file.
- **`astromesh/core/model_router.py`.** `ModelRouter.route()` is used by the whole platform. It is not touched. See §6.
- **The REST route, the ADK, the channels bus.** `on_event` defaults to `None`; without it, behavior is byte-for-byte what it is today.

---

## 3. The event contract

Events are plain `dict`s, emitted in the order the run produces them.

**Two layers emit, and the split is deliberate.** The engine emits only what is invisible from outside a run. The transport frames the lifecycle.

| Event | Payload | Emitted by | When |
|---|---|---|---|
| `token` | `{type, content: str}` | **engine** | a model completion returns non-empty content |
| `tool_call` | `{type, id: str, name: str, arguments: dict}` | **engine** | **before** the tool executes |
| `tool_result` | `{type, id: str, ok: bool}` | **engine** | after it returns or raises |
| `status` | `{type, status: "processing"}` | **handler** | before the run is awaited |
| `done` | `{type, answer: str, session_id: str, usage: dict\|None}` | **handler** | `run()` returned |
| `error` | `{type, message: str}` | **handler** | `run()` raised |

**Why the engine does not emit `status`/`done`:** for a direct caller — the REST route, the ADK, a test — they are noise. `run()` returning *is* `done`; a caller that awaited it does not need to be told. Those two events only carry information across a wire, where the consumer cannot see the call return. So they belong to the transport that has a wire. This keeps `on_event`'s contract narrow and honest: it reports things that happen *inside* a run, and nothing else.

`id` is a `uuid4` string, matching `ChannelEvent.create()`'s convention (`astromesh/channels/event_bus.py`). It exists so a consumer can pair a `tool_call` with its `tool_result` and key UI by it.

`tool_result` carries `ok` but **not** the tool's return value. Tool output can be large and can contain anything the tool touched; the trace already records it (`tool_result` span attribute, truncated to 5000 chars). A live event stream is the wrong channel for it, and callers that need it have `steps` and the trace.

---

## 4. The mechanism

```python
AgentRuntime.run(agent_name, query, session_id, context=None, parent_trace_id=None, on_event=None)
Agent.run(query, session_id, context=None, parent_trace_id=None, on_event=None)
```

`AgentRuntime.run()` passes `on_event` straight through to `Agent.run()`.

**`on_event` is a synchronous callable**, `Callable[[dict], None]`. This mirrors `ChannelEventBus.emit()` (`event_bus.py`), which is also sync — the established shape in this repo. Synchronous means the run loop cannot be blocked by a slow consumer: a callback that does real I/O is the caller's bug, and the contract says so.

**Why a callback and not a global bus.** `channel_event_bus` is a module-level singleton with a shared ring buffer; subscribers filter by agent themselves. For run events that would be wrong: the runtime is multi-tenant (Cloud namespaces agents as `{org_slug}__{agent_name}`), and a subscriber that filters incorrectly would see another tenant's run. A callback passed into the call it belongs to has no global state and no cross-run visibility by construction. A bus can be built on top of it later if a second consumer ever wants one; nothing here forecloses that.

### Emission points, both in `Agent.run()`

**`tool_fn`** (`engine.py:684`) — wrap the existing closure. It already has the try/except that finishes the span and re-raises; the events go alongside:

- emit `tool_call` before `await self._tools.execute(...)`
- emit `tool_result {ok: True}` after it returns
- emit `tool_result {ok: False}` in the `except` branch, **before** the existing `raise`

**`model_fn`** (`engine.py:~626`) — after `await router.route(...)` returns, emit `token` with `response.content` when it is non-empty.

That is all the engine emits. `status`, `done` and `error` are the handler's (§3).

Emission must never break a run. Every `on_event` call is wrapped so that a raising callback is logged and swallowed, exactly as `ChannelEventBus.emit()` swallows `QueueFull`. An observer that breaks the thing it observes is worse than no observer.

### In the WebSocket handler

Per query, the handler: emits `status`, awaits `_runtime.run(..., on_event=cb)`, then emits `done` — or `error` if it raised (§5). `done.answer` is `result["answer"]`; `done.session_id` is the connection's; `done.usage` is computed from `result["trace"]["spans"]` by summing `input_tokens`/`output_tokens`, exactly as `api/routes/agents.py` already does for `AgentRunResponse.usage`. That summing logic is duplicated in two routes the moment this lands — if it grows a third caller, extract it; two is not yet a pattern.

The callback does `queue.put_nowait(event)` on a per-connection `asyncio.Queue`; a separate task drains the queue to the socket. Two properties this buys:

- **Events reach the client while the run is still going.** Draining only after `await run(...)` returns would deliver everything at once at the end, which defeats the entire point.
- **A slow socket cannot stall the agent.** `put_nowait` never awaits.

**The flush-before-`done` race is the thing to get right:** when `run()` returns, the pump may not have sent everything yet. The queue must be drained before `done` goes out, or the last `tool_result` — sometimes the last `tool_call` — is lost, and the consumer renders a run that never finished. The pump task must also not outlive the connection.

The queue is bounded. A full queue means something is very wrong (a runaway loop, a dead pump); log it. Dropping a `tool_call` silently means a consumer's UI never mounts that component, so the log line matters.

---

## 5. Errors

| Failure | Behavior |
|---|---|
| A tool raises | `tool_result {ok: false}`, then the exception propagates as it does today (the pattern does not catch it) → the handler emits `error` |
| `ModelProviderError` | propagates → `error` (the REST route maps this to 502; the WS has no status codes, so the message carries it) |
| Unknown agent (`ValueError` from `AgentRuntime.run`) | → `error` |
| Malformed client JSON | → `error`, connection stays open. Today an unparseable payload raises inside the loop and kills the connection. |
| `WebSocketDisconnect` | as today: `manager.disconnect`, and the in-flight run's pump task is cancelled |

**Every failure produces an `error` event before the connection closes.** A consumer that gets silence cannot distinguish "still thinking" from "dead", and will hang forever waiting. This is a hard requirement, not a nicety.

---

## 6. `token` — what this does and does not do

`token` carries **one whole completion's content**, not individual tokens. Every provider implements real token-level streaming (`ProviderProtocol.stream()`, `providers/base.py:65-70`; concrete generators in `openai_compat.py:155`, `ollama_provider.py:144`, `vllm_provider.py:78`, `hf_tgi_provider.py:75`, `llamacpp_provider.py:75`) — but `ModelRouter.route()` (`core/model_router.py:57`) only ever calls `provider.complete()`. The streaming machinery exists and is entirely unwired.

Wiring it means changing `ModelRouter`, `model_fn`, and every pattern's loop to handle a partial response whose `tool_calls` only arrive at the end. That is a real AstroMesh feature with a blast radius across the platform, and it deserves its own spec rather than riding along in this one.

**The contract does not change when that happens.** `token` appends; a consumer that concatenates `token.content` renders identically whether it receives one chunk or forty. Real streaming later subdivides these chunks and nothing downstream needs to know.

---

## 7. Consequence: per-iteration content is now visible

In ReAct, a tool-calling iteration's `response.content` is the model's **thought**, and it is emitted as `token`.

This is not optional. Without it, all text arrives in the final iteration and every tool event precedes it — a consumer would render every component first and the narration last, inverting the order the run actually happened in.

**So this spec exposes the model's per-iteration reasoning to whoever is watching.** For an internal operator that is a feature. For an agent facing the public, it means the prompt is now load-bearing: if a prompt tells the model to reason aloud in `content`, its reasoning is on someone's screen.

**This is a requirement on consumers, recorded here so it isn't discovered later:** an agent whose run is streamed to end users must be prompted so that `content` is narration written for the reader, not private deliberation. That is prompt design, out of scope here — but this change is what makes it matter.

---

## 8. Testing

**`tests/test_run_events.py`** — `on_event` at the engine level, no HTTP. Pass `events.append` and assert on the list. This is the reason for a plain callback: the seam is testable with a list.

- events arrive in run order: (`token`? `tool_call` → `tool_result`)* — and **no `status`/`done`**, which are the transport's (§3)
- `tool_call` is emitted **before** the tool executes (assert against a tool that records when it ran)
- `tool_call.arguments` matches what the tool received; the `id` pairs with its `tool_result`
- a raising tool → `tool_result {ok: false}` and the exception still propagates
- **`on_event=None` produces byte-for-byte today's behavior** — the regression that matters most, since every existing caller passes nothing
- a callback that raises does not break the run
- empty `content` emits no `token`

**`tests/test_ws_agent.py`** — the repo's first WebSocket test (`grep -rl "websocket_connect" tests/` is empty today). Follow the shape of `tests/test_agent_channels.py`: a bare `FastAPI()`, `include_router(router, prefix="/v1")`, `set_runtime(mock_runtime)` with an `AsyncMock`, `TestClient(app)` — then `client.websocket_connect(...)` instead of `client.stream(...)`.

- a query returns `status` … `done`, and the answer is the runtime's, not an echo
- a mock runtime that calls `on_event` mid-run → the client receives those events **before** `done`
- **every queued event is delivered before `done`** — the flush race in §4
- a runtime that raises → `error`, not silence
- malformed JSON → `error`, connection survives
- disconnect mid-run does not leak the pump task

`asyncio_mode = "auto"` (`pyproject.toml`), so no `@pytest.mark.asyncio`. Tests live flat in `tests/`. Command: `uv run pytest -v` (there is **no** `--cov-fail-under` in this repo — checked `pyproject.toml`, `Makefile`, `.github/workflows/*`).

---

## 9. Security: this makes the endpoint live

Today `ws.py` is an echo. It costs nothing and does nothing. **After this change, anyone who can reach the port can run agents and spend money on model calls.**

The API surface has no auth at all: no middleware, no `Depends`, and CORS defaults to `allow_origins="*"` (`api/main.py`). That is true of `/v1/agents/{name}/run` today too — this change does not introduce the gap, but it does make the WS worth abusing.

**Auth is deliberately not added here**, for a reason that outlives this spec: the intended consumer is a public web page, and a credential shipped to a browser is not a credential. WS auth would produce the feeling of protection without protection.

Abuse belongs to the deployment. The precedent is CLARUS, which keeps `clarus-agents` as a ClusterIP service and never puts it on the Ingress. Whoever exposes this runtime owns: how it's reachable, rate limiting, and quotas. **This spec's obligation is to say so plainly rather than to leave it implied.**

---

## 10. Out of scope

- Token-level streaming (§6) — its own spec.
- Auth, rate limiting, quotas (§9) — the deployment's.
- Prompt design for public-facing agents (§7) — the consumer's.
- SSE for run events. `on_event` makes it easy later; no second consumer wants it today (YAGNI).
- The `POST /v1/agents/{name}/run` route — untouched.
