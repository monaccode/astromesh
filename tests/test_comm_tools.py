"""Tests for communication tools: send_webhook, send_slack, send_email."""

import respx
import httpx
from astromesh.tools.base import ToolContext


def _ctx(**kwargs):
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestSendWebhookTool:
    @respx.mock
    async def test_send_webhook(self):
        from astromesh.tools.builtin.communication import SendWebhookTool

        respx.post("https://hooks.example.com/trigger").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        tool = SendWebhookTool()
        result = await tool.execute(
            {"url": "https://hooks.example.com/trigger", "payload": {"message": "Hello"}},
            _ctx(),
        )
        assert result.success is True
        assert result.data["status_code"] == 200

    @respx.mock
    async def test_send_webhook_with_custom_headers(self):
        from astromesh.tools.builtin.communication import SendWebhookTool

        respx.post("https://hooks.example.com/trigger").mock(
            return_value=httpx.Response(201, text="created")
        )
        tool = SendWebhookTool()
        result = await tool.execute(
            {
                "url": "https://hooks.example.com/trigger",
                "payload": {"event": "test"},
                "headers": {"X-Custom": "value"},
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["status_code"] == 201

    @respx.mock
    async def test_send_webhook_network_error(self):
        from astromesh.tools.builtin.communication import SendWebhookTool

        respx.post("https://hooks.example.com/fail").mock(side_effect=httpx.ConnectError("refused"))
        tool = SendWebhookTool()
        result = await tool.execute(
            {"url": "https://hooks.example.com/fail", "payload": {}},
            _ctx(),
        )
        assert result.success is False
        assert result.error is not None

    @respx.mock
    async def test_send_webhook_metadata_contains_url(self):
        from astromesh.tools.builtin.communication import SendWebhookTool

        url = "https://hooks.example.com/trigger"
        respx.post(url).mock(return_value=httpx.Response(200, text="ok"))
        tool = SendWebhookTool()
        result = await tool.execute({"url": url, "payload": {}}, _ctx())
        assert result.metadata["url"] == url


class TestSendSlackTool:
    @respx.mock
    async def test_send_slack_webhook(self):
        from astromesh.tools.builtin.communication import SendSlackTool

        respx.post("https://hooks.slack.com/services/T/B/X").mock(
            return_value=httpx.Response(200, text="ok")
        )
        tool = SendSlackTool(config={"webhook_url": "https://hooks.slack.com/services/T/B/X"})
        result = await tool.execute({"message": "Hello Slack!"}, _ctx())
        assert result.success is True

    @respx.mock
    async def test_send_slack_via_secret(self):
        from astromesh.tools.builtin.communication import SendSlackTool

        respx.post("https://hooks.slack.com/services/T/B/Y").mock(
            return_value=httpx.Response(200, text="ok")
        )
        tool = SendSlackTool()
        ctx = _ctx(secrets={"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/Y"})
        result = await tool.execute({"message": "Hello via secret!"}, ctx)
        assert result.success is True

    async def test_send_slack_no_webhook_configured(self):
        from astromesh.tools.builtin.communication import SendSlackTool

        tool = SendSlackTool(config={})
        result = await tool.execute({"message": "Hello"}, _ctx())
        assert result.success is False
        assert result.error is not None

    @respx.mock
    async def test_send_slack_network_error(self):
        from astromesh.tools.builtin.communication import SendSlackTool

        respx.post("https://hooks.slack.com/services/T/B/Z").mock(
            side_effect=httpx.ConnectError("refused")
        )
        tool = SendSlackTool(config={"webhook_url": "https://hooks.slack.com/services/T/B/Z"})
        result = await tool.execute({"message": "Hello"}, _ctx())
        assert result.success is False


class TestSendEmailTool:
    async def test_missing_smtp_config(self):
        from astromesh.tools.builtin.communication import SendEmailTool

        tool = SendEmailTool(config={})
        result = await tool.execute(
            {"to": "user@example.com", "subject": "Test", "body": "Hello"}, _ctx()
        )
        assert result.success is False
        assert "smtp" in result.error.lower()

    async def test_missing_smtp_config_no_secret(self):
        from astromesh.tools.builtin.communication import SendEmailTool

        tool = SendEmailTool()
        result = await tool.execute(
            {"to": "a@b.com", "subject": "Hi", "body": "Body"}, _ctx(secrets={})
        )
        assert result.success is False

    async def test_smtp_sends_message(self, monkeypatch):
        """Test that email is sent when SMTP config is provided."""
        from astromesh.tools.builtin.communication import SendEmailTool
        import asyncio

        sent = {}

        def fake_send():
            sent["called"] = True

        async def fake_to_thread(fn, *args, **kwargs):
            fn()

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        from unittest.mock import MagicMock, patch

        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            tool = SendEmailTool(
                config={
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "smtp_user": "user@example.com",
                    "smtp_password": "secret",
                    "from_address": "user@example.com",
                }
            )
            result = await tool.execute(
                {"to": "recipient@example.com", "subject": "Test", "body": "Hello"},
                _ctx(),
            )
        assert result.success is True
        assert result.data["to"] == "recipient@example.com"
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret")
        mock_server.send_message.assert_called_once()
