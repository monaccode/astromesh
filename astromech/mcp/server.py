import json
from dataclasses import dataclass
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


class MCPServer:
    """Expose Astromech agents as MCP tools."""

    def __init__(self, runtime=None):
        self._runtime = runtime
        self._router = APIRouter()
        self._setup_routes()

    def _setup_routes(self):
        @self._router.post("/mcp")
        async def handle_mcp(request: Request):
            body = await request.json()
            method = body.get("method", "")
            params = body.get("params", {})
            request_id = body.get("id", 1)

            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "astromech", "version": "0.1.0"},
                }
            elif method == "tools/list":
                tools = []
                if self._runtime:
                    for agent_info in self._runtime.list_agents():
                        tools.append({
                            "name": f"agent_{agent_info['name']}",
                            "description": f"Run agent: {agent_info['name']}",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "The query to send"},
                                    "session_id": {"type": "string", "description": "Session ID"},
                                },
                                "required": ["query"],
                            },
                        })
                result = {"tools": tools}
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                agent_name = tool_name.replace("agent_", "", 1)
                query = arguments.get("query", "")
                session_id = arguments.get("session_id", "mcp-session")

                try:
                    if self._runtime:
                        response = await self._runtime.run(agent_name, query, session_id)
                        result = {"content": [{"type": "text", "text": response.get("answer", "")}]}
                    else:
                        result = {"content": [{"type": "text", "text": "No runtime configured"}]}
                except Exception as e:
                    result = {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
            else:
                result = {}

            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

    @property
    def router(self):
        return self._router
