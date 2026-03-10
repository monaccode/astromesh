"""SQL query built-in tool with read-only safety mode."""

import re
import sqlite3

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

_WRITE_PATTERNS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE)\s",
    re.IGNORECASE,
)


class SqlQueryTool(BuiltinTool):
    name = "sql_query"
    description = "Execute SQL queries against a database (SQLite)"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "params": {"type": "array"},
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        query = arguments["query"]
        params = arguments.get("params", [])
        conn_str = self.config.get("connection_string")
        read_only = self.config.get("read_only", True)
        max_rows = self.config.get("max_rows", 1000)

        if not conn_str:
            return ToolResult(
                success=False,
                data=None,
                error="connection_string is required in tool config",
            )
        if read_only and _WRITE_PATTERNS.match(query):
            return ToolResult(
                success=False,
                data=None,
                error="Write operations blocked: read_only mode is enabled",
            )
        if conn_str.startswith("sqlite:///"):
            return await self._execute_sqlite(
                conn_str[len("sqlite:///") :], query, params, max_rows
            )
        return ToolResult(success=False, data=None, error="Unsupported connection string format")

    async def _execute_sqlite(
        self, db_path: str, query: str, params: list, max_rows: int
    ) -> ToolResult:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = [dict(row) for row in cursor.fetchmany(max_rows)]
                conn.close()
                return ToolResult(
                    success=True,
                    data={"columns": columns, "rows": rows, "row_count": len(rows)},
                    metadata={"db": db_path},
                )
            else:
                conn.commit()
                conn.close()
                return ToolResult(
                    success=True,
                    data={"affected_rows": cursor.rowcount},
                    metadata={"db": db_path},
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
