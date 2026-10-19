"""`origen` del turno (humano|agente) en REST y WS.

Un agente remoto que habla con éste NO es una persona: su "si" no puede
confirmar una acción gateada. `origen` default `humano` (compatibilidad).
"""

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astromesh.api import ws as ws_module
from astromesh.api.routes import agents as agents_routes
from tests.test_confirmacion_engine import (
    _limpiar_pendientes,  # noqa: F401
    _PideLaTool,
    _runtime,
)


class _Espia:
    def __init__(self):
        self.llamadas = []

    async def run(self, agent_name, query, session_id, context=None, **kw):
        self.llamadas.append(kw)
        return {"answer": "ok", "steps": [], "trace": {}}


class _ConCredenciales:
    """Runtime real; sólo inyecta las credenciales que el plano de control daría."""

    def __init__(self, runtime):
        self._rt = runtime

    async def run(self, agent_name, query, session_id, context=None, **kw):
        kw["connections"] = {"demo_conn": {"access_token": "t"}}
        return await self._rt.run(agent_name, query, session_id, context, **kw)


@pytest.fixture
def espia():
    rt = _Espia()
    agents_routes.set_runtime(rt)
    yield rt
    agents_routes.set_runtime(None)


def _app():
    app = FastAPI()
    app.include_router(agents_routes.router, prefix="/v1")
    app.include_router(ws_module.router, prefix="/v1")
    return app


def test_run_origen_agente_pasa_desde_humano_false(espia):
    r = TestClient(_app()).post("/v1/agents/x/run", json={"query": "si", "origen": "agente"})
    assert r.status_code == 200
    assert espia.llamadas[0]["desde_humano"] is False


def test_run_sin_origen_es_humano(espia):
    r = TestClient(_app()).post("/v1/agents/x/run", json={"query": "hola"})
    assert r.status_code == 200
    assert espia.llamadas[0]["desde_humano"] is True


@pytest.mark.parametrize("valor", ["bot", "Agente", "HUMANO", ""])
def test_run_origen_invalido_422(espia, valor):
    r = TestClient(_app()).post("/v1/agents/x/run", json={"query": "hola", "origen": valor})
    assert r.status_code == 422
    assert espia.llamadas == []


@pytest.mark.parametrize(
    ("origen", "debe_ejecutar"), [("agente", False), ("humano", True)], ids=["agente", "humano"]
)
@respx.mock
async def test_agente_no_puede_autoconfirmar(tmp_path, monkeypatch, origen, debe_ejecutar):
    """Con control positivo: el mismo flujo con `humano` SÍ ejecuta la tool."""
    ruta = respx.post("https://api.demo.test/thing").mock(return_value=httpx.Response(200, json={}))
    runtime = await _runtime(tmp_path, monkeypatch)
    runtime._agents["demo-agent"]._pattern = _PideLaTool([("demo_write_thing", {"x": 1})])
    agents_routes.set_runtime(_ConCredenciales(runtime))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app()), base_url="http://t"
        ) as c:
            await c.post("/v1/agents/demo-agent/run", json={"query": "cargá esto"})
            assert ruta.called is False  # turno 1: propuesta, queda pendiente
            r = await c.post("/v1/agents/demo-agent/run", json={"query": "si", "origen": origen})
        assert r.status_code == 200
        assert ruta.called is debe_ejecutar
    finally:
        agents_routes.set_runtime(None)


@pytest.mark.parametrize(
    ("origen", "debe_ejecutar"), [("agente", False), ("humano", True)], ids=["agente", "humano"]
)
@respx.mock
def test_ws_origen_agente_no_confirma(tmp_path, monkeypatch, origen, debe_ejecutar):
    import asyncio

    ruta = respx.post("https://api.demo.test/thing").mock(return_value=httpx.Response(200, json={}))
    loop = asyncio.new_event_loop()
    try:
        runtime = loop.run_until_complete(_runtime(tmp_path, monkeypatch))
    finally:
        loop.close()
    runtime._agents["demo-agent"]._pattern = _PideLaTool([("demo_write_thing", {"x": 1})])
    ws_module.set_runtime(_ConCredenciales(runtime))
    try:
        with TestClient(_app()).websocket_connect("/v1/ws/agent/demo-agent?session_id=s1") as ws:
            ws.send_json({"query": "cargá esto"})
            _drain(ws)
            assert ruta.called is False  # turno 1: propuesta, queda pendiente
            ws.send_json({"query": "si", "origen": origen})
            _drain(ws)
        assert ruta.called is debe_ejecutar
    finally:
        ws_module.set_runtime(None)


def test_ws_origen_pasa_desde_humano(espia):
    ws_module.set_runtime(espia)
    try:
        with TestClient(_app()).websocket_connect("/v1/ws/agent/x") as ws:
            ws.send_json({"query": "a", "origen": "agente"})
            _drain(ws)
            ws.send_json({"query": "b"})
            _drain(ws)
    finally:
        ws_module.set_runtime(None)
    assert [c["desde_humano"] for c in espia.llamadas] == [False, True]


@pytest.mark.parametrize("valor", ["bot", ["x"], {"a": 1}, 5, None])
def test_ws_origen_invalido_es_error_y_no_corre(espia, valor):
    ws_module.set_runtime(espia)
    try:
        with TestClient(_app()).websocket_connect("/v1/ws/agent/x") as ws:
            ws.send_json({"query": "a", "origen": valor})
            ev = ws.receive_json()
    finally:
        ws_module.set_runtime(None)
    assert ev["type"] == "error"
    assert "origen" in ev["message"]
    assert espia.llamadas == []


def _drain(ws):
    for _ in range(50):
        ev = ws.receive_json()
        if ev["type"] in ("done", "error"):
            return ev
    raise AssertionError("sin done")
