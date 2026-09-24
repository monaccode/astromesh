"""La ficha de una API del tenant, traducida a un manifest de integración.

La escribe quien administra el tenant (CLARUS la emite desde OFFICIUM), no quien
mantiene el catálogo. Dos consecuencias: la ficha se valida entera al construir
el agente y LEVANTA si algo no cierra —una API que el admin cree habilitada y no
existe es el mismo silencio que ya costó `confirm`—, y sus tools se registran
con `permitir_internos=False` (host público, `tools/builtin/_red.py`).
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from astromesh.core.schema import InvalidToolParameters
from astromesh.integrations.manifest import ActionSpec, AuthSpec, IntegrationManifest

_SLUG = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_OPERACION = re.compile(r"^[a-z][a-z0-9_]*$")
_ESQUEMAS = ("header", "bearer", "basic", "query")
_METODOS = ("GET", "POST")
_CLAVES_DE_OPERACION = ("name", "description", "parameters", "request", "response")
# OpenAI y Anthropic validan los nombres de función contra
# ^[a-zA-Z0-9_-]{1,64}$ (`core/tools.py:170-171`).
_LARGO_MAXIMO = 64

#: Dónde trae la credencial el material de la conexión, para todos los
#: esquemas. En `basic` es un mapping con `username` y `password`
#: (`integrations/auth.py:36-49`).
CLAVE_CREDENCIAL = "credential"


def _nombre_de_tool(slug: str, operacion: str) -> str:
    return f"{slug.replace('-', '_')}_{operacion}"


def manifiesto_de_api(tool_def: dict) -> tuple[IntegrationManifest, str]:
    """(manifest en memoria, nombre de la conexión). Levanta ValueError con el motivo.

    Sin `base_url`: viene de la conexión (`integrations/executor.py:116`), que es de Nexus.
    """
    slug = tool_def.get("name")
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise ValueError(f"tool api {slug!r}: 'name' tiene que ser un slug kebab (erp-cliente)")
    conexion = tool_def.get("connection")
    if not isinstance(conexion, str) or not conexion:
        raise ValueError(f"tool api {slug!r}: falta 'connection'")
    auth = tool_def.get("auth") or {}
    esquema = auth.get("scheme")
    if esquema not in _ESQUEMAS:
        raise ValueError(
            f"tool api {slug!r}: auth.scheme {esquema!r} no es uno de {', '.join(_ESQUEMAS)}"
        )
    operaciones = tool_def.get("operations")
    if not isinstance(operaciones, list) or not operaciones:
        raise ValueError(f"tool api {slug!r}: 'operations' está vacío")

    acciones: list[dict] = []
    for op in operaciones:
        if not isinstance(op, dict):
            # ValueError y no TypeError: el contrato es un solo tipo con el motivo.
            raise ValueError(f"tool api {slug!r}: cada operación tiene que ser un mapping")  # noqa: TRY004
        nombre = op.get("name")
        if not isinstance(nombre, str) or not _OPERACION.match(nombre):
            raise ValueError(f"tool api {slug!r}: la operación {nombre!r} no es snake_case")
        if len(_nombre_de_tool(slug, nombre)) > _LARGO_MAXIMO:
            raise ValueError(
                f"tool api {slug!r}: '{_nombre_de_tool(slug, nombre)}' pasa los "
                f"{_LARGO_MAXIMO} caracteres que aceptan los proveedores"
            )
        if op.get("writes") is not False:
            raise ValueError(
                f"tool api {slug!r}: la operación {nombre!r} no declara writes: false — "
                "una API del tenant sólo lee"
            )
        metodo = (op.get("request") or {}).get("method")
        if metodo not in _METODOS:
            raise ValueError(
                f"tool api {slug!r}: la operación {nombre!r} tiene que ser GET o POST, "
                f"es {metodo!r}"
            )
        accion = {k: op[k] for k in _CLAVES_DE_OPERACION if op.get(k) is not None}
        acciones.append({**accion, "writes": False})

    try:
        specs = [ActionSpec(**a) for a in acciones]
        for s in specs:
            # `register_integration_tool` lo llama después; acá, para que un
            # `parameters` roto levante con el nombre de la API y no a mitad
            # del registro.
            s.tool_parameters()
        manifest = IntegrationManifest(
            slug=slug.replace("-", "_"),
            description=str(tool_def.get("description") or ""),
            auth=AuthSpec(
                scheme=esquema,
                credential=CLAVE_CREDENCIAL,
                header_name=auth.get("header"),
                param_name=auth.get("param"),
            ),
            actions=specs,
        )
    except (ValidationError, InvalidToolParameters, TypeError) as exc:
        raise ValueError(f"tool api {slug!r}: ficha inválida: {exc}") from exc
    return manifest, conexion
