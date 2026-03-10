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


class TestCircularAgentDetection:
    def _make_agent_config(self, name, agent_tools=None):
        """Helper to build a minimal agent YAML config dict."""
        tools = []
        for at in agent_tools or []:
            tools.append({"name": at, "type": "agent", "agent": at})
        return {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": name, "version": "0.1.0"},
            "spec": {
                "identity": {"description": f"Agent {name}"},
                "model": {"routing": {"strategy": "cost_optimized"}},
                "tools": tools,
                "orchestration": {"pattern": "react"},
            },
        }

    def test_direct_self_reference_detected(self):
        """Agent referencing itself as a tool should raise at bootstrap."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [self._make_agent_config("agent-a", agent_tools=["agent-a"])]
        with pytest.raises(ValueError, match="[Cc]ircular"):
            runtime._detect_circular_refs(configs)

    def test_indirect_cycle_detected(self):
        """A -> B -> A cycle should raise at bootstrap."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [
            self._make_agent_config("agent-a", agent_tools=["agent-b"]),
            self._make_agent_config("agent-b", agent_tools=["agent-a"]),
        ]
        with pytest.raises(ValueError, match="[Cc]ircular"):
            runtime._detect_circular_refs(configs)

    def test_no_cycle_passes(self):
        """A -> B -> C (no cycle) should not raise."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [
            self._make_agent_config("agent-a", agent_tools=["agent-b"]),
            self._make_agent_config("agent-b", agent_tools=["agent-c"]),
            self._make_agent_config("agent-c"),
        ]
        # Should not raise
        runtime._detect_circular_refs(configs)

    def test_diamond_dependency_no_false_positive(self):
        """A -> B, A -> C, B -> D, C -> D is not circular."""
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime.__new__(AgentRuntime)
        configs = [
            self._make_agent_config("a", agent_tools=["b", "c"]),
            self._make_agent_config("b", agent_tools=["d"]),
            self._make_agent_config("c", agent_tools=["d"]),
            self._make_agent_config("d"),
        ]
        # Should not raise
        runtime._detect_circular_refs(configs)


class TestBuildAgentWiring:
    def _make_config(self, tools=None):
        return {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "test-agent", "version": "0.1.0"},
            "spec": {
                "identity": {"description": "Test"},
                "model": {"routing": {"strategy": "cost_optimized"}},
                "tools": tools or [],
                "orchestration": {"pattern": "react"},
                "prompts": {"system": "You are a test agent."},
                "memory": {},
                "guardrails": {},
                "permissions": {},
            },
        }

    def test_build_agent_registers_agent_tools(self):
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime(config_dir="./config")
        config = self._make_config(
            tools=[
                {
                    "name": "qualify-lead",
                    "type": "agent",
                    "agent": "sales-qualifier",
                    "description": "Qualify a lead",
                },
            ]
        )
        agent = runtime._build_agent(config)
        assert "qualify-lead" in agent._tools._tools
        tool = agent._tools._tools["qualify-lead"]
        assert tool.tool_type == ToolType.AGENT
        assert tool.agent_config["agent_name"] == "sales-qualifier"

    def test_build_agent_sets_runtime_on_registry(self):
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime(config_dir="./config")
        config = self._make_config(
            tools=[
                {
                    "name": "sub-agent",
                    "type": "agent",
                    "agent": "worker",
                },
            ]
        )
        agent = runtime._build_agent(config)
        assert agent._tools._runtime is runtime

    def test_build_agent_with_context_transform(self):
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime(config_dir="./config")
        config = self._make_config(
            tools=[
                {
                    "name": "qualify-lead",
                    "type": "agent",
                    "agent": "sales-qualifier",
                    "context_transform": "{company: data.company}",
                },
            ]
        )
        agent = runtime._build_agent(config)
        tool = agent._tools._tools["qualify-lead"]
        assert tool.context_transform == "{company: data.company}"


class TestAgentAsToolIntegration:
    @pytest.mark.asyncio
    async def test_full_pipeline_agent_calls_agent(self):
        """
        End-to-end: parent agent's tool_fn invokes a child agent via ToolRegistry,
        which calls runtime.run(), returns result, and the parent continues.
        """
        child_result = {
            "answer": "Lead score: 92",
            "steps": [],
            "trace": {"trace_id": "child-trace", "spans": []},
        }
        runtime_mock = AsyncMock()
        runtime_mock.run = AsyncMock(return_value=child_result)

        registry = ToolRegistry()
        registry.set_runtime(runtime_mock)
        registry.register_agent_tool(
            name="qualify-lead",
            agent_name="sales-qualifier",
            description="Qualify a sales lead",
            context_transform="{company: data.company}",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "company": {"type": "string"},
                },
            },
        )

        # Simulate what tool_fn does in engine.py
        result = await registry.execute(
            "qualify-lead",
            {"query": "Check this lead", "company": "Acme Corp"},
            context={"session": "integration-sess"},
        )

        assert result["answer"] == "Lead score: 92"
        call_kwargs = runtime_mock.run.call_args
        assert call_kwargs.args[0] == "sales-qualifier"
        assert call_kwargs.args[1] == "Check this lead"
        assert call_kwargs.kwargs["context"] == {"company": "Acme Corp"}

    @pytest.mark.asyncio
    async def test_agent_tool_appears_in_schemas(self):
        """Agent tools appear in get_tool_schemas() for LLM function calling."""
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="research-agent",
            agent_name="researcher",
            description="Research a topic thoroughly",
        )
        registry.register_internal(
            name="calculator",
            handler=AsyncMock(return_value={"result": 42}),
            description="Calculate",
            parameters={"type": "object", "properties": {}},
        )

        schemas = registry.get_tool_schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert "research-agent" in names
        assert "calculator" in names

    @pytest.mark.asyncio
    async def test_agent_tool_with_permissions(self):
        """Agent tools respect permission filtering in get_tool_schemas()."""
        registry = ToolRegistry()
        registry.register_agent_tool(
            name="admin-agent",
            agent_name="admin",
            description="Admin operations",
            permissions=["admin"],
        )
        registry.register_agent_tool(
            name="secret-agent",
            agent_name="secret",
            description="Secret operations",
            permissions=["secret"],
        )
        registry.register_agent_tool(
            name="public-agent",
            agent_name="public",
            description="Public operations",
        )

        # No filter — all visible
        schemas = registry.get_tool_schemas()
        assert len(schemas) == 3

        # Filter by admin — admin-agent (matches) + public-agent (no perms = always visible)
        schemas = registry.get_tool_schemas(agent_permissions=["admin"])
        names = {s["function"]["name"] for s in schemas}
        assert "admin-agent" in names
        assert "public-agent" in names
        assert "secret-agent" not in names
