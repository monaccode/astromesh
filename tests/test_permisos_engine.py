"""`permissions.allowed_actions`/`denied_actions` en el engine: al ofrecer y al ejecutar."""

import json

import pytest

from astromesh.core import tokens
from astromesh.errors import AgentConfigError
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import _PENDIENTES, AgentRuntime
from tests.test_client_tools import _agent_spec
from tests.test_confirmacion_engine import AGENT as CONFIRM_AGENT
from tests.test_confirmacion_engine import _catalog
from tests.test_guardrails_run import Fake


@pytest.fixture(autouse=True)
def _aislar(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)
    _PENDIENTES._por_sesion.clear()
    yield
    _PENDIENTES._por_sesion.clear()


def _tool(nombre):
    return {
        "name": nombre,
        "type": "client",
        "description": nombre,
        "parameters": {"type": "object", "properties": {}},
    }


def _agente(permissions=None, prefetch=None, tools=None):
    spec = _agent_spec(tools if tools is not None else [_tool("leer"), _tool("borrar")])
    if permissions is not None:
        spec["spec"]["permissions"] = permissions
    if prefetch is not None:
        spec["spec"]["prefetch"] = prefetch
    return AgentRuntime(config_dir="/nonexistent")._build_agent(spec)


def _resp(content="", tool_calls=None):
    return CompletionResponse(
        content=content,
        model="m",
        provider="p",
        usage={"input_tokens": 1, "output_tokens": 1},
        latency_ms=1.0,
        cost=0.0,
        tool_calls=tool_calls or [],
    )


def _con_modelo(agente, respuestas):
    """Fija el modelo; devuelve las listas de nombres de tool que recibió."""
    agente._memory._conversation = Fake()
    ofrecidas, cola = [], list(respuestas)

    async def route(messages, tools=None, **kwargs):
        ofrecidas.append([t["function"]["name"] for t in tools or []])
        return cola.pop(0) if len(cola) > 1 else cola[0]

    agente._routers["default"].route = route
    return ofrecidas


async def test_tool_no_permitida_no_se_ofrece_al_modelo():
    agente = _agente({"allowed_actions": ["leer"]})
    ofrecidas = _con_modelo(agente, [_resp("ok")])
    await agente.run("hola", "s1")
    assert ofrecidas[0] == ["leer"]


async def test_tool_no_permitida_que_el_modelo_llama_no_se_ejecuta():
    agente = _agente({"allowed_actions": ["leer"]})
    _con_modelo(
        agente,
        [_resp("", [{"id": "c1", "name": "borrar", "arguments": {}}]), _resp("listo")],
    )
    eventos = []
    result = await agente.run("hola", "s1", on_event=eventos.append)
    assert json.loads(result["steps"][0].observation) == {
        "error": "tool 'borrar' no permitida por permissions"
    }
    assert not [e for e in eventos if e["type"] == "tool_call" and e["name"] == "borrar"]
    span = next(
        s
        for s in result["trace"]["spans"]
        if s["name"] == "tool.call" and s["attributes"]["tool"] == "borrar"
    )
    assert span["attributes"]["tool.denied"] is True
    assert span["status"] == "error"


async def test_tool_denegada_no_registra_pendiente(tmp_path, monkeypatch):
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    spec = {**CONFIRM_AGENT, "spec": {**CONFIRM_AGENT["spec"]}}
    spec["spec"]["permissions"] = {"denied_actions": ["demo_write_thing"]}
    agente = AgentRuntime(config_dir="/nonexistent")._build_agent(spec)
    _con_modelo(
        agente,
        [_resp("", [{"id": "c1", "name": "demo_write_thing", "arguments": {}}]), _resp("ok")],
    )
    await agente.run("hola", "s1", connections={"demo_conn": {"access_token": "t"}})
    assert _PENDIENTES.pendiente("s1") is None


def test_prefetch_de_tool_no_permitida_no_carga(tmp_path, monkeypatch):
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    spec = {**CONFIRM_AGENT, "spec": {**CONFIRM_AGENT["spec"]}}
    spec["spec"]["tools"] = [{**spec["spec"]["tools"][0], "confirm": []}]
    spec["spec"]["permissions"] = {"allowed_actions": ["demo_write_thing"]}
    spec["spec"]["prefetch"] = [{"name": "p", "tool": "demo_ping"}]
    with pytest.raises(AgentConfigError, match=r"prefetch.*demo_ping.*permissions"):
        AgentRuntime(config_dir="/nonexistent")._build_agent(spec)


def test_sin_permissions_se_ofrecen_todas():
    agente = _agente()
    assert agente._permitidas is None
    nombres = [s["function"]["name"] for s in agente._tools.get_tool_schemas(agente._permitidas)]
    assert nombres == ["leer", "borrar"]
