import pytest

from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"key": "value"}, metadata={})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self):
        result = ToolResult(success=False, data=None, metadata={}, error="Something failed")
        assert result.success is False
        assert result.error == "Something failed"

    def test_to_dict(self):
        result = ToolResult(success=True, data="hello", metadata={"tokens": 10})
        d = result.to_dict()
        assert d == {"success": True, "data": "hello", "metadata": {"tokens": 10}, "error": None}

    def test_to_dict_backward_compat(self):
        result = ToolResult(success=True, data={"answer": "42"}, metadata={})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["data"]["answer"] == "42"


class TestToolContext:
    def test_context_has_required_fields(self):
        ctx = ToolContext(
            agent_name="test-agent",
            session_id="sess-123",
            trace_span=None,
            cache={},
            secrets={},
        )
        assert ctx.agent_name == "test-agent"
        assert ctx.session_id == "sess-123"
        assert ctx.trace_span is None


class _FakeTool(BuiltinTool):
    name = "fake_tool"
    description = "A fake tool for testing"
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data=f"fake: {arguments.get('query')}", metadata={})


class TestToolLoader:
    def test_register_and_get(self):
        loader = ToolLoader()
        loader.register_class(_FakeTool)
        assert loader.get("fake_tool") is _FakeTool

    def test_get_unknown_returns_none(self):
        loader = ToolLoader()
        assert loader.get("nonexistent") is None

    def test_list_available(self):
        loader = ToolLoader()
        loader.register_class(_FakeTool)
        available = loader.list_available()
        assert "fake_tool" in available

    async def test_create_instance_with_config(self):
        loader = ToolLoader()
        loader.register_class(_FakeTool)
        instance = loader.create("fake_tool", config={"key": "val"})
        assert isinstance(instance, _FakeTool)
        assert instance.config == {"key": "val"}

    def test_create_unknown_raises(self):
        loader = ToolLoader()
        with pytest.raises(KeyError, match="nonexistent"):
            loader.create("nonexistent")
