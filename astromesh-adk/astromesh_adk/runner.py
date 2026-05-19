"""ADK Runtime — in-process execution bridging ADK abstractions to the
Astromesh core engine (orchestration patterns + model router + providers +
tracing)."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, Any

from astromesh_adk.providers import parse_model_string, resolve_provider
from astromesh_adk.result import RunResult, StreamEvent

if TYPE_CHECKING:
    from astromesh_adk.agent import Agent, AgentWrapper
    from astromesh_adk.callbacks import Callbacks
    from astromesh_adk.team import AgentTeam

_default_runtime: ADKRuntime | None = None


def _provider_and_model(model: str) -> tuple[str, str]:
    """Map a model id to (provider_name, model_name).

    Bare Clarus model ids (e.g. 'claude-haiku-4-5', 'gpt-4o-mini') have no
    'provider/' prefix; parse_model_string would wrongly default them all to
    openai, so we route by family first.
    """
    if "/" in model:
        return parse_model_string(model)
    if model.startswith("claude"):
        return "anthropic", model
    if model.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return "openai", model
    return parse_model_string(model)


def get_or_create_runtime() -> ADKRuntime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ADKRuntime()
    return _default_runtime


def set_runtime(rt: ADKRuntime | None) -> None:
    """Test hook: override the process-wide runtime singleton."""
    global _default_runtime
    _default_runtime = rt


class ADKRuntime:
    """Placeholder — methods filled in subsequent tasks."""

    def __init__(self, provider_factory: Any = resolve_provider) -> None:
        self._provider_factory = provider_factory

    async def start(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def __aenter__(self) -> ADKRuntime:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.shutdown()
        return False
