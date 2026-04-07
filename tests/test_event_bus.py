"""Tests for ChannelEventBus."""
from __future__ import annotations

import asyncio
import pytest
from astromesh.channels.event_bus import ChannelEvent, ChannelEventBus


def _evt(agent: str = "bot", direction: str = "in") -> ChannelEvent:
    return ChannelEvent.create(
        agent=agent,
        channel="whatsapp",
        direction=direction,
        sender="+1234567890",
        text="hello",
    )


def test_event_create_has_required_fields():
    evt = ChannelEvent.create(
        agent="mybot", channel="whatsapp", direction="out",
        sender="+9876543210", text="Hi!", media={"type": "image", "url": "http://x"},
    )
    assert evt.agent == "mybot"
    assert evt.direction == "out"
    assert evt.media == {"type": "image", "url": "http://x"}
    assert evt.id  # non-empty UUID
    assert evt.ts  # non-empty ISO timestamp


def test_buffer_max_size():
    bus = ChannelEventBus(buffer_size=3)
    for _ in range(5):
        bus.emit(_evt())
    assert len(bus._buffer) == 3


def test_get_buffer_snapshot_returns_copy():
    bus = ChannelEventBus()
    bus.emit(_evt(agent="a"))
    snapshot = bus.get_buffer_snapshot()
    assert len(snapshot) == 1
    snapshot.clear()
    assert len(bus._buffer) == 1  # original unaffected


def test_new_subscriber_queue_receives_future_events():
    bus = ChannelEventBus()
    q = bus.new_subscriber_queue()
    bus.emit(_evt(agent="x"))
    assert not q.empty()
    evt = q.get_nowait()
    assert evt.agent == "x"


def test_remove_subscriber_stops_delivery():
    bus = ChannelEventBus()
    q = bus.new_subscriber_queue()
    bus.remove_subscriber(q)
    bus.emit(_evt())
    assert q.empty()


def test_remove_subscriber_idempotent():
    bus = ChannelEventBus()
    q = bus.new_subscriber_queue()
    bus.remove_subscriber(q)
    bus.remove_subscriber(q)  # should not raise
