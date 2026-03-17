"""Observational callbacks for agent execution."""

from typing import Any


class Callbacks:
    """Base class for observational callbacks.

    Callbacks are read-only observers — they cannot modify or block execution.
    Override any method to receive notifications. All methods are no-ops by default.
    """

    async def on_step(self, step: dict) -> None:
        """Called after each orchestration step completes."""

    async def on_tool_result(self, tool_name: str, args: dict, result: Any) -> None:
        """Called after a tool execution completes."""

    async def on_model_call(self, model: str, messages: list[dict], response: Any) -> None:
        """Called after a model call completes."""

    async def on_error(self, error: Exception, context: dict) -> None:
        """Called when an error occurs. Errors in callbacks are logged, not propagated."""
