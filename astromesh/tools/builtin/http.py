from urllib.parse import urlparse

import httpx

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}


class HttpRequestTool(BuiltinTool):
    name = "http_request"
    description = "Make HTTP requests (GET, POST, PUT, DELETE) to external APIs"
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            },
            "url": {"type": "string", "description": "Request URL"},
            "headers": {"type": "object", "description": "Request headers"},
            "body": {"description": "Request body (for POST/PUT/PATCH)"},
        },
        "required": ["method", "url"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        url = arguments["url"]
        method = arguments["method"].upper()
        headers = arguments.get("headers", {})
        body = arguments.get("body")
        allow_localhost = self.config.get("allow_localhost", False)
        if not allow_localhost:
            parsed = urlparse(url)
            if parsed.hostname in _BLOCKED_HOSTS:
                return ToolResult(
                    success=False,
                    data=None,
                    error="Blocked: requests to localhost are not allowed",
                )
        timeout = self.config.get("timeout_seconds", 30)
        max_size = self.config.get("max_response_bytes", 5 * 1024 * 1024)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                kwargs: dict = {"headers": headers}
                if body is not None and method in ("POST", "PUT", "PATCH"):
                    kwargs["json"] = body
                resp = await client.request(method, url, **kwargs)
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = resp.text[:max_size]
                return ToolResult(
                    success=True,
                    data={
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp_body,
                    },
                    metadata={"url": url, "method": method},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class GraphQLQueryTool(BuiltinTool):
    name = "graphql_query"
    description = "Execute GraphQL queries against an endpoint"
    parameters = {
        "type": "object",
        "properties": {
            "endpoint": {"type": "string"},
            "query": {"type": "string"},
            "variables": {"type": "object"},
            "headers": {"type": "object"},
        },
        "required": ["endpoint", "query"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        endpoint = arguments["endpoint"]
        query = arguments["query"]
        variables = arguments.get("variables", {})
        headers = arguments.get("headers", {})
        timeout = self.config.get("timeout_seconds", 30)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    endpoint,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                return ToolResult(
                    success=True,
                    data=resp.json(),
                    metadata={"endpoint": endpoint, "status_code": resp.status_code},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
