"""Per-agent channel webhook endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from astromesh.channels.media import build_multimodal_query
from astromesh.channels.resolver import get_agent_channel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["channels"])

_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


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
        return Response(status_code=404, content=f"Agent '{agent_name}' has no {channel_type} channel configured")

    if channel_type == "whatsapp":
        result = adapter.verify_webhook(hub_mode or "", hub_token or "", hub_challenge or "")
        if result is not None:
            return Response(content=result, media_type="text/plain")
    return Response(status_code=403)


async def _process_agent_message(agent_name: str, channel_type: str, message):
    """Process incoming message for a specific agent in background."""
    try:
        adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
        if not adapter:
            logger.error("No adapter for %s/%s during message processing", agent_name, channel_type)
            return

        query = await build_multimodal_query(message, adapter)
        result = await _runtime.run(
            agent_name=agent_name,
            query=query,
            session_id=f"{channel_type}_{message.sender_id}",
        )
        answer = result.get("answer", "Sorry, I couldn't process your message.")
        await adapter.send_text(message.sender_id, answer)
    except Exception:
        logger.exception("Failed to process %s message for agent %s from %s", channel_type, agent_name, message.sender_id)
        try:
            await adapter.send_text(message.sender_id, "Sorry, an error occurred. Please try again.")
        except Exception:
            logger.exception("Failed to send error reply to %s", message.sender_id)


@router.post("/agents/{agent_name}/channels/{channel_type}/webhook")
async def receive_agent_message(
    agent_name: str,
    channel_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive incoming messages for a specific agent's channel."""
    adapter, _ = get_agent_channel(_runtime, agent_name, channel_type)
    if adapter is None:
        return Response(status_code=404, content=f"Agent '{agent_name}' has no {channel_type} channel configured")

    body = await request.body()

    # Signature verification
    if channel_type == "whatsapp":
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not adapter.verify_request(body, signature):
            return Response(status_code=403)

    payload = await request.json()
    messages = await adapter.parse_incoming(payload)

    for msg in messages:
        logger.info("%s message for agent %s from %s: %s", channel_type, agent_name, msg.sender_id, msg.message_id)
        background_tasks.add_task(_process_agent_message, agent_name, channel_type, msg)

    return {"status": "ok"}
