"""El manifiesto de un empleado de OFFICIUM, tal como lo emite CLARUS.

La fixture es copia exacta de
`clarus-platform/apps/backend/src/officium/fixtures/manifiesto-officium-api.json`,
que fija su propio test del lado de CLARUS
(`src/officium/manifiesto-api.fixture.spec.ts`). Si esto se pone rojo, lo que
CLARUS publica no carga en este runtime: el empleado quedaría en `draft` o sin
la tool.
"""

import json
from pathlib import Path

import httpx
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

FIXTURE = Path(__file__).parent / "fixtures" / "clarus" / "manifiesto-officium-api.json"

# `permitir_internos=False` pinea la conexión a la IP pública ya resuelta
# (`astromesh/tools/builtin/_red.py::pin_a_ip_publica`): el request sale a esa
# IP con el `Host` original, no al nombre — respx mockea la IP, como
# `tests/test_api_tool.py`.
PIN = "https://93.184.216.34"


async def test_el_manifiesto_de_clarus_carga_y_llama_a_la_api(tmp_path, monkeypatch):
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
    assert {"erp_cliente_consultar_stock", "erp_cliente_cotizar", "datetime_now"} <= set(
        tools._tools
    )
    assert "erp_cliente_crear_pedido" not in tools._tools

    ctx = {
        "connections": {
            "api_erp-cliente": {"base_url": "https://api.cliente.com", "credential": "K"}
        }
    }
    with respx.mock:
        stock = respx.get(f"{PIN}/stock/A-1").mock(
            return_value=httpx.Response(200, json={"disponible": 3})
        )
        cot = respx.post(f"{PIN}/cotizaciones").mock(
            return_value=httpx.Response(200, json={"total": 10})
        )
        r1 = await tools.execute("erp_cliente_consultar_stock", {"sku": "A-1"}, ctx)
        r2 = await tools.execute("erp_cliente_cotizar", {"producto": "A-1", "cantidad": 2}, ctx)

    assert r1["success"] is True
    assert r1["data"] == {"disponible": 3}
    assert r2["success"] is True
    assert stock.calls.last.request.headers["X-Api-Key"] == "K"
    assert stock.calls.last.request.headers["Host"] == "api.cliente.com"
    assert json.loads(cot.calls.last.request.content) == {"producto": "A-1", "cantidad": 2}
