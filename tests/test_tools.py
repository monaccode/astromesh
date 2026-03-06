import pytest
from astromech.core.tools import ToolRegistry, ToolDefinition, ToolType


@pytest.fixture
def registry():
    return ToolRegistry()


async def double_handler(x: int):
    return {"result": x * 2}


def test_register_internal_tool(registry):
    registry.register_internal(
        name="double",
        handler=double_handler,
        description="Doubles a number",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
    )
    assert "double" in registry._tools
    assert registry._tools["double"].tool_type == ToolType.INTERNAL
    assert registry._tools["double"].handler is double_handler


@pytest.mark.asyncio
async def test_execute_internal_tool(registry):
    registry.register_internal(
        name="double",
        handler=double_handler,
        description="Doubles a number",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
    )
    result = await registry.execute("double", {"x": 5})
    assert result == {"result": 10}


@pytest.mark.asyncio
async def test_execute_missing_tool(registry):
    result = await registry.execute("nonexistent", {})
    assert "error" in result
    assert "not found" in result["error"]


def test_get_tool_schemas(registry):
    registry.register_internal(
        name="tool_a",
        handler=double_handler,
        description="Tool A",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
    )
    registry.register_internal(
        name="tool_b",
        handler=double_handler,
        description="Tool B",
        parameters={"type": "object", "properties": {"y": {"type": "string"}}},
    )
    schemas = registry.get_tool_schemas()
    assert len(schemas) == 2
    assert schemas[0]["type"] == "function"
    assert "function" in schemas[0]
    assert schemas[0]["function"]["name"] == "tool_a"
    assert schemas[1]["function"]["name"] == "tool_b"
    assert "parameters" in schemas[0]["function"]


def test_get_tool_schemas_filtered(registry):
    registry.register_internal(
        name="admin_tool",
        handler=double_handler,
        description="Admin only",
        parameters={},
        permissions=["admin"],
    )
    registry.register_internal(
        name="public_tool",
        handler=double_handler,
        description="Public tool",
        parameters={},
    )
    # Agent with "user" permission should not see admin_tool but should see public_tool
    schemas = registry.get_tool_schemas(agent_permissions=["user"])
    names = [s["function"]["name"] for s in schemas]
    assert "public_tool" in names
    assert "admin_tool" not in names

    # Agent with "admin" permission should see both
    schemas_admin = registry.get_tool_schemas(agent_permissions=["admin"])
    names_admin = [s["function"]["name"] for s in schemas_admin]
    assert "admin_tool" in names_admin
    assert "public_tool" in names_admin
