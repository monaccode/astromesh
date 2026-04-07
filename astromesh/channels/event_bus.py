"""Channel event bus — streams real-time in/out events to SSE subscribers."""
from __future__ import annotations

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ChannelEvent:
    id: str
    ts: str
    agent: str
    channel: str
    direction: str   # "in" | "out"
    sender: str
    text: str | None
    media: dict | None

    @classmethod
    def create(
        cls,
        agent: str,
        channel: str,
        direction: str,
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

    def emit(self, event: ChannelEvent) -> None:
        """Store in ring buffer and fan-out to all registered subscriber queues."""
        self._buffer.append(event)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow subscriber — drop

    def new_subscriber_queue(self) -> asyncio.Queue[ChannelEvent]:
        """Register and return a fresh Queue. Caller MUST call remove_subscriber when done."""
        q: asyncio.Queue[ChannelEvent] = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def remove_subscriber(self, q: asyncio.Queue[ChannelEvent]) -> None:
        """Unregister a subscriber queue."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    def get_buffer_snapshot(self) -> list[ChannelEvent]:
        """Return a copy of the current ring buffer (most recent up to buffer_size events)."""
        return list(self._buffer)


# Module-level singleton used by agent_channels.py
channel_event_bus = ChannelEventBus()
