"""Lo que un modelo NO puede hacer con los builtins, aunque se lo pidan.

El modelo decide los argumentos de una tool, y un documento que el agente lee
puede decirle qué pedir (prompt injection). Estos tests fijan tres cierres:
un template de `json_transform` no ejecuta código, `wikipedia` no cambia de
host, y las tools de red no alcanzan servicios internos del cluster.
"""

import socket

import pytest
import respx
from httpx import Response

from astromesh.tools.base import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(agent_name="t", session_id="s")


# --- json_transform ---------------------------------------------------------


async def test_json_transform_no_ejecuta_codigo():
    from astromesh.tools.builtin.utilities import JsonTransformTool

    r = await JsonTransformTool().execute(
        {"data": {}, "template": "{{ lipsum.__globals__.os.popen('echo hola').read() | tojson }}"},
        _ctx(),
    )
    assert r.success is False
    assert "hola" not in str(r.data)


async def test_json_transform_sigue_transformando():
    from astromesh.tools.builtin.utilities import JsonTransformTool

    r = await JsonTransformTool().execute(
        {"data": {"a": 1}, "template": '{"b": {{ data.a + 1 }}}'}, _ctx()
    )
    assert r.success is True
    assert r.data == {"b": 2}


# --- wikipedia --------------------------------------------------------------


@pytest.mark.parametrize(
    "lang",
    ["nexus.nexus-dev.svc.cluster.local:8080/x#", "10.0.0.1", "en.evil.com", "", "EN/../"],
)
async def test_wikipedia_rechaza_un_idioma_que_cambia_el_host(lang):
    from astromesh.tools.builtin.web_search import WikipediaTool

    r = await WikipediaTool().execute({"topic": "Python", "language": lang}, _ctx())
    assert r.success is False
    assert "language" in (r.error or "").lower()


@respx.mock
async def test_wikipedia_codifica_el_tema():
    from astromesh.tools.builtin.web_search import WikipediaTool

    ruta = respx.get("https://es.wikipedia.org/api/rest_v1/page/summary/a%2F..%2F..%2Fx").mock(
        return_value=Response(200, json={"title": "t", "extract": "e"})
    )
    r = await WikipediaTool().execute({"topic": "a/../../x", "language": "es"}, _ctx())
    assert ruta.called
    assert r.success is True


# --- tools de red -----------------------------------------------------------


INTERNOS = [
    "http://nexus.nexus-dev.svc.cluster.local:8080/api/v1/admin",
    "http://astromesh-redis:6379/",
    "http://10.42.0.253/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]:8000/",
    "http://127.0.0.1:8000/",
    "http://localhost/",
    "file:///etc/passwd",
]


@pytest.mark.parametrize("url", INTERNOS)
async def test_http_request_no_alcanza_destinos_internos(url):
    from astromesh.tools.builtin.http import HttpRequestTool

    r = await HttpRequestTool().execute({"method": "GET", "url": url}, _ctx())
    assert r.success is False
    assert "blocked" in (r.error or "").lower()


@pytest.mark.parametrize("url", INTERNOS[:4])
async def test_graphql_query_no_alcanza_destinos_internos(url):
    from astromesh.tools.builtin.http import GraphQLQueryTool

    r = await GraphQLQueryTool().execute({"endpoint": url, "query": "{ x }"}, _ctx())
    assert r.success is False
    assert "blocked" in (r.error or "").lower()


@pytest.mark.parametrize("url", INTERNOS[:4])
async def test_web_scrape_no_alcanza_destinos_internos(url):
    from astromesh.tools.builtin.web_search import WebScrapeTool

    r = await WebScrapeTool().execute({"url": url}, _ctx())
    assert r.success is False
    assert "blocked" in (r.error or "").lower()


@pytest.mark.parametrize("url", INTERNOS[:4])
async def test_send_webhook_no_alcanza_destinos_internos(url):
    from astromesh.tools.builtin.communication import SendWebhookTool

    r = await SendWebhookTool().execute({"url": url, "payload": {}}, _ctx())
    assert r.success is False
    assert "blocked" in (r.error or "").lower()


async def test_un_nombre_que_resuelve_a_una_ip_privada_se_bloquea(monkeypatch):
    from astromesh.tools.builtin import _red
    from astromesh.tools.builtin.http import HttpRequestTool

    async def falso(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port or 80))]

    monkeypatch.setattr(_red, "_resolver", falso)
    r = await HttpRequestTool().execute(
        {"method": "GET", "url": "http://parece-publico.com/"}, _ctx()
    )
    assert r.success is False
    assert "blocked" in (r.error or "").lower()


@respx.mock
async def test_un_redirect_hacia_un_destino_interno_se_bloquea(monkeypatch):
    from astromesh.tools.builtin import _red
    from astromesh.tools.builtin.web_search import WebScrapeTool

    async def publico(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

    monkeypatch.setattr(_red, "_resolver", publico)
    respx.get("https://publico.com/").mock(
        return_value=Response(302, headers={"location": "http://10.0.0.5/secreto"})
    )
    interno = respx.get("http://10.0.0.5/secreto").mock(return_value=Response(200, text="secreto"))
    r = await WebScrapeTool().execute({"url": "https://publico.com/"}, _ctx())
    assert not interno.called
    assert r.success is False


@respx.mock
async def test_un_destino_publico_sigue_andando(monkeypatch):
    from astromesh.tools.builtin import _red
    from astromesh.tools.builtin.http import HttpRequestTool

    async def publico(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

    monkeypatch.setattr(_red, "_resolver", publico)
    respx.get("https://api.example.com/data").mock(return_value=Response(200, json={"ok": True}))
    r = await HttpRequestTool().execute(
        {"method": "GET", "url": "https://api.example.com/data"}, _ctx()
    )
    assert r.success is True
