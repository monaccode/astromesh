"""Las cadenas se compilan y registran al arrancar; los errores explotan ahí."""

import pytest

from astromesh.chain.compiler import chain_workflow_name
from astromesh.runtime.engine import AgentRuntime

BASE = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: {nombre}
spec:
  identity:
    description: "agente {nombre}"
  model:
    primary:
      provider: ollama
      model: "test"
      endpoint: "http://localhost:11434"
  prompts:
    system: "hola"
  orchestration:
    pattern: react
{extra}"""


def _escribir(tmp_path, nombre, extra=""):
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    (agents / f"{nombre}.agent.yaml").write_text(
        BASE.format(nombre=nombre, extra=extra), encoding="utf-8"
    )


async def test_la_cadena_queda_compilada(tmp_path):
    _escribir(tmp_path, "a", "  chain:\n    on_complete:\n      - agent: b\n")
    _escribir(tmp_path, "b")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    cadenas = runtime.compiled_chains()
    assert chain_workflow_name("a") in cadenas
    assert [s.agent for s in cadenas[chain_workflow_name("a")].steps] == ["a", "b"]
    assert runtime.has_chain("a")
    assert not runtime.has_chain("b")


async def test_agente_sin_cadena_no_produce_workflow(tmp_path):
    _escribir(tmp_path, "solo")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert runtime.compiled_chains() == {}


async def test_ciclo_explota_al_arrancar(tmp_path):
    _escribir(tmp_path, "a", "  chain:\n    on_complete:\n      - agent: b\n")
    _escribir(tmp_path, "b", "  chain:\n    on_complete:\n      - agent: a\n")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    with pytest.raises(ValueError, match="ciclo"):
        await runtime.bootstrap()


async def test_agente_inexistente_explota_al_arrancar(tmp_path):
    _escribir(tmp_path, "a", "  chain:\n    on_complete:\n      - agent: fantasma\n")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    with pytest.raises(ValueError, match="fantasma"):
        await runtime.bootstrap()


def test_el_loader_rechaza_el_prefijo_reservado(tmp_path):
    from astromesh.workflow.loader import WorkflowLoader

    wf = tmp_path / "malo.workflow.yaml"
    wf.write_text(
        """
apiVersion: astromesh/v1
kind: Workflow
metadata:
  name: __chain__a
spec:
  steps:
    - name: uno
      tool: noop
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="__chain__"):
        WorkflowLoader(str(tmp_path)).load_file(wf)
