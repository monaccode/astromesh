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
