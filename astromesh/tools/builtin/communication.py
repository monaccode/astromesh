"""Communication built-in tools: send_webhook, send_slack, send_email."""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class SendWebhookTool(BuiltinTool):
    name = "send_webhook"
    description = "Send an HTTP POST to a webhook URL with a JSON payload"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "payload": {"description": "JSON payload"},
            "headers": {"type": "object"},
        },
        "required": ["url", "payload"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    arguments["url"],
                    json=arguments["payload"],
                    headers=arguments.get("headers", {}),
                )
                return ToolResult(
                    success=True,
                    data={"status_code": resp.status_code, "response": resp.text},
                    metadata={"url": arguments["url"]},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class SendSlackTool(BuiltinTool):
    name = "send_slack"
    description = "Send a message to Slack via webhook"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "channel": {"type": "string"},
        },
        "required": ["message"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        webhook_url = self.config.get("webhook_url") or context.secrets.get("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return ToolResult(success=False, data=None, error="No webhook_url configured")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json={"text": arguments["message"]})
                return ToolResult(
                    success=True,
                    data={"response": resp.text},
                    metadata={"method": "webhook"},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class SendEmailTool(BuiltinTool):
    name = "send_email"
    description = "Send an email via SMTP"
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        host = self.config.get("smtp_host") or context.secrets.get("SMTP_HOST")
        if not host:
            return ToolResult(success=False, data=None, error="SMTP host not configured")
        port = self.config.get("smtp_port", 587)
        user = self.config.get("smtp_user") or context.secrets.get("SMTP_USER")
        password = self.config.get("smtp_password") or context.secrets.get("SMTP_PASSWORD")
        from_addr = self.config.get("from_address", user)

        msg = MIMEText(arguments["body"])
        msg["Subject"] = arguments["subject"]
        msg["From"] = from_addr
        msg["To"] = arguments["to"]

        try:

            def _send():
                with smtplib.SMTP(host, port) as server:
                    server.starttls()
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)

            await asyncio.to_thread(_send)
            return ToolResult(
                success=True,
                data={"to": arguments["to"], "subject": arguments["subject"]},
                metadata={},
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
