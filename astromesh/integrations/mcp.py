"""El servidor MCP de un tenant, con su instantánea de tools inline en el manifiesto.

Lo registra quien administra el tenant (CLARUS, OFFICIUM R2c) y CLARUS guarda
la lista de tools que descubrió: el runtime NO descubre. `_build_agent` corre al
cargar el agente, sin red y sin la credencial del tenant, que llega por corrida
en `context["connections"]` (`runtime/engine.py`, `tool_fn`). Así que cada tool
de la instantánea se registra con su schema tal cual, sin abrir una conexión, y
cada llamada es una sesión corta del SDK oficial (`initialize` + `tools/call`)
por `TransportePineado` (`tools/builtin/_red.py`): host público, IP pineada,
sin redirects, cuerpo acotado.

La ficha LEVANTA si algo no cierra, como la de `api`: un servidor que el admin
cree habilitado y no existe es el mismo silencio que ya costó `confirm`.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Callable
from typing import Literal

import anyio
import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from astromesh.integrations.api import CLAVE_CREDENCIAL
from astromesh.integrations.credentials import CredentialResolver
from astromesh.integrations.manifest import Defaults
from astromesh.tools.base import ToolResult
from astromesh.tools.builtin._red import TransportePineado

_SLUG = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
_NO_PERMITIDO = re.compile(r"[^a-z0-9_]")
# OpenAI y Anthropic validan los nombres de función contra
# ^[a-zA-Z0-9_-]{1,64}$ (`core/tools.py:170-171`).
_LARGO_MAXIMO = 64
#: Timeout de cada llamada: el de las integraciones (`manifest.py::Defaults`).
TIMEOUT_LLAMADA = Defaults().timeout_seconds
# Los topes de la instantánea que aplica CLARUS al listar
# (`apps/backend/src/officium/mcp.ts`, `MAX_BYTES_SCHEMA` y `MAX_NIVELES_SCHEMA`).
# El runtime no le cree: un manifiesto editado a mano llega igual.
MAX_BYTES_SCHEMA = 16 * 1024
MAX_NIVELES_SCHEMA = 8
# Los que arma el transporte o el SDK: pisarlos con la credencial rompe la
# llamada o el pineado. Comparados en minúsculas.
_HEADERS_RESERVADOS = frozenset(
    {
        "host",
        "content-type",
        "content-length",
        "accept",
        "accept-encoding",
        "connection",
        "transfer-encoding",
        "mcp-session-id",
        "mcp-protocol-version",
    }
)


def _pasa_de_niveles(v: object, tope: int) -> bool:
    """Si `v` anida más de `tope` objetos o arrays, como `pasaDeNiveles` de
    CLARUS. Iterativo: un schema de miles de niveles revienta una recursión (y
    `json.dumps`), así que esto corre ANTES de medir los bytes."""
    pila: list[tuple[object, int]] = [(v, 1)]
    while pila:
        x, nivel = pila.pop()
        if not isinstance(x, (dict, list)):
            continue
        if nivel > tope:
            return True
        pila.extend((h, nivel + 1) for h in (x.values() if isinstance(x, dict) else x))
    return False


class _AuthMcp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: Literal["bearer", "header"]
    header: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,64}$")

    @field_validator("header")
    @classmethod
    def _header_no_reservado(cls, v: str | None) -> str | None:
        if v is not None and v.lower() in _HEADERS_RESERVADOS:
            raise ValueError(f"auth.header {v!r} es un header reservado")
        return v

    @model_validator(mode="after")
    def _header_con_nombre(self):
        if self.scheme == "header" and not self.header:
            raise ValueError("auth.scheme header requiere 'header'")
        return self


class _ToolMcp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    input_schema: dict
    #: Sin default a propósito: una entrada que no DECLARA `writes: false` no
    #: valida. Un servidor del tenant sólo lee (OFFICIUM R2c).
    writes: Literal[False]

    @field_validator("input_schema")
    @classmethod
    def _schema_sano(cls, v: dict) -> dict:
        if v.get("type") != "object":
            raise ValueError("input_schema tiene que ser type: object")
        if _pasa_de_niveles(v, MAX_NIVELES_SCHEMA):
            raise ValueError(f"input_schema pasa los {MAX_NIVELES_SCHEMA} niveles")
        crudo = json.dumps(v, separators=(",", ":"), ensure_ascii=False).encode()
        if len(crudo) > MAX_BYTES_SCHEMA:
            raise ValueError(f"input_schema pasa los {MAX_BYTES_SCHEMA // 1024} KB")
        return v


class _ServidorMcp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["mcp"]
    name: str = Field(pattern=_SLUG, max_length=30)
    connection: str = Field(min_length=1)
    path: str = Field(pattern=r"^/[^?#]*$")
    auth: _AuthMcp
    tools: list[_ToolMcp] = Field(min_length=1)
    rate_limit: dict | None = None


def nombre_de_tool(slug: str, nombre: str) -> str:
    """`<slug con _>_<nombre en [a-z0-9_]>`; CLARUS arma el mismo
    (`apps/backend/src/officium/mcp.ts`, `toolDeMcp`)."""
    return f"{slug.replace('-', '_')}_{_NO_PERMITIDO.sub('_', nombre.lower())}"


def servidor_de_mcp(tool_def: dict) -> _ServidorMcp:
    """La ficha validada, o ValueError con el motivo (nombres incluidos)."""
    try:
        s = _ServidorMcp.model_validate(tool_def)
    except ValidationError as exc:
        raise ValueError(f"tool mcp {tool_def.get('name')!r}: ficha inválida: {exc}") from exc
    vistos: dict[str, str] = {}
    for t in s.tools:
        n = nombre_de_tool(s.name, t.name)
        if len(n) > _LARGO_MAXIMO:
            raise ValueError(
                f"tool mcp {s.name!r}: '{n}' pasa los {_LARGO_MAXIMO} caracteres "
                "que aceptan los proveedores"
            )
        if n in vistos:
            raise ValueError(
                f"tool mcp {s.name!r}: '{t.name}' y '{vistos[n]}' se registrarían "
                f"las dos como '{n}'"
            )
        vistos[n] = t.name
    if importlib.util.find_spec("mcp") is None:
        # Sin el extra, el agente cargaría en verde y cada llamada fallaría.
        raise ValueError(f"tool mcp {s.name!r}: este runtime no tiene el extra 'mcp'")
    return s


def _texto(resultado) -> str:
    partes: list[str] = []
    for bloque in resultado.content:
        tipo = getattr(bloque, "type", None)
        if tipo == "text":
            partes.append(bloque.text)
        elif tipo == "image":
            partes.append("[imagen omitida]")
        elif tipo == "audio":
            partes.append("[audio omitido]")
        else:
            partes.append("[recurso omitido]")
    return "\n".join(partes)


def _primera(exc: BaseException) -> BaseException:
    """El SDK corre la sesión en task groups de anyio: lo que falla adentro
    sale envuelto en `ExceptionGroup`, a veces anidado. La causa es la hoja."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


async def llamar_tool_mcp(
    url: str,
    headers: dict[str, str],
    nombre: str,
    argumentos: dict,
    timeout: float | None = None,  # noqa: ASYNC109
    transporte: httpx.AsyncBaseTransport | None = None,
) -> ToolResult:
    """Una sesión corta contra el servidor: `initialize` + `tools/call` +
    cierre (D3 de la spec de OFFICIUM R2c). Nunca levanta: `tool_fn` re-lanza
    lo que reciba y eso mata la corrida entera.

    Dos cosas del SDK 1.28.1 que no se deducen de su API:
    - `streamablehttp_client(httpx_client_factory=...)` está deprecado
      (`mcp/client/streamable_http.py:685-686`); el vigente recibe el cliente
      armado (`streamable_http_client(url, http_client=...)`, `:600-615`). Y el
      cliente por defecto SIGUE redirects (`mcp/shared/_httpx_utils.py:69-71`):
      acá va `follow_redirects=False`.
    - `ClientSession.call_tool` pide `tools/list` por su cuenta para validar el
      `structuredContent` (`mcp/client/session.py:412-421`): una ida y vuelta
      más por llamada, y un servidor con `outputSchema` rechazaría un
      resultado sin él. Se manda el `CallToolRequest` con `send_request`.
    """
    # Leído acá y no como default del parámetro: un default se evalúa una vez,
    # al importar, y el test del tope no podría achicarlo.
    timeout = timeout if timeout is not None else TIMEOUT_LLAMADA

    t = TransportePineado(interno=transporte) if transporte else TransportePineado()
    cliente = httpx.AsyncClient(
        transport=t, headers=headers, timeout=timeout, follow_redirects=False
    )
    rechazo: type[Exception] | None = None
    try:
        # Adentro del `try`: un runtime con otro SDK (mcp 2.x renombra
        # `McpError` y pide otro cliente http) degrada la llamada, no la corrida.
        from mcp import ClientSession, McpError, types
        from mcp.client.streamable_http import streamable_http_client

        rechazo = McpError
        # El tope es de la LLAMADA entera, no de cada request: con el de httpx
        # solo, `initialize` + `tools/call` lentos llegaban a casi el doble.
        with anyio.fail_after(timeout):
            async with (
                cliente,
                streamable_http_client(url, http_client=cliente) as (r, w, _),
                ClientSession(r, w) as s,
            ):
                await s.initialize()
                resultado = await s.send_request(
                    types.ClientRequest(
                        types.CallToolRequest(
                            params=types.CallToolRequestParams(name=nombre, arguments=argumentos)
                        )
                    ),
                    types.CallToolResult,
                )
    # Atrapar todo es el contrato: un servidor del tenant que falla degrada esta
    # llamada, nunca la corrida.
    except Exception as exc:  # noqa: BLE001
        causa = _primera(exc)
        if rechazo is not None and isinstance(causa, rechazo):
            # Es lo que terminó la llamada: gana a una falla anterior que el SDK
            # se tragó (un 3xx en el GET de SSE). Un bloqueo de la guarda no
            # llega como McpError: sale del task group como la excepción de httpx.
            motivo = f"el servidor MCP rechazó la llamada: {causa.error.message}"
        elif t.motivo:
            motivo = t.motivo
        elif isinstance(causa, TimeoutError):
            motivo = f"el servidor MCP no contestó en {timeout:g} s"
        elif isinstance(causa, httpx.HTTPStatusError):
            # Sin el mensaje de httpx: trae la URL con la IP pineada y un link a MDN.
            motivo = f"el servidor MCP contestó {causa.response.status_code}"
        elif isinstance(causa, ImportError):
            motivo = f"este runtime no tiene un SDK de MCP compatible (mcp 1.x): {causa}"
        else:
            motivo = f"{type(causa).__name__}: {causa}"
        return ToolResult(success=False, data=None, error=motivo)
    texto = _texto(resultado)
    if resultado.isError:
        return ToolResult(success=False, data=None, error=texto or "la tool devolvió un error")
    return ToolResult(success=True, data=texto)


def handler_de_tool(
    servidor: _ServidorMcp,
    tool: _ToolMcp,
    resolver: CredentialResolver,
) -> Callable:
    """El handler que registra `_build_agent`. La conexión se resuelve en cada
    llamada desde el bundle de la corrida, como en `ToolRegistry.execute` para
    las integraciones: el registro es por agente y el bundle por corrida."""

    async def _handler(_run_context=None, **argumentos):
        bundle = (_run_context or {}).get("connections") or {}
        conexion = resolver.resolve(servidor.connection, bundle)
        credencial = (conexion.material.get(CLAVE_CREDENCIAL) if conexion else None) or None
        if conexion is None or not conexion.base_url or not isinstance(credencial, str):
            return ToolResult(
                success=False,
                data=None,
                error=f"la conexión '{servidor.connection}' no está configurada",
            ).to_dict()
        if servidor.auth.scheme == "bearer":
            headers = {"Authorization": f"Bearer {credencial}"}
        else:
            headers = {servidor.auth.header or "": credencial}
        url = conexion.base_url.rstrip("/") + servidor.path
        return (await llamar_tool_mcp(url, headers, tool.name, argumentos)).to_dict()

    # Marca de opt-in de `ToolRegistry.execute` (`core/tools.py`): recibe el
    # context de la corrida al lado de los argumentos, nunca dentro.
    _handler.wants_run_context = True
    return _handler
