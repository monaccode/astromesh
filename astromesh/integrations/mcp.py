"""La llamada a una tool del servidor MCP de un tenant.

Cada llamada es una sesión corta del SDK oficial (`initialize` + `tools/call`
+ cierre) por `TransportePineado` (`tools/builtin/_red.py`): host público, IP
pineada, sin redirects, cuerpo acotado.
"""

from __future__ import annotations

from datetime import timedelta

import httpx

from astromesh.integrations.manifest import Defaults
from astromesh.tools.base import ToolResult
from astromesh.tools.builtin._red import TransportePineado

#: Timeout de cada llamada: el de las integraciones (`manifest.py::Defaults`).
TIMEOUT_LLAMADA = Defaults().timeout_seconds


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
    from mcp import ClientSession, McpError, types
    from mcp.client.streamable_http import streamable_http_client

    # Leído acá y no como default del parámetro: un default se evalúa una vez,
    # al importar, y el test del tope no podría achicarlo.
    timeout = timeout if timeout is not None else TIMEOUT_LLAMADA

    t = TransportePineado(interno=transporte) if transporte else TransportePineado()
    cliente = httpx.AsyncClient(
        transport=t, headers=headers, timeout=timeout, follow_redirects=False
    )
    try:
        async with (
            cliente,
            streamable_http_client(url, http_client=cliente) as (r, w, _),
            ClientSession(r, w, read_timeout_seconds=timedelta(seconds=timeout)) as s,
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
        if t.motivo:
            motivo = t.motivo
        elif isinstance(causa, McpError):
            motivo = f"el servidor MCP rechazó la llamada: {causa.error.message}"
        else:
            motivo = f"{type(causa).__name__}: {causa}"
        return ToolResult(success=False, data=None, error=motivo)
    texto = _texto(resultado)
    if resultado.isError:
        return ToolResult(success=False, data=None, error=texto or "la tool devolvió un error")
    return ToolResult(success=True, data=texto)
