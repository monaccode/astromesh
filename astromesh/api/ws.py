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
        # Retrieve the task's outcome so asyncio never logs "Task exception was
        # never retrieved" for it. A clean cancellation is expected and swallowed;
        # anything else is logged, not re-raised — the exception that got us into
        # this finally (if any) is what must keep propagating, not a teardown
        # failure in the task we're cleaning up after.
        try:
            await run_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "run task raised during teardown agent=%s session=%s", agent_name, session_id
            )

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
        pass
    finally:
        # Unconditional: any exit path — a clean disconnect, a RuntimeError, a
        # cancellation, an unexpected Starlette error — must deregister the
        # socket. session_id defaults to "default", so a leak here means
        # anonymous connections pile into one list that never shrinks.
        manager.disconnect(websocket, session_id)
