"""Tests for astromeshctl run, dev, and client extensions."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.client import api_get_params, api_post_with_timeout
from cli.main import app

runner = CliRunner()


# --- Client tests ---


def test_api_post_with_timeout():
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": "ok"}
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response) as mock_post:
        result = api_post_with_timeout("/v1/agents/test/run", json={"query": "hi"}, timeout=30.0)
    assert result == {"result": "ok"}
    mock_post.assert_called_once()


def test_api_get_params():
    mock_response = MagicMock()
    mock_response.json.return_value = {"traces": []}
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_response):
        result = api_get_params("/v1/traces/", params={"agent": "test", "limit": 10})
    assert result == {"traces": []}


# --- Run command tests ---


def test_run_agent():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": "Hello from agent",
        "trace_id": "abc-123",
        "tokens_used": 150,
    }
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["run", "support-agent", "What is your return policy?"])
    assert result.exit_code == 0
    assert "Hello from agent" in result.output


def test_run_agent_with_json_output():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "ok", "trace_id": "x"}
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["run", "support-agent", "hi", "--json"])
    assert result.exit_code == 0
    assert "trace_id" in result.output


def test_run_workflow():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "workflow": "my-workflow",
        "status": "completed",
        "steps_executed": 2,
    }
    mock_response.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["run", "my-workflow", "--workflow", "--input", "{}"])
    assert result.exit_code == 0
    assert "completed" in result.output.lower() or "my-workflow" in result.output


# --- Dev command tests ---


def test_dev_command_shows_startup_info(monkeypatch):
    """Test that dev prints startup info before launching uvicorn."""
    import cli.commands.dev as dev_mod

    calls = []
    monkeypatch.setattr(dev_mod, "_launch_uvicorn", lambda **kw: calls.append(kw))
    result = runner.invoke(app, ["dev", "--port", "9000", "--no-open"])
    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0]["port"] == 9000
