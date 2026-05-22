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


def _is_pydantic_model(t) -> bool:
    """Duck-typed Pydantic v2 BaseModel check (avoids a hard pydantic dep)."""
    return inspect.isclass(t) and hasattr(t, "model_json_schema") and hasattr(t, "model_validate")


def _generate_schema(func) -> dict:
    """Generate JSON schema from function signature and type hints.

    Special case: a single user-facing param annotated as a Pydantic BaseModel
    returns that model's own JSON schema, so the LLM sees the real field shape
    instead of `"string"` (the fallback for non-primitive types).
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    user_params = [n for n in sig.parameters if n not in ("self", "ctx", "context")]
    if len(user_params) == 1:
        ann = hints.get(user_params[0])
        if _is_pydantic_model(ann):
            return ann.model_json_schema()

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
        # If called only with kwargs and the function takes a single Pydantic
        # model parameter, construct that model from the kwargs (the LLM sees
        # the model's schema and sends its fields directly). Both calling
        # forms are accepted: nested (`{"<param>": {field: value, ...}}`)
        # and flat (`{field: value, ...}`).
        if not args and kwargs:
            sig = inspect.signature(self._func)
            user_params = [n for n in sig.parameters if n not in ("self", "ctx", "context")]
            if len(user_params) == 1:
                hints = get_type_hints(self._func)
                ann = hints.get(user_params[0])
                if _is_pydantic_model(ann):
                    if user_params[0] in kwargs and len(kwargs) == 1:
                        raw = kwargs[user_params[0]]
                        if isinstance(raw, dict):
                            return await self._func(ann.model_validate(raw))
                        return await self._func(raw)
                    return await self._func(ann.model_validate(kwargs))
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
