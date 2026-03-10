import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

try:
    from astromesh._native import RustRateLimiter

    _NATIVE_RATE_LIMITER = RustRateLimiter()
    _HAS_NATIVE_RL = True
except ImportError:
    _NATIVE_RATE_LIMITER = None
    _HAS_NATIVE_RL = False


class ToolType(str, Enum):
    INTERNAL = "internal"
    MCP_STDIO = "mcp_stdio"
    MCP_SSE = "mcp_sse"
    MCP_HTTP = "mcp_http"
    WEBHOOK = "webhook"
    RAG = "rag"
    AGENT = "agent"


@dataclass
class ToolDefinition:
    name: str
    description: str
    tool_type: ToolType
    parameters: dict
    handler: Callable | None = None
    mcp_config: dict = field(default_factory=dict)
    requires_approval: bool = False
    timeout_seconds: int = 30
    rate_limit: dict | None = None
    permissions: list[str] = field(default_factory=list)
    agent_config: dict | None = None
    context_transform: str | None = None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._mcp_clients: dict[str, Any] = {}
        self._call_counts: dict[str, list[float]] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def register_internal(self, name, handler, description, parameters, **kwargs):
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            tool_type=ToolType.INTERNAL,
            parameters=parameters,
            handler=handler,
            **kwargs,
        )

    def register_agent_tool(
        self,
        name: str,
        agent_name: str,
        description: str,
        parameters: dict | None = None,
        context_transform: str | None = None,
        **kwargs,
    ):
        """Register an agent as a callable tool."""
        default_params = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query or task to send to the agent",
                },
            },
            "required": ["query"],
        }
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            tool_type=ToolType.AGENT,
            parameters=parameters or default_params,
            agent_config={"agent_name": agent_name},
            context_transform=context_transform,
            **kwargs,
        )

    async def execute(self, tool_name, arguments, context=None) -> dict:
        tool = self._tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}
        if tool.rate_limit and not self._check_rate_limit(tool_name, tool.rate_limit):
            return {"error": f"Rate limit exceeded for '{tool_name}'"}
        if tool.tool_type == ToolType.INTERNAL and tool.handler:
            return await tool.handler(**arguments)
        elif tool.tool_type.value.startswith("mcp_"):
            server_name = tool.mcp_config["server"]
            client = self._mcp_clients.get(server_name)
            if not client:
                return {"error": f"MCP server '{server_name}' not connected"}
            return await client.call_tool(tool.mcp_config["tool_name"], arguments)
        return {"error": f"Unsupported tool type: {tool.tool_type}"}

    def get_tool_schemas(self, agent_permissions=None) -> list[dict]:
        schemas = []
        for name, tool in self._tools.items():
            if agent_permissions and tool.permissions:
                if not any(p in agent_permissions for p in tool.permissions):
                    continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    async def register_mcp_server(self, server_name: str, client) -> int:
        """Register all tools from an MCP server."""
        self._mcp_clients[server_name] = client
        tools_registered = 0
        for tool_info in client.get_tools():
            self._tools[tool_info.name] = ToolDefinition(
                name=tool_info.name,
                description=tool_info.description,
                tool_type=ToolType.MCP_HTTP,
                parameters=tool_info.parameters,
                mcp_config={"server": server_name, "tool_name": tool_info.name},
            )
            tools_registered += 1
        return tools_registered

    async def register_builtin(self, name: str, config: dict | None = None):
        """Register a built-in tool by name from the catalog."""
        from astromesh.tools import ToolLoader

        loader = ToolLoader()
        loader.auto_discover()
        instance = loader.create(name, config=config)
        await instance.validate_config(config or {})

        async def _handler(**arguments):
            from astromesh.tools.base import ToolContext

            ctx = ToolContext(agent_name="", session_id="", trace_span=None, cache={}, secrets={})
            result = await instance.execute(arguments, ctx)
            return result.to_dict()

        self.register_internal(
            name=instance.name,
            handler=_handler,
            description=instance.description,
            parameters=instance.parameters,
        )

    def _check_rate_limit(self, tool_name, rate_limit):
        if _HAS_NATIVE_RL and not os.environ.get("ASTROMESH_FORCE_PYTHON"):
            window = rate_limit.get("window_seconds", 60)
            max_calls = rate_limit.get("max_calls", 10)
            return _NATIVE_RATE_LIMITER.check(tool_name, window, max_calls)
        now = time.time()
        window = rate_limit.get("window_seconds", 60)
        max_calls = rate_limit.get("max_calls", 10)
        if tool_name not in self._call_counts:
            self._call_counts[tool_name] = []
        self._call_counts[tool_name] = [t for t in self._call_counts[tool_name] if now - t < window]
        if len(self._call_counts[tool_name]) >= max_calls:
            return False
        self._call_counts[tool_name].append(now)
        return True
