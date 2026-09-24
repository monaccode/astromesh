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
    Y si el resolver FALLA (en vez de responder "no existe"), también se
    bloquea: devolver `None` ahí mandaría el request sin pinear, por hostname
    — el camino guardado NUNCA manda por hostname, porque eso reabre la
    ventana de rebinding que esta función existe para cerrar (`_chequear`
    resolvería nombre por su cuenta, y httpcore una tercera vez al conectar).

    `httpx.URL` hace el trabajo fino: `.raw_host` es el host ya IDNA-encodeado
    (lo mismo que httpx manda a conectar — un `Host`/SNI armado a mano con el
    `hostname` unicode de `urlparse` revienta con `UnicodeEncodeError` en un
    header), y `.copy_with(host=ip)` deja el resto de la URL —puerto, path,
    userinfo, query, fragment— byte a byte, con el corchete de un IPv6 puesto
    solo. El userinfo de una URL con credenciales (`https://u:pw@host`) no lo
    toca esta función a propósito: acá la auth la resuelve `apply_auth` sobre
    `resolved.material`, nunca el userinfo de la URL (`executor.py::execute`).
    """
    u = httpx.URL(url)
    host = u.raw_host.decode("ascii") if u.raw_host else ""
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
        infos = await _resolver(host, u.port)
    except OSError as exc:
        # `destino_bloqueado` deja pasar este mismo caso ("va a fallar solo",
        # sin pin no hay a dónde llegar) porque ahí el request sigue sin
        # resolver — nunca llega a la red. Acá SÍ hay un camino sin pin: el
        # request seguiría por hostname, y un resolver que falla la primera
        # vez y responde distinto la segunda (rebinding con una respuesta
        # negativa) volvería a resolver dos veces más sin ningún chequeo de
        # por medio. Por eso este caso se bloquea en vez de degradar a `None`.
        raise httpx.RequestError(f"Blocked: {host} does not resolve") from exc
    direcciones = [str(info[4][0]) for info in infos]
    if not direcciones or any(_ip_no_global(ip) for ip in direcciones):
        raise httpx.RequestError(f"Blocked: {host} resolves to a non-public address")

    url_pineada = str(u.copy_with(host=direcciones[0]))

    default_port = 443 if u.scheme == "https" else 80
    host_header = host if not u.port or u.port == default_port else f"{host}:{u.port}"
    return url_pineada, host, host_header


def cliente_seguro(permitir_internos: bool = False, **kwargs) -> httpx.AsyncClient:
    """Un AsyncClient que chequea el destino de cada request (redirects
    incluidos). `permitir_internos` es sólo para un despliegue que lo configure
    a propósito (la config `allow_localhost` de `http_request`)."""
    if permitir_internos:
        return httpx.AsyncClient(**kwargs)
    return httpx.AsyncClient(event_hooks={"request": [_chequear]}, **kwargs)
