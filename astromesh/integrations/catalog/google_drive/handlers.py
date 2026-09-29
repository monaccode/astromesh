"""Acciones de Google Drive que no caben en un solo request.

`upload_file` necesita una sesión resumable: primero un POST que devuelve
una URL de sesión en el header Location, después un PUT del contenido a esa
URL. Dos llamadas encadenadas, con el resultado de la primera alimentando a
la segunda — exactamente lo que el manifest declarativo no puede expresar.
"""

from __future__ import annotations

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
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


async def read_file(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    """Un archivo de Drive como texto; nunca binario."""
    file_id = arguments["file_id"]
    meta = await ctx.client.get(
        f"{ctx.base_url}/files/{file_id}", params={"fields": "id,name,mimeType"}
    )
    if meta.status_code >= 400:
        return _fallo("leer los metadatos del archivo", meta)
    info = meta.json()
    mime = info.get("mimeType", "")

    if mime in EXPORTABLES:
        contenido = await ctx.client.get(
            f"{ctx.base_url}/files/{file_id}/export", params={"mimeType": EXPORTABLES[mime]}
        )
    elif _es_descargable(mime):
        contenido = await ctx.client.get(f"{ctx.base_url}/files/{file_id}", params={"alt": "media"})
    else:
        return ToolResult(
            success=False,
            data=None,
            error=f"No puedo leer archivos {mime}: pedí que lo pasen a un Doc de Google.",
            metadata={"error_kind": errors.BAD_REQUEST},
        )
    if contenido.status_code >= 400:
        return _fallo("leer el contenido del archivo", contenido)

    texto = contenido.content.decode("utf-8", errors="replace")
    recortado = len(texto) > TOPE_ARCHIVO
    if recortado:
        texto = (
            texto[:TOPE_ARCHIVO] + f"\n\n[… recortado: el original tiene {len(texto)} caracteres]"
        )
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
