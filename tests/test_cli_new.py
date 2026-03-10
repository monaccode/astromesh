"""Tests for astromeshctl new (scaffolding) commands."""

from typer.testing import CliRunner

from cli.commands.new import render_agent_template, render_tool_template, render_workflow_template
from cli.main import app

runner = CliRunner()


class TestTemplateRendering:
    def test_render_agent_template_minimal(self):
        result = render_agent_template(name="test-bot", provider="ollama", model="llama3.1:8b")
        assert "name: test-bot" in result
        assert "apiVersion: astromesh/v1" in result
        assert "kind: Agent" in result
        assert "ollama" in result

    def test_render_agent_template_with_tools(self):
        result = render_agent_template(
            name="helper",
            provider="openai",
            model="gpt-4o",
            tools=["web_search", "http_request"],
        )
        assert "web_search" in result
        assert "http_request" in result

    def test_render_workflow_template(self):
        result = render_workflow_template(name="my-workflow")
        assert "name: my-workflow" in result
        assert "kind: Workflow" in result

    def test_render_tool_template(self):
        result = render_tool_template(name="my_custom_tool", description="Does something useful")
        assert "class MyCustomToolTool(BuiltinTool)" in result
        assert "Does something useful" in result


class TestNewAgentCommand:
    def test_new_agent_non_interactive(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "new",
                "agent",
                "my-bot",
                "--provider",
                "ollama",
                "--model",
                "llama3.1:8b",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        agent_file = tmp_path / "my-bot.agent.yaml"
        assert agent_file.exists()
        content = agent_file.read_text()
        assert "name: my-bot" in content

    def test_new_agent_refuses_overwrite_without_force(self, tmp_path):
        (tmp_path / "existing.agent.yaml").write_text("existing")
        result = runner.invoke(
            app,
            [
                "new",
                "agent",
                "existing",
                "--provider",
                "ollama",
                "--model",
                "llama3.1:8b",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "already exists" in result.output.lower() or "overwrite" in result.output.lower()

    def test_new_tool_creates_python_file(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "new",
                "tool",
                "my_checker",
                "--description",
                "Checks things",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        tool_file = tmp_path / "my_checker.py"
        assert tool_file.exists()

    def test_new_workflow_creates_file(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "new",
                "workflow",
                "my-pipeline",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        wf_file = tmp_path / "my-pipeline.workflow.yaml"
        assert wf_file.exists()
        content = wf_file.read_text()
        assert "kind: Workflow" in content
