from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standardized result from any tool execution."""

    success: bool
    data: Any
    metadata: dict = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class ToolContext:
    """Context passed to tools during execution."""

    agent_name: str
    session_id: str
    trace_span: Any | None = None
    cache: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)
    model_fn: Any | None = None


class BuiltinTool(ABC):
    """Base class for all built-in tools."""

    name: str = ""
    description: str = ""
    parameters: dict = {}
    config_schema: dict = {}

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult: ...

    async def validate_config(self, config: dict) -> None:
        pass

    async def health_check(self) -> bool:
        return True
