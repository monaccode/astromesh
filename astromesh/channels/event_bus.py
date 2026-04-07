"""Channel event bus — streams real-time in/out events to SSE subscribers."""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class ChannelEvent:
    id: str
    ts: str
    agent: str
    channel: str
    direction: Literal["in", "out"]
    sender: str
    text: str | None
    media: dict | None

    @classmethod
    def create(
        cls,
        agent: str,
        channel: str,
        direction: Literal["in", "out"],
        sender: str,
        text: str | None = None,
        media: dict | None = None,
    ) -> "ChannelEvent":
        return cls(
            id=str(uuid.uuid4()),
            ts=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            channel=channel,
            direction=direction,
            sender=sender,
            text=text,
            media=media,
        )


class ChannelEventBus:
    def __init__(self, buffer_size: int = 100) -> None:
        self._buffer: deque[ChannelEvent] = deque(maxlen=buffer_size)
        self._subscribers: list[asyncio.Queue[ChannelEvent]] = []
        self._lock = threading.Lock()

    def emit(self, event: ChannelEvent) -> None:
        """Store in ring buffer and fan-out to all registered subscriber queues."""
        with self._lock:
            self._buffer.append(event)
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("Subscriber queue full — dropping event for agent=%s", event.agent)

    def new_subscriber_queue(self) -> asyncio.Queue[ChannelEvent]:
        """Register and return a fresh Queue. Caller MUST call remove_subscriber when done."""
        q: asyncio.Queue[ChannelEvent] = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(q)
        return q

    def remove_subscriber(self, q: asyncio.Queue[ChannelEvent]) -> None:
        """Unregister a subscriber queue."""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def get_buffer_snapshot(self) -> list[ChannelEvent]:
        """Return a copy of the current ring buffer (most recent up to buffer_size events)."""
        return list(self._buffer)


# Module-level singleton used by agent_channels.py
channel_event_bus = ChannelEventBus()
