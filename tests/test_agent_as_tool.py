from astromesh.core.tools import ToolType, ToolDefinition


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
