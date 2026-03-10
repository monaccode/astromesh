"""File read and write built-in tools with path restriction support."""

import os
from pathlib import Path

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


def _is_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    """Return True if *path* is under at least one of *allowed_paths*."""
    if not allowed_paths:
        return True
    resolved = os.path.realpath(path)
    return any(resolved.startswith(os.path.realpath(ap)) for ap in allowed_paths)


class ReadFileTool(BuiltinTool):
    name = "read_file"
    description = "Read the contents of a local file (text, CSV, JSON)"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        path = arguments["path"]
        encoding = arguments.get("encoding", "utf-8")
        allowed = self.config.get("allowed_paths", [])
        if allowed and not _is_path_allowed(path, allowed):
            return ToolResult(success=False, data=None, error=f"Path not allowed: {path}")
        try:
            content = Path(path).read_text(encoding=encoding)
            return ToolResult(
                success=True,
                data={"content": content, "path": path, "size": len(content)},
                metadata={"encoding": encoding},
            )
        except FileNotFoundError:
            return ToolResult(success=False, data=None, error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WriteFileTool(BuiltinTool):
    name = "write_file"
    description = "Write content to a local file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        path = arguments["path"]
        content = arguments["content"]
        encoding = arguments.get("encoding", "utf-8")
        allowed = self.config.get("allowed_paths", [])
        if allowed and not _is_path_allowed(path, allowed):
            return ToolResult(success=False, data=None, error=f"Path not allowed: {path}")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding=encoding)
            return ToolResult(
                success=True,
                data={"path": path, "bytes_written": len(content.encode(encoding))},
                metadata={},
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
