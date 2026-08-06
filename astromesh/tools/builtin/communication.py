"""Communication built-in tools: send_webhook, send_slack, send_email, send_message."""

from __future__ import annotations

import asyncio
import os
import smtplib
from email.mime.text import MIMEText
from typing import ClassVar

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class SendWebhookTool(BuiltinTool):
    name = "send_webhook"
    description = "Send an HTTP POST to a webhook URL with a JSON payload"
    parameters: ClassVar[dict] = {
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
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))


class SendSlackTool(BuiltinTool):
    name = "send_slack"
    description = "Send a message to Slack via webhook"
    parameters: ClassVar[dict] = {
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
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))


class SendEmailTool(BuiltinTool):
    name = "send_email"
    description = "Send an email via SMTP"
    parameters: ClassVar[dict] = {
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
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))


# Dónde vive Nexus. Es configuración del runtime, no algo que Nexus pueda
# afirmar sobre sí mismo en el context de la corrida: el pool de runtimes es
# compartido y su operador es quien sabe a qué Nexus responde.
NEXUS_URL_ENV = "ASTROMESH_NEXUS_URL"

# La clave del ToolContext.secrets donde el runtime deja el token de la corrida.
# La pone `Agent.run` leyendo `_nexus_run_token` del context del llamador.
RUN_TOKEN_SECRET = "NEXUS_RUN_TOKEN"

# Igual que en el cliente Go de Nexus: un error más largo que esto no es de
# Nexus, es un proxy devolviendo HTML, y citarlo entero no ayuda a nadie.
_MAX_ERR_BODY = 4 * 1024


class SendMessageTool(BuiltinTool):
    """Manda un mensaje a una persona por un canal de comunicación, vía Nexus.

    Es la única tool del repo que usa una credencial que el agente no configuró:
    Nexus acuña un token por invocación y lo baja en el context de la corrida.
    Eso es a propósito — el pool de runtimes es compartido entre tenants, así que
    darle secretos por tenant sería poner la llave de todos en un proceso. Este
    token vale para un tenant, una capacidad (encolar un mensaje) y una corrida.

    Consecuencia visible: fuera de una corrida despachada por Nexus la tool no
    funciona, y devuelve eso como error en vez de intentar cualquier cosa.
    """

    name = "send_message"
    description = (
        "Send a message to a person through a communications channel such as WhatsApp. "
        "Use it to reach someone who is not currently waiting on a reply. "
        "Delivery is asynchronous: a successful call means the message was queued."
    )
    parameters: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel to send through, e.g. 'whatsapp'.",
            },
            "recipient": {
                "type": "string",
                "description": "Who to reach on that channel, e.g. a phone number in E.164.",
            },
            "text": {"type": "string", "description": "The message body."},
            "conversation_ref": {
                "type": "string",
                "description": (
                    "Optional id of an existing conversation. Pinning the send to one "
                    "keeps it inside WhatsApp's 24-hour window; without it the send is "
                    "a cold contact and the provider may require an approved template."
                ),
            },
        },
        "required": ["channel", "recipient", "text"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        token = context.secrets.get(RUN_TOKEN_SECRET)
        if not token:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    "this run carries no send credential: send_message only works on a run "
                    "dispatched by Nexus, which mints one per invocation"
                ),
            )
        base = self.config.get("nexus_url") or os.environ.get(NEXUS_URL_ENV, "")
        if not base:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    f"no Nexus URL configured: set the tool's nexus_url or the "
                    f"{NEXUS_URL_ENV} environment variable"
                ),
            )

        # Se valida acá aunque Nexus también valide: un 400 tras un round-trip es
        # una observación peor para el modelo que decirle qué le falta.
        missing = [k for k in ("channel", "recipient", "text") if not arguments.get(k)]
        if missing:
            return ToolResult(
                success=False, data=None, error=f"missing required: {', '.join(missing)}"
            )

        payload = {
            "channel": arguments["channel"],
            "recipient": arguments["recipient"],
            "text": arguments["text"],
        }
        if arguments.get("conversation_ref"):
            payload["conversation_ref"] = arguments["conversation_ref"]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    base.rstrip("/") + "/api/v1/runs/messages/send",
                    json=payload,
                    # El token va en el header y en ningún otro lado: ni en el
                    # payload, ni en metadata, ni en el texto de un error. Lo que
                    # esta tool devuelve termina en la traza y en el prompt de la
                    # próxima iteración del patrón.
                    headers={"X-Nexus-Run-Token": token},
                )
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=f"send_message: {e}")

        if resp.status_code < 200 or resp.status_code > 299:
            detail = ""
            try:
                body = resp.json()
                if isinstance(body, dict):
                    detail = str(body.get("error", ""))
            except ValueError:
                detail = resp.text[:_MAX_ERR_BODY]
            return ToolResult(
                success=False,
                data=None,
                error=f"send_message: {detail or 'unexpected status'} ({resp.status_code})",
                metadata={"status_code": resp.status_code},
            )

        try:
            ack = resp.json()
        except ValueError:
            return ToolResult(success=False, data=None, error="send_message: malformed ack")
        return ToolResult(
            success=True,
            # "pending" es la respuesta normal, no un problema: el outbox de
            # Herald es asincrónico y at-least-once, y el id es cómo se consulta
            # el resultado después.
            data={"message_id": ack.get("message_id"), "status": ack.get("status")},
            metadata={"channel": arguments["channel"]},
        )
