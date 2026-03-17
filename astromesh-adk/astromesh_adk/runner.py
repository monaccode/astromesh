"""ADK Runtime — stub for initial agent module import."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astromesh_adk.agent import AgentWrapper, Agent

_default_runtime = None


def get_or_create_runtime():
    """Get or lazily create the default ADKRuntime."""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ADKRuntime()
    return _default_runtime


class ADKRuntime:
    """Placeholder — full implementation in Task 13."""

    async def start(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()
        return False

    async def run_agent(self, agent_wrapper, query, session_id, context, callbacks):
        raise NotImplementedError("ADKRuntime.run_agent not yet implemented")

    async def stream_agent(self, agent_wrapper, query, session_id, context, stream_steps, callbacks):
        raise NotImplementedError("ADKRuntime.stream_agent not yet implemented")
        yield  # make it a generator

    async def run_class_agent(self, agent_instance, query, session_id, context, callbacks):
        raise NotImplementedError("ADKRuntime.run_class_agent not yet implemented")

    async def stream_class_agent(self, agent_instance, query, session_id, context, stream_steps, callbacks):
        raise NotImplementedError("ADKRuntime.stream_class_agent not yet implemented")
        yield  # make it a generator

    async def run_team(self, team, query, session_id, context, callbacks):
        raise NotImplementedError("ADKRuntime.run_team not yet implemented")
