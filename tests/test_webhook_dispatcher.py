"""Tests for the webhook event dispatcher and contact name enrichment."""
from __future__ import annotations

from astromesh.channels.base import ChannelMessage


def test_channel_message_contact_name_defaults_to_none():
    msg = ChannelMessage(
        sender_id="573001234567",
        text="hola",
        media=[],
        message_id="wamid.abc",
        timestamp="1712500000",
        channel="whatsapp",
        raw_payload={},
    )
    assert msg.contact_name is None


def test_channel_message_accepts_contact_name():
    msg = ChannelMessage(
        sender_id="573001234567",
        text="hola",
        media=[],
        message_id="wamid.abc",
        timestamp="1712500000",
        channel="whatsapp",
        raw_payload={},
        contact_name="Juan Pérez",
    )
    assert msg.contact_name == "Juan Pérez"
