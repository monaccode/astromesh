import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from astromech.api.main import app
from astromech.channels.whatsapp import WhatsAppClient, IncomingMessage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_webhook_payload(phone="5511999999999", text="Hola", msg_id="wamid.abc123"):
    """Build a minimal Meta Cloud API webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "BIZ_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": phone,
                        "id": msg_id,
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
                "field": "messages",
            }],
        }],
    }


# ---------------------------------------------------------------------------
# WhatsAppClient unit tests
# ---------------------------------------------------------------------------

class TestWhatsAppClient:

    def test_verify_webhook_valid(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-token")
        client = WhatsAppClient()
        result = client.verify_webhook("subscribe", "my-token", "challenge123")
        assert result == "challenge123"

    def test_verify_webhook_invalid_token(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-token")
        client = WhatsAppClient()
        assert client.verify_webhook("subscribe", "wrong", "challenge123") is None

    def test_verify_webhook_invalid_mode(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "my-token")
        client = WhatsAppClient()
        assert client.verify_webhook("unsubscribe", "my-token", "challenge123") is None

    def test_validate_signature_valid(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret123")
        client = WhatsAppClient()
        payload = b'{"test": true}'
        expected_sig = "sha256=" + hmac.new(
            b"secret123", payload, hashlib.sha256
        ).hexdigest()
        assert client.validate_signature(payload, expected_sig) is True

    def test_validate_signature_invalid(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret123")
        client = WhatsAppClient()
        assert client.validate_signature(b'{"test": true}', "sha256=bad") is False

    def test_validate_signature_skips_without_secret(self):
        client = WhatsAppClient()
        client.app_secret = ""
        assert client.validate_signature(b"anything", "") is True

    def test_parse_webhook_text_message(self):
        client = WhatsAppClient()
        payload = _make_webhook_payload(phone="5511888888888", text="Hello")
        messages = client.parse_webhook(payload)
        assert len(messages) == 1
        assert messages[0].phone_number == "5511888888888"
        assert messages[0].message_text == "Hello"
        assert messages[0].message_id == "wamid.abc123"

    def test_parse_webhook_ignores_non_text(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {"from": "123", "id": "m1", "type": "image", "image": {}},
            ]}}]}],
        }
        assert client.parse_webhook(payload) == []

    def test_parse_webhook_empty_payload(self):
        client = WhatsAppClient()
        assert client.parse_webhook({}) == []
        assert client.parse_webhook({"entry": []}) == []

    def test_parse_webhook_multiple_messages(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {"from": "111", "id": "m1", "timestamp": "1", "type": "text", "text": {"body": "A"}},
                {"from": "222", "id": "m2", "timestamp": "2", "type": "text", "text": {"body": "B"}},
            ]}}]}],
        }
        messages = client.parse_webhook(payload)
        assert len(messages) == 2
        assert messages[0].phone_number == "111"
        assert messages[1].phone_number == "222"


# ---------------------------------------------------------------------------
# Webhook route tests (GET verification)
# ---------------------------------------------------------------------------

async def test_webhook_verify_success(client, monkeypatch):
    monkeypatch.setattr(
        "astromech.api.routes.whatsapp._whatsapp.verify_token", "test-token"
    )
    resp = await client.get("/v1/channels/whatsapp/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "test-token",
        "hub.challenge": "challenge_abc",
    })
    assert resp.status_code == 200
    assert resp.text == "challenge_abc"


async def test_webhook_verify_failure(client):
    resp = await client.get("/v1/channels/whatsapp/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong-token",
        "hub.challenge": "challenge_abc",
    })
    assert resp.status_code == 403


async def test_webhook_verify_missing_params(client):
    resp = await client.get("/v1/channels/whatsapp/webhook")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Webhook route tests (POST incoming messages)
# ---------------------------------------------------------------------------

async def test_webhook_post_valid_message(client, monkeypatch):
    """POST with valid payload returns 200 and schedules background task."""
    monkeypatch.setattr(
        "astromech.api.routes.whatsapp._whatsapp.app_secret", ""
    )
    payload = _make_webhook_payload()
    resp = await client.post(
        "/v1/channels/whatsapp/webhook",
        json=payload,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_webhook_post_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(
        "astromech.api.routes.whatsapp._whatsapp.app_secret", "real-secret"
    )
    payload = _make_webhook_payload()
    resp = await client.post(
        "/v1/channels/whatsapp/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    assert resp.status_code == 403


async def test_webhook_post_valid_signature(client, monkeypatch):
    monkeypatch.setattr(
        "astromech.api.routes.whatsapp._whatsapp.app_secret", "my-secret"
    )
    payload = _make_webhook_payload()
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"my-secret", body, hashlib.sha256).hexdigest()
    resp = await client.post(
        "/v1/channels/whatsapp/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200


async def test_webhook_post_empty_messages(client, monkeypatch):
    monkeypatch.setattr(
        "astromech.api.routes.whatsapp._whatsapp.app_secret", ""
    )
    resp = await client.post(
        "/v1/channels/whatsapp/webhook",
        json={"entry": []},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Background processing tests
# ---------------------------------------------------------------------------

async def test_process_message_calls_runtime_and_sends_reply():
    from astromech.api.routes import whatsapp as whatsapp_routes

    mock_runtime = AsyncMock()
    mock_runtime.run = AsyncMock(return_value={"answer": "Hola!"})

    original_runtime = getattr(whatsapp_routes, "_runtime", None)
    whatsapp_routes._runtime = mock_runtime

    mock_send = AsyncMock(return_value={"messages": [{"id": "sent1"}]})
    original_send = whatsapp_routes._whatsapp.send_message
    whatsapp_routes._whatsapp.send_message = mock_send

    try:
        await whatsapp_routes._process_message("5511999999999", "Hello")

        mock_runtime.run.assert_called_once_with(
            agent_name="whatsapp-assistant",
            query="Hello",
            session_id="wa_5511999999999",
        )
        mock_send.assert_called_once_with("5511999999999", "Hola!")
    finally:
        whatsapp_routes._runtime = original_runtime
        whatsapp_routes._whatsapp.send_message = original_send


async def test_process_message_sends_error_on_runtime_failure():
    from astromech.api.routes import whatsapp as whatsapp_routes

    mock_runtime = AsyncMock()
    mock_runtime.run = AsyncMock(side_effect=RuntimeError("boom"))

    original_runtime = getattr(whatsapp_routes, "_runtime", None)
    whatsapp_routes._runtime = mock_runtime

    mock_send = AsyncMock(return_value={})
    original_send = whatsapp_routes._whatsapp.send_message
    whatsapp_routes._whatsapp.send_message = mock_send

    try:
        await whatsapp_routes._process_message("5511999999999", "Hello")

        mock_send.assert_called_once_with(
            "5511999999999", "Lo siento, ocurrio un error. Intenta de nuevo."
        )
    finally:
        whatsapp_routes._runtime = original_runtime
        whatsapp_routes._whatsapp.send_message = original_send


# ---------------------------------------------------------------------------
# WhatsAppClient.send_message tests
# ---------------------------------------------------------------------------

async def test_send_message_calls_graph_api(monkeypatch):
    client = WhatsAppClient()
    client.access_token = "token123"
    client.phone_number_id = "12345"

    mock_response = AsyncMock()
    mock_response.json = lambda: {"messages": [{"id": "wamid.sent"}]}
    mock_response.raise_for_status = lambda: None

    mock_post = AsyncMock(return_value=mock_response)

    with patch("astromech.channels.whatsapp.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post = mock_post
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await client.send_message("5511999999999", "Test message")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "12345/messages" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"]["to"] == "5511999999999"
        assert call_kwargs.kwargs["json"]["text"]["body"] == "Test message"
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer token123"
        assert result == {"messages": [{"id": "wamid.sent"}]}
