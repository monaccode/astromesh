"""A dónde puede ir una tool de red que maneja el modelo.

El modelo elige la URL (o el endpoint) de `http_request`, `graphql_query`,
`web_scrape` y `send_webhook`, y un documento que el agente lee puede decirle
cuál elegir. Sin este cierre, esas tools alcanzaban los servicios internos del
cluster —Nexus, Redis, la base— y la metadata de la nube.

La regla: sólo `http`/`https`, y el host tiene que ser PÚBLICO. Se rechaza un
nombre interno (sin punto, `localhost`, `*.local`, `*.internal`, `*.svc`,
`*.cluster.local`) sin resolver nada, y un nombre que resuelve a una IP no
global (privada, loopback, link-local, reservada). El chequeo corre en CADA
request del cliente —redirects incluidos— con `cliente_seguro()`.

ponytail: la IP se resuelve para chequear y httpx vuelve a resolver para
conectar, así que un DNS que cambia entre las dos (rebinding) todavía pasa.
Cerrarlo del todo es conectar a la IP ya chequeada; hasta entonces, la
NetworkPolicy del pod es la otra mitad del cierre.
"""

import asyncio
import ipaddress
from urllib.parse import urlparse

import httpx

_SUFIJOS_INTERNOS = (".local", ".internal", ".svc", ".cluster.local", ".localhost")


async def _resolver(host: str, port: int | None) -> list:
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo(host, port)


def _ip_no_global(texto: str) -> bool:
    try:
        return not ipaddress.ip_address(texto.split("%")[0]).is_global
    except ValueError:
        return False


async def destino_bloqueado(url: str) -> str | None:
    """Por qué `url` no se puede pedir, o None si se puede."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return f"Blocked: scheme {p.scheme or '(none)'!r} is not allowed"
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        return "Blocked: URL without a host"

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return None if ip.is_global else f"Blocked: {host} is not a public address"

    if host == "localhost" or "." not in host or host.endswith(_SUFIJOS_INTERNOS):
        return f"Blocked: {host} is an internal host"

    try:
        infos = await _resolver(host, p.port)
    except OSError:
        # No resuelve: el request va a fallar solo. No hay a dónde llegar.
        return None
    for info in infos:
        if _ip_no_global(str(info[4][0])):
            return f"Blocked: {host} resolves to a non-public address"
    return None


async def _chequear(request: httpx.Request) -> None:
    motivo = await destino_bloqueado(str(request.url))
    if motivo:
        raise httpx.RequestError(motivo, request=request)


def cliente_seguro(permitir_internos: bool = False, **kwargs) -> httpx.AsyncClient:
    """Un AsyncClient que chequea el destino de cada request (redirects
    incluidos). `permitir_internos` es sólo para un despliegue que lo configure
    a propósito (la config `allow_localhost` de `http_request`)."""
    if permitir_internos:
        return httpx.AsyncClient(**kwargs)
    return httpx.AsyncClient(event_hooks={"request": [_chequear]}, **kwargs)
