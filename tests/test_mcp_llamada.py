"""`llamar_tool_mcp`: una sesión corta del SDK oficial por `TransportePineado`."""

import asyncio
import json
import sys
import types

import httpx
import pytest
import respx

from astromesh.integrations import mcp as modulo
from astromesh.integrations.mcp import llamar_tool_mcp
from astromesh.tools.builtin import _red

PIN = "https://93.184.216.34/mcp"
URL = "https://praxis.cliente.com/mcp"
HEADERS = {"Authorization": "Bearer praxis_K"}


@pytest.fixture
def dns_publico(monkeypatch):
    async def resolver(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)


def servidor_mcp(resultado: dict | None = None, sse: bool = True, error: dict | None = None):
    """Un servidor MCP sin sesión, como el de PRAXIS: SSE por defecto. Anota
    cada método que recibe en `metodos`."""
    metodos: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        m = json.loads(request.content)
        metodos.append(m["method"])
        if "id" not in m:
            return httpx.Response(202)
        if m["method"] == "initialize":
            cuerpo = {
                "jsonrpc": "2.0",
                "id": m["id"],
                "result": {
                    "protocolVersion": m["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "praxis", "version": "0"},
                },
            }
        elif error is not None:
            cuerpo = {"jsonrpc": "2.0", "id": m["id"], "error": error}
        else:
            cuerpo = {"jsonrpc": "2.0", "id": m["id"], "result": resultado}
        if sse:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=f"event: message\ndata: {json.dumps(cuerpo)}\n\n",
            )
        return httpx.Response(200, json=cuerpo)

    return responder, metodos


@pytest.mark.parametrize("sse", [True, False])
async def test_initialize_antes_de_tools_call_contra_la_ip_pineada(dns_publico, sse):
    responder, metodos = servidor_mcp({"content": [{"type": "text", "text": "3 registros"}]}, sse)
    with respx.mock:
        ruta = respx.post(PIN).mock(side_effect=responder)
        r = await llamar_tool_mcp(URL, HEADERS, "Get-Record.v2", {"id": "7"})
    assert r.success is True
    assert r.data == "3 registros"
    # Sin el `tools/list` extra que haría `ClientSession.call_tool`.
    assert metodos == ["initialize", "notifications/initialized", "tools/call"]
    llamada = json.loads(ruta.calls.last.request.content)
    assert llamada["params"] == {"name": "Get-Record.v2", "arguments": {"id": "7"}}
    req = ruta.calls.last.request
    assert req.headers["Authorization"] == "Bearer praxis_K"
    assert req.headers["Host"] == "praxis.cliente.com"


async def test_is_error_es_un_error_de_la_tool(dns_publico):
    responder, _ = servidor_mcp(
        {"content": [{"type": "text", "text": "sin permiso"}], "isError": True}
    )
    with respx.mock:
        respx.post(PIN).mock(side_effect=responder)
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert r.error == "sin permiso"


async def test_un_error_json_rpc_es_un_error_de_la_tool(dns_publico):
    responder, _ = servidor_mcp(error={"code": -32602, "message": "Tool nope not found"})
    with respx.mock:
        respx.post(PIN).mock(side_effect=responder)
        r = await llamar_tool_mcp(URL, HEADERS, "nope", {})
    assert r.success is False
    assert "Tool nope not found" in r.error


async def test_imagen_audio_y_recurso_se_omiten(dns_publico):
    responder, _ = servidor_mcp(
        {
            "content": [
                {"type": "text", "text": "hola"},
                {"type": "image", "data": "AA==", "mimeType": "image/png"},
                {"type": "audio", "data": "AA==", "mimeType": "audio/wav"},
                {"type": "resource", "resource": {"uri": "file:///x", "text": "y"}},
            ]
        }
    )
    with respx.mock:
        respx.post(PIN).mock(side_effect=responder)
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.data == "hola\n[imagen omitida]\n[audio omitido]\n[recurso omitido]"


async def test_un_cuerpo_de_mas_del_tope_es_un_error(dns_publico, monkeypatch):
    # El SDK se traga el error de lectura (`mcp/client/streamable_http.py:393-395`)
    # y la llamada termina por timeout; el motivo sale de `TransportePineado`.
    monkeypatch.setattr(_red, "TOPE_CUERPO", 2048)
    monkeypatch.setattr(modulo, "TIMEOUT_LLAMADA", 1)
    responder, _ = servidor_mcp({"content": [{"type": "text", "text": "x" * 5000}]})
    with respx.mock:
        respx.post(PIN).mock(side_effect=responder)
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert r.error == "la respuesta pasa los 0 MB"


async def test_un_nombre_que_resuelve_a_una_privada_no_sale(monkeypatch):
    async def resolver(host, port):
        return [(2, 1, 6, "", ("10.1.2.3", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    with respx.mock:
        ruta = respx.route().mock(return_value=httpx.Response(200))
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert "Blocked" in r.error
    assert not ruta.called


async def test_un_redirect_no_se_sigue(dns_publico):
    with respx.mock:
        respx.post(PIN).mock(
            return_value=httpx.Response(302, headers={"location": "http://10.0.0.5/mcp"})
        )
        interna = respx.route(host="10.0.0.5").mock(return_value=httpx.Response(200))
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert r.error == "el servidor contestó 302"
    assert not interna.called


async def test_un_redirect_al_mismo_host_tampoco_se_sigue(dns_publico):
    # El transporte ya corta un redirect a OTRO host (un host por transporte);
    # a otra ruta del MISMO host sólo lo frena `follow_redirects=False`.
    responder, _ = servidor_mcp({"content": [{"type": "text", "text": "no debería"}]})

    def tools_call_redirige(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content).get("method") == "tools/call":
            return httpx.Response(302, headers={"location": "https://praxis.cliente.com/otra"})
        return responder(request)

    with respx.mock:
        respx.post(PIN).mock(side_effect=tools_call_redirige)
        otra = respx.route(url__startswith="https://93.184.216.34/otra").mock(side_effect=responder)
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert r.error == "el servidor contestó 302"
    assert not otra.called


def servidor_lento(demora: float):
    """`servidor_mcp` con `demora` segundos en `initialize` y en `tools/call`."""
    responder, _ = servidor_mcp({"content": [{"type": "text", "text": "tarde"}]})

    async def lento(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content).get("method") in ("initialize", "tools/call"):
            await asyncio.sleep(demora)
        return responder(request)

    return lento


async def test_el_timeout_es_de_la_llamada_entera(dns_publico):
    # Cada request entra en el tope; las dos juntas no.
    with respx.mock:
        respx.post(PIN).mock(side_effect=servidor_lento(0.6))
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {}, timeout=1)
    assert r.success is False
    assert r.error == "el servidor MCP no contestó en 1 s"


async def test_un_servidor_que_no_contesta_es_un_timeout(dns_publico):
    with respx.mock:
        respx.post(PIN).mock(side_effect=servidor_lento(30))
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {}, timeout=0.5)
    assert r.success is False
    assert r.error == "el servidor MCP no contestó en 0.5 s"


@pytest.mark.parametrize("status", [401, 500])
async def test_un_4xx_o_5xx_dice_el_status_sin_la_ip_pineada(dns_publico, status):
    with respx.mock:
        respx.post(PIN).mock(return_value=httpx.Response(status))
        r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert r.error == f"el servidor MCP contestó {status}"


async def test_un_sdk_de_mcp_incompatible_es_un_error_de_la_tool(dns_publico, monkeypatch):
    # mcp 2.x no tiene `McpError` (es `MCPError`): la llamada degrada, no levanta.
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    r = await llamar_tool_mcp(URL, HEADERS, "query_records", {})
    assert r.success is False
    assert r.error.startswith("este runtime no tiene un SDK de MCP compatible (mcp 1.x)")


async def test_el_rechazo_json_rpc_gana_a_un_3xx_tragado(dns_publico):
    # Con sesión, el SDK abre un GET de SSE; su 302 se lo traga
    # (`mcp/client/streamable_http.py:247-275`) pero queda anotado en el
    # transporte. Lo que terminó la llamada es el rechazo del `tools/call`.
    responder, _ = servidor_mcp(error={"code": -32602, "message": "Tool nope not found"})

    async def con_sesion(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(302, headers={"location": "https://praxis.cliente.com/otra"})
        if request.method == "DELETE":
            return httpx.Response(200)
        if json.loads(request.content).get("method") == "tools/call":
            await asyncio.sleep(0.2)  # el GET llega antes
        r = responder(request)
        r.headers["mcp-session-id"] = "s1"
        return r

    with respx.mock:
        get = respx.route(url=PIN).mock(side_effect=con_sesion)
        r = await llamar_tool_mcp(URL, HEADERS, "nope", {})
    assert any(c.request.method == "GET" for c in get.calls)
    assert r.success is False
    assert r.error == "el servidor MCP rechazó la llamada: Tool nope not found"
