"""Tests for communication tools: send_webhook, send_slack, send_email."""

import httpx
import respx

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
        import asyncio

        from astromesh.tools.builtin.communication import SendEmailTool

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


class TestSendMessageTool:
    """La tool que deja a un agente alcanzar a una persona, vía Nexus → Herald."""

    def _tool(self):
        from astromesh.tools.builtin.communication import SendMessageTool

        return SendMessageTool(config={"nexus_url": "https://nexus.example.com"})

    def _args(self, **over):
        return {"channel": "whatsapp", "recipient": "+5491100000001", "text": "hola", **over}

    @respx.mock
    async def test_queues_through_nexus_with_the_run_token_in_the_header(self):
        route = respx.post("https://nexus.example.com/api/v1/runs/messages/send").mock(
            return_value=httpx.Response(202, json={"message_id": "m-1", "status": "pending"})
        )
        result = await self._tool().execute(
            self._args(), _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})
        )

        assert result.success is True
        assert result.data == {"message_id": "m-1", "status": "pending"}
        sent = route.calls.last.request
        assert sent.headers["X-Nexus-Run-Token"] == "tok-abc"
        # El token va sólo en el header: el body se registra en la traza.
        assert b"tok-abc" not in sent.content

    @respx.mock
    async def test_the_token_never_appears_in_what_the_tool_returns(self):
        # Lo que devuelve una tool se escribe en la traza y vuelve al modelo en la
        # próxima iteración del patrón, así que un token acá se filtra dos veces.
        respx.post("https://nexus.example.com/api/v1/runs/messages/send").mock(
            return_value=httpx.Response(401, json={"error": "invalid run token"})
        )
        result = await self._tool().execute(
            self._args(), _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})
        )
        assert result.success is False
        assert "tok-abc" not in str(result.to_dict())

    async def test_without_a_run_token_it_refuses_instead_of_calling(self):
        # Una corrida local, no despachada por Nexus, no tiene credencial.
        result = await self._tool().execute(self._args(), _ctx())
        assert result.success is False
        assert "no send credential" in result.error

    async def test_without_a_nexus_url_it_says_so(self, monkeypatch):
        from astromesh.tools.builtin.communication import NEXUS_URL_ENV, SendMessageTool

        monkeypatch.delenv(NEXUS_URL_ENV, raising=False)
        result = await SendMessageTool().execute(
            self._args(), _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})
        )
        assert result.success is False
        assert NEXUS_URL_ENV in result.error

    @respx.mock
    async def test_the_env_var_configures_the_url_when_the_yaml_does_not(self, monkeypatch):
        from astromesh.tools.builtin.communication import NEXUS_URL_ENV, SendMessageTool

        monkeypatch.setenv(NEXUS_URL_ENV, "https://nexus.env.example.com/")
        respx.post("https://nexus.env.example.com/api/v1/runs/messages/send").mock(
            return_value=httpx.Response(202, json={"message_id": "m-2", "status": "pending"})
        )
        result = await SendMessageTool().execute(
            self._args(), _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})
        )
        assert result.success is True
        assert result.data["message_id"] == "m-2"

    @respx.mock
    async def test_nexus_own_error_survives(self):
        respx.post("https://nexus.example.com/api/v1/runs/messages/send").mock(
            return_value=httpx.Response(
                502, json={"error": "herald send: conversation or account not found (404)"}
            )
        )
        result = await self._tool().execute(
            self._args(), _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})
        )
        assert result.success is False
        assert "conversation or account not found" in result.error

    async def test_missing_arguments_are_named_without_a_round_trip(self):
        # Sin respx montado: si intentara salir a la red, el test fallaría.
        result = await self._tool().execute(
            {"channel": "whatsapp"}, _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})
        )
        assert result.success is False
        assert "recipient" in result.error
        assert "text" in result.error

    @respx.mock
    async def test_conversation_ref_is_forwarded_only_when_given(self):
        import json

        route = respx.post("https://nexus.example.com/api/v1/runs/messages/send").mock(
            return_value=httpx.Response(202, json={"message_id": "m-3", "status": "pending"})
        )
        ctx = _ctx(secrets={"NEXUS_RUN_TOKEN": "tok-abc"})

        await self._tool().execute(self._args(), ctx)
        assert "conversation_ref" not in json.loads(route.calls.last.request.content)

        await self._tool().execute(self._args(conversation_ref="c-9"), ctx)
        assert json.loads(route.calls.last.request.content)["conversation_ref"] == "c-9"
