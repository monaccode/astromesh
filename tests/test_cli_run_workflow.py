# tests/test_cli_run_workflow.py
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


class TestCLIRunWorkflow:
    def test_run_workflow_basic(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "workflow_name": "lead-qual",
            "status": "completed",
            "output": {"answer": "lead is qualified"},
            "steps": {"s1": {"status": "success", "output": {"answer": "ok"}}},
            "duration_ms": 1234.5,
        }
        mock_response.raise_for_status = MagicMock()
        with patch("cli.client.httpx.post", return_value=mock_response) as mock_post:
            result = runner.invoke(
                app, ["run", "lead-qual", "--workflow", "--input", '{"query": "test lead"}']
            )
        assert result.exit_code == 0
        assert "completed" in result.output.lower() or "lead-qual" in result.output
        # Verify correct endpoint was called
        call_url = mock_post.call_args[0][0]
        assert "/v1/workflows/lead-qual/run" in call_url

    def test_run_workflow_json_output(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "workflow_name": "wf1",
            "status": "completed",
            "output": {"answer": "done"},
            "steps": {},
            "duration_ms": 100.0,
        }
        mock_response.raise_for_status = MagicMock()
        with patch("cli.client.httpx.post", return_value=mock_response):
            result = runner.invoke(
                app, ["run", "wf1", "--workflow", "--json", "--input", '{"query": "hi"}']
            )
        assert result.exit_code == 0
        assert "workflow_name" in result.output

    def test_run_workflow_failure(self):
        with patch("cli.client.httpx.post", side_effect=Exception("connection refused")):
            result = runner.invoke(
                app, ["run", "wf1", "--workflow", "--input", '{"query": "hi"}']
            )
        assert result.exit_code == 1

    def test_run_workflow_default_empty_input(self):
        """When --input is not provided, send empty trigger with query from positional arg."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "workflow_name": "wf1",
            "status": "completed",
            "output": {},
            "steps": {},
            "duration_ms": 50.0,
        }
        mock_response.raise_for_status = MagicMock()
        with patch("cli.client.httpx.post", return_value=mock_response) as mock_post:
            result = runner.invoke(app, ["run", "wf1", "hello world", "--workflow"])
        assert result.exit_code == 0
        call_json = mock_post.call_args[1].get("json") or mock_post.call_args.kwargs.get("json")
        assert call_json["query"] == "hello world"
