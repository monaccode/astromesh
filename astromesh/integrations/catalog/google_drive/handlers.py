"""Acciones de Google Drive que no caben en un solo request.

`upload_file` necesita una sesión resumable: primero un POST que devuelve
una URL de sesión en el header Location, después un PUT del contenido a esa
URL. Dos llamadas encadenadas, con el resultado de la primera alimentando a
la segunda — exactamente lo que el manifest declarativo no puede expresar.
"""

from __future__ import annotations

import codecs

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.integrations.interpolation import InterpolationError, interpolate
from astromesh.tools.base import ToolResult

_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"


async def upload_file(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    metadata: dict = {"name": arguments["name"]}
    if arguments.get("parent_folder_id"):
        metadata["parents"] = [arguments["parent_folder_id"]]

    content = arguments["content"]
    payload = content.encode() if isinstance(content, str) else content
    mime_type = arguments.get("mime_type") or "text/plain"

    init = await ctx.client.post(
        _UPLOAD_ENDPOINT,
        params={"uploadType": "resumable"},
        json=metadata,
        headers={
            "X-Upload-Content-Type": mime_type,
            "X-Upload-Content-Length": str(len(payload)),
        },
    )
    if init.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"iniciar la subida falló: HTTP {init.status_code}: {init.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(init.status_code),
                "status_code": init.status_code,
            },
        )

    session_url = init.headers.get("Location")
    if not session_url:
        return ToolResult(
            success=False,
            data=None,
            error="Drive no devolvió una URL de sesión (header Location ausente)",
            metadata={"error_kind": errors.UPSTREAM_ERROR},
        )

    upload = await ctx.client.put(session_url, content=payload, headers={"Content-Type": mime_type})
    if upload.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"subir el contenido falló: HTTP {upload.status_code}: {upload.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(upload.status_code),
                "status_code": upload.status_code,
            },
        )

    try:
        data = upload.json()
    except ValueError:
        data = {"raw": upload.text}
    return ToolResult(success=True, data=data, metadata={"status_code": upload.status_code})


TOPE_ARCHIVO = 50_000

# Formatos de Google: no se descargan, se exportan a texto.
EXPORTABLES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _es_descargable(mime: str) -> bool:
    return mime.startswith("text/") or mime in ("application/json", "application/xml")


def _fallo(paso: str, response) -> ToolResult:
    return ToolResult(
        success=False,
        data=None,
        error=f"{paso} falló: HTTP {response.status_code}: {response.text[:300]}",
        metadata={
            "error_kind": errors.classify_status(response.status_code),
            "status_code": response.status_code,
        },
    )


async def _leer_con_tope(ctx: IntegrationContext, url: str, params: dict):
    """GET en streaming que corta a TOPE_ARCHIVO * 4 bytes (un carácter UTF-8 son <= 4)."""
    tope = TOPE_ARCHIVO * 4
    async with ctx.client.stream("GET", url, params=params) as response:
        # Un 3xx tampoco es contenido (el cliente no sigue redirects): sería el
        # cuerpo del redirect leído como si fuera el archivo.
        if response.status_code >= 300:
            await response.aread()
            return response, b"", False
        buf = bytearray()
        async for trozo in response.aiter_bytes():
            buf += trozo
            if len(buf) > tope:
                return response, bytes(buf[:tope]), True
        return response, bytes(buf), False


async def read_file(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    """Un archivo de Drive como texto; nunca binario."""
    try:
        # Mismo guard que el ejecutor declarativo: el id lo elige el modelo.
        file_id = interpolate("{id}", {"id": arguments["file_id"]}, position="path")
    except InterpolationError as exc:
        return ToolResult(
            success=False,
            data=None,
            error=f"file_id inválido: {exc}",
            metadata={"error_kind": errors.BAD_REQUEST},
        )
    meta = await ctx.client.get(
        f"{ctx.base_url}/files/{file_id}", params={"fields": "id,name,mimeType"}
    )
    if meta.status_code >= 400:
        return _fallo("leer los metadatos del archivo", meta)
    info = meta.json()
    mime = info.get("mimeType", "")

    if mime in EXPORTABLES:
        url, params = f"{ctx.base_url}/files/{file_id}/export", {"mimeType": EXPORTABLES[mime]}
    elif _es_descargable(mime):
        url, params = f"{ctx.base_url}/files/{file_id}", {"alt": "media"}
    else:
        return ToolResult(
            success=False,
            data=None,
            error=f"No puedo leer archivos {mime}: pedí que lo pasen a un Doc de Google.",
            metadata={"error_kind": errors.BAD_REQUEST},
        )
    contenido, crudo, cortado = await _leer_con_tope(ctx, url, params)
    if contenido.status_code >= 300:
        return _fallo("leer el contenido del archivo", contenido)

    # El decoder incremental descarta una secuencia UTF-8 partida al final del corte.
    texto = codecs.getincrementaldecoder("utf-8")("replace").decode(crudo, final=not cortado)
    recortado = cortado or len(texto) > TOPE_ARCHIVO
    if recortado:
        cuanto = f"más de {len(texto)}" if cortado else f"{len(texto)}"
        texto = texto[:TOPE_ARCHIVO] + f"\n\n[… recortado: el original tiene {cuanto} caracteres]"
    return ToolResult(
        success=True,
        data={
            "id": info.get("id", file_id),
            "name": info.get("name", ""),
            "mime_type": mime,
            "texto": texto,
            "recortado": recortado,
        },
        metadata={"status_code": contenido.status_code},
    )
