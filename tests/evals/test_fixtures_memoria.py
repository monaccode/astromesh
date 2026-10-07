"""Fixtures de tools por caso y memoria aislada del eval."""

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.tools import ToolRegistry
from astromesh.evals import fixtures
from astromesh.evals.memoria import MemoriaDeEval
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _registry():
    reg = ToolRegistry()
    llamadas = []

    async def real(**kw):
        llamadas.append(kw)
        return {"real": True}

    reg.register_internal(
        name="stock", handler=real, description="d", parameters={"type": "object"}
    )
    return reg, llamadas


async def test_con_fixture_no_ejecuta_y_devuelve_el_valor():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({"stock": {"stock": 12}}, bloquear=False) as estado:
        assert await reg.execute("stock", {}) == {"stock": 12}
    assert llamadas == []
    assert estado.llamadas == ["stock"]


async def test_valor_no_dict_se_envuelve():
    reg, _ = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({"stock": 12}, bloquear=False):
        assert await reg.execute("stock", {}) == {"result": 12}


async def test_block_sin_fixture_devuelve_error_y_no_ejecuta():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({}, bloquear=True):
        assert await reg.execute("stock", {}) == {"error": "tool sin fixture en el eval: stock"}
    assert llamadas == []


async def test_real_sin_fixture_ejecuta():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({}, bloquear=False) as estado:
        assert await reg.execute("stock", {"sku": "X"}) == {"real": True}
    assert llamadas == [{"sku": "X"}]
    assert estado.llamadas == ["stock"]


async def test_fuera_de_un_caso_ejecuta_la_real():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    assert await reg.execute("stock", {}) == {"real": True}
    assert len(llamadas) == 1


async def test_instalar_es_idempotente():
    reg, _ = _registry()
    fixtures.instalar(reg)
    fixtures.instalar(reg)
    with fixtures.caso({}, bloquear=False) as estado:
        await reg.execute("stock", {})
    assert estado.llamadas == ["stock"]  # una sola vez, no envuelta dos veces


async def test_fixture_se_devuelve_como_copia():
    reg, _ = _registry()
    fixtures.instalar(reg)
    fijo = {"stock": {"items": [1]}}
    with fixtures.caso(fijo, bloquear=False):
        (await reg.execute("stock", {}))["items"].append(2)
    with fixtures.caso(fijo, bloquear=False):
        assert await reg.execute("stock", {}) == {"items": [1]}


async def test_memoria_separa_sesiones():
    from datetime import UTC, datetime

    from astromesh.core.memory import ConversationTurn

    m = MemoriaDeEval()
    t = ConversationTurn(role="user", content="hola", timestamp=datetime.now(UTC))
    await m.save_turn("a", t)
    assert [x.content for x in await m.get_history("a")] == ["hola"]
    assert await m.get_history("b") == []
    await m.save_summary("a", "res")
    assert await m.get_summary("a") == "res"
    assert await m.get_summary("b") is None
    await m.clear("a")
    assert await m.get_history("a") == []


async def test_preparar_aisla_memoria_e_instala_fixtures(tmp_path):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    for nombre, memoria in (("con-mem", True), ("sin-mem", False)):
        spec = {
            "identity": {"description": "demo"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
        }
        if memoria:
            spec["memory"] = {
                "conversational": {
                    "backend": "redis",
                    "connection": {"url": "redis://localhost:1"},
                    "strategy": "sliding_window",
                }
            }
        (d / "agents" / f"{nombre}.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "astromesh/v1",
                    "kind": "Agent",
                    "metadata": {"name": nombre, "version": "0.1.0"},
                    "spec": spec,
                }
            )
        )
    rt = AgentRuntime(config_dir=str(d))
    await rt.bootstrap()
    assert set(rt._agents) == {"con-mem", "sin-mem"}, rt._agent_errors
    fixtures.preparar(rt)
    assert isinstance(rt._agents["con-mem"]._memory._conversation, MemoriaDeEval)
    assert not isinstance(rt._agents["sin-mem"]._memory._conversation, MemoriaDeEval)
    for agente in rt._agents.values():
        assert getattr(agente._tools, "_eval_fixtures", False)
