"""The WebSocket agent endpoint: runs the agent and streams its events."""

from __future__ import annotations

import logging

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


def test_a_full_queue_drops_the_event_and_logs_a_warning(client, mock_runtime, monkeypatch, caplog):
    """The queue is bounded so a runaway loop can't grow memory without limit.

    A drop must be loud (logged), not silent, and the run must still finish
    rather than getting stuck on a full queue. The real cap (1000) would take
    an impractical number of synchronous on_event calls to reliably overflow
    in a unit test, so the constant is monkeypatched down rather than lowered
    in ws.py itself.
    """
    import astromesh.api.ws as ws_module

    monkeypatch.setattr(ws_module, "_EVENT_QUEUE_MAX", 3)

    async def run_that_floods(agent_name, query, session_id, context=None, on_event=None, **kw):
        # No awaits in this loop: on_event runs synchronously back-to-back, so
        # nothing drains the queue in between and the cap is actually hit.
        for i in range(5):
            on_event({"type": "token", "content": str(i)})
        return {"answer": "listo", "steps": [], "trace": {}}

    mock_runtime.run = AsyncMock(side_effect=run_that_floods)

    with caplog.at_level(logging.WARNING, logger="astromesh.api.ws"):
        with client.websocket_connect("/v1/ws/agent/demo") as ws:
            ws.send_json({"query": "hola"})
            events = _drain(ws)

    assert events[-1]["type"] == "done"
    dropped = [r for r in caplog.records if "queue full" in r.message]
    assert dropped, f"expected a queue-full warning, got: {[r.message for r in caplog.records]}"


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


async def test_events_stream_while_the_run_is_still_in_flight():
    """The defining property of the feature: an event reaches the socket before
    the run finishes, not all at once at the end.

    This is expressed as a handshake a batched implementation cannot fake: the
    run cannot return until the socket has already received the event it just
    emitted. A "run to completion, then drain the queue, then send done"
    implementation would await the run first and never look at the queue in
    time to unblock it — that's a deadlock, caught here by a bounded timeout
    rather than a hung suite.

    Driven directly against `_run_and_stream`, not `TestClient`: TestClient runs
    the app in a worker thread (sync-over-async), which erases exactly the
    interleaving this test depends on.
    """
    import asyncio

    from astromesh.api.ws import _run_and_stream, set_runtime as set_ws_runtime

    delivered = asyncio.Event()

    async def run_that_waits_for_delivery(agent_name, query, session_id, context=None, on_event=None, **kw):
        on_event({"type": "token", "content": "uno"})
        # Cannot return until the socket already got that event. A batched
        # implementation awaits this coroutine before ever draining the queue,
        # so against it this line hangs until the outer wait_for times out.
        await asyncio.wait_for(delivered.wait(), timeout=5)
        return {"answer": "listo", "steps": [], "trace": {}}

    rt = MagicMock()
    rt.run = AsyncMock(side_effect=run_that_waits_for_delivery)
    set_ws_runtime(rt)

    class HandshakeSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, message):
            self.sent.append(message)
            if message.get("type") == "token" and message.get("content") == "uno":
                delivered.set()

    socket = HandshakeSocket()
    try:
        await asyncio.wait_for(_run_and_stream(socket, "demo", "s1", "hola"), timeout=5)
    finally:
        set_ws_runtime(None)

    assert delivered.is_set(), "the token event never reached the socket"
    assert socket.sent[-1]["type"] == "done"


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


async def test_a_non_disconnect_exception_still_deregisters_the_socket():
    """`manager.disconnect` must run however the handler exits, not only on
    WebSocketDisconnect. session_id defaults to "default", so a leaked entry
    from any other escaping exception (a RuntimeError, a cancellation, an
    unexpected Starlette error) piles anonymous connections into one list
    that never shrinks.

    Driven directly against `agent_websocket`, not TestClient: the decorator
    just registers the route and returns the function unchanged, so it is
    callable with a bare fake socket exposing accept/receive_text/send_json.
    """
    import json as json_mod

    from astromesh.api.ws import agent_websocket, manager, set_runtime as set_ws_runtime

    rt = MagicMock()
    rt.run = AsyncMock(return_value={"answer": "listo", "steps": [], "trace": {}})
    set_ws_runtime(rt)

    class FlakySocket:
        """Answers one valid query, then blows up with something that is
        not WebSocketDisconnect — the class of exception the old handler
        never cleaned up after."""

        def __init__(self):
            self.query_params = {"session_id": "flaky"}
            self._calls = 0

        async def accept(self):
            pass

        async def receive_text(self):
            self._calls += 1
            if self._calls == 1:
                return json_mod.dumps({"query": "hola"})
            raise RuntimeError("boom")

        async def send_json(self, message):
            pass

    socket = FlakySocket()
    try:
        with pytest.raises(RuntimeError, match="boom"):
            await agent_websocket(socket, "demo")
        assert "flaky" not in manager.active_connections, (
            "the socket was never deregistered after a non-disconnect exception"
        )
    finally:
        set_ws_runtime(None)


async def test_run_task_is_retrieved_even_if_it_misbehaves_during_cancellation():
    """The `finally` in `_run_and_stream` requests `run_task.cancel()` but must
    also await it, or a run that raises something other than CancelledError
    during teardown becomes a task whose exception nobody retrieves (asyncio
    logs "Task exception was never retrieved").

    This must not change what actually propagates out of `_run_and_stream`:
    the socket failure (WebSocketDisconnect here) is still the cause, even
    though the run's own teardown also failed.
    """
    import asyncio

    from fastapi import WebSocketDisconnect

    from astromesh.api.ws import _run_and_stream, set_runtime as set_ws_runtime

    async def run_that_misbehaves_on_cancel(
        agent_name, query, session_id, context=None, on_event=None, **kw
    ):
        on_event({"type": "token", "content": "uno"})
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            # Simulates a run whose teardown itself fails, rather than
            # cleanly propagating the cancellation.
            raise RuntimeError("teardown blew up") from None
        return {"answer": "nunca llega", "steps": [], "trace": {}}

    rt = MagicMock()
    rt.run = AsyncMock(side_effect=run_that_misbehaves_on_cancel)
    set_ws_runtime(rt)

    class DyingSocket:
        def __init__(self):
            self.sends = 0

        async def send_json(self, message):
            self.sends += 1
            if self.sends >= 2:
                raise WebSocketDisconnect()

    try:
        # If the teardown await isn't caught, the RuntimeError raised inside
        # the finally block would replace this and the test would see
        # RuntimeError instead — pinning that the socket failure still wins.
        with pytest.raises(WebSocketDisconnect):
            await _run_and_stream(DyingSocket(), "demo", "s1", "hola")
    finally:
        set_ws_runtime(None)
