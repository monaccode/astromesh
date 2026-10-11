"""Las tres tools con que un agente navega su knowledge bundle OKF.

Las registra el engine cuando el agente declara `spec.knowledge.bundle`; el agente no las
declara en `spec.tools`. Como `rag_query`, nunca levantan: un error vuelve como resultado.
"""

from __future__ import annotations

import asyncio

from astromesh.core.tools import ToolRegistry
from astromesh.knowledge.okf import Bundle, BundleError
from astromesh.tools.base import ToolResult

TOOL_NAMES = ("kb_index", "kb_read", "kb_find")

_INDEX = (
    "List a directory of the knowledge bundle. Start here with path '/'. Links starting "
    "with '/' are bundle-absolute; other links in an index are relative to the listed directory."
)
_READ = (
    "Read one concept of the knowledge bundle: metadata, trust warnings, body, and its "
    "links already resolved to concept ids you can pass back to kb_read."
)
_FIND = (
    "Search concepts of the knowledge bundle by type, tags (all must match) and text. "
    "Deprecated concepts are excluded unless include_deprecated is true."
)


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _str_or_none(value):
    return None if value is None else str(value)


def _tags(tags):
    # La coerción de lo que manda el modelo vive acá, no en Bundle.
    if isinstance(tags, str):
        return [tags]
    if isinstance(tags, (list, tuple)):
        return [str(t) for t in tags]
    return None


async def _call(fn, *args, **kwargs) -> dict:
    try:
        data = await asyncio.to_thread(fn, *args, **kwargs)
    except BundleError as exc:
        return ToolResult(success=False, data=None, error=str(exc)).to_dict()
    # permisos, un archivo que desaparece, o un ValueError suelto
    except (OSError, ValueError) as exc:
        return ToolResult(success=False, data=None, error=f"bundle read failed: {exc}").to_dict()
    return ToolResult(success=True, data=data).to_dict()


def register_bundle_tools(registry: ToolRegistry, bundle: Bundle) -> None:
    taken = [name for name in TOOL_NAMES if name in registry._tools]
    if taken:
        raise ValueError(f"knowledge.bundle registraría {', '.join(taken)}, que el agente ya tiene")

    # `**_ignored`: una clave inventada por el modelo no puede tirar la llamada con TypeError.
    async def kb_index(path: str = "/", **_ignored) -> dict:
        return await _call(bundle.index, path)

    async def kb_read(concept_id: str = "", **_ignored) -> dict:
        return await _call(bundle.read, concept_id)

    async def kb_find(
        text=None, type=None, tags=None, include_deprecated=False, limit=20, **_ignored
    ) -> dict:
        return await _call(
            bundle.find,
            text=_str_or_none(text),
            type_=_str_or_none(type),
            tags=_tags(tags),
            include_deprecated=_bool(include_deprecated),
            limit=_int(limit, 20),
        )

    registry.register_internal(
        name="kb_index",
        handler=kb_index,
        description=_INDEX,
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "default": "/"}},
        },
    )
    registry.register_internal(
        name="kb_read",
        handler=kb_read,
        description=_READ,
        parameters={
            "type": "object",
            "properties": {"concept_id": {"type": "string"}},
            "required": ["concept_id"],
        },
    )
    registry.register_internal(
        name="kb_find",
        handler=kb_find,
        description=_FIND,
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "type": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "include_deprecated": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 20, "maximum": 100},
            },
        },
    )
