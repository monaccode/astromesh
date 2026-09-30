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
import re
from email.message import EmailMessage
from html.parser import HTMLParser

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.integrations.interpolation import InterpolationError, interpolate
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
            self.partes.append(re.sub(r"\s+", " ", data))


def _sin_etiquetas(html: str) -> str:
    parser = _Texto()
    parser.feed(html)
    parser.close()
    # convert_charrefs=True ya decodificó las entidades: decodificar de nuevo
    # convertiría "&amp;lt;" (texto literal "&lt;") en "<".
    texto = "".join(parser.partes)
    texto = re.sub(r"[^\S\n]+", " ", texto)  # runs de espacios, sin tocar los saltos
    texto = re.sub(r" ?\n ?", "\n", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _charset(part: dict) -> str:
    for h in part.get("headers") or []:
        if h.get("name", "").lower() == "content-type":
            m = re.search(r"charset=\"?([\w.:-]+)", h.get("value", ""), re.IGNORECASE)
            if m:
                return m.group(1)
    return "utf-8"


def _decodificar(data: str, charset: str = "utf-8") -> str:
    crudo = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    try:
        return crudo.decode(charset, errors="replace")
    except LookupError:
        return crudo.decode("utf-8", errors="replace")


def _recorrer(part: dict, cuerpos: dict, adjuntos: list[str], grandes: list[str]) -> None:
    if part.get("filename"):
        adjuntos.append(part["filename"])
        return
    mime = part.get("mimeType", "")
    body = part.get("body") or {}
    data = body.get("data")
    if data and mime in ("text/plain", "text/html"):
        cuerpos.setdefault(mime, _decodificar(data, _charset(part)))
    elif body.get("attachmentId") and mime in ("text/plain", "text/html"):
        # Gmail manda un cuerpo grande como adjunto, sin `data`.
        grandes.append(mime)
    for hija in part.get("parts") or []:
        _recorrer(hija, cuerpos, adjuntos, grandes)


AVISO_CUERPO_GRANDE = (
    "El cuerpo del correo es muy grande y Gmail lo manda como adjunto: no lo puedo leer."
)


async def read_message(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    """Un correo como texto: cabeceras, cuerpo (plano, o HTML sin etiquetas) y nombres de adjuntos."""
    try:
        # Mismo guard que el ejecutor declarativo: el id lo elige el modelo y
        # no puede salirse de este segmento (`..`, `/`, `?`).
        message_id = interpolate("{id}", {"id": arguments["message_id"]}, position="path")
    except InterpolationError as exc:
        return ToolResult(
            success=False,
            data=None,
            error=f"message_id inválido: {exc}",
            metadata={"error_kind": errors.BAD_REQUEST},
        )
    response = await ctx.client.get(
        f"{ctx.base_url}/users/me/messages/{message_id}", params={"format": "full"}
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
    grandes: list[str] = []
    _recorrer(payload, cuerpos, adjuntos, grandes)
    if "text/plain" in cuerpos:
        texto = cuerpos["text/plain"]
    else:
        texto = _sin_etiquetas(cuerpos.get("text/html", ""))
    if not texto and grandes:
        texto = AVISO_CUERPO_GRANDE

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
