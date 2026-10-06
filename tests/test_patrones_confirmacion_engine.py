"""`confirm` sigue gateado bajo los patrones que no son react (engine entero)."""

import copy
from dataclasses import dataclass

import httpx
import pytest
import respx

from tests.test_confirmacion_engine import (  # noqa: F401  (fixture autouse + harness)
    AGENT,
    _limpiar_pendientes,
    _runtime,
)


@dataclass
class R:
    content: str
    tool_calls: list | None = None
    reasoning_content: str | None = None
    usage: None = None
    model: str = "fake"
    provider: str = "fake"
    latency_ms: float = 0.0
    cost: float = 0.0


LLAMADA = [{"id": "t1", "name": "demo_write_thing", "arguments": {"x": 1}}]

GUION = {
    "plan_and_execute": [
        '{"steps": [{"step": 1, "description": "cargar"}]}',
        LLAMADA,
        "paso",
        "final",
    ],
    "parallel_fan_out": ['["cargar"]', LLAMADA, "sub", "final"],
    "pipeline": [LLAMADA, "e1", "e2", "e3"],
    "supervisor": [LLAMADA, "no pude", "final"],
}


class _Router:
    def __init__(self, guion):
        self.guion = list(guion)

    async def route(self, messages, tools=None, **kw):
        paso = self.guion.pop(0)
        return R("", tool_calls=paso) if isinstance(paso, list) else R(paso)


@pytest.mark.parametrize("patron", list(GUION))
@respx.mock
async def test_confirm_sigue_gateado(tmp_path, monkeypatch, patron):
    ruta = respx.post("https://api.demo.test/thing").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    cfg = copy.deepcopy(AGENT)
    cfg["spec"]["orchestration"] = {"pattern": patron}
    if patron == "supervisor":
        cfg["spec"]["tools"].append({"type": "agent", "name": "consultar_a", "agent": "a"})
    runtime = await _runtime(tmp_path, monkeypatch, cfg)
    agente = runtime._agents["demo-agent"]
    router = _Router(GUION[patron])
    agente._routers = dict.fromkeys(agente._routers, router)
    agente._routers.setdefault("default", router)

    resultado = await agente.run(
        "cargá esto", session_id="s1", connections={"demo_conn": {"access_token": "t"}}
    )

    assert ruta.called is False, "se escribió sin confirmación"
    if patron == "supervisor":
        # demo_write_thing no es un trabajador: ni se ejecuta ni se propone.
        return
    from astromesh.runtime.engine import _PENDIENTES

    assert _PENDIENTES.pendiente("s1")["tool"] == "demo_write_thing"
    assert any("confirmacion_requerida" in str(s.observation) for s in resultado.get("steps", []))
