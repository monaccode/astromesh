"""Built-in tools package for Astromesh."""

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class ToolLoader:
    """Discovers and instantiates built-in tools by name."""

    def __init__(self):
        self._registry: dict[str, type[BuiltinTool]] = {}

    def register_class(self, tool_cls: type[BuiltinTool]):
        self._registry[tool_cls.name] = tool_cls

    def get(self, name: str) -> type[BuiltinTool] | None:
        return self._registry.get(name)

    def list_available(self) -> list[str]:
        return list(self._registry.keys())

    def create(self, name: str, config: dict | None = None) -> BuiltinTool:
        cls = self._registry.get(name)
        if cls is None:
            raise KeyError(f"Built-in tool '{name}' not found. Available: {self.list_available()}")
        return cls(config=config)

    def auto_discover(self):
        from astromesh.tools.builtin import ALL_TOOLS

        for tool_cls in ALL_TOOLS:
            self.register_class(tool_cls)


__all__ = ["ToolLoader", "BuiltinTool", "ToolResult", "ToolContext"]
