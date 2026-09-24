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
conectar, así que un DNS que cambia entre las dos (rebinding) todavía pasa
en `cliente_seguro()` — `http_request`, `graphql_query`, `web_scrape`,
`send_webhook` (`astromesh/tools/builtin/utilities.py`). El camino
`permitir_internos=False` del ejecutor de integraciones (tools `api`,
`astromesh/integrations/executor.py::_run_request`) SÍ está pineado:
`pin_a_ip_publica()` resuelve una vez y fija la conexión a esa IP, así que
ahí no queda ventana de rebinding. Hasta que `cliente_seguro()` pinee
también, la NetworkPolicy del pod es la otra mitad del cierre para esas
cuatro tools.
"""

import asyncio
import ipaddress
from urllib.parse import urlparse, urlunparse

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


async def pin_a_ip_publica(url: str) -> tuple[str, str, str] | None:
    """Resuelve el host de `url` UNA sola vez y devuelve la URL con ese host
    reemplazado por la IP pública que se chequeó, para que quien conecte
    (httpcore) no vuelva a resolver el nombre — cerrando la ventana de DNS
    rebinding que describe el comentario de arriba del módulo.

    Devuelve `(url_pineada, sni_hostname, host_header)`, o `None` si no hay
    nombre que fijar: la URL ya usa una IP literal, o el host cae en un caso
    que `destino_bloqueado` bloquea sin resolver (`.svc`, `localhost`, sin
    punto) — ésos quedan para el chequeo de siempre, que ya los rechaza sin
    tocar la red. Levanta `httpx.RequestError` si el nombre no resuelve a
    (sólo) direcciones públicas: si UNA sola dirección no es global, se
    bloquea la resolución entera — no hay "usar la pública y descartar la
    otra", porque cuál devuelve el resolver primero no lo elige quien pregunta.
    """
    p = urlparse(url)
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    if host == "localhost" or "." not in host or host.endswith(_SUFIJOS_INTERNOS):
        return None
    try:
        infos = await _resolver(host, p.port)
    except OSError:
        # No resuelve: destino_bloqueado tampoco lo bloquea (va a fallar solo)
        # y no hay IP para fijar.
        return None
    direcciones = [str(info[4][0]) for info in infos]
    if not direcciones or any(_ip_no_global(ip) for ip in direcciones):
        raise httpx.RequestError(f"Blocked: {host} resolves to a non-public address")

    ip = direcciones[0]
    netloc_ip = f"[{ip}]" if ":" in ip else ip
    if p.port:
        netloc_ip = f"{netloc_ip}:{p.port}"
    url_pineada = urlunparse(p._replace(netloc=netloc_ip))

    default_port = 443 if p.scheme == "https" else 80
    host_header = host if not p.port or p.port == default_port else f"{host}:{p.port}"
    return url_pineada, host, host_header


def cliente_seguro(permitir_internos: bool = False, **kwargs) -> httpx.AsyncClient:
    """Un AsyncClient que chequea el destino de cada request (redirects
    incluidos). `permitir_internos` es sólo para un despliegue que lo configure
    a propósito (la config `allow_localhost` de `http_request`)."""
    if permitir_internos:
        return httpx.AsyncClient(**kwargs)
    return httpx.AsyncClient(event_hooks={"request": [_chequear]}, **kwargs)
