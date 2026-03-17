"""RunContext and ToolContext types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable


@dataclass
class MemoryAccessor:
    """Accessor for agent memory within a run context."""

    _store_fn: Callable[..., Awaitable] | None = None
    _retrieve_fn: Callable[..., Awaitable] | None = None
    _search_fn: Callable[..., Awaitable] | None = None

    async def store(self, key: str, value: str) -> None:
        if self._store_fn:
            await self._store_fn(key, value)

    async def retrieve(self, key: str) -> str | None:
        if self._retrieve_fn:
            return await self._retrieve_fn(key)
        return None

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self._search_fn:
            return await self._search_fn(query, top_k)
        return []


@dataclass
class RunContext:
    """Context passed to agent handlers and lifecycle hooks."""

    query: str
    session_id: str
    agent_name: str
    user_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    memory: MemoryAccessor = field(default_factory=MemoryAccessor)
    tools: list[str] = field(default_factory=list)

    # Internal callables — set by the runner, not by the user
    _run_default_fn: Callable[..., Awaitable] | None = field(default=None, repr=False)
    _complete_fn: Callable[..., Awaitable] | None = field(default=None, repr=False)
    _call_tool_fn: Callable[..., Awaitable] | None = field(default=None, repr=False)

    async def run_default(self):
        """Execute the default orchestration pipeline."""
        if self._run_default_fn:
            return await self._run_default_fn()
        raise RuntimeError("run_default is not available in this context")

    async def complete(self, query: str, **kwargs) -> str:
        """Call the model directly, bypassing orchestration."""
        if self._complete_fn:
            return await self._complete_fn(query, **kwargs)
        raise RuntimeError("complete is not available in this context")

    async def call_tool(self, name: str, args: dict) -> Any:
        """Execute a tool by name."""
        if self._call_tool_fn:
            return await self._call_tool_fn(name, args)
        raise RuntimeError("call_tool is not available in this context")

    @classmethod
    def from_run_params(
        cls,
        query: str,
        session_id: str,
        agent_name: str,
        context: dict | None,
        tool_names: list[str],
    ) -> RunContext:
        """Build RunContext from agent.run() parameters."""
        ctx = context or {}
        return cls(
            query=query,
            session_id=session_id,
            agent_name=agent_name,
            user_id=ctx.get("user_id"),
            metadata={k: v for k, v in ctx.items() if k != "user_id"},
            tools=tool_names,
        )


@dataclass
class ToolContext:
    """Context passed to tool execute methods."""

    agent_name: str
    session_id: str
    metadata: dict = field(default_factory=dict)
