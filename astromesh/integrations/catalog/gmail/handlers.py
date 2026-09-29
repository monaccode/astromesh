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
from html import unescape
from html.parser import HTMLParser

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


TOPE_CORREO = 20_000


class _Texto(HTMLParser):
    """Junta el texto visible de un HTML; omite script y style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._omitir = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._omitir += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._omitir:
            self._omitir -= 1

    def handle_data(self, data):
        if not self._omitir:
            self.partes.append(data)


def _sin_etiquetas(html: str) -> str:
    parser = _Texto()
    parser.feed(html)
    parser.close()
    return unescape("".join(parser.partes)).strip()


def _decodificar(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _recorrer(part: dict, cuerpos: dict, adjuntos: list[str]) -> None:
    if part.get("filename"):
        adjuntos.append(part["filename"])
        return
    mime = part.get("mimeType", "")
    data = (part.get("body") or {}).get("data")
    if data and mime in ("text/plain", "text/html"):
        cuerpos.setdefault(mime, _decodificar(data))
    for hija in part.get("parts") or []:
        _recorrer(hija, cuerpos, adjuntos)


async def read_message(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    """Un correo como texto: cabeceras, cuerpo (plano, o HTML sin etiquetas) y nombres de adjuntos."""
    response = await ctx.client.get(
        f"{ctx.base_url}/users/me/messages/{arguments['message_id']}", params={"format": "full"}
    )
    if response.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"leer el correo falló: HTTP {response.status_code}: {response.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(response.status_code),
                "status_code": response.status_code,
            },
        )

    mensaje = response.json()
    payload = mensaje.get("payload") or {}
    cuerpos: dict[str, str] = {}
    adjuntos: list[str] = []
    _recorrer(payload, cuerpos, adjuntos)
    if "text/plain" in cuerpos:
        texto = cuerpos["text/plain"]
    else:
        texto = _sin_etiquetas(cuerpos.get("text/html", ""))

    cabeceras = {h["name"].lower(): h["value"] for h in payload.get("headers") or []}
    recortado = len(texto) > TOPE_CORREO
    if recortado:
        texto = (
            texto[:TOPE_CORREO] + f"\n\n[… recortado: el original tiene {len(texto)} caracteres]"
        )
    return ToolResult(
        success=True,
        data={
            "id": mensaje.get("id"),
            "thread_id": mensaje.get("threadId"),
            "from": cabeceras.get("from", ""),
            "to": cabeceras.get("to", ""),
            "cc": cabeceras.get("cc", ""),
            "date": cabeceras.get("date", ""),
            "subject": cabeceras.get("subject", ""),
            "texto": texto,
            "adjuntos": adjuntos,
            "recortado": recortado,
        },
        metadata={"status_code": response.status_code},
    )
