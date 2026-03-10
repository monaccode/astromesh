"""Base channel abstraction for all messaging integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MediaAttachment:
    """A media item attached to an incoming channel message."""

    media_type: str  # "image", "audio", "video", "document"
    mime_type: str  # "image/jpeg", "audio/ogg", etc.
    content: bytes | None  # Raw downloaded bytes (None if not yet fetched)
    source_id: str  # Channel-specific media ID (e.g. WhatsApp media ID)
    filename: str | None = None  # Original filename if available


@dataclass
class ChannelMessage:
    """Channel-agnostic representation of an incoming message."""

    sender_id: str  # Channel-specific user ID (phone number, user ID, etc.)
    text: str | None  # Text content (may be None for media-only messages)
    media: list[MediaAttachment]  # Attached media items
    message_id: str  # Channel-specific message ID
    timestamp: str
    channel: str  # "whatsapp", "telegram", etc.
    raw_payload: dict = field(default_factory=dict)  # Original payload for debugging


class ChannelAdapter(ABC):
    """Base class for all channel integrations."""

    @abstractmethod
    async def parse_incoming(self, payload: dict) -> list[ChannelMessage]:
        """Parse a raw webhook payload into channel messages."""
        ...

    @abstractmethod
    async def send_text(self, recipient_id: str, text: str) -> dict:
        """Send a text message to a recipient."""
        ...

    @abstractmethod
    async def download_media(self, attachment: MediaAttachment) -> bytes:
        """Download media bytes for an attachment."""
        ...

    @abstractmethod
    def verify_request(self, payload: bytes, signature: str) -> bool:
        """Verify the authenticity of an incoming webhook request."""
        ...
