"""Utilities for converting channel messages to LLM-compatible queries."""

from __future__ import annotations

import base64
import logging

from astromesh.channels.base import ChannelAdapter, ChannelMessage

logger = logging.getLogger(__name__)

# Media types that can be sent as vision content to multimodal LLMs.
_VISION_MIME_PREFIXES = ("image/",)


async def build_multimodal_query(
    message: ChannelMessage,
    adapter: ChannelAdapter,
) -> str | list[dict]:
    """Convert a ChannelMessage into an LLM-compatible query.

    Returns a plain ``str`` for text-only messages (backward compatible) or a
    ``list[dict]`` in OpenAI *content* format for messages that include images.

    Audio, video, and document attachments cannot be sent to vision models
    directly, so they are represented as a text description that informs the
    agent about the attached media.
    """
    if not message.media:
        return message.text or ""

    content_parts: list[dict] = []

    # Add text part if present.
    if message.text:
        content_parts.append({"type": "text", "text": message.text})

    for attachment in message.media:
        # Download media bytes if not yet fetched.
        if attachment.content is None:
            try:
                attachment.content = await adapter.download_media(attachment)
            except Exception:
                logger.warning(
                    "Failed to download media %s (%s), skipping",
                    attachment.source_id,
                    attachment.media_type,
                )
                content_parts.append({
                    "type": "text",
                    "text": f"[Attached {attachment.media_type}: download failed]",
                })
                continue

        if attachment.mime_type.startswith(_VISION_MIME_PREFIXES[0]):
            # Images → base64 data URL for vision models.
            b64 = base64.b64encode(attachment.content).decode()
            data_url = f"data:{attachment.mime_type};base64,{b64}"
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        else:
            # Non-image media → text description so the agent is aware.
            desc = f"[Attached {attachment.media_type}: {attachment.mime_type}"
            if attachment.filename:
                desc += f", filename={attachment.filename}"
            desc += f", {len(attachment.content)} bytes]"
            content_parts.append({"type": "text", "text": desc})

    # If we ended up with only text parts (no images were successfully processed),
    # collapse back to a plain string for backward compatibility.
    if all(p["type"] == "text" for p in content_parts):
        return " ".join(p["text"] for p in content_parts)

    return content_parts
