"""Los pasos `agent` deben correr dentro del trace y la sesión del run."""

from astromesh.workflow.executor import StepExecutor
from astromesh.workflow.models import StepSpec


class _RuntimeSpy:
    """Registra con qué session_id y parent_trace_id se invocó cada agente."""

    def __init__(self):
        self.calls = []

    async def run(self, agent_name, query, session_id, context=None, parent_trace_id=None, **kw):
        self.calls.append(
            {
                "agent": agent_name,
                "query": query,
                "session_id": session_id,
                "parent_trace_id": parent_trace_id,
            }
        )
        return {"answer": f"respuesta de {agent_name}", "steps": []}


async def test_agent_step_inherits_trace_and_session():
    runtime = _RuntimeSpy()
    executor = StepExecutor(
        runtime=runtime,
        tool_registry=None,
        parent_trace_id="trace-abc",
        session_id="sesion-1",
    )
    step = StepSpec(name="uno", agent="analista", input_template="hola")

    await executor.execute_step(step, {})

    assert runtime.calls[0]["parent_trace_id"] == "trace-abc"
    assert runtime.calls[0]["session_id"] == "sesion-1"


async def test_all_steps_share_one_session():
    runtime = _RuntimeSpy()
    executor = StepExecutor(
        runtime=runtime,
        tool_registry=None,
        parent_trace_id="trace-abc",
        session_id="sesion-1",
    )

    await executor.execute_step(StepSpec(name="uno", agent="a", input_template="x"), {})
    await executor.execute_step(StepSpec(name="dos", agent="b", input_template="y"), {})

    sesiones = {c["session_id"] for c in runtime.calls}
    assert sesiones == {"sesion-1"}, f"cada paso abrió su propia sesión: {sesiones}"


async def test_falls_back_to_generated_session_when_not_given():
    """Sin session_id explícito se sigue generando uno: no rompe llamadas viejas."""
    runtime = _RuntimeSpy()
    executor = StepExecutor(runtime=runtime, tool_registry=None)

    await executor.execute_step(StepSpec(name="uno", agent="a", input_template="x"), {})

    assert runtime.calls[0]["session_id"]
    assert runtime.calls[0]["parent_trace_id"] is None
