import pytest
from unittest.mock import AsyncMock
from astromesh.core.tools import ToolRegistry, ToolType, ToolDefinition


class TestToolTypeAgent:
    def test_agent_enum_exists(self):
        assert ToolType.AGENT == "agent"
        assert ToolType.AGENT.value == "agent"

    def test_tool_definition_agent_config(self):
        tool = ToolDefinition(
            name="qualify-lead",
            description="Qualify a sales lead",
            tool_type=ToolType.AGENT,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            agent_config={"agent_name": "sales-qualifier"},
        )
        assert tool.agent_config["agent_name"] == "sales-qualifier"
        assert tool.context_transform is None

    def test_tool_definition_with_context_transform(self):
        tool = ToolDefinition(
            name="qualify-lead",
            description="Qualify a sales lead",
            tool_type=ToolType.AGENT,
            parameters={"type": "object", "properties": {}},
            agent_config={"agent_name": "sales-qualifier"},
            context_transform="{company: data.company, summary: data.summary}",
        )
        assert tool.context_transform is not None

    def test_tool_definition_defaults_unchanged(self):
        """Existing ToolDefinition usage still works with new fields defaulting."""
        tool = ToolDefinition(
            name="old-tool",
            description="Legacy tool",
            tool_type=ToolType.INTERNAL,
            parameters={},
        )
        assert tool.agent_config is None
        assert tool.context_transform is None


class TestRegisterAgentTool:
    def test_register_agent_tool_basic(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        assert "qualify-lead" in registry._tools
        tool = registry._tools["qualify-lead"]
        assert tool.tool_type == ToolType.AGENT
        assert tool.agent_config["agent_name"] == "sales-qualifier"

    def test_register_agent_tool_with_transform(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="summarize",
            agent_name="summarizer",
            description="Summarize content",
            context_transform="{text: data.content}",
        )
        tool = registry._tools["summarize"]
        assert tool.context_transform == "{text: data.content}"

    def test_register_agent_tool_generates_schema(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        schemas = registry.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "qualify-lead"
        assert schemas[0]["function"]["description"] == "Qualify a sales lead"

    def test_register_agent_tool_custom_parameters(self):
        registry = ToolRegistry()
        params = {
            "type": "object",
            "properties": {"company": {"type": "string"}},
            "required": ["company"],
        }
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
            parameters=params,
        )
        tool = registry._tools["qualify-lead"]
        assert tool.parameters == params


class TestExecuteAgentTool:
    @pytest.fixture
    def runtime_mock(self):
        runtime = AsyncMock()
        runtime.run = AsyncMock(
            return_value={"answer": "Lead is qualified", "steps": []}
        )
        return runtime

    @pytest.fixture
    def registry_with_agent(self, runtime_mock):
        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        return registry

    @pytest.mark.asyncio
    async def test_execute_agent_tool(self, registry_with_agent, runtime_mock):
        result = await registry_with_agent.execute(
            "qualify-lead",
            {"query": "Is Acme Corp a good lead?"},
            context={"session": "sess-1"},
        )
        runtime_mock.run.assert_called_once_with(
            "sales-qualifier",
            "Is Acme Corp a good lead?",
            session_id="sess-1",
            context=None,
            parent_trace_id=None,
        )
        assert result["answer"] == "Lead is qualified"

    @pytest.mark.asyncio
    async def test_execute_agent_tool_no_runtime(self):
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        result = await registry.execute("qualify-lead", {"query": "test"})
        assert "error" in result
        assert "runtime" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_agent_tool_extracts_session(self, runtime_mock):
        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
        )
        await registry.execute(
            "qualify-lead",
            {"query": "test"},
            context={"session": "sess-42", "agent": "parent-agent"},
        )
        runtime_mock.run.assert_called_once_with(
            "sales-qualifier",
            "test",
            session_id="sess-42",
            context=None,
            parent_trace_id=None,
        )


class TestAgentToolTracing:
    @pytest.mark.asyncio
    async def test_agent_tool_creates_child_span(self):
        """Agent-as-tool calls should appear as child spans in the trace."""
        from astromesh.observability.tracing import TracingContext

        child_trace = {
            "trace_id": "child-trace-123",
            "spans": [{"name": "agent.run", "span_id": "s1"}],
        }
        runtime_mock = AsyncMock()
        runtime_mock.run = AsyncMock(
            return_value={"answer": "done", "steps": [], "trace": child_trace}
        )

        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="sub-agent",
            agent_name="worker-agent",
            description="Sub agent",
        )

        tracing = TracingContext(agent_name="parent", session_id="s1")
        parent_span = tracing.start_span("tool.call", {"tool": "sub-agent"})

        result = await registry.execute(
            "sub-agent",
            {"query": "do work"},
            context={"session": "s1", "tracing": tracing, "parent_span": parent_span},
        )

        assert result["answer"] == "done"
        # The runtime.run call should have received parent trace info
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_agent_tool_result_includes_child_trace(self):
        """Result from agent tool includes child trace for merging."""
        child_trace = {
            "trace_id": "child-abc",
            "spans": [{"name": "agent.run", "span_id": "cs1"}],
        }
        runtime_mock = AsyncMock()
        runtime_mock.run = AsyncMock(
            return_value={"answer": "result", "steps": [], "trace": child_trace}
        )

        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="sub-agent",
            agent_name="worker",
            description="Worker",
        )

        result = await registry.execute(
            "sub-agent",
            {"query": "work"},
            context={"session": "s1"},
        )
        assert "trace" in result
        assert result["trace"]["trace_id"] == "child-abc"
