"""Catálogo de integraciones expuesto por HTTP.

Publica *qué* material de credencial hay que entregar, nunca valores: es lo
que Nexus consume para pintar la UI de conexiones y armar el OAuth.
"""

from fastapi import APIRouter, HTTPException

from astromesh.integrations import default_catalog

router = APIRouter()


def _action_payload(action) -> dict:
    return {
        "name": action.name,
        "description": action.description,
        "writes": action.mutates,
        "parameters": action.tool_parameters(),
        "paginated": action.pagination is not None,
    }


def _manifest_payload(manifest, *, with_actions: bool) -> dict:
    payload = {
        "slug": manifest.slug,
        "version": manifest.version,
        "description": manifest.description,
        "base_url": manifest.base_url,
        "auth": {
            "scheme": manifest.auth.scheme,
            "credential": manifest.auth.credential,
        },
        "action_count": len(manifest.actions),
    }
    if with_actions:
        payload["actions"] = [_action_payload(a) for a in manifest.actions]
    return payload


@router.get("/integrations")
async def list_integrations():
    manifests = default_catalog().all()
    return {
        "integrations": [_manifest_payload(m, with_actions=False) for m in manifests],
        "count": len(manifests),
    }


@router.get("/integrations/{slug}")
async def get_integration(slug: str):
    manifest = default_catalog().get(slug)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Integration '{slug}' not found")
    return _manifest_payload(manifest, with_actions=True)
