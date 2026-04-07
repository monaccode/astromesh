"""Tests for per-agent channel endpoints and resolver."""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock

from astromesh.channels.resolver import resolve_env_vars, get_channel_adapter


def test_resolve_env_vars_replaces_references(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret123")
    config = {"access_token": "${MY_TOKEN}", "static": "plain"}
    result = resolve_env_vars(config)
    assert result["access_token"] == "secret123"
    assert result["static"] == "plain"


def test_resolve_env_vars_missing_var_stays_empty():
    config = {"token": "${NONEXISTENT_VAR_XYZ}"}
    result = resolve_env_vars(config)
    assert result["token"] == ""


def test_get_channel_adapter_whatsapp(monkeypatch):
    monkeypatch.setenv("WA_TOKEN", "tok")
    monkeypatch.setenv("WA_PHONE", "123")
    monkeypatch.setenv("WA_SECRET", "sec")
    monkeypatch.setenv("WA_VERIFY", "ver")

    channel_spec = {
        "type": "whatsapp",
        "config": {
            "access_token": "${WA_TOKEN}",
            "phone_number_id": "${WA_PHONE}",
            "app_secret": "${WA_SECRET}",
            "verify_token": "${WA_VERIFY}",
        },
    }
    adapter = get_channel_adapter(channel_spec)
    assert adapter is not None
    assert adapter.access_token == "tok"
    assert adapter.phone_number_id == "123"
    assert adapter.verify_token == "ver"


def test_get_channel_adapter_unknown_type():
    adapter = get_channel_adapter({"type": "slack", "config": {}})
    assert adapter is None


from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from astromesh.api.routes.agent_channels import router, set_runtime


@pytest.fixture
def mock_runtime():
    rt = MagicMock()
    rt._agent_configs = {
        "test-agent": {
            "spec": {
                "channels": [
                    {
                        "type": "whatsapp",
                        "config": {
                            "access_token": "test-token",
                            "phone_number_id": "12345",
                            "app_secret": "",
                            "verify_token": "my-verify",
                        },
                    }
                ]
            }
        }
    }
    rt.run = AsyncMock(return_value={"answer": "Hello!"})
    return rt


@pytest.fixture
def client(mock_runtime):
    from fastapi import FastAPI
    from astromesh.channels.resolver import clear_cache

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    set_runtime(mock_runtime)
    clear_cache()
    return TestClient(app)


def test_webhook_verify(client):
    resp = client.get(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my-verify",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge123"


def test_webhook_verify_wrong_token(client):
    resp = client.get(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 403


def test_webhook_verify_unknown_agent(client):
    resp = client.get(
        "/v1/agents/nonexistent/channels/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my-verify",
            "hub.challenge": "challenge123",
        },
    )
    assert resp.status_code == 404


# ── SSE endpoint tests ─────────────────────────────────────────────────────

from astromesh.channels.event_bus import channel_event_bus, ChannelEvent as BusEvent


@pytest.fixture(autouse=False)
def clean_bus():
    """Reset event bus state between tests."""
    channel_event_bus._buffer.clear()
    channel_event_bus._subscribers.clear()
    yield
    channel_event_bus._buffer.clear()
    channel_event_bus._subscribers.clear()


def test_sse_endpoint_exists_and_returns_event_stream(client, clean_bus):
    """GET /v1/channels/events should return 200 text/event-stream."""
    with client.stream("GET", "/v1/channels/events") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


def test_sse_replays_buffered_events(client, clean_bus):
    """Events in the buffer should be replayed immediately on SSE connect."""
    channel_event_bus.emit(BusEvent.create(
        agent="test-agent", channel="whatsapp", direction="in",
        sender="+1", text="buffered",
    ))

    import json
    with client.stream("GET", "/v1/channels/events") as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:].strip())
                assert evt["text"] == "buffered"
                break


def test_sse_agent_filter(client, clean_bus):
    """?agent= filter should only replay matching events."""
    channel_event_bus.emit(BusEvent.create(
        agent="bot-a", channel="whatsapp", direction="in", sender="+1", text="a",
    ))
    channel_event_bus.emit(BusEvent.create(
        agent="bot-b", channel="whatsapp", direction="in", sender="+2", text="b",
    ))

    import json
    lines_seen = []
    with client.stream("GET", "/v1/channels/events?agent=bot-a") as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                evt = json.loads(line[5:].strip())
                lines_seen.append(evt["agent"])
                break

    assert lines_seen == ["bot-a"]


# ── Two-phase dispatcher tests ─────────────────────────────────────────────

from unittest.mock import AsyncMock


def test_contact_name_extracted_and_set_on_message(client, mock_runtime, mocker):
    """Contact name from contacts[] is set on the ChannelMessage before processing."""
    captured_messages = []

    def capture_task(func, *args, **kwargs):
        # args = (agent_name, channel_type, msg)
        if len(args) >= 3:
            captured_messages.append(args[2])  # the ChannelMessage

    mocker.patch(
        "astromesh.api.routes.agent_channels.BackgroundTasks.add_task",
        side_effect=capture_task,
    )

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"profile": {"name": "Juan Pérez"}, "wa_id": "573001234567"}],
                    "messages": [{
                        "from": "573001234567",
                        "id": "wamid.test123",
                        "timestamp": "1712500000",
                        "type": "text",
                        "text": {"body": "hola"},
                    }],
                },
            }],
        }],
    }
    resp = client.post(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    assert len(captured_messages) == 1
    assert captured_messages[0].contact_name == "Juan Pérez"


def test_status_update_dispatched_not_sent_to_agent(client, mock_runtime, mocker):
    """Payloads with only statuses[] go to dispatcher, never to the agent."""
    mock_dispatch = mocker.patch(
        "astromesh.api.routes.agent_channels.webhook_dispatcher.dispatch",
        new_callable=AsyncMock,
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "statuses": [
                        {"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}
                    ],
                },
            }],
        }],
    }
    resp = client.post(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    mock_runtime.run.assert_not_called()
    mock_dispatch.assert_called_once_with(
        "statuses",
        {"statuses": [{"status": "delivered", "recipient_id": "573001234567", "id": "wamid.abc"}]},
        "test-agent",
    )


def test_unknown_field_dispatched(client, mock_runtime, mocker):
    """Non-messages fields go to dispatcher."""
    mock_dispatch = mocker.patch(
        "astromesh.api.routes.agent_channels.webhook_dispatcher.dispatch",
        new_callable=AsyncMock,
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "account_update", "value": {"event": "VERIFIED_ACCOUNT"}}]}],
    }
    resp = client.post(
        "/v1/agents/test-agent/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=bypass"},
    )
    assert resp.status_code == 200
    mock_runtime.run.assert_not_called()
    mock_dispatch.assert_called_once_with(
        "account_update",
        {"event": "VERIFIED_ACCOUNT"},
        "test-agent",
    )
