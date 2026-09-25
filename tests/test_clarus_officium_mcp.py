"""El manifiesto de un empleado de OFFICIUM con un servidor MCP, tal como lo emite CLARUS.

La fixture es copia exacta de
`clarus-platform/apps/backend/src/officium/fixtures/manifiesto-officium-mcp.json`,
que fija su propio test del lado de CLARUS
(`src/officium/manifiesto-mcp.fixture.spec.ts`). Si esto se pone rojo, lo que
CLARUS publica no carga en este runtime: el empleado quedaría en `draft` o sin
la tool.
"""

import json
from pathlib import Path

import httpx
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

FIXTURE = Path(__file__).parent / "fixtures" / "clarus" / "manifiesto-officium-mcp.json"


async def test_el_manifiesto_de_clarus_carga_y_llama_al_servidor(tmp_path, monkeypatch):
    config = json.loads(FIXTURE.read_text())
    nombre = config["metadata"]["name"]
    monkeypatch.setenv("MOONSHOT_API_KEY", "x")

    async def resolver(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("astromesh.tools.builtin._red._resolver", resolver)
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / f"{nombre}.agent.yaml").write_text(yaml.safe_dump(config))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    assert runtime._agent_errors.get(nombre) is None
    tools = runtime._agents[nombre]._tools
    assert {"praxis_erp_query_records", "praxis_erp_get_record", "datetime_now"} <= set(
        tools._tools
    )
    assert "praxis_erp_create_record" not in tools._tools
    assert tools._tools["praxis_erp_query_records"].parameters["required"] == ["entity"]

    metodos: list[str] = []

    def servidor(request: httpx.Request) -> httpx.Response:
        m = json.loads(request.content)
        metodos.append(m["method"])
        if "id" not in m:
            return httpx.Response(202)
        result = (
            {
                "protocolVersion": m["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "praxis", "version": "0"},
            }
            if m["method"] == "initialize"
            else {"content": [{"type": "text", "text": '{"ok":true,"value":[]}'}]}
        )
        cuerpo = json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": result})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=f"event: message\ndata: {cuerpo}\n\n",
        )

    ctx = {
        "connections": {
            "mcp_praxis-erp": {"base_url": "https://praxis.cliente.com", "credential": "praxis_K"}
        }
    }
    with respx.mock:
        ruta = respx.post("https://93.184.216.34/mcp").mock(side_effect=servidor)
        r = await tools.execute("praxis_erp_get_record", {"entity": "x", "id": "7"}, ctx)

    assert r["success"] is True
    assert r["data"] == '{"ok":true,"value":[]}'
    assert metodos == ["initialize", "notifications/initialized", "tools/call"]
    llamada = json.loads(ruta.calls.last.request.content)
    assert llamada["params"]["name"] == "Get-Record"
    assert ruta.calls.last.request.headers["Authorization"] == "Bearer praxis_K"
