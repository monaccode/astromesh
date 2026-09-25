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


#: Tope del cuerpo de una respuesta en `TransportePineado`: el mismo de las
#: tools `api` (`integrations/executor.py::_TOPE_TEXTO`).
TOPE_CUERPO = 5 * 1024 * 1024


class _CuerpoAcotado(httpx.AsyncByteStream):
    """El stream de la respuesta, cortado apenas pasa el tope: nunca se
    bufferea entero para medirlo después."""

    def __init__(self, stream, tope: int, transporte: "TransportePineado"):
        self._stream = stream
        self._tope = tope
        self._transporte = transporte

    async def __aiter__(self):
        total = 0
        async for chunk in self._stream:
            total += len(chunk)
            if total > self._tope:
                self._transporte.anotar(f"la respuesta pasa los {self._tope // (1024 * 1024)} MB")
                raise httpx.ReadError(self._transporte.motivo or "")
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class TransportePineado(httpx.AsyncBaseTransport):
    """La guarda de `pin_a_ip_publica` como transporte de httpx, para un
    cliente que no arma sus requests (el SDK de MCP, `integrations/mcp.py`).

    Resuelve cada host UNA vez por transporte —una sesión— y exige que TODAS
    sus IPs sean globales; conecta a la IP chequeada con el `Host` y el SNI
    originales; falla cerrado si el nombre no resuelve (`pin_a_ip_publica`);
    corta el cuerpo en `tope` bytes. No sigue redirects: eso lo decide el
    cliente (`follow_redirects=False`), y un 3xx queda anotado en `motivo`.

    `motivo` guarda la PRIMERA falla que vio: el SDK de MCP se traga algunas
    (`mcp/client/streamable_http.py:393-395` y `:429-430`) y la llamada sólo
    termina por timeout; quien llama la lee para decir qué pasó de verdad.
    """

    def __init__(
        self,
        tope: int | None = None,
        interno: httpx.AsyncBaseTransport | None = None,
    ):
        self._interno = interno or httpx.AsyncHTTPTransport()
        self._tope = tope if tope is not None else TOPE_CUERPO
        self._pines: dict[tuple, tuple[str, str, str] | None] = {}
        self.motivo: str | None = None

    def anotar(self, motivo: str) -> None:
        if self.motivo is None:
            self.motivo = motivo

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        clave = (request.url.scheme, request.url.raw_host, request.url.port)
        if clave not in self._pines:
            try:
                # `pin_a_ip_publica` primero: es la ÚNICA resolución. Si no hay
                # nombre que fijar (IP literal, o un nombre interno) devuelve
                # None, y `destino_bloqueado` decide sin resolver nada.
                pin = await pin_a_ip_publica(str(request.url))
                if pin is None:
                    bloqueo = await destino_bloqueado(str(request.url))
                    if bloqueo:
                        raise httpx.RequestError(bloqueo, request=request)
                self._pines[clave] = pin
            except httpx.RequestError as exc:
                self.anotar(str(exc))
                raise
        pin = self._pines[clave]
        if pin is not None:
            url_pineada, sni, host_header = pin
            request.url = request.url.copy_with(host=httpx.URL(url_pineada).host)
            request.headers["Host"] = host_header
            if request.url.scheme == "https":
                request.extensions = {**request.extensions, "sni_hostname": sni}
        response = await self._interno.handle_async_request(request)
        if response.status_code >= 300:
            self.anotar(f"el servidor contestó {response.status_code}")
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_CuerpoAcotado(response.stream, self._tope, self),
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        await self._interno.aclose()
