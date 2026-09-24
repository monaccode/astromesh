import base64
import json

import httpx
import pytest
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

API = {
    "type": "api",
    "name": "erp-cliente",
    "connection": "api_erp-cliente",
    "auth": {"scheme": "header", "header": "X-Api-Key"},
    "operations": [
        {
            "name": "consultar_stock",
            "description": "Stock de un SKU",
            "parameters": {"sku": {"type": "string", "required": True}},
            "request": {"method": "GET", "path": "/stock/{sku}", "query": {}, "body": None},
            "writes": False,
        },
        {
            "name": "buscar_clientes",
            "description": "Busca clientes",
            "parameters": {"q": {"type": "string", "required": True}, "limite": {"type": "number"}},
            "request": {
                "method": "GET",
                "path": "/clientes",
                "query": {"q": "{q}", "limite": "{limite}"},
                "body": None,
            },
            "writes": False,
        },
        {
            "name": "cotizar",
            "description": "Cotiza sin guardar",
            "parameters": {
                "producto": {"type": "string", "required": True},
                "cantidad": {"type": "number", "required": True},
            },
            "request": {
                "method": "POST",
                "path": "/cotizaciones",
                "query": {},
                "body": {"producto": "{producto}", "cantidad": "{cantidad}"},
            },
            "writes": False,
        },
    ],
}


def _agente(tool: dict) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "demo-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": {"primary": {"source": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
            "tools": [tool],
        },
    }


async def _runtime(tmp_path, tool: dict) -> AgentRuntime:
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(_agente(tool)))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


def _copia(**cambios) -> dict:
    t = json.loads(json.dumps(API))
    t.update(cambios)
    return t


@pytest.fixture
def dns_publico(monkeypatch):
    async def resolver(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)


# `permitir_internos=False` fija la conexión a la IP que chequeó `dns_publico`
# (`tools/builtin/_red.py`, `pin_a_ip_publica`): el request sale a la IP con el
# `Host` original.
PIN = "https://93.184.216.34"


def _ctx(material: dict) -> dict:
    return {"connections": {"api_erp-cliente": {"base_url": "https://api.cliente.com", **material}}}


async def test_registra_cada_operacion_con_el_slug_en_snake_y_sin_internos(tmp_path):
    runtime = await _runtime(tmp_path, API)
    tools = runtime._agents["demo-agent"]._tools._tools
    assert set(tools) == {
        "erp_cliente_consultar_stock",
        "erp_cliente_buscar_clientes",
        "erp_cliente_cotizar",
    }
    for t in tools.values():
        assert t.integration_config["permitir_internos"] is False
        assert t.requires_approval is False


async def test_arma_path_query_y_body(tmp_path, dns_publico):
    runtime = await _runtime(tmp_path, API)
    tools = runtime._agents["demo-agent"]._tools
    ctx = _ctx({"credential": "K"})
    with respx.mock:
        stock = respx.get(f"{PIN}/stock/A-1").mock(
            return_value=httpx.Response(200, json={"disponible": 3})
        )
        clientes = respx.get(f"{PIN}/clientes").mock(return_value=httpx.Response(200, json=[]))
        cot = respx.post(f"{PIN}/cotizaciones").mock(
            return_value=httpx.Response(200, json={"total": 10})
        )
        r = await tools.execute("erp_cliente_consultar_stock", {"sku": "A-1"}, ctx)
        await tools.execute("erp_cliente_buscar_clientes", {"q": "acme"}, ctx)
        await tools.execute("erp_cliente_cotizar", {"producto": "A-1", "cantidad": 2}, ctx)
    assert r["success"] is True
    assert r["data"] == {"disponible": 3}
    # Un query param opcional sin argumento se omite (interpolate_structure).
    assert dict(clientes.calls.last.request.url.params) == {"q": "acme"}
    assert json.loads(cot.calls.last.request.content) == {"producto": "A-1", "cantidad": 2}
    assert stock.calls.last.request.headers["X-Api-Key"] == "K"
    assert stock.calls.last.request.headers["Host"] == "api.cliente.com"


@pytest.mark.parametrize(
    ("auth", "material", "revisar"),
    [
        (
            {"scheme": "header", "header": "X-Token"},
            {"credential": "K"},
            lambda req: req.headers["X-Token"] == "K",
        ),
        (
            {"scheme": "bearer"},
            {"credential": "K"},
            lambda req: req.headers["Authorization"] == "Bearer K",
        ),
        (
            {"scheme": "basic"},
            {"credential": {"username": "ana", "password": "s:e"}},
            lambda req: (
                req.headers["Authorization"] == "Basic " + base64.b64encode(b"ana:s:e").decode()
            ),
        ),
        (
            {"scheme": "query", "param": "api_key"},
            {"credential": "K"},
            lambda req: req.url.params["api_key"] == "K",
        ),
    ],
)
async def test_cada_esquema_de_auth_firma_el_request(
    tmp_path, dns_publico, auth, material, revisar
):
    runtime = await _runtime(tmp_path, _copia(auth=auth))
    with respx.mock:
        ruta = respx.get(f"{PIN}/stock/A-1").mock(return_value=httpx.Response(200, json={}))
        r = await runtime._agents["demo-agent"]._tools.execute(
            "erp_cliente_consultar_stock", {"sku": "A-1"}, _ctx(material)
        )
    assert r["success"] is True
    assert revisar(ruta.calls.last.request)


async def test_una_api_contra_un_host_interno_devuelve_blocked(tmp_path):
    runtime = await _runtime(tmp_path, API)
    ctx = {
        "connections": {
            "api_erp-cliente": {
                "base_url": "http://clarus-backend.clarus-dev.svc",
                "credential": "K",
            }
        }
    }
    with respx.mock:
        ruta = respx.get("http://clarus-backend.clarus-dev.svc/stock/A-1").mock(
            return_value=httpx.Response(200, json={})
        )
        r = await runtime._agents["demo-agent"]._tools.execute(
            "erp_cliente_consultar_stock", {"sku": "A-1"}, ctx
        )
    assert r["success"] is False
    assert "Blocked" in r["error"]
    assert not ruta.called


async def test_writes_true_no_carga_el_agente(tmp_path):
    t = _copia()
    t["operations"][0]["writes"] = True
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" not in runtime._agents
    assert "writes" in runtime._agent_errors["demo-agent"]


async def test_sin_writes_declarado_tampoco_carga(tmp_path):
    t = _copia()
    del t["operations"][0]["writes"]
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" not in runtime._agents


@pytest.mark.parametrize(
    ("romper", "motivo"),
    [
        (lambda t: t.update(name="Erp Cliente"), "slug"),
        (lambda t: t.pop("connection"), "connection"),
        (lambda t: t.update(auth={"scheme": "oauth2"}), "scheme"),
        (lambda t: t.update(auth={"scheme": "header"}), "header_name"),
        (lambda t: t.update(operations=[]), "operations"),
        (lambda t: t["operations"][0]["request"].update(method="DELETE"), "GET o POST"),
        (lambda t: t["operations"][0].update(description=" "), "description"),
        (lambda t: t["operations"][0].update(name="consultar_" + "x" * 60), "64"),
        (lambda t: t["operations"][1].update(name="consultar_stock"), "duplicada"),
    ],
)
async def test_una_ficha_invalida_levanta_con_el_motivo(tmp_path, romper, motivo):
    t = _copia()
    romper(t)
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" not in runtime._agents
    assert motivo in runtime._agent_errors["demo-agent"]


async def test_una_respuesta_binaria_es_un_error_de_la_tool(tmp_path, dns_publico):
    runtime = await _runtime(tmp_path, API)
    with respx.mock:
        respx.get(f"{PIN}/stock/A-1").mock(
            return_value=httpx.Response(
                200, content=b"\x89PNG\r\n", headers={"content-type": "image/png"}
            )
        )
        r = await runtime._agents["demo-agent"]._tools.execute(
            "erp_cliente_consultar_stock", {"sku": "A-1"}, _ctx({"credential": "K"})
        )
    assert r["success"] is False
    assert "no es texto" in r["error"]


async def test_el_texto_se_trunca_al_tope(tmp_path, dns_publico, monkeypatch):
    monkeypatch.setattr("astromesh.integrations.executor._TOPE_TEXTO", 10)
    runtime = await _runtime(tmp_path, API)
    with respx.mock:
        respx.get(f"{PIN}/stock/A-1").mock(
            return_value=httpx.Response(200, text="x" * 50, headers={"content-type": "text/plain"})
        )
        r = await runtime._agents["demo-agent"]._tools.execute(
            "erp_cliente_consultar_stock", {"sku": "A-1"}, _ctx({"credential": "K"})
        )
    assert r["success"] is True
    assert r["data"] == "x" * 10


async def test_una_api_no_deja_claves_ignoradas(tmp_path, caplog):
    await _runtime(tmp_path, API)
    assert "que este runtime no lee" not in caplog.text
