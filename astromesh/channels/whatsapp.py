import hashlib
import hmac
import httpx
import logging
import os

from astromesh.channels.base import ChannelAdapter, ChannelMessage, MediaAttachment

logger = logging.getLogger(__name__)

# WhatsApp media type to generic media type mapping.
_WA_MEDIA_TYPES = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "document": "document",
}


class WhatsAppClient(ChannelAdapter):
    GRAPH_API_URL = "https://graph.facebook.com/v21.0"

    def __init__(self):
        self.verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        self.access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.app_secret = os.environ.get("WHATSAPP_APP_SECRET", "")

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Verify Meta webhook subscription. Returns challenge if valid, None otherwise."""
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        return None

    def verify_request(self, payload: bytes, signature: str) -> bool:
        """Validate X-Hub-Signature-256 header from Meta."""
        if not self.app_secret:
            return True  # Skip validation if no secret configured
        expected = (
            "sha256=" + hmac.new(self.app_secret.encode(), payload, hashlib.sha256).hexdigest()
        )
        return hmac.compare_digest(expected, signature)

    async def parse_incoming(self, value: dict) -> list[ChannelMessage]:
        """Parse a single ``change["value"]`` dict into ChannelMessages.

        Args:
            value: The ``change["value"]`` dict from a Meta webhook entry.
                   Contains ``messages``, ``contacts``, ``statuses``, etc.
                   The caller (webhook endpoint) is responsible for iterating
                   ``entry[].changes[]`` and passing each value here.

        Returns:
            List of parsed ChannelMessage objects (text and/or media).
            Unsupported message types (sticker, reaction, etc.) are silently skipped.
        """
        messages: list[ChannelMessage] = []
        for msg in value.get("messages", []):
            msg_type = msg.get("type", "")
            text: str | None = None
            media: list[MediaAttachment] = []

            if msg_type == "text":
                text = msg["text"]["body"]
            elif msg_type in _WA_MEDIA_TYPES:
                media_data = msg.get(msg_type, {})
                media.append(
                    MediaAttachment(
                        media_type=_WA_MEDIA_TYPES[msg_type],
                        mime_type=media_data.get("mime_type", f"{msg_type}/*"),
                        content=None,
                        source_id=media_data.get("id", ""),
                        filename=media_data.get("filename"),
                    )
                )
                caption = media_data.get("caption")
                if caption:
                    text = caption
            else:
                continue  # Skip unsupported types (sticker, reaction, interactive, etc.)

            messages.append(
                ChannelMessage(
                    sender_id=msg["from"],
                    text=text,
                    media=media,
                    message_id=msg["id"],
                    timestamp=msg.get("timestamp", ""),
                    channel="whatsapp",
                    raw_payload=msg,
                )
            )
        return messages

    async def send_text(self, recipient_id: str, text: str) -> dict:
        """Send a text message via WhatsApp Cloud API."""
        url = f"{self.GRAPH_API_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": text},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def download_media(self, attachment: MediaAttachment) -> bytes:
        """Download media from WhatsApp via the Graph API.

        Two-step process: first retrieve the download URL, then fetch the bytes.
        Media URLs expire after ~5 minutes.
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            # Step 1: Get the download URL.
            meta_resp = await client.get(
                f"{self.GRAPH_API_URL}/{attachment.source_id}",
                headers=headers,
            )
            meta_resp.raise_for_status()
            download_url = meta_resp.json()["url"]

            # Step 2: Download the actual media bytes.
            media_resp = await client.get(download_url, headers=headers)
            media_resp.raise_for_status()
            return media_resp.content
