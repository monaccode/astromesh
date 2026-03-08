"""WhatsApp channel webhook handler."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response

from astromesh.channels.whatsapp import WhatsAppClient
from astromesh.channels.media import build_multimodal_query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["channels"])

_whatsapp = WhatsAppClient()
_default_agent = "whatsapp-assistant"  # TODO: make configurable

_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


@router.get("/channels/whatsapp/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification endpoint."""
    result = _whatsapp.verify_webhook(hub_mode or "", hub_token or "", hub_challenge or "")
    if result is not None:
        return Response(content=result, media_type="text/plain")
    return Response(status_code=403)


async def _process_message(message):
    """Process incoming ChannelMessage in background."""
    try:
        # Download media and build the query (str or multimodal list).
        query = await build_multimodal_query(message, _whatsapp)
        result = await _runtime.run(
            agent_name=_default_agent,
            query=query,
            session_id=f"wa_{message.sender_id}",
        )
        answer = result.get("answer", "Lo siento, no pude procesar tu mensaje.")
        await _whatsapp.send_text(message.sender_id, answer)
    except Exception:
        logger.exception("Failed to process WhatsApp message from %s", message.sender_id)
        try:
            await _whatsapp.send_text(
                message.sender_id, "Lo siento, ocurrio un error. Intenta de nuevo."
            )
        except Exception:
            logger.exception("Failed to send error message to %s", message.sender_id)


@router.post("/channels/whatsapp/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """Receive incoming WhatsApp messages from Meta webhook."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not _whatsapp.verify_request(body, signature):
        return Response(status_code=403)

    payload = await request.json()
    messages = await _whatsapp.parse_incoming(payload)

    for msg in messages:
        logger.info("WhatsApp message from %s: %s", msg.sender_id, msg.message_id)
        background_tasks.add_task(_process_message, msg)

    return {"status": "ok"}
