"""Envío de correo por Gmail.

Es un handler y no una acción declarativa por una razón concreta: la API no
recibe `to`/`subject`/`body` como campos. Recibe un único campo `raw` con el
mensaje MIME RFC 5322 **entero**, codificado en base64url. Construir ese
mensaje es armado de estructura, no plantillado de texto, y un manifest
declarativo no puede expresarlo.

Se usa `email.message.EmailMessage` de la biblioteca estándar en vez de
concatenar cabeceras a mano: se encarga del plegado de líneas largas, del
juego de caracteres y del escapado de cabeceras. Un asunto con acentos
concatenado a mano sale roto en la mitad de los clientes.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.tools.base import ToolResult


def _build_mime(arguments: dict) -> bytes:
    message = EmailMessage()
    message["To"] = arguments["to"]
    message["Subject"] = arguments["subject"]
    if arguments.get("cc"):
        message["Cc"] = arguments["cc"]
    message.set_content(arguments["body"])
    return message.as_bytes()


async def send_message(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    # base64**url** (-_ en vez de +/): Gmail rechaza el base64 estándar acá.
    raw = base64.urlsafe_b64encode(_build_mime(arguments)).decode()

    payload: dict = {"raw": raw}
    if arguments.get("reply_to_thread_id"):
        payload["threadId"] = arguments["reply_to_thread_id"]

    response = await ctx.client.post(f"{ctx.base_url}/users/me/messages/send", json=payload)
    if response.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"enviar el correo falló: HTTP {response.status_code}: {response.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(response.status_code),
                "status_code": response.status_code,
            },
        )

    return ToolResult(
        success=True, data=response.json(), metadata={"status_code": response.status_code}
    )
