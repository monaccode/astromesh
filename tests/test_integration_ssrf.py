"""La guarda de red del ejecutor de integraciones.

Una integración de catálogo apunta legítimamente a servicios del cluster
(conocimiento, praxis); una tool `api` la escribe el tenant. Por eso la guarda
es opt-in por tool (`permitir_internos=False`) y el default no cambia nada.
"""

import httpx
import pytest
import respx

from astromesh.core.tools import ToolRegistry
from astromesh.integrations.credentials import CredentialResolver
from astromesh.integrations.manifest import IntegrationManifest

MANIFEST = IntegrationManifest(
    slug="interna",
    auth={"scheme": "none"},
    actions=[
        {"name": "leer", "description": "Lee", "request": {"method": "GET", "path": "/datos"}}
    ],
)


def _registro(permitir_internos: bool) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register_integration_tool(
        name="interna_leer",
        manifest=MANIFEST,
        action=MANIFEST.action("leer"),
        connection="c",
        resolver=CredentialResolver(),
        permitir_internos=permitir_internos,
    )
    return reg


def _ctx(base_url: str) -> dict:
    return {"connections": {"c": {"base_url": base_url}}}


def _dns(monkeypatch, ip: str) -> None:
    async def resolver(host, port):
        return [(2, 1, 6, "", (ip, 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)


@respx.mock
async def test_una_integracion_de_catalogo_sigue_alcanzando_un_host_interno():
    ruta = respx.get("http://praxis-backend.praxis-dev.svc/datos").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    reg = ToolRegistry()
    # Sin pasar el parámetro: es el default el que no puede romper conocimiento/praxis.
    reg.register_integration_tool(
        name="interna_leer",
        manifest=MANIFEST,
        action=MANIFEST.action("leer"),
        connection="c",
        resolver=CredentialResolver(),
    )
    r = await reg.execute("interna_leer", {}, _ctx("http://praxis-backend.praxis-dev.svc"))
    assert r["success"] is True
    assert ruta.called


@pytest.mark.parametrize(
    "base",
    [
        "http://10.0.0.5",
        "http://clarus-backend.clarus-dev.svc",
        "http://localhost:8080",
        "http://169.254.169.254",
    ],
)
@respx.mock
async def test_sin_internos_bloquea_un_destino_interno(base):
    ruta = respx.get(f"{base}/datos").mock(return_value=httpx.Response(200, json={}))
    r = await _registro(False).execute("interna_leer", {}, _ctx(base))
    assert r["success"] is False
    assert "Blocked" in r["error"]
    assert not ruta.called


async def test_sin_internos_bloquea_un_nombre_que_resuelve_a_una_privada(monkeypatch):
    _dns(monkeypatch, "10.1.2.3")
    with respx.mock:
        ruta = respx.get("https://api.cliente.com/datos").mock(
            return_value=httpx.Response(200, json={})
        )
        r = await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert r["success"] is False
    assert "Blocked" in r["error"]
    assert not ruta.called


async def test_sin_internos_deja_pasar_un_host_publico(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    with respx.mock:
        # El pin manda el request a la IP chequeada, no al nombre: la ruta
        # mockeada es la IP (ver test_..._pinea_a_la_primera_ip... para la
        # razón — DNS rebinding).
        ruta = respx.get("https://93.184.216.34/datos").mock(
            return_value=httpx.Response(200, json={"stock": 3})
        )
        r = await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert r["success"] is True
    assert r["data"] == {"stock": 3}
    assert ruta.called


async def test_sin_internos_no_llega_a_un_host_interno_por_un_redirect(monkeypatch):
    # `_run_request` nunca pasa `follow_redirects=True`, así que httpx ya
    # rechaza seguir el 302 por su cuenta: este test no puede discriminar la
    # guarda (pasa igual con la guarda sacada, mientras el redirect siga sin
    # seguirse). Lo que fija es que el host interno nunca reciba un request.
    _dns(monkeypatch, "93.184.216.34")
    with respx.mock:
        respx.get("https://93.184.216.34/datos").mock(
            return_value=httpx.Response(302, headers={"location": "http://10.0.0.5/datos"})
        )
        interna = respx.get("http://10.0.0.5/datos").mock(
            return_value=httpx.Response(200, json={"secreto": 1})
        )
        await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert not interna.called


async def test_sin_internos_pinea_a_la_primera_ip_del_resolver_y_nunca_llega_a_la_segunda(
    monkeypatch,
):
    """DNS rebinding: el nombre lo resuelve el tenant en su propio `base_url`,
    así que puede responder distinto entre una llamada al resolver y la
    siguiente (TTL bajo). El pin resuelve UNA sola vez y fija la conexión a
    esa dirección — la request real tiene que ir a la primera IP (pública) y
    la segunda (privada) no se pide nunca, ni siquiera para chequearla."""
    llamadas: list[str] = []

    async def resolver(host, port):
        llamadas.append(host)
        ip = "93.184.216.34" if len(llamadas) == 1 else "10.1.2.3"
        return [(2, 1, 6, "", (ip, 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    with respx.mock:
        publica = respx.get("https://93.184.216.34/datos").mock(
            return_value=httpx.Response(200, json={"ok": 1})
        )
        privada = respx.get("https://10.1.2.3/datos").mock(
            return_value=httpx.Response(200, json={"secreto": 1})
        )
        r = await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert r["success"] is True
    assert publica.called
    assert not privada.called
    assert llamadas == ["api.cliente.com"]


async def test_sin_internos_manda_host_y_sni_del_nombre_original(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    with respx.mock:
        ruta = respx.get("https://93.184.216.34/datos").mock(
            return_value=httpx.Response(200, json={"ok": 1})
        )
        await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    peticion = ruta.calls.last.request
    assert peticion.headers["host"] == "api.cliente.com"
    assert peticion.extensions.get("sni_hostname") == "api.cliente.com"


async def test_sin_internos_bloquea_si_una_sola_direccion_de_la_resolucion_no_es_publica(
    monkeypatch,
):
    """Una sola resolución que trae pública Y privada junta: no hay "usar la
    pública y descartar la otra", porque el orden de la respuesta no lo
    elige quien pregunta. Se bloquea entera."""

    async def resolver(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.1.2.3", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    with respx.mock:
        ruta = respx.route().mock(return_value=httpx.Response(200, json={}))
        r = await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert r["success"] is False
    assert "Blocked" in r["error"]
    assert not ruta.called
