"""`mode: propose`: una escritura de una API o de un servidor MCP del tenant se
registra para aprobación y NUNCA se ejecuta desde el runtime (OFFICIUM R3)."""

import asyncio
import json

import httpx
import pytest
import respx
import yaml

from astromesh.integrations.propuestas import AVISO, MAX_PROPUESTAS
from astromesh.runtime.engine import AgentRuntime

API = {
    "type": "api",
    "name": "erp-cliente",
    "connection": "api_erp-cliente",
    "auth": {"scheme": "bearer"},
    "operations": [
        {
            "name": "consultar_stock",
            "description": "Stock de un SKU",
            "parameters": {"sku": {"type": "string", "required": True}},
            "request": {"method": "GET", "path": "/stock/{sku}", "query": {}, "body": None},
            "writes": False,
        },
        {
            "name": "crear_pedido",
            "description": "Crea un pedido",
            "parameters": {
                "sku": {"type": "string", "required": True},
                "cantidad": {"type": "number", "required": True},
            },
            "request": {
                "method": "POST",
                "path": "/pedidos",
                "query": {},
                "body": {"sku": "{sku}", "cantidad": "{cantidad}"},
            },
            "writes": True,
            "mode": "propose",
        },
    ],
}

MCP = {
    "type": "mcp",
    "name": "praxis-erp",
    "connection": "mcp_praxis-erp",
    "path": "/mcp",
    "auth": {"scheme": "bearer"},
    "tools": [
        {
            "name": "query_records",
            "description": "Busca registros",
            "input_schema": {"type": "object", "properties": {"entity": {"type": "string"}}},
            "writes": False,
        },
        {
            "name": "Create-Record",
            "description": "Crea un registro",
            "input_schema": {
                "type": "object",
                "properties": {"entity": {"type": "string"}, "data": {"type": "object"}},
                "required": ["entity", "data"],
            },
            "writes": True,
            "mode": "propose",
        },
    ],
}

CONEXIONES = {
    "api_erp-cliente": {"base_url": "https://api.cliente.com", "credential": "K"},
    "mcp_praxis-erp": {"base_url": "https://praxis.cliente.com", "credential": "praxis_K"},
}


def _agente(*tools: dict) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "demo-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": {"primary": {"source": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
            "tools": list(tools),
        },
    }


async def _runtime(tmp_path, *tools: dict) -> AgentRuntime:
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(_agente(*tools)))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    return runtime


def _copia(t: dict) -> dict:
    return json.loads(json.dumps(t))


class _PideLaTool:
    """Un patrón que llama las tools que le digan (`test_confirmacion_engine.py`)."""

    def __init__(self, llamadas):
        self.llamadas = llamadas
        self.observaciones: list = []

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        for nombre, args in self.llamadas:
            self.observaciones.append(await tool_fn(nombre, args))
        return {"answer": "listo", "steps": []}


async def _correr(runtime, llamadas, session_id="s1"):
    agente = runtime._agents["demo-agent"]
    patron = _PideLaTool(llamadas)
    agente._pattern = patron
    r = await agente.run("hacelo", session_id=session_id, connections=CONEXIONES)
    return r, patron.observaciones


@pytest.fixture
def ningun_host():
    """Un servidor que falla el test si recibe CUALQUIER cosa: proponer no llama."""
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as m:
        ruta = m.route().mock(side_effect=AssertionError("la propuesta salió a la red"))
        yield ruta


async def test_una_propuesta_de_api_no_llama_y_queda_en_la_corrida(tmp_path, ningun_host):
    runtime = await _runtime(tmp_path, API)
    r, obs = await _correr(runtime, [("erp_cliente_crear_pedido", {"sku": "A-1", "cantidad": 3})])
    assert obs == [{"success": True, "data": AVISO, "metadata": {}, "error": None}]
    assert r["propuestas"] == [
        {
            "tool": "erp_cliente_crear_pedido",
            "tipo": "api",
            "destino": "erp-cliente",
            "operacion": "crear_pedido",
            "argumentos": {"sku": "A-1", "cantidad": 3},
        }
    ]
    assert not ningun_host.called


async def test_una_propuesta_de_mcp_lleva_el_nombre_del_servidor_tal_cual(tmp_path, ningun_host):
    runtime = await _runtime(tmp_path, MCP)
    r, _ = await _correr(
        runtime,
        [("praxis_erp_create_record", {"entity": "contribuyente", "data": {"rif": "J-1"}})],
    )
    assert r["propuestas"] == [
        {
            "tool": "praxis_erp_create_record",
            "tipo": "mcp",
            "destino": "praxis-erp",
            "operacion": "Create-Record",
            "argumentos": {"entity": "contribuyente", "data": {"rif": "J-1"}},
        }
    ]
    assert not ningun_host.called


async def test_argumentos_que_no_calzan_vuelven_al_modelo_sin_registrar(tmp_path, ningun_host):
    runtime = await _runtime(tmp_path, MCP)
    r, obs = await _correr(runtime, [("praxis_erp_create_record", {"entity": 7})])
    assert obs[0]["success"] is False
    assert "argumentos inválidos" in obs[0]["error"]
    assert "data: campo requerido faltante" in obs[0]["error"]
    assert r["propuestas"] == []


async def test_argumentos_de_mas_de_16_kb_no_se_registran(tmp_path, ningun_host):
    runtime = await _runtime(tmp_path, MCP)
    grande = {"entity": "x", "data": {"nota": "a" * (16 * 1024)}}
    r, obs = await _correr(runtime, [("praxis_erp_create_record", grande)])
    assert obs[0]["success"] is False
    assert "16 KB" in obs[0]["error"]
    assert r["propuestas"] == []


async def test_la_propuesta_21_se_rechaza_al_modelo(tmp_path, ningun_host):
    runtime = await _runtime(tmp_path, API)
    llamada = ("erp_cliente_crear_pedido", {"sku": "A-1", "cantidad": 1})
    r, obs = await _correr(runtime, [llamada] * (MAX_PROPUESTAS + 1))
    assert len(r["propuestas"]) == MAX_PROPUESTAS
    assert all(o["success"] for o in obs[:MAX_PROPUESTAS])
    assert obs[MAX_PROPUESTAS]["success"] is False
    assert "20 escrituras" in obs[MAX_PROPUESTAS]["error"]


async def test_una_lectura_sigue_llamando_de_verdad(tmp_path, monkeypatch):
    async def resolver(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    runtime = await _runtime(tmp_path, API)
    with respx.mock:
        ruta = respx.get("https://93.184.216.34/stock/A-1").mock(
            return_value=httpx.Response(200, text="stock 3")
        )
        r, obs = await _correr(runtime, [("erp_cliente_consultar_stock", {"sku": "A-1"})])
    assert ruta.called
    assert obs[0]["data"] == "stock 3"
    assert r["propuestas"] == []


async def test_dos_corridas_simultaneas_no_se_mezclan_las_propuestas(tmp_path, ningun_host):
    runtime = await _runtime(tmp_path, API)
    agente = runtime._agents["demo-agent"]
    suelta = asyncio.Event()

    # Un solo objeto `Agent` y un solo patrón para las dos, como en el runtime
    # real: lo único por corrida es lo que arma `Agent.run`.
    class _PorSesion:
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            sku = query
            await tool_fn("erp_cliente_crear_pedido", {"sku": sku, "cantidad": 1})
            await suelta.wait()
            await tool_fn("erp_cliente_crear_pedido", {"sku": sku, "cantidad": 2})
            return {"answer": "listo", "steps": []}

    agente._pattern = _PorSesion()
    a = asyncio.create_task(agente.run("A", session_id="sa", connections=CONEXIONES))
    b = asyncio.create_task(agente.run("B", session_id="sb", connections=CONEXIONES))
    await asyncio.sleep(0.05)
    suelta.set()
    ra, rb = await asyncio.gather(a, b)
    assert [p["argumentos"] for p in ra["propuestas"]] == [
        {"sku": "A", "cantidad": 1},
        {"sku": "A", "cantidad": 2},
    ]
    assert [p["argumentos"] for p in rb["propuestas"]] == [
        {"sku": "B", "cantidad": 1},
        {"sku": "B", "cantidad": 2},
    ]


async def test_una_corrida_reentrante_no_propone(tmp_path, ningun_host):
    """Un sub-agente o un paso de workflow: su respuesta no sale en `/run`, así
    que proponer ahí se rechaza al modelo en vez de perderse."""
    runtime = await _runtime(tmp_path, API)
    agente = runtime._agents["demo-agent"]
    patron = _PideLaTool([("erp_cliente_crear_pedido", {"sku": "A-1", "cantidad": 1})])
    agente._pattern = patron
    r = await agente.run("x", session_id="s1", connections=CONEXIONES, desde_humano=False)
    assert patron.observaciones[0]["success"] is False
    assert "corrida principal" in patron.observaciones[0]["error"]
    assert r["propuestas"] == []


@pytest.mark.parametrize(
    ("romper", "motivo"),
    [
        (lambda t: t["operations"][1].pop("mode"), "nunca escribe directo"),
        (lambda t: t["operations"][1].update(mode="execute"), "nunca escribe directo"),
        (lambda t: t["operations"][0].update(mode="propose"), "nunca escribe directo"),
        (lambda t: t["operations"][1].update(writes=1), "nunca escribe directo"),
    ],
)
async def test_api_writes_true_sin_propose_no_carga(tmp_path, romper, motivo):
    t = _copia(API)
    romper(t)
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" not in runtime._agents
    assert motivo in runtime._agent_errors["demo-agent"]


@pytest.mark.parametrize(
    "romper",
    [
        lambda t: t["tools"][1].pop("mode"),
        lambda t: t["tools"][1].update(mode="execute"),
        lambda t: t["tools"][0].update(mode="propose"),
        lambda t: t["tools"][1].update(writes="true"),
    ],
)
async def test_mcp_writes_true_sin_propose_no_carga(tmp_path, romper):
    t = _copia(MCP)
    romper(t)
    runtime = await _runtime(tmp_path, t)
    assert "demo-agent" not in runtime._agents
    assert "ficha inválida" in runtime._agent_errors["demo-agent"]


async def test_run_devuelve_propuestas_y_vacia_si_no_hubo(client, monkeypatch):
    from astromesh.api.routes import agents as agents_module

    propuesta = {
        "tool": "t",
        "tipo": "mcp",
        "destino": "praxis-erp",
        "operacion": "create_record",
        "argumentos": {"a": 1},
    }

    class FakeRuntime:
        def __init__(self, result):
            self.result = result

        async def run(self, *_args, **_kwargs):
            return self.result

    monkeypatch.setattr(
        agents_module, "_runtime", FakeRuntime({"answer": "ok", "propuestas": [propuesta]})
    )
    con = await client.post("/v1/agents/any-agent/run", json={"query": "hola"})
    monkeypatch.setattr(agents_module, "_runtime", FakeRuntime({"answer": "ok"}))
    sin = await client.post("/v1/agents/any-agent/run", json={"query": "hola"})

    assert con.json()["propuestas"] == [propuesta]
    assert sin.json()["propuestas"] == []
