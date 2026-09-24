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
        ruta = respx.get("https://api.cliente.com/datos").mock(
            return_value=httpx.Response(200, json={"stock": 3})
        )
        r = await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert r["success"] is True
    assert r["data"] == {"stock": 3}
    assert ruta.called


async def test_sin_internos_no_llega_a_un_host_interno_por_un_redirect(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    with respx.mock:
        respx.get("https://api.cliente.com/datos").mock(
            return_value=httpx.Response(302, headers={"location": "http://10.0.0.5/datos"})
        )
        interna = respx.get("http://10.0.0.5/datos").mock(
            return_value=httpx.Response(200, json={"secreto": 1})
        )
        await _registro(False).execute("interna_leer", {}, _ctx("https://api.cliente.com"))
    assert not interna.called
