"""`orchestration.timeout_seconds` corta la corrida (AgentRunTimeout)."""

import asyncio
import logging
import time

import pytest

from astromesh.errors import AgentConfigError, AgentRunTimeout
from astromesh.runtime.engine import _PENDIENTES, AgentRuntime, _timeout_de
from tests.test_guardrails_run import _agente, _manifest, sin_litellm  # noqa: F401
from tests.test_memoria_episodica_engine import FakeEpisodic


class _Duerme:
    def __init__(self, seg, pre=None):
        self.seg, self.pre = seg, pre

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        if self.pre:
            self.pre()
        await asyncio.sleep(self.seg)
        return {"answer": "listo", "steps": []}


class _TimeoutPropio:
    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        raise TimeoutError("la tool tardó")


def _man(**orq):
    return _manifest(orchestration={"pattern": "react", **orq})


async def test_sin_timeout_no_corta(tmp_path):
    agente, _ = await _agente(tmp_path, _man())
    agente._pattern = _Duerme(0.05)
    assert (await agente.run("q", "s1"))["answer"] == "listo"


async def test_timeout_corta_la_corrida(tmp_path):
    agente, _ = await _agente(tmp_path, _man(timeout_seconds=0.05))
    agente._pattern = _Duerme(5)
    t0 = time.monotonic()
    with pytest.raises(AgentRunTimeout) as e:
        await agente.run("q", "s1")
    assert (e.value.timeout_seconds, e.value.agent) == (0.05, "g-agent")
    assert time.monotonic() - t0 < 1


@pytest.mark.parametrize("v", [0, -5, "60", True])
def test_timeout_invalido_no_carga(v):
    with pytest.raises(AgentConfigError, match="timeout_seconds"):
        _timeout_de("a", {"timeout_seconds": v})


async def test_timeout_invalido_no_levanta_el_agente(tmp_path):
    import yaml

    d = tmp_path / "config" / "agents"
    d.mkdir(parents=True)
    (d / "g-agent.agent.yaml").write_text(yaml.safe_dump(_man(timeout_seconds=0)))
    rt = AgentRuntime(config_dir=str(tmp_path / "config"))
    await rt.bootstrap()
    assert "g-agent" not in rt._agents
    assert "timeout_seconds" in str(rt._agent_errors)


async def test_alias_timeout_aplica_y_avisa(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        agente, _ = await _agente(tmp_path, _man(timeout=30))
    assert agente._timeout_seconds == 30
    assert any("timeout_seconds" in r.getMessage() for r in caplog.records)


async def test_timeout_error_de_una_tool_no_es_timeout_de_corrida(tmp_path):
    agente, _ = await _agente(tmp_path, _man(timeout_seconds=60))
    agente._pattern = _TimeoutPropio()
    with pytest.raises(TimeoutError) as e:
        await agente.run("q", "s1")
    assert not isinstance(e.value, AgentRunTimeout)


async def test_timeout_cierra_el_pendiente_de_confirmacion(tmp_path):
    agente, _ = await _agente(tmp_path, _man(timeout_seconds=0.05))
    agente._pattern = _Duerme(5, pre=lambda: _PENDIENTES.registrar("s1", "t", "fp", {}))
    with pytest.raises(AgentRunTimeout):
        await agente.run("q", "s1")
    assert _PENDIENTES.pendiente("s1") is None


async def test_timeout_deja_episodio_timeout(tmp_path):
    agente, _ = await _agente(tmp_path, _man(timeout_seconds=0.05))
    fake = FakeEpisodic()
    agente._memory._episodic = fake
    agente._pattern = _Duerme(5)
    with pytest.raises(AgentRunTimeout):
        await agente.run("q", "s1")
    assert fake.grabados[0].outcome["result"] == "timeout"


class _ToolLenta:
    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        await tool_fn("leer", {})
        return {"answer": "x", "steps": []}


async def test_timeout_cierra_la_tool_en_vuelo(tmp_path, caplog):
    agente, _ = await _agente(tmp_path, _man(timeout_seconds=0.05))

    async def lenta(*a, **k):
        await asyncio.sleep(5)

    agente._pattern = _ToolLenta()
    agente._tools.execute = lenta
    eventos = []
    with caplog.at_level(logging.WARNING), pytest.raises(AgentRunTimeout):
        await agente.run("q", "s1", on_event=eventos.append)
    res = [e for e in eventos if e["type"] == "tool_result"]
    assert len(res) == 1
    assert (res[0]["ok"], res[0]["cancelled"]) == (False, True)
    assert any("timed out" in r.getMessage() for r in caplog.records)
