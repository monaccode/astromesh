import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from jinja2 import BaseLoader, Environment, TemplateSyntaxError, UndefinedError

from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class DatetimeNowTool(BuiltinTool):
    name = "datetime_now"
    description = "Get the current date and time with optional timezone"
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name (e.g. 'UTC', 'US/Eastern'). Defaults to UTC.",
            }
        },
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        tz_name = arguments.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = timezone.utc
            tz_name = "UTC"
        now = datetime.now(tz)
        return ToolResult(
            success=True,
            data={
                "datetime": now.isoformat(),
                "timezone": tz_name,
                "unix_timestamp": now.timestamp(),
            },
            metadata={},
        )


class JsonTransformTool(BuiltinTool):
    name = "json_transform"
    description = "Transform JSON data using a Jinja2 template that outputs JSON"
    parameters = {
        "type": "object",
        "properties": {
            "data": {"description": "The input data to transform"},
            "template": {
                "type": "string",
                "description": "Jinja2 template that produces valid JSON",
            },
        },
        "required": ["data", "template"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        data = arguments["data"]
        template_str = arguments["template"]
        try:
            env = Environment(loader=BaseLoader())
            template = env.from_string(template_str)
            rendered = template.render(data=data)
            parsed = json.loads(rendered)
            return ToolResult(success=True, data=parsed, metadata={})
        except (TemplateSyntaxError, UndefinedError, json.JSONDecodeError) as e:
            return ToolResult(success=False, data=None, metadata={}, error=str(e))


class CacheStoreTool(BuiltinTool):
    name = "cache_store"
    description = "Temporary key-value cache for sharing data between tool calls"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set", "delete"],
                "description": "Cache operation",
            },
            "key": {"type": "string", "description": "Cache key"},
            "value": {"description": "Value to store (for set action)"},
        },
        "required": ["action", "key"],
    }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        action = arguments["action"]
        key = arguments["key"]
        cache = context.cache
        if action == "set":
            cache[key] = arguments.get("value")
            return ToolResult(success=True, data=None, metadata={"action": "set", "key": key})
        elif action == "get":
            return ToolResult(
                success=True,
                data=cache.get(key),
                metadata={"action": "get", "key": key},
            )
        elif action == "delete":
            cache.pop(key, None)
            return ToolResult(success=True, data=None, metadata={"action": "delete", "key": key})
        return ToolResult(success=False, data=None, error=f"Unknown action: {action}")
