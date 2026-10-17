"""Swarm desde el manifiesto: workers de las tools `type: agent` y handoff real."""

import itertools
from dataclasses import dataclass

import pytest
import yaml

from astromesh.errors import AgentConfigError
from astromesh.orchestration.swarm import SwarmPattern
from astromesh.runtime.engine import AgentRuntime

TOOLS = [{"name": "billing", "type": "agent", "agent": "billing"}]


def _build(orchestration, tools=TOOLS):
    rt = AgentRuntime.__new__(AgentRuntime)
    return rt._build_pattern({"orchestration": orchestration, "tools": tools})


def test_swarm_sin_tools_agent_no_carga():
    with pytest.raises(AgentConfigError, match="type: agent"):
        _build({"pattern": "swarm"}, tools=[{"name": "x", "type": "builtin"}])


@pytest.mark.parametrize("v", [0, -1, "3", True])
def test_max_handoffs_invalido_no_carga(v):
    with pytest.raises(AgentConfigError, match="max_handoffs"):
        _build({"pattern": "swarm", "max_handoffs": v})


def test_max_handoffs_default_3():
    p = _build({"pattern": "swarm"})
    assert isinstance(p, SwarmPattern)
    assert p._max_handoffs == 3
    assert p._workers == ["billing"]


def test_max_handoffs_del_yaml():
    assert _build({"pattern": "swarm", "max_handoffs": 5})._max_handoffs == 5


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


class _Router:
    def __init__(self, *guion):
        self.guion = list(guion)
        self.vistos = []

    async def route(self, messages, tools=None, **kw):
        self.vistos.append(messages)
        paso = self.guion.pop(0)
        return R("", tool_calls=paso) if isinstance(paso, list) else R(paso)


def _agente(name, spec_extra):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": name, "version": "0.1.0"},
        "spec": {
            "identity": {"description": name},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": f"sos {name}"},
            **spec_extra,
        },
    }


async def test_handoff_real_corre_el_otro_agente(tmp_path):
    agents = tmp_path / "config" / "agents"
    agents.mkdir(parents=True)
    triage = _agente("triage", {"orchestration": {"pattern": "swarm"}, "tools": TOOLS})
    billing = _agente("billing", {"orchestration": {"pattern": "react"}})
    (agents / "triage.agent.yaml").write_text(yaml.safe_dump(triage))
    (agents / "billing.agent.yaml").write_text(yaml.safe_dump(billing))
    runtime = AgentRuntime(config_dir=str(tmp_path / "config"))
    await runtime.bootstrap()
    assert {"triage", "billing"} <= set(runtime._agents), runtime._agent_errors

    llamada = [{"id": "t1", "name": "billing", "arguments": {"query": "factura"}}]
    routers = {"triage": _Router(llamada), "billing": _Router("soy billing")}
    for name, router in routers.items():
        agente = runtime._agents[name]
        agente._routers = dict.fromkeys(agente._routers, router)
        agente._routers.setdefault("default", router)

    r = await runtime.run("triage", "quiero mi factura", "s1")

    assert r["answer"] == "soy billing"
    assert len(routers["triage"].vistos) == 1
    assert "factura" in routers["billing"].vistos[0][-1]["content"]


async def _dos_agentes(tmp_path, triage_orch):
    agents = tmp_path / "config" / "agents"
    agents.mkdir(parents=True)
    triage = _agente("triage", {"orchestration": triage_orch, "tools": TOOLS})
    billing = _agente("billing", {"orchestration": {"pattern": "react"}})
    (agents / "triage.agent.yaml").write_text(yaml.safe_dump(triage))
    (agents / "billing.agent.yaml").write_text(yaml.safe_dump(billing))
    runtime = AgentRuntime(config_dir=str(tmp_path / "config"))
    await runtime.bootstrap()
    assert {"triage", "billing"} <= set(runtime._agents), runtime._agent_errors
    return runtime


def _guionar(runtime, **guiones):
    routers = {name: _Router(*g) for name, g in guiones.items()}
    for name, router in routers.items():
        agente = runtime._agents[name]
        agente._routers = dict.fromkeys(agente._routers, router)
        agente._routers.setdefault("default", router)
    return routers


@pytest.mark.parametrize("valor", ["x", None, -5, True, [1]])
async def test_contador_invalido_en_el_context_de_la_corrida(tmp_path, valor):
    runtime = await _dos_agentes(tmp_path, {"pattern": "swarm", "max_handoffs": 1})
    llamada = [{"id": "t1", "name": "billing", "arguments": {"query": "factura"}}]
    _guionar(runtime, triage=[llamada], billing=["soy billing"])
    r = await runtime.run("triage", "q", "s1", context={"_handoffs": valor})
    assert r["answer"] == "soy billing"


async def test_contador_en_el_tope_desde_el_context_no_hace_handoff(tmp_path):
    runtime = await _dos_agentes(tmp_path, {"pattern": "swarm", "max_handoffs": 1})
    llamada = [{"id": "t1", "name": "billing", "arguments": {"query": "factura"}}]
    routers = _guionar(runtime, triage=[llamada, "sin pasar"], billing=["soy billing"])
    r = await runtime.run("triage", "q", "s1", context={"_handoffs": 1})
    assert r["answer"] == "sin pasar"
    assert routers["billing"].vistos == []


async def test_handoffs_escrito_por_el_modelo_se_ignora():
    """Un `_handoffs` en los argumentos no fija el contador del hijo: manda el del runtime."""
    from unittest.mock import AsyncMock

    from astromesh.core.tools import ToolRegistry

    registry = ToolRegistry()
    registry.register_agent_tool(name="billing", agent_name="billing", description="d")
    runtime = AsyncMock()
    runtime.run.return_value = {"answer": "ok"}
    registry.set_runtime(runtime)

    await registry.execute("billing", {"query": "q", "_handoffs": -7}, {"_handoffs": 2})
    assert runtime.run.await_args.kwargs["context"]["_handoffs"] == 3

    await registry.execute("billing", {"query": "q", "_handoffs": 0}, {"_handoffs": 3})
    assert runtime.run.await_args.kwargs["context"]["_handoffs"] == 4

    await registry.execute("billing", {"query": "q"}, {"_handoffs": 2})
    assert runtime.run.await_args.kwargs["context"]["_handoffs"] == 2

    await registry.execute("billing", {"query": "q"}, {"_handoffs": "x"})
    assert runtime.run.await_args.kwargs["context"] is None


async def test_cinco_turnos_con_memoria_compartida_no_crecen(tmp_path, monkeypatch):
    """C1: con la misma memoria conversacional, el handoff no duplica la historia.

    Antes el destino guardaba la transcripción entera como turno del usuario EN LA
    SESIÓN DE LA PERSONA, y la próxima transcripción la incluía: ~doble por turno.
    """
    import astromesh.runtime.engine as eng
    from astromesh.core.memory import ConversationBackend

    store: dict[str, list] = {}

    class Compartida(ConversationBackend):
        async def save_turn(self, sid, turn):
            store.setdefault(sid, []).append(turn)

        async def get_history(self, sid, limit=50):
            return store.get(sid, [])[-limit:]

        async def clear(self, sid):
            store.pop(sid, None)

        async def get_summary(self, sid):
            return None

        async def save_summary(self, sid, s):
            pass

    monkeypatch.setattr(eng, "build_conversation_backend", lambda cfg: Compartida())
    agents = tmp_path / "config" / "agents"
    agents.mkdir(parents=True)
    mem = {"memory": {"conversational": {"backend": "redis", "connection": {"url": "x"}}}}
    triage = _agente("triage", {"orchestration": {"pattern": "swarm"}, "tools": TOOLS, **mem})
    billing = _agente("billing", {"orchestration": {"pattern": "react"}, **mem})
    (agents / "t.agent.yaml").write_text(yaml.safe_dump(triage))
    (agents / "b.agent.yaml").write_text(yaml.safe_dump(billing))
    runtime = AgentRuntime(config_dir=str(tmp_path / "config"))
    await runtime.bootstrap()
    assert runtime._agent_errors == {}

    largos = []
    for i in range(5):
        llamada = [{"id": f"t{i}", "name": "billing", "arguments": {"query": f"pedido {i}"}}]
        routers = _guionar(runtime, triage=[llamada], billing=[f"respuesta {i}"])
        await runtime.run("triage", f"mensaje {i}", "s1")
        largos.append(sum(len(m["content"] or "") for m in routers["billing"].vistos[0]))

    # La persona: un par por turno, sin la respuesta repetida.
    assert [(t.role, t.content) for t in store["s1"]][-2:] == [
        ("user", "mensaje 4"),
        ("assistant", "respuesta 4"),
    ]
    assert len(store["s1"]) == 10
    # El destino: su propia sesión, con el pedido y no la transcripción.
    assert [t.content for t in store["s1::billing"] if t.role == "user"] == [
        f"pedido {i}" for i in range(5)
    ]
    # Lo que ve el destino crece lineal (historia acotada), no al doble.
    crecimientos = [b - a for a, b in itertools.pairwise(largos)]
    assert max(crecimientos) - min(crecimientos) < 10, largos


def test_transcripcion_omite_vacios_suma_el_mensaje_y_se_acota():
    from astromesh.orchestration.swarm import (
        TRANSCRIPCION_MAX_CHARS,
        TRANSCRIPCION_MAX_TURNOS,
        _transcripcion,
    )

    ctx = {
        "_history_messages": [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": None},
        ]
    }
    assert _transcripcion(ctx, "ahora") == "user: hola\nuser: ahora"

    muchos = [{"role": "user", "content": f"m{i}"} for i in range(100)]
    lineas = _transcripcion({"_history_messages": muchos}, "fin").splitlines()
    assert len(lineas) == TRANSCRIPCION_MAX_TURNOS
    assert lineas[-1] == "user: fin"

    largos = [{"role": "user", "content": "x" * 3000} for _ in range(10)]
    assert len(_transcripcion({"_history_messages": largos}, "fin")) <= TRANSCRIPCION_MAX_CHARS
