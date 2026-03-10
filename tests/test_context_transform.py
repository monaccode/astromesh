import pytest
from unittest.mock import AsyncMock
from astromesh.core.tools import ToolRegistry


@pytest.fixture
def runtime_mock():
    runtime = AsyncMock()
    runtime.run = AsyncMock(return_value={"answer": "ok", "steps": []})
    return runtime


@pytest.fixture
def registry(runtime_mock):
    reg = ToolRegistry()
    reg.set_runtime(runtime_mock)
    return reg


class TestContextTransform:
    @pytest.mark.asyncio
    async def test_no_transform_passes_query(self, registry, runtime_mock):
        """No context_transform: query string passed as-is."""
        registry.register_agent_tool(
            name="agent-b",
            agent_name="my-agent",
            description="Agent B",
        )
        await registry.execute(
            "agent-b",
            {"query": "hello world"},
            context={"session": "s1"},
        )
        runtime_mock.run.assert_called_once_with(
            "my-agent",
            "hello world",
            session_id="s1",
            context=None,
            parent_trace_id=None,
        )

    @pytest.mark.asyncio
    async def test_transform_reshapes_context(self, registry, runtime_mock):
        """context_transform produces a dict passed as context kwarg."""
        registry.register_agent_tool(
            name="agent-b",
            agent_name="my-agent",
            description="Agent B",
            context_transform="{score: data.score, name: data.name}",
        )
        await registry.execute(
            "agent-b",
            {"query": "evaluate", "score": 95, "name": "Alice"},
            context={"session": "s2"},
        )
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs.kwargs["context"] == {"score": 95, "name": "Alice"}

    @pytest.mark.asyncio
    async def test_transform_with_nested_data(self, registry, runtime_mock):
        """Transform can access nested fields."""
        registry.register_agent_tool(
            name="agent-c",
            agent_name="deep-agent",
            description="Agent C",
            context_transform="{city: data.address.city}",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "address": {"type": "object"},
                },
            },
        )
        await registry.execute(
            "agent-c",
            {"query": "lookup", "address": {"city": "Portland", "state": "OR"}},
            context={"session": "s3"},
        )
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs.kwargs["context"] == {"city": "Portland"}

    @pytest.mark.asyncio
    async def test_transform_error_returns_error_dict(self, registry):
        """Invalid transform template returns error instead of crashing."""
        registry.register_agent_tool(
            name="bad-agent",
            agent_name="crash-agent",
            description="Bad transform",
            context_transform="{broken: data.nonexistent.deep.path}",
        )
        result = await registry.execute(
            "bad-agent",
            {"query": "test"},
            context={"session": "s4"},
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_transform_treated_as_none(self, registry, runtime_mock):
        """Empty string transform treated same as no transform."""
        registry.register_agent_tool(
            name="agent-d",
            agent_name="my-agent",
            description="Agent D",
            context_transform="",
        )
        await registry.execute(
            "agent-d",
            {"query": "go"},
            context={"session": "s5"},
        )
        runtime_mock.run.assert_called_once_with(
            "my-agent",
            "go",
            session_id="s5",
            context=None,
            parent_trace_id=None,
        )
