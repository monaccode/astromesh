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


import pytest
from unittest.mock import AsyncMock, patch

from astromesh.channels.webhook_dispatcher import (
    WebhookEventDispatcher,
    DefaultWebhookEventHandler,
    StatusUpdateHandler,
)


@pytest.mark.asyncio
async def test_dispatcher_uses_default_for_unknown_field():
    dispatcher = WebhookEventDispatcher()
    default_mock = AsyncMock()
    dispatcher._default = default_mock
    await dispatcher.dispatch("account_update", {"foo": "bar"}, "my-agent")
    default_mock.handle.assert_called_once_with("account_update", {"foo": "bar"}, "my-agent")


@pytest.mark.asyncio
async def test_dispatcher_uses_registered_handler():
    dispatcher = WebhookEventDispatcher()
    custom_handler = AsyncMock()
    dispatcher.register("flows", custom_handler)
    await dispatcher.dispatch("flows", {"data": 1}, "my-agent")
    custom_handler.handle.assert_called_once_with("flows", {"data": 1}, "my-agent")


@pytest.mark.asyncio
async def test_status_update_handler_emits_system_event(monkeypatch):
    mock_emit = AsyncMock()
    monkeypatch.setattr(
        "astromesh.channels.webhook_dispatcher.channel_event_bus.emit", mock_emit
    )
    handler = StatusUpdateHandler()
    value = {
        "statuses": [
            {"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}
        ]
    }
    await handler.handle("statuses", value, "my-agent")
    mock_emit.assert_called_once()
    event = mock_emit.call_args[0][0]
    assert event.direction == "system"
    assert "delivered" in event.text


@pytest.mark.asyncio
async def test_default_handler_emits_system_event(monkeypatch):
    mock_emit = AsyncMock()
    monkeypatch.setattr(
        "astromesh.channels.webhook_dispatcher.channel_event_bus.emit", mock_emit
    )
    handler = DefaultWebhookEventHandler()
    await handler.handle("account_update", {}, "my-agent")
    mock_emit.assert_called_once()
    event = mock_emit.call_args[0][0]
    assert event.direction == "system"
    assert "account_update" in event.text


@pytest.mark.asyncio
async def test_dispatcher_has_status_handler_preregistered():
    dispatcher = WebhookEventDispatcher()
    assert "statuses" in dispatcher._handlers
    assert isinstance(dispatcher._handlers["statuses"], StatusUpdateHandler)
