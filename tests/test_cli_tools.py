"""Tests for astromeshctl tools list/test commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_tools_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "tools": [
            {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {"query": {"type": "string"}},
            },
            {
                "name": "http_request",
                "description": "Make HTTP requests",
                "parameters": {},
            },
        ],
        "count": 2,
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["tools", "list"])
    assert result.exit_code == 0
    assert "web_search" in result.output
    assert "http_request" in result.output


def test_tools_test():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "tool": "web_search",
        "result": {"data": "results"},
        "status": "ok",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["tools", "test", "web_search", '{"query": "test"}'])
    assert result.exit_code == 0
    assert "results" in result.output or "ok" in result.output


def test_tools_test_invalid_json():
    result = runner.invoke(app, ["tools", "test", "web_search", "not-json"])
    assert result.exit_code == 1 or "invalid" in result.output.lower()
