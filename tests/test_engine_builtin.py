from unittest.mock import patch
from astromesh.runtime.engine import AgentRuntime
from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolResult, ToolContext


class _FakeBuiltinTool(BuiltinTool):
    name = "fake_builtin"
    description = "A fake builtin tool for testing engine wiring"
    parameters = {"type": "object", "properties": {"input": {"type": "string"}}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data=f"fake: {arguments.get('input')}", metadata={})


class TestBuiltinToolLoading:
    def test_build_agent_resolves_builtin_type(self):
        """type: builtin in YAML should register the tool in the agent's ToolRegistry."""
        config = {
            "apiVersion": "astromesh/v1",
            "kind": "Agent",
            "metadata": {"name": "test-agent", "version": "1.0.0"},
            "spec": {
                "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
                "orchestration": {"pattern": "react"},
                "tools": [
                    {"name": "fake_builtin", "type": "builtin"},
                ],
            },
        }

        def _fake_discover(self):
            self.register_class(_FakeBuiltinTool)

        with patch.object(ToolLoader, "auto_discover", _fake_discover):
            runtime = AgentRuntime(config_dir="./config")
            agent = runtime._build_agent(config)

        schemas = agent._tools.get_tool_schemas()
        tool_names = [s["function"]["name"] for s in schemas]
        assert "fake_builtin" in tool_names
