"""Publicación en Instagram, que la Graph API parte en dos llamadas.

Primero se crea un *contenedor* de media (POST /{ig_user_id}/media), que
devuelve un `creation_id`; después se publica ese contenedor (POST
/{ig_user_id}/media_publish?creation_id=...). La segunda llamada depende del
resultado de la primera, que es justo lo que un manifest declarativo no puede
expresar.

Deliberadamente **no** se poléa el estado del contenedor acá. Para fotos está
listo de inmediato, y dormir dentro de una llamada de tool consume el timeout
del agente sin darle nada que decidir. Si la publicación falla porque el
contenedor todavía se está procesando, se devuelve el `creation_id` en el
error para que el agente reintente con `publish_container` — el bucle ReAct
es el poleador, no este handler.
"""

from __future__ import annotations

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.tools.base import ToolResult


async def publish_photo(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    ig_user_id = arguments["ig_user_id"]

    container_params = {"image_url": arguments["image_url"]}
    if arguments.get("caption"):
        container_params["caption"] = arguments["caption"]

    created = await ctx.client.post(f"{ctx.base_url}/{ig_user_id}/media", params=container_params)
    if created.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"crear el contenedor falló: HTTP {created.status_code}: {created.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(created.status_code),
                "status_code": created.status_code,
            },
        )

    creation_id = (created.json() or {}).get("id")
    if not creation_id:
        return ToolResult(
            success=False,
            data=None,
            error="Instagram no devolvió un id de contenedor al crear el media",
            metadata={"error_kind": errors.UPSTREAM_ERROR},
        )

    published = await ctx.client.post(
        f"{ctx.base_url}/{ig_user_id}/media_publish", params={"creation_id": creation_id}
    )
    if published.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=(
                f"el contenedor {creation_id} se creó pero publicarlo falló: "
                f"HTTP {published.status_code}: {published.text[:300]}. "
                f"Se puede reintentar con publish_container usando ese creation_id."
            ),
            metadata={
                "error_kind": errors.classify_status(published.status_code),
                "status_code": published.status_code,
                "creation_id": creation_id,
            },
        )

    return ToolResult(
        success=True,
        data=published.json(),
        metadata={"status_code": published.status_code, "creation_id": creation_id},
    )
