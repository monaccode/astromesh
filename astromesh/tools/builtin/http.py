from typing import ClassVar

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult
from astromesh.tools.builtin._red import cliente_seguro, destino_bloqueado


class HttpRequestTool(BuiltinTool):
    name = "http_request"
    description = "Make HTTP requests (GET, POST, PUT, DELETE) to external APIs"
    parameters: ClassVar[dict] = {
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
            motivo = await destino_bloqueado(url)
            if motivo:
                return ToolResult(success=False, data=None, error=motivo)
        timeout = self.config.get("timeout_seconds", 30)
        max_size = self.config.get("max_response_bytes", 5 * 1024 * 1024)
        try:
            async with cliente_seguro(permitir_internos=allow_localhost, timeout=timeout) as client:
                kwargs: dict = {"headers": headers}
                if body is not None and method in ("POST", "PUT", "PATCH"):
                    kwargs["json"] = body
                resp = await client.request(method, url, **kwargs)
                try:
                    resp_body = resp.json()
                except Exception:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
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
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))


class GraphQLQueryTool(BuiltinTool):
    name = "graphql_query"
    description = "Execute GraphQL queries against an endpoint"
    parameters: ClassVar[dict] = {
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
        motivo = await destino_bloqueado(endpoint)
        if motivo:
            return ToolResult(success=False, data=None, error=motivo)
        try:
            async with cliente_seguro(timeout=timeout) as client:
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
        except Exception as e:  # noqa: BLE001  (una tool que revienta degrada su llamada, nunca la corrida)
            return ToolResult(success=False, data=None, error=str(e))
