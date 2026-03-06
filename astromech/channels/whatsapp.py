import hashlib
import hmac
import httpx
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    phone_number: str
    message_text: str
    message_id: str
    timestamp: str


class WhatsAppClient:
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

    def validate_signature(self, payload: bytes, signature: str) -> bool:
        """Validate X-Hub-Signature-256 header from Meta."""
        if not self.app_secret:
            return True  # Skip validation if no secret configured
        expected = "sha256=" + hmac.new(
            self.app_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict) -> list[IncomingMessage]:
        """Parse Meta webhook payload and extract messages."""
        messages = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") == "text":
                        messages.append(IncomingMessage(
                            phone_number=msg["from"],
                            message_text=msg["text"]["body"],
                            message_id=msg["id"],
                            timestamp=msg.get("timestamp", ""),
                        ))
        return messages

    async def send_message(self, to: str, text: str) -> dict:
        """Send a text message via WhatsApp Cloud API."""
        url = f"{self.GRAPH_API_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            return resp.json()
