"""`TransportePineado`: la guarda de red de las tools `api`, como transporte de
httpx para un cliente que arma sus propios requests (el SDK de MCP)."""

import gzip

import httpx
import pytest

from astromesh.tools.builtin import _red
from astromesh.tools.builtin._red import TransportePineado


def _dns(monkeypatch, *ips: str) -> list[str]:
    llamadas: list[str] = []

    async def resolver(host, port):
        llamadas.append(host)
        return [(2, 1, 6, "", (ip, 443)) for ip in ips]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    return llamadas


def _registrar() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    vistos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(200, text="ok")

    return httpx.MockTransport(handler), vistos


async def test_conecta_a_la_ip_chequeada_con_host_y_sni_del_nombre(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    interno, vistos = _registrar()
    async with httpx.AsyncClient(transport=TransportePineado(interno=interno)) as c:
        r = await c.post("https://mcp.cliente.com:8443/mcp?x=1", json={})
    assert r.status_code == 200
    assert str(vistos[0].url) == "https://93.184.216.34:8443/mcp?x=1"
    assert vistos[0].headers["Host"] == "mcp.cliente.com:8443"
    assert vistos[0].extensions["sni_hostname"] == "mcp.cliente.com"


async def test_resuelve_una_sola_vez_por_transporte(monkeypatch):
    """Rebinding: la segunda resolución daría una privada; no hay segunda."""
    llamadas: list[str] = []

    async def resolver(host, port):
        llamadas.append(host)
        ip = "93.184.216.34" if len(llamadas) == 1 else "10.1.2.3"
        return [(2, 1, 6, "", (ip, 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    interno, vistos = _registrar()
    async with httpx.AsyncClient(transport=TransportePineado(interno=interno)) as c:
        for _ in range(3):
            await c.post("https://mcp.cliente.com/mcp", json={})
    assert len(llamadas) == 1
    assert {str(v.url) for v in vistos} == {"https://93.184.216.34/mcp"}


@pytest.mark.parametrize(
    ("url", "ips"),
    [
        ("https://10.0.0.5/mcp", ()),
        ("https://clarus-backend.clarus-dev.svc/mcp", ()),
        ("https://localhost/mcp", ()),
        ("https://mcp.cliente.com/mcp", ("10.1.2.3",)),
        ("https://mcp.cliente.com/mcp", ("93.184.216.34", "10.1.2.3")),
        ("https://[64:ff9b::a00:5]/mcp", ()),
        ("https://mcp.cliente.com/mcp", ("64:ff9b::a00:5",)),
    ],
)
async def test_un_destino_interno_no_sale_y_queda_anotado(monkeypatch, url, ips):
    _dns(monkeypatch, *ips)
    interno, vistos = _registrar()
    t = TransportePineado(interno=interno)
    async with httpx.AsyncClient(transport=t) as c:
        with pytest.raises(httpx.RequestError, match="Blocked"):
            await c.post(url, json={})
    assert vistos == []
    assert t.motivo is not None
    assert "Blocked" in t.motivo


async def test_un_nombre_que_no_resuelve_falla_cerrado(monkeypatch):
    async def no_resuelve(host, port):
        raise OSError("nxdomain")

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", no_resuelve)
    interno, vistos = _registrar()
    async with httpx.AsyncClient(transport=TransportePineado(interno=interno)) as c:
        with pytest.raises(httpx.RequestError, match="does not resolve"):
            await c.post("https://mcp.cliente.com/mcp", json={})
    assert vistos == []


async def test_un_redirect_no_se_sigue_y_queda_anotado(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    vistos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(302, headers={"location": "http://10.0.0.5/mcp"})

    t = TransportePineado(interno=httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=t, follow_redirects=False) as c:
        r = await c.post("https://mcp.cliente.com/mcp", json={})
    assert r.status_code == 302
    assert len(vistos) == 1
    assert t.motivo == "el servidor contestó 302"


async def test_el_cuerpo_se_corta_en_el_tope(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(_red, "TOPE_CUERPO", 10)
    t = TransportePineado(interno=httpx.MockTransport(lambda r: httpx.Response(200, text="x" * 50)))
    async with httpx.AsyncClient(transport=t) as c:
        with pytest.raises(httpx.ReadError):
            await c.post("https://mcp.cliente.com/mcp", json={})
    assert t.motivo == "la respuesta pasa los 0 MB"


async def test_nat64_se_juzga_por_la_ipv4_de_adentro():
    # 64:ff9b::a00:5 es 10.0.0.5; 64:ff9b::808:808 es 8.8.8.8 (DNS64 de un host público).
    assert await _red.destino_bloqueado("https://[64:ff9b::a00:5]/x") is not None
    assert await _red.destino_bloqueado("https://[64:ff9b::808:808]/x") is None
    assert await _red.destino_bloqueado("https://[2606:4700::1111]/x") is None


async def test_un_nombre_con_dns64_a_una_publica_sale(monkeypatch):
    _dns(monkeypatch, "64:ff9b::808:808")
    interno, vistos = _registrar()
    t = TransportePineado(interno=interno)
    async with httpx.AsyncClient(transport=t) as c:
        await c.post("https://mcp.cliente.com/mcp", json={})
    assert len(vistos) == 1
    assert t.motivo is None


async def test_una_bomba_gzip_no_se_descomprime(monkeypatch):
    """El tope cuenta bytes decodificados: ~50 KB de gzip que inflan a 6 MB."""
    _dns(monkeypatch, "93.184.216.34")
    bomba = gzip.compress(b"x" * (6 * 1024 * 1024))
    assert len(bomba) < 64 * 1024
    vistos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(200, content=bomba, headers={"content-encoding": "gzip"})

    t = TransportePineado(interno=httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=t) as c:
        with pytest.raises(httpx.RequestError, match="content-encoding gzip"):
            await c.post("https://mcp.cliente.com/mcp", json={})
    assert vistos[0].headers["Accept-Encoding"] == "identity"
    assert t.motivo is not None
    assert "gzip" in t.motivo


async def test_un_405_no_tapa_la_falla_real(monkeypatch):
    """El SDK de MCP recibe 405 en el GET de SSE por diseño: no es la guarda."""
    _dns(monkeypatch, "93.184.216.34")
    monkeypatch.setattr(_red, "TOPE_CUERPO", 10)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(405)
        return httpx.Response(200, text="x" * 50)

    t = TransportePineado(interno=httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=t) as c:
        assert (await c.get("https://mcp.cliente.com/mcp")).status_code == 405
        assert t.motivo is None
        with pytest.raises(httpx.ReadError):
            await c.post("https://mcp.cliente.com/mcp", json={})
    assert t.motivo == "la respuesta pasa los 0 MB"


async def test_un_transporte_sirve_a_un_solo_host(monkeypatch):
    _dns(monkeypatch, "93.184.216.34")
    interno, vistos = _registrar()
    t = TransportePineado(interno=interno)
    async with httpx.AsyncClient(transport=t) as c:
        await c.post("https://mcp.cliente.com/mcp", json={})
        with pytest.raises(httpx.RequestError, match="only one host"):
            await c.post("https://otro.cliente.com/mcp", json={})
    assert len(vistos) == 1
    assert t.motivo is not None
    assert "only one host" in t.motivo
