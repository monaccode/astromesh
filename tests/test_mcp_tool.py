"""La tool `mcp`: el servidor MCP de un tenant con su instantánea de tools."""

import json
import socket

import httpx
import pytest
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

SERVIDOR = {
    "type": "mcp",
    "name": "praxis-erp",
    "connection": "mcp_praxis-erp",
    "path": "/mcp",
    "auth": {"scheme": "bearer"},
    "tools": [
        {
            "name": "query_records",
            "description": "Busca registros",
            "input_schema": {
                "type": "object",
                "properties": {"entity": {"type": "string"}},
                "required": ["entity"],
            },
            "writes": False,
        },
        {
            "name": "Get-Record.v2",
            "description": "Trae un registro",
            "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
            "writes": False,
        },
    ],
}
PIN = "https://93.184.216.34/mcp"
CTX = {
    "connections": {
        "mcp_praxis-erp": {"base_url": "https://praxis.cliente.com", "credential": "praxis_K"}
    }
}


def _agente(*tool: dict) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "demo-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": {"primary": {"source": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
            "tools": list(tool),
        },
    }


async def _runtime(tmp_path, *tool: dict) -> AgentRuntime:
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(_agente(*tool)))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


def _copia() -> dict:
    return json.loads(json.dumps(SERVIDOR))


def _sse(m: dict, result: dict) -> httpx.Response:
    cuerpo = json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": result})
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, text=f"data: {cuerpo}\n\n"
    )


def _servidor(request: httpx.Request) -> httpx.Response:
    m = json.loads(request.content)
    if "id" not in m:
        return httpx.Response(202)
    if m["method"] == "initialize":
        return _sse(
            m,
            {
                "protocolVersion": m["params"]["protocolVersion"],
                "capabilities": {},
                "serverInfo": {"name": "s", "version": "0"},
            },
        )
    return _sse(m, {"content": [{"type": "text", "text": "ok"}]})


@pytest.fixture
def dns_publico(monkeypatch):
    async def resolver(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)


async def test_registra_cada_tool_normalizada_y_sin_abrir_una_conexion(tmp_path, monkeypatch):
    async def sin_dns(host, port):
        raise AssertionError("el build resolvió un nombre")

    async def sin_red(self, request):
        raise AssertionError("el build abrió una conexión")

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", sin_dns)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", sin_red)

    # Y por debajo de httpx: un cliente síncrono o un socket crudo tampoco.
    def sin_socket(*a, **k):
        raise AssertionError("el build tocó la red")

    monkeypatch.setattr(socket, "getaddrinfo", sin_socket)
    monkeypatch.setattr(socket.socket, "connect", sin_socket)
    runtime = await _runtime(tmp_path, SERVIDOR)
    assert runtime._agent_errors.get("demo-agent") is None
    tools = runtime._agents["demo-agent"]._tools._tools
    assert set(tools) == {"praxis_erp_query_records", "praxis_erp_get_record_v2"}
    assert tools["praxis_erp_query_records"].parameters == SERVIDOR["tools"][0]["input_schema"]
    assert tools["praxis_erp_query_records"].description == "Busca registros"


def _anidado(niveles: int) -> dict:
    """Un schema de exactamente `niveles` dicts anidados, contando la raíz."""
    s: dict = {"type": "object"}
    for _ in range(niveles - 1):
        s = {"type": "object", "a": s}
    return s


@pytest.mark.parametrize(
    ("romper", "motivo"),
    [
        (lambda t: t["tools"][0].pop("writes"), "writes"),
        (lambda t: t["tools"][0].update(writes=True), "writes"),
        (lambda t: t.update(name="Praxis ERP"), "name"),
        (lambda t: t.pop("connection"), "connection"),
        (lambda t: t.update(path="mcp"), "path"),
        (lambda t: t.update(auth={"scheme": "basic"}), "scheme"),
        (lambda t: t.update(auth={"scheme": "header"}), "header"),
        (lambda t: t.update(tools=[]), "tools"),
        (lambda t: t["tools"][1].update(name="query-records"), "se registrarían"),
        (lambda t: t["tools"][0].update(name="x" * 60), "64"),
        (lambda t: t.update(url="https://otro"), "url"),
        (lambda t: t["tools"][0].update(input_schema={"type": "string"}), "type: object"),
        (lambda t: t["tools"][0].update(input_schema={"properties": {}}), "type: object"),
        (lambda t: t["tools"][0].update(input_schema=_anidado(9)), "8 niveles"),
        (
            lambda t: t["tools"][0].update(
                input_schema={
                    "type": "object",
                    "description": "x" * (16 * 1024 - 33),
                }  # 16385 bytes: uno de más
            ),
            "16 KB",
        ),
        (lambda t: t.update(auth={"scheme": "header", "header": "Host"}), "reservado"),
        (lambda t: t.update(auth={"scheme": "header", "header": "mcp-session-id"}), "reservado"),
        (lambda t: t.update(auth={"scheme": "header", "header": "Content-Type"}), "reservado"),
    ],
)
async def test_una_ficha_invalida_no_carga_el_agente(tmp_path, romper, motivo):
    t = _copia()
    romper(t)
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" not in runtime._agents
    assert motivo in runtime._agent_errors["demo-agent"]


async def test_sin_el_extra_mcp_no_carga(tmp_path, monkeypatch):
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda n, *a: None if n == "mcp" else real(n, *a)
    )
    runtime = await _runtime(tmp_path, SERVIDOR)
    assert "extra 'mcp'" in runtime._agent_errors["demo-agent"]


async def test_una_llamada_arma_url_y_bearer_desde_la_conexion(tmp_path, dns_publico):
    runtime = await _runtime(tmp_path, SERVIDOR)
    with respx.mock:
        ruta = respx.post(PIN).mock(side_effect=_servidor)
        r = await runtime._agents["demo-agent"]._tools.execute(
            "praxis_erp_get_record_v2", {"id": "7"}, CTX
        )
    assert r == {"success": True, "data": "ok", "metadata": {}, "error": None}
    assert json.loads(ruta.calls.last.request.content)["params"]["name"] == "Get-Record.v2"
    assert ruta.calls.last.request.headers["Authorization"] == "Bearer praxis_K"


async def test_auth_header(tmp_path, dns_publico):
    t = _copia()
    t["auth"] = {"scheme": "header", "header": "X-Api-Key"}
    runtime = await _runtime(tmp_path, t)
    with respx.mock:
        ruta = respx.post(PIN).mock(side_effect=_servidor)
        await runtime._agents["demo-agent"]._tools.execute("praxis_erp_query_records", {}, CTX)
    assert ruta.calls.last.request.headers["X-Api-Key"] == "praxis_K"
    assert "Authorization" not in ruta.calls.last.request.headers


async def test_sin_la_conexion_es_un_error_sin_llamar(tmp_path, dns_publico):
    runtime = await _runtime(tmp_path, SERVIDOR)
    with respx.mock:
        ruta = respx.route().mock(return_value=httpx.Response(200))
        r = await runtime._agents["demo-agent"]._tools.execute(
            "praxis_erp_query_records", {}, {"connections": {}}
        )
    assert r["success"] is False
    assert "mcp_praxis-erp" in r["error"]
    assert not ruta.called


async def test_un_mcp_no_deja_claves_ignoradas(tmp_path, caplog):
    await _runtime(tmp_path, SERVIDOR)
    assert "que este runtime no lee" not in caplog.text


async def test_un_schema_en_el_tope_carga(tmp_path):
    t = _copia()
    t["tools"][0]["input_schema"] = _anidado(8)
    t["tools"][1]["input_schema"] = {
        "type": "object",
        "description": "x" * (16 * 1024 - 34),
    }  # 16384: justo
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" in runtime._agents


OTRO = {
    "type": "mcp",
    "name": "praxis",
    "connection": "mcp_praxis",
    "path": "/mcp",
    "auth": {"scheme": "bearer"},
    "tools": [{"name": "erp_query_records", "input_schema": {"type": "object"}, "writes": False}],
}


@pytest.mark.parametrize(
    "previa",
    [
        {"name": "text_summarize", "type": "builtin"},
        {"name": "praxis_erp_query_records", "type": "client", "description": "x"},
        OTRO,
    ],
    ids=["builtin", "client", "otro-mcp"],
)
async def test_un_nombre_que_el_agente_ya_tiene_no_carga(tmp_path, previa):
    t = _copia()
    if previa.get("type") == "builtin":
        t["name"] = "text"
        t["tools"] = [{"name": "summarize", "input_schema": {"type": "object"}, "writes": False}]
    runtime = await _runtime(tmp_path, previa, t)
    assert "demo-agent" not in runtime._agents
    assert "que el agente ya tiene" in runtime._agent_errors["demo-agent"]


@pytest.mark.parametrize(
    "despues",
    [
        {"name": "text_summarize", "type": "builtin"},
        {"name": "praxis_erp_query_records", "type": "client", "description": "x"},
    ],
    ids=["builtin", "client"],
)
async def test_un_nombre_declarado_despues_tampoco_carga(tmp_path, despues):
    t = _copia()
    if despues["type"] == "builtin":
        t["name"] = "text"
        t["tools"] = [{"name": "summarize", "input_schema": {"type": "object"}, "writes": False}]
    runtime = await _runtime(tmp_path, t, despues)
    assert "demo-agent" not in runtime._agents
    assert "que el agente ya tiene" in runtime._agent_errors["demo-agent"]
