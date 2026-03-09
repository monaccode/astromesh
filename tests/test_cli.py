"""Tests for astromeshctl CLI."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.5.0" in result.output


def test_status_daemon_running():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": "0.5.0",
        "uptime_seconds": 123.45,
        "mode": "dev",
        "agents_loaded": 3,
        "pid": 12345,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "0.5.0" in result.output
    assert "dev" in result.output


def test_status_daemon_not_running():
    with patch("cli.client.httpx.get", side_effect=Exception("Connection refused")):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not reachable" in result.output.lower() or "error" in result.output.lower()
