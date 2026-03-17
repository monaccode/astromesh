import pytest
from astromesh_adk.tools import tool, Tool, ToolDefinitionWrapper


# --- @tool decorator tests ---

@tool(description="Search the web")
async def web_search(query: str, max_results: int = 5) -> str:
    return f"Results for {query}"


@tool(description="Calculate", rate_limit={"max_calls": 10, "window_seconds": 60})
async def calculator(expression: str) -> float:
    return 42.0


def test_tool_decorator_preserves_callable():
    """The decorated function is still callable as a tool handler."""
    assert callable(web_search)


def test_tool_decorator_creates_wrapper():
    assert isinstance(web_search, ToolDefinitionWrapper)


def test_tool_decorator_name_from_function():
    assert web_search.tool_name == "web_search"


def test_tool_decorator_description():
    assert web_search.tool_description == "Search the web"


def test_tool_decorator_schema_generation():
    schema = web_search.parameters_schema
    assert schema["type"] == "object"
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["type"] == "string"
    assert "max_results" in schema["properties"]
    assert schema["properties"]["max_results"]["type"] == "integer"
    assert schema["properties"]["max_results"].get("default") == 5
    assert schema["required"] == ["query"]


def test_tool_decorator_rate_limit():
    assert calculator.rate_limit == {"max_calls": 10, "window_seconds": 60}


async def test_tool_decorator_execution():
    result = await web_search(query="test", max_results=3)
    assert result == "Results for test"


# --- Optional type hints ---

@tool(description="Optional param")
async def optional_tool(name: str, count: int | None = None) -> str:
    return name


def test_tool_optional_params():
    schema = optional_tool.parameters_schema
    assert "count" in schema["properties"]
    assert "count" not in schema["required"]


# --- Tool base class tests ---

class MyTool(Tool):
    name = "my_tool"
    description = "A custom tool"

    def parameters(self):
        return {
            "input": {"type": "string", "description": "The input"},
        }

    async def execute(self, args: dict, ctx=None) -> str:
        return f"processed: {args['input']}"


async def test_tool_class_execute():
    t = MyTool()
    result = await t.execute({"input": "hello"})
    assert result == "processed: hello"


def test_tool_class_attributes():
    t = MyTool()
    assert t.name == "my_tool"
    assert t.description == "A custom tool"
    assert "input" in t.parameters()
