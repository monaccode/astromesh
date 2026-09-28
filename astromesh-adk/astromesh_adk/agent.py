"""@agent decorator and Agent base class."""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator

from astromesh_adk.context import RunContext
from astromesh_adk.exceptions import AgentNotFoundError
from astromesh_adk.guardrails import normalize_guardrails_config
from astromesh_adk.memory import normalize_memory_config
from astromesh_adk.result import RunResult, StreamEvent
from astromesh_adk.tools import ToolDefinitionWrapper
from astromesh_adk.callbacks import Callbacks
from astromesh_adk.connection import RemoteConnection, get_connection


def _remote_connection(agent_obj) -> RemoteConnection | None:
    """Where this agent runs: its own ``bind()`` wins over ``remote()``/``connect()``."""
    if agent_obj._remote_url:
        return RemoteConnection(url=agent_obj._remote_url, api_key=agent_obj._remote_api_key or "")
    return get_connection()


class AgentWrapper:
    """Wraps a decorated function as an agent with .run() and .stream()."""

    def __init__(
        self,
        handler,
        name: str,
        model: str,
        description: str = "",
        fallback_model: str | None = None,
        routing: str = "cost_optimized",
        model_config: dict | None = None,
        tools: list | None = None,
        pattern: str = "react",
        max_iterations: int = 10,
        memory: str | dict | None = None,
        guardrails: dict | None = None,
    ):
        self._handler = handler
        self.name = name
        self.model = model
        self.description = description or name
        self.system_prompt = inspect.getdoc(handler) or ""
        self.fallback_model = fallback_model
        self.routing = routing
        self.model_config = model_config
        self.tools = tools or []
        self.pattern = pattern
        self.max_iterations = max_iterations
        self.memory_config = normalize_memory_config(memory)
        self.guardrails_config = normalize_guardrails_config(guardrails)

        # Remote binding (set via .bind())
        self._remote_url: str | None = None
        self._remote_api_key: str | None = None

    async def run(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> RunResult:
        """Execute the agent with a query.

        With a remote connection in effect (``bind()``, ``remote()`` or ``connect()``) and no
        explicit ``runtime``, runs the agent of this name on that node instead.
        """
        conn = _remote_connection(self) if runtime is None else None
        if conn is not None:
            from astromesh_adk._remote import run_remote

            return await run_remote(conn, self.name, query, session_id, context)
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        return await rt.run_agent(self, query, session_id, context, callbacks)

    async def stream(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        stream_steps: bool = False,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the agent execution (remotely over the node's WS when connected)."""
        conn = _remote_connection(self) if runtime is None else None
        if conn is not None:
            from astromesh_adk._remote import stream_remote

            async for event in stream_remote(conn, self.name, query, session_id):
                yield event
            return
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        async for event in rt.stream_agent(self, query, session_id, context, stream_steps, callbacks):
            yield event

    def as_tool(self) -> ToolDefinitionWrapper:
        """Convert this agent to a tool that can be used by other agents."""
        async def _agent_tool_handler(**kwargs):
            query = kwargs.get("query", kwargs.get("task", ""))
            result = await self.run(query)
            return result.answer

        wrapper = ToolDefinitionWrapper(
            func=_agent_tool_handler,
            description=f"Delegate to agent '{self.name}': {self.description}",
        )
        wrapper.tool_name = self.name
        wrapper.parameters_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The task or query to delegate"},
            },
            "required": ["query"],
        }
        return wrapper

    def bind(self, remote: str | None, api_key: str | None) -> None:
        """Bind this agent to execute on a specific remote Astromesh instance (None unbinds)."""
        self._remote_url = remote
        self._remote_api_key = api_key

    def __repr__(self):
        return f"<Agent {self.name!r} model={self.model!r}>"


def agent(
    name: str,
    model: str,
    description: str = "",
    fallback_model: str | None = None,
    routing: str = "cost_optimized",
    model_config: dict | None = None,
    tools: list | None = None,
    pattern: str = "react",
    max_iterations: int = 10,
    memory: str | dict | None = None,
    guardrails: dict | None = None,
):
    """Decorator to define an agent from an async function.

    The function's docstring becomes the system prompt.
    The function body is the run handler (return None for default orchestration).
    """

    def decorator(func):
        return AgentWrapper(
            handler=func,
            name=name,
            model=model,
            description=description,
            fallback_model=fallback_model,
            routing=routing,
            model_config=model_config,
            tools=tools,
            pattern=pattern,
            max_iterations=max_iterations,
            memory=memory,
            guardrails=guardrails,
        )

    return decorator


class Agent:
    """Base class for advanced agents with lifecycle hooks.

    Subclass this for agents that need custom system prompts,
    lifecycle hooks (on_before_run, on_after_run, on_tool_call),
    or state management.
    """

    name: str = ""
    model: str = ""
    description: str = ""
    fallback_model: str | None = None
    routing: str = "cost_optimized"
    model_config: dict | None = None
    tools: list = []
    pattern: str = "react"
    max_iterations: int = 10
    memory: str | dict | None = None
    guardrails: dict | None = None

    def __init__(self):
        self.tools = list(self.__class__.tools)  # copy to avoid shared mutable default
        self.memory_config = normalize_memory_config(self.memory)
        self.guardrails_config = normalize_guardrails_config(self.guardrails)
        self._remote_url: str | None = None
        self._remote_api_key: str | None = None

    @property
    def system_prompt(self) -> str:
        """Default system prompt from class docstring."""
        return inspect.getdoc(self) or ""

    def system_prompt_fn(self, ctx: RunContext) -> str:
        """Override for dynamic system prompts."""
        return self.system_prompt

    async def on_before_run(self, ctx: RunContext) -> None:
        """Hook: called before agent execution. Override to customize."""

    async def on_after_run(self, ctx: RunContext, result: RunResult) -> None:
        """Hook: called after agent execution. Override to customize."""

    async def on_tool_call(self, ctx: RunContext, tool_name: str, args: dict) -> None:
        """Hook: called before each tool call. Override to intercept."""

    async def run(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> RunResult:
        """Execute the agent (on the connected node when there is one; see AgentWrapper.run)."""
        conn = _remote_connection(self) if runtime is None else None
        if conn is not None:
            from astromesh_adk._remote import run_remote

            return await run_remote(conn, self.name, query, session_id, context)
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        return await rt.run_class_agent(self, query, session_id, context, callbacks)

    async def stream(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        stream_steps: bool = False,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the agent execution (remotely over the node's WS when connected)."""
        conn = _remote_connection(self) if runtime is None else None
        if conn is not None:
            from astromesh_adk._remote import stream_remote

            async for event in stream_remote(conn, self.name, query, session_id):
                yield event
            return
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        async for event in rt.stream_class_agent(self, query, session_id, context, stream_steps, callbacks):
            yield event

    def as_tool(self) -> ToolDefinitionWrapper:
        """Convert this agent to a tool for other agents."""
        async def _handler(**kwargs):
            query = kwargs.get("query", kwargs.get("task", ""))
            result = await self.run(query)
            return result.answer

        wrapper = ToolDefinitionWrapper(
            func=_handler,
            description=f"Delegate to agent '{self.name}': {self.description}",
        )
        wrapper.tool_name = self.name
        wrapper.parameters_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The task or query to delegate"},
            },
            "required": ["query"],
        }
        return wrapper

    def bind(self, remote: str | None, api_key: str | None) -> None:
        """Bind this agent to execute on a specific remote Astromesh instance (None unbinds)."""
        self._remote_url = remote
        self._remote_api_key = api_key

    def __repr__(self):
        return f"<Agent {self.name!r} model={self.model!r}>"
