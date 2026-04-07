"""Per-agent channel webhook endpoints + SSE channel event stream."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from fastapi.responses import StreamingResponse

from astromesh.channels.event_bus import ChannelEvent, channel_event_bus
from astromesh.channels.media import build_multimodal_query
from astromesh.channels.resolver import get_agent_channel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["channels"])

_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


# ── Webhook verification ────────────────────────────────────────────────────

@router.get("/agents/{agent_name}/channels/{channel_type}/webhook")
async def verify_agent_webhook(
    agent_name: str,
    channel_type: str,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Webhook verification for a specific agent's channel."""
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(
            status_code=404,
            content=f"Agent '{agent_name}' has no {channel_type} channel configured",
        )
    if channel_type == "whatsapp":
        result = adapter.verify_webhook(hub_mode or "", hub_token or "", hub_challenge or "")
        if result is not None:
            return Response(content=result, media_type="text/plain")
    return Response(status_code=403)


# ── Incoming message handler ────────────────────────────────────────────────

async def _process_agent_message(agent_name: str, channel_type: str, message) -> None:
    """Process incoming channel message in background, send reply, emit out-event."""
    try:
        adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
        if not adapter:
            logger.error("No adapter for %s/%s during processing", agent_name, channel_type)
            return

        query = await build_multimodal_query(message, adapter)
        result = await _runtime.run(
            agent_name=agent_name,
            query=query,
            session_id=f"{channel_type}_{message.sender_id}",
        )
        answer = result.get("answer", "Sorry, I couldn't process your message.")
        await adapter.send_text(message.sender_id, answer)

        # Emit outgoing event
        channel_event_bus.emit(ChannelEvent.create(
            agent=agent_name,
            channel=channel_type,
            direction="out",
            sender=message.sender_id,
            text=answer,
        ))
    except Exception:
        logger.exception(
            "Failed to process %s message for agent %s from %s",
            channel_type, agent_name, message.sender_id,
        )
        try:
            await adapter.send_text(message.sender_id, "Sorry, an error occurred.")
        except Exception:
            logger.exception("Failed to send error reply to %s", message.sender_id)


@router.post("/agents/{agent_name}/channels/{channel_type}/webhook")
async def receive_agent_message(
    agent_name: str,
    channel_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive incoming channel messages, emit in-events, dispatch to agent."""
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(
            status_code=404,
            content=f"Agent '{agent_name}' has no {channel_type} channel configured",
        )

    body = await request.body()

    if channel_type == "whatsapp":
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not adapter.verify_request(body, signature):
            return Response(status_code=403)

    payload = await request.json()
    messages = await adapter.parse_incoming(payload)

    for msg in messages:
        logger.info(
            "%s message for agent %s from %s: %s",
            channel_type, agent_name, msg.sender_id, msg.message_id,
        )
        # Emit incoming event
        channel_event_bus.emit(ChannelEvent.create(
            agent=agent_name,
            channel=channel_type,
            direction="in",
            sender=msg.sender_id,
            text=msg.text,
            media=(
                {"type": msg.media[0].media_type, "url": msg.media[0].source_id}
                if msg.media else None
            ),
        ))
        background_tasks.add_task(_process_agent_message, agent_name, channel_type, msg)

    return {"status": "ok"}


# ── SSE channel event stream ────────────────────────────────────────────────

@router.get("/channels/events")
async def stream_channel_events(request: Request, agent: str | None = Query(None)):
    """SSE stream of channel in/out events.

    Connect with ?agent=<name> to filter to a specific agent.
    Replays the last 100 buffered events on connect, then streams live.
    Sends a keepalive comment every 15 s to prevent proxy timeouts.
    """

    async def generate():
        q = channel_event_bus.new_subscriber_queue()
        try:
            # Replay buffer for late-joining subscribers.
            for event in channel_event_bus.get_buffer_snapshot():
                if agent is None or event.agent == agent:
                    yield f"data: {json.dumps(dataclasses.asdict(event))}\n\n"

            # Stream live events.  Poll with a short inner timeout so that
            # a) disconnect is noticed promptly (Starlette sets is_disconnected via
            #    a cancelled CancelScope which always returns False in TestClient,
            #    so we rely on the outer keepalive / idle-exit mechanism instead), and
            # b) the generator terminates gracefully in test environments where the
            #    HTTP transport never sends a real disconnect signal.
            #
            # Pattern: try to dequeue for up to POLL_INTERVAL seconds; if nothing
            # arrives for IDLE_EXIT_AFTER consecutive polls, close the stream so
            # the EventSource client can reconnect.  Between reconnects the ring
            # buffer preserves all events, so no data is lost.
            # Tune via env vars for production vs. test environments.
            import os
            POLL_INTERVAL = float(os.getenv("ASTROMESH_SSE_POLL_INTERVAL", "1.0"))
            KEEPALIVE_EVERY = int(os.getenv("ASTROMESH_SSE_KEEPALIVE_EVERY", "15"))
            IDLE_EXIT_AFTER = int(os.getenv("ASTROMESH_SSE_IDLE_EXIT_AFTER", "30"))

            idle_ticks = 0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=POLL_INTERVAL)
                    idle_ticks = 0
                except asyncio.TimeoutError:
                    idle_ticks += 1
                    if idle_ticks % KEEPALIVE_EVERY == 0:
                        yield ": keepalive\n\n"
                    if idle_ticks >= IDLE_EXIT_AFTER:
                        # Let the client reconnect; buffer preserves recent events.
                        break
                    continue
                if agent is None or event.agent == agent:
                    yield f"data: {json.dumps(dataclasses.asdict(event))}\n\n"
                    idle_ticks = 0
        finally:
            channel_event_bus.remove_subscriber(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
