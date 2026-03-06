import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from astromech.mcp.client import MCPClient, MCPToolInfo
from astromech.mcp.server import MCPServer
from astromech.core.tools import ToolRegistry


async def test_mcp_client_call_tool():
    client = MCPClient({"transport": "http", "url": "http://localhost:3000/mcp"})
    client._http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {"content": [{"type": "text", "text": "tool result"}]}
    }
    mock_response.raise_for_status = MagicMock()
    client._http_client.post = AsyncMock(return_value=mock_response)

    result = await client.call_tool("test_tool", {"arg": "value"})
    assert result["result"] == "tool result"


async def test_mcp_client_get_tools():
    client = MCPClient({"transport": "http", "url": "http://localhost:3000/mcp"})
    client._tools = [MCPToolInfo(name="tool1", description="A tool", parameters={})]
    tools = client.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "tool1"


async def test_mcp_server_tools_list():
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI

    runtime = MagicMock()
    runtime.list_agents.return_value = [
        {"name": "echo", "version": "0.1.0", "namespace": "default"}
    ]

    app = FastAPI()
    mcp_server = MCPServer(runtime=runtime)
    app.include_router(mcp_server.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["result"]["tools"]) == 1
        assert data["result"]["tools"][0]["name"] == "agent_echo"


async def test_tool_registry_register_mcp():
    registry = ToolRegistry()
    mock_client = MagicMock()
    mock_client.get_tools.return_value = [
        MCPToolInfo(name="mcp_tool", description="An MCP tool", parameters={"x": {"type": "number"}})
    ]
    count = await registry.register_mcp_server("test-server", mock_client)
    assert count == 1
    assert "mcp_tool" in registry._tools
    schemas = registry.get_tool_schemas()
    assert any(s["function"]["name"] == "mcp_tool" for s in schemas)
