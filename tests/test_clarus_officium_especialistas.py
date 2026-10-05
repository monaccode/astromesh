"""Un empleado de OFFICIUM con un especialista, tal como los emite CLARUS.

La fixture es copia exacta de
`clarus-platform/apps/backend/src/officium/fixtures/manifiesto-officium-especialistas.json`,
que fija su propio test del lado de CLARUS
(`src/officium/manifiesto-especialistas.fixture.spec.ts`). Si esto se pone rojo,
lo que CLARUS publica no carga en este runtime, o lo que el especialista propone
no llega a la corrida del empleado: la escritura se perdería.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

FIXTURE = Path(__file__).parent / "fixtures" / "clarus" / "manifiesto-officium-especialistas.json"


class _PideLaTool:
    """Un patrón que llama las tools que le digan (`test_propuestas.py`)."""

    def __init__(self, llamadas):
        self.llamadas = llamadas
        self.observaciones: list = []

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        for nombre, args in self.llamadas:
            self.observaciones.append(await tool_fn(nombre, args))
        return {"answer": "listo", "steps": []}


async def test_lo_que_propone_el_especialista_de_clarus_llega_al_empleado_con_via(
    tmp_path, monkeypatch
):
    doc = json.loads(FIXTURE.read_text())
    monkeypatch.setenv("MOONSHOT_API_KEY", "x")
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    for m in [doc["empleado"], *doc["especialistas"]]:
        (config_dir / "agents" / f"{m['metadata']['name']}.agent.yaml").write_text(
            yaml.safe_dump(m)
        )
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()

    empleado = doc["empleado"]["metadata"]["name"]
    padron = doc["especialistas"][0]["metadata"]["name"]
    assert runtime._agent_errors.get(empleado) is None
    assert runtime._agent_errors.get(padron) is None
    consulta = next(t for t in doc["empleado"]["spec"]["tools"] if t["type"] == "agent")
    assert consulta["agent"] == padron

    especialista = _PideLaTool(
        [("praxis_erp_create_record", {"entity": "contribuyente", "data": {"rif": "J-1"}})]
    )
    runtime._agents[padron]._pattern = especialista
    runtime._agents[empleado]._pattern = _PideLaTool([(consulta["name"], {"query": "cargá J-1"})])
    # La memoria del empleado es el Redis del cluster (`spec.memory` de la
    # fixture); acá no hay Redis. El especialista no tiene memoria.
    memoria = MagicMock()
    memoria.build_context = AsyncMock(return_value={})
    memoria.persist_turn = AsyncMock()
    runtime._agents[empleado]._memory = memoria

    conexiones = {
        "mcp_praxis-erp": {"base_url": "https://praxis.cliente.com", "credential": "praxis_K"}
    }
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as m:
        red = m.route().mock(side_effect=AssertionError("la propuesta salió a la red"))
        r = await runtime._agents[empleado].run("encargo", session_id="s1", connections=conexiones)

    assert not red.called
    assert especialista.observaciones[0]["success"] is True
    assert r["propuestas"] == [
        {
            "tool": "praxis_erp_create_record",
            "tipo": "mcp",
            "destino": "praxis-erp",
            "operacion": "create_record",
            "argumentos": {"entity": "contribuyente", "data": {"rif": "J-1"}},
            "via": padron,
        }
    ]
