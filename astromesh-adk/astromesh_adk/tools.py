"""@tool decorator and Tool base class."""

from __future__ import annotations

import inspect
import types
from abc import ABC, abstractmethod
from typing import Any, get_type_hints, get_origin, get_args, Union

# Python type → JSON schema type
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _is_optional(annotation) -> bool:
    """Check if a type hint is Optional (Union[X, None] or X | None)."""
    origin = get_origin(annotation)
    if origin is Union or isinstance(annotation, types.UnionType):
        args = get_args(annotation)
        return type(None) in args
    return False


def _unwrap_optional(annotation):
    """Get the inner type from Optional[X]."""
    args = get_args(annotation)
    return next(a for a in args if a is not type(None))


def _python_type_to_json(annotation) -> str:
    """Convert a Python type annotation to a JSON schema type string."""
    if _is_optional(annotation):
        annotation = _unwrap_optional(annotation)
    return _TYPE_MAP.get(annotation, "string")


def _generate_schema(func) -> dict:
    """Generate JSON schema from function signature and type hints."""
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "ctx", "context"):
            continue

        annotation = hints.get(param_name, str)
        prop: dict[str, Any] = {"type": _python_type_to_json(annotation)}

        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            if not _is_optional(annotation):
                required.append(param_name)

        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class ToolDefinitionWrapper:
    """Wraps a decorated function with tool metadata and schema."""

    def __init__(
        self,
        func,
        description: str,
        rate_limit: dict | None = None,
        requires_approval: bool = False,
        timeout: int = 30,
    ):
        self._func = func
        self.tool_name = func.__name__
        self.tool_description = description
        self.parameters_schema = _generate_schema(func)
        self.rate_limit = rate_limit
        self.requires_approval = requires_approval
        self.timeout = timeout

    async def __call__(self, *args, **kwargs):
        return await self._func(*args, **kwargs)

    def __repr__(self):
        return f"<Tool {self.tool_name!r}>"


def tool(
    description: str,
    rate_limit: dict | None = None,
    requires_approval: bool = False,
    timeout: int = 30,
):
    """Decorator to define a tool from an async function.

    JSON schema is auto-generated from type hints.
    """

    def decorator(func):
        return ToolDefinitionWrapper(
            func,
            description=description,
            rate_limit=rate_limit,
            requires_approval=requires_approval,
            timeout=timeout,
        )

    return decorator


class Tool(ABC):
    """Base class for stateful tools with lifecycle management."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def parameters(self) -> dict:
        """Return the JSON schema for tool parameters."""

    @abstractmethod
    async def execute(self, args: dict, ctx: Any = None) -> Any:
        """Execute the tool with the given arguments."""

    async def cleanup(self) -> None:
        """Clean up resources. Called during runtime shutdown."""
