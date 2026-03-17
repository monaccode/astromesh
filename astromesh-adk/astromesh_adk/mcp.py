"""MCP tools integration — lazy discovery."""

from __future__ import annotations

from typing import Any, Iterator


class MCPToolSet:
    """Lazy MCP tool set descriptor.

    Created synchronously at import time. Actual MCP server connection
    and tool discovery happens on first agent run via discover().
    """

    def __init__(self, config: dict):
        self.config = config
        self.discovered = False
        self._tools: list[dict] = []
        self._client: Any = None

    async def discover(self) -> list[dict]:
        """Connect to MCP server and discover available tools.

        Called automatically by the ADK runner on first agent execution.
        """
        from astromesh.mcp.client import MCPClient

        self._client = MCPClient(self.config)
        await self._client.connect()
        mcp_tools_info = self._client.get_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in mcp_tools_info
        ]
        self.discovered = True
        return self._tools

    async def cleanup(self) -> None:
        """Disconnect from MCP server."""
        if self._client:
            await self._client.disconnect()
            self._client = None

    def __iter__(self) -> Iterator:
        """Allow unpacking with * in tools list.

        Before discovery, yields self as a lazy marker.
        After discovery, yields individual tool dicts.
        """
        if self.discovered:
            yield from self._tools
        else:
            yield self

    def __repr__(self) -> str:
        transport = self.config.get("transport", "unknown")
        return f"<MCPToolSet transport={transport!r} discovered={self.discovered}>"


def mcp_tools(
    transport: str,
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    headers: dict | None = None,
    env: dict | None = None,
) -> MCPToolSet:
    """Create a lazy MCP tool set.

    Returns immediately (no async). Connection happens on first agent run.
    Use with * unpacking in agent tools list:

        github = mcp_tools(transport="stdio", command="npx", args=[...])

        @agent(tools=[search, *github])
        async def my_agent(ctx): ...
    """
    config: dict[str, Any] = {"transport": transport}
    if command is not None:
        config["command"] = command
    if args is not None:
        config["args"] = args
    if url is not None:
        config["url"] = url
    if headers is not None:
        config["headers"] = headers
    if env is not None:
        config["env"] = env

    return MCPToolSet(config)
