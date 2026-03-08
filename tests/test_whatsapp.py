import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from astromesh.api.main import app
from astromesh.channels.whatsapp import WhatsAppClient
from astromesh.channels.base import ChannelMessage, MediaAttachment


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

    def test_verify_request_valid(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret123")
        client = WhatsAppClient()
        payload = b'{"test": true}'
        expected_sig = "sha256=" + hmac.new(
            b"secret123", payload, hashlib.sha256
        ).hexdigest()
        assert client.verify_request(payload, expected_sig) is True

    def test_verify_request_invalid(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_APP_SECRET", "secret123")
        client = WhatsAppClient()
        assert client.verify_request(b'{"test": true}', "sha256=bad") is False

    def test_verify_request_skips_without_secret(self):
        client = WhatsAppClient()
        client.app_secret = ""
        assert client.verify_request(b"anything", "") is True

    async def test_parse_incoming_text_message(self):
        client = WhatsAppClient()
        payload = _make_webhook_payload(phone="5511888888888", text="Hello")
        messages = await client.parse_incoming(payload)
        assert len(messages) == 1
        assert messages[0].sender_id == "5511888888888"
        assert messages[0].text == "Hello"
        assert messages[0].message_id == "wamid.abc123"
        assert messages[0].channel == "whatsapp"

    async def test_parse_incoming_image_message(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {
                    "from": "123", "id": "m1", "timestamp": "1700000000",
                    "type": "image",
                    "image": {"id": "img_123", "mime_type": "image/jpeg"},
                },
            ]}}]}],
        }
        messages = await client.parse_incoming(payload)
        assert len(messages) == 1
        assert messages[0].text is None
        assert len(messages[0].media) == 1
        assert messages[0].media[0].media_type == "image"
        assert messages[0].media[0].mime_type == "image/jpeg"
        assert messages[0].media[0].source_id == "img_123"

    async def test_parse_incoming_image_with_caption(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {
                    "from": "123", "id": "m1", "timestamp": "1700000000",
                    "type": "image",
                    "image": {
                        "id": "img_123", "mime_type": "image/jpeg",
                        "caption": "What is this?",
                    },
                },
            ]}}]}],
        }
        messages = await client.parse_incoming(payload)
        assert len(messages) == 1
        assert messages[0].text == "What is this?"
        assert len(messages[0].media) == 1

    async def test_parse_incoming_audio_message(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {
                    "from": "123", "id": "m1", "timestamp": "1700000000",
                    "type": "audio",
                    "audio": {"id": "aud_1", "mime_type": "audio/ogg"},
                },
            ]}}]}],
        }
        messages = await client.parse_incoming(payload)
        assert len(messages) == 1
        assert messages[0].media[0].media_type == "audio"
        assert messages[0].media[0].mime_type == "audio/ogg"

    async def test_parse_incoming_document_with_filename(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {
                    "from": "123", "id": "m1", "timestamp": "1700000000",
                    "type": "document",
                    "document": {
                        "id": "doc_1", "mime_type": "application/pdf",
                        "filename": "report.pdf",
                    },
                },
            ]}}]}],
        }
        messages = await client.parse_incoming(payload)
        assert len(messages) == 1
        assert messages[0].media[0].media_type == "document"
        assert messages[0].media[0].filename == "report.pdf"

    async def test_parse_incoming_ignores_unsupported_types(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {"from": "123", "id": "m1", "type": "sticker", "sticker": {}},
            ]}}]}],
        }
        messages = await client.parse_incoming(payload)
        assert messages == []

    async def test_parse_incoming_empty_payload(self):
        client = WhatsAppClient()
        assert await client.parse_incoming({}) == []
        assert await client.parse_incoming({"entry": []}) == []

    async def test_parse_incoming_multiple_messages(self):
        client = WhatsAppClient()
        payload = {
            "entry": [{"changes": [{"value": {"messages": [
                {"from": "111", "id": "m1", "timestamp": "1", "type": "text", "text": {"body": "A"}},
                {"from": "222", "id": "m2", "timestamp": "2", "type": "text", "text": {"body": "B"}},
            ]}}]}],
        }
        messages = await client.parse_incoming(payload)
        assert len(messages) == 2
        assert messages[0].sender_id == "111"
        assert messages[1].sender_id == "222"


# ---------------------------------------------------------------------------
# Webhook route tests (GET verification)
# ---------------------------------------------------------------------------

async def test_webhook_verify_success(client, monkeypatch):
    monkeypatch.setattr(
        "astromesh.api.routes.whatsapp._whatsapp.verify_token", "test-token"
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
        "astromesh.api.routes.whatsapp._whatsapp.app_secret", ""
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
        "astromesh.api.routes.whatsapp._whatsapp.app_secret", "real-secret"
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
        "astromesh.api.routes.whatsapp._whatsapp.app_secret", "my-secret"
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
        "astromesh.api.routes.whatsapp._whatsapp.app_secret", ""
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
    from astromesh.api.routes import whatsapp as whatsapp_routes

    mock_runtime = AsyncMock()
    mock_runtime.run = AsyncMock(return_value={"answer": "Hola!"})

    original_runtime = getattr(whatsapp_routes, "_runtime", None)
    whatsapp_routes._runtime = mock_runtime

    mock_send = AsyncMock(return_value={"messages": [{"id": "sent1"}]})
    original_send = whatsapp_routes._whatsapp.send_text
    whatsapp_routes._whatsapp.send_text = mock_send

    msg = ChannelMessage(
        sender_id="5511999999999",
        text="Hello",
        media=[],
        message_id="wamid.abc123",
        timestamp="1700000000",
        channel="whatsapp",
    )

    try:
        await whatsapp_routes._process_message(msg)

        mock_runtime.run.assert_called_once_with(
            agent_name="whatsapp-assistant",
            query="Hello",
            session_id="wa_5511999999999",
        )
        mock_send.assert_called_once_with("5511999999999", "Hola!")
    finally:
        whatsapp_routes._runtime = original_runtime
        whatsapp_routes._whatsapp.send_text = original_send


async def test_process_message_sends_error_on_runtime_failure():
    from astromesh.api.routes import whatsapp as whatsapp_routes

    mock_runtime = AsyncMock()
    mock_runtime.run = AsyncMock(side_effect=RuntimeError("boom"))

    original_runtime = getattr(whatsapp_routes, "_runtime", None)
    whatsapp_routes._runtime = mock_runtime

    mock_send = AsyncMock(return_value={})
    original_send = whatsapp_routes._whatsapp.send_text
    whatsapp_routes._whatsapp.send_text = mock_send

    msg = ChannelMessage(
        sender_id="5511999999999",
        text="Hello",
        media=[],
        message_id="wamid.abc123",
        timestamp="1700000000",
        channel="whatsapp",
    )

    try:
        await whatsapp_routes._process_message(msg)

        mock_send.assert_called_once_with(
            "5511999999999", "Lo siento, ocurrio un error. Intenta de nuevo."
        )
    finally:
        whatsapp_routes._runtime = original_runtime
        whatsapp_routes._whatsapp.send_text = original_send


# ---------------------------------------------------------------------------
# WhatsAppClient.send_text tests
# ---------------------------------------------------------------------------

async def test_send_text_calls_graph_api(monkeypatch):
    client = WhatsAppClient()
    client.access_token = "token123"
    client.phone_number_id = "12345"

    mock_response = AsyncMock()
    mock_response.json = lambda: {"messages": [{"id": "wamid.sent"}]}
    mock_response.raise_for_status = lambda: None

    mock_post = AsyncMock(return_value=mock_response)

    with patch("astromesh.channels.whatsapp.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post = mock_post
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await client.send_text("5511999999999", "Test message")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "12345/messages" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"]["to"] == "5511999999999"
        assert call_kwargs.kwargs["json"]["text"]["body"] == "Test message"
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer token123"
        assert result == {"messages": [{"id": "wamid.sent"}]}


# ---------------------------------------------------------------------------
# WhatsAppClient.download_media tests
# ---------------------------------------------------------------------------

async def test_download_media_two_step_fetch():
    client = WhatsAppClient()
    client.access_token = "token123"

    att = MediaAttachment(
        media_type="image",
        mime_type="image/jpeg",
        content=None,
        source_id="media_id_123",
    )

    mock_meta_resp = AsyncMock()
    mock_meta_resp.json = lambda: {"url": "https://cdn.example.com/media/file.jpg"}
    mock_meta_resp.raise_for_status = lambda: None

    mock_media_resp = AsyncMock()
    mock_media_resp.content = b"\xff\xd8\xff\xe0"
    mock_media_resp.raise_for_status = lambda: None

    with patch("astromesh.channels.whatsapp.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=[mock_meta_resp, mock_media_resp])
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await client.download_media(att)

        assert result == b"\xff\xd8\xff\xe0"
        assert instance.get.call_count == 2
        # First call: metadata endpoint
        first_call = instance.get.call_args_list[0]
        assert "media_id_123" in first_call.args[0]
        # Second call: download URL
        second_call = instance.get.call_args_list[1]
        assert second_call.args[0] == "https://cdn.example.com/media/file.jpg"
