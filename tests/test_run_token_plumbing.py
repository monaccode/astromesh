"""El token por corrida: de dónde entra, hasta dónde llega, y por dónde no pasa.

Nexus acuña una credencial por invocación y la baja en el context de la corrida
bajo `_nexus_run_token`. La cadena completa es

    context del llamador → Agent.run → tool_fn → ToolRegistry.execute
        → clausura builtin → ToolContext.secrets → send_message → header HTTP

y cada eslabón de esa cadena es un lugar donde una credencial puede quedar
escrita en disco o volver al modelo. Los tests de abajo recorren la cadena
entera y además fijan las dos negativas que la hacen segura: el token no aparece
en la traza, y no aparece en el context que ve el patrón (o sea, tampoco en un
programa Glyph ni en un `ask()` al proveedor).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import respx

from astromesh.core.tools import ToolRegistry
from astromesh.runtime.engine import Agent, _make_builtin_handler, _public_caller_context
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

RUN_TOKEN = "run-token-de-prueba"
NEXUS = "https://nexus.example.com"


class _SpyTool(BuiltinTool):
    """Registra el ToolContext que le llegó, que es justamente lo que se prueba."""

    name = "spy"
    description = "records its context"
    parameters = {"type": "object", "properties": {"input": {"type": "string"}}}

    def __init__(self, config=None):
        super().__init__(config)
        self.seen: list[tuple[dict, ToolContext]] = []

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        self.seen.append((arguments, context))
        return ToolResult(success=True, data="ok", metadata={})


class _FakeResponse:
    def __init__(self, content=""):
        self.content = content
        self.tool_calls = []
        self.model = "fake-model"
        self.provider = "fake"
        self.latency_ms = 1
        self.cost = 0.0
        self.usage = {"input_tokens": 1, "output_tokens": 1}


class _CallsATool:
    """Hace de patrón: maneja las mismas clausuras que maneja un patrón real."""

    def __init__(self, tool_name, args):
        self.tool_name = tool_name
        self.args = args
        self.seen_context = None

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        from astromesh.orchestration.patterns import AgentStep

        self.seen_context = context
        observation = await tool_fn(self.tool_name, self.args)
        return {
            "answer": "listo",
            "steps": [
                AgentStep(
                    action=self.tool_name, action_input=self.args, observation=str(observation)
                )
            ],
        }


def _agent(tools: ToolRegistry, pattern) -> Agent:
    agent = Agent.__new__(Agent)
    agent.name = "test-agent"
    agent._pattern = pattern
    agent._role_map = {}
    agent._orchestration_config = {"pattern": "test"}
    agent._permissions = {}
    agent._output_schema = None
    agent._guardrails = {}
    agent._rag = None
    agent._knowledge = None
    agent._system_prompt = "you are a test agent"
    agent._tools = tools

    router = MagicMock()
    router.route = AsyncMock(return_value=_FakeResponse(content="narrando"))
    agent._routers = {"default": router}

    memory = MagicMock()
    # Un dict, no una lista: `run` sólo adjunta `_caller_context` cuando el
    # contexto de memoria es un dict, y esa es la rama donde el filtrado de
    # claves reservadas tiene que valer.
    memory.build_context = AsyncMock(return_value={})
    memory.persist_turn = AsyncMock()
    agent._memory = memory

    prompt = MagicMock()
    prompt.render = MagicMock(return_value="you are a test agent")
    agent._prompt_engine = prompt
    return agent


def _with_spy(pattern) -> tuple[Agent, _SpyTool]:
    spy = _SpyTool()
    tools = ToolRegistry()
    tools.register_internal(
        name="spy",
        handler=_make_builtin_handler(spy, "test-agent"),
        description=spy.description,
        parameters=spy.parameters,
    )
    return _agent(tools, pattern), spy


async def test_the_run_token_reaches_a_builtin_tool():
    pattern = _CallsATool("spy", {"input": "x"})
    agent, spy = _with_spy(pattern)

    await agent.run("hola", "s1", context={"_nexus_run_token": RUN_TOKEN})

    _, ctx = spy.seen[0]
    assert ctx.secrets["NEXUS_RUN_TOKEN"] == RUN_TOKEN


async def test_a_run_without_a_token_leaves_secrets_empty_rather_than_stale():
    pattern = _CallsATool("spy", {"input": "x"})
    agent, spy = _with_spy(pattern)

    await agent.run("hola", "s1", context={"locale": "es-AR"})

    _, ctx = spy.seen[0]
    assert ctx.secrets == {}


async def test_the_session_reaches_a_builtin_tool_too():
    """Iba fijo en "" antes de que el context de la corrida bajara a la clausura."""
    pattern = _CallsATool("spy", {"input": "x"})
    agent, spy = _with_spy(pattern)

    await agent.run("hola", "sesion-7")

    _, ctx = spy.seen[0]
    assert ctx.session_id == "sesion-7"


async def test_the_token_is_not_in_the_context_the_pattern_sees():
    """La mitad que protege a los programas Glyph y a lo que se manda al modelo."""
    pattern = _CallsATool("spy", {"input": "x"})
    agent, _ = _with_spy(pattern)

    await agent.run("hola", "s1", context={"_nexus_run_token": RUN_TOKEN, "locale": "es-AR"})

    assert RUN_TOKEN not in json.dumps(pattern.seen_context, default=str)
    # Y lo que sí es del llamador sigue llegando: el filtro es por prefijo, no un
    # portazo.
    assert pattern.seen_context["_caller_context"] == {"locale": "es-AR"}


def test_reserved_keys_are_stripped_from_the_caller_context():
    assert _public_caller_context({"_nexus_run_token": RUN_TOKEN, "a": 1}) == {"a": 1}


async def test_the_token_is_not_written_to_the_trace():
    pattern = _CallsATool("spy", {"input": "x"})
    agent, _ = _with_spy(pattern)

    result = await agent.run("hola", "s1", context={"_nexus_run_token": RUN_TOKEN})

    assert RUN_TOKEN not in json.dumps(result.get("trace", {}), default=str)
    assert RUN_TOKEN not in json.dumps(result, default=str)


async def test_a_model_authored_run_context_argument_is_dropped():
    """Si colisionara con el kwarg real, Python levantaría TypeError y se caería
    la llamada entera; y un modelo no puede fabricarse un context."""
    pattern = _CallsATool("spy", {"input": "x", "_run_context": {"secrets": {"a": "b"}}})
    agent, spy = _with_spy(pattern)

    await agent.run("hola", "s1", context={"_nexus_run_token": RUN_TOKEN})

    args, ctx = spy.seen[0]
    assert "_run_context" not in args
    assert ctx.secrets == {"NEXUS_RUN_TOKEN": RUN_TOKEN}


async def test_a_handler_that_does_not_opt_in_is_called_unchanged():
    """register_internal lo usan handlers ajenos con firmas arbitrarias."""
    calls = []

    async def plain_handler(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    tools = ToolRegistry()
    tools.register_internal(
        name="plain", handler=plain_handler, description="d", parameters={"type": "object"}
    )
    agent = _agent(tools, _CallsATool("plain", {"input": "x"}))

    await agent.run("hola", "s1", context={"_nexus_run_token": RUN_TOKEN})

    assert calls == [{"input": "x"}]


@respx.mock
async def test_end_to_end_the_agent_sends_through_nexus_with_the_minted_token():
    """La cadena completa, con la tool real: el token entra por el context del
    llamador y sale como header hacia Nexus, sin pasar por args ni por la traza."""
    from astromesh.tools.builtin.communication import SendMessageTool

    route = respx.post(f"{NEXUS}/api/v1/runs/messages/send").mock(
        return_value=httpx.Response(202, json={"message_id": "m-1", "status": "pending"})
    )
    tool = SendMessageTool(config={"nexus_url": NEXUS})
    tools = ToolRegistry()
    tools.register_internal(
        name="send_message",
        handler=_make_builtin_handler(tool, "test-agent"),
        description=tool.description,
        parameters=tool.parameters,
    )
    args = {"channel": "whatsapp", "recipient": "+5491100000001", "text": "tu turno es mañana"}
    pattern = _CallsATool("send_message", args)
    agent = _agent(tools, pattern)

    result = await agent.run("avisale", "s1", context={"_nexus_run_token": RUN_TOKEN})

    assert route.called
    sent = route.calls.last.request
    assert sent.headers["X-Nexus-Run-Token"] == RUN_TOKEN
    assert json.loads(sent.content)["text"] == "tu turno es mañana"
    assert RUN_TOKEN not in json.dumps(result, default=str)
