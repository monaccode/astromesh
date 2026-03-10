import asyncio
import json
from dataclasses import dataclass, field
import httpx


@dataclass
class MCPToolInfo:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


class MCPClient:
    """Client for MCP (Model Context Protocol) servers supporting stdio, SSE, and HTTP transports."""

    def __init__(self, config: dict):
        self._transport = config.get("transport", "stdio")
        self._command = config.get("command")
        self._args = config.get("args", [])
        self._url = config.get("url")
        self._headers = config.get("headers", {})
        self._process = None
        self._tools: list[MCPToolInfo] = []
        self._http_client = (
            httpx.AsyncClient(timeout=30.0) if self._transport in ("sse", "http") else None
        )

    async def connect(self):
        if self._transport == "stdio":
            self._process = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        # Discover tools
        await self._discover_tools()

    async def _discover_tools(self):
        result = await self._send_request("tools/list", {})
        tools_data = result.get("tools", [])
        self._tools = [
            MCPToolInfo(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    async def _send_request(self, method: str, params: dict) -> dict:
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

        if self._transport == "stdio" and self._process:
            self._process.stdin.write((json.dumps(request) + "\n").encode())
            await self._process.stdin.drain()
            line = await self._process.stdout.readline()
            return json.loads(line.decode()).get("result", {})

        elif self._transport == "http":
            resp = await self._http_client.post(self._url, json=request, headers=self._headers)
            resp.raise_for_status()
            return resp.json().get("result", {})

        elif self._transport == "sse":
            resp = await self._http_client.post(self._url, json=request, headers=self._headers)
            resp.raise_for_status()
            return resp.json().get("result", {})

        return {}

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        result = await self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content", [])
        if content and isinstance(content, list):
            return {"result": content[0].get("text", str(content))}
        return {"result": str(result)}

    def get_tools(self) -> list[MCPToolInfo]:
        return self._tools

    async def disconnect(self):
        if self._process:
            self._process.terminate()
            await self._process.wait()
        if self._http_client:
            await self._http_client.aclose()
