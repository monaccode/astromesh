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
