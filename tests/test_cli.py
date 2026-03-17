"""Tests for astromeshctl CLI."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from astromesh import __version__
from cli.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_status_daemon_running():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": __version__,
        "uptime_seconds": 123.45,
        "mode": "dev",
        "agents_loaded": 3,
        "pid": 12345,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "dev" in result.output


def test_status_daemon_not_running():
    with patch("cli.client.httpx.get", side_effect=Exception("Connection refused")):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not reachable" in result.output.lower() or "error" in result.output.lower()


def test_doctor_healthy():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "healthy": True,
        "checks": {
            "runtime": {"status": "ok", "message": "Runtime initialized"},
            "provider:ollama": {"status": "ok", "message": "Provider ollama health check"},
        },
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "healthy" in result.output.lower() or "ok" in result.output.lower()


def test_doctor_unhealthy():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "healthy": False,
        "checks": {
            "runtime": {"status": "unavailable", "message": "Runtime not initialized"},
        },
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "unhealthy" in result.output.lower() or "unavailable" in result.output.lower()


def test_agents_list():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "agents": [
            {"name": "support-agent", "version": "1.0.0", "namespace": "support"},
            {"name": "sales-agent", "version": "0.2.0", "namespace": "sales"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["agents", "list"])
    assert result.exit_code == 0
    assert "support-agent" in result.output
    assert "sales-agent" in result.output


def test_providers_list():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "providers": [
            {"name": "ollama", "endpoint": "http://localhost:11434", "models": ["llama3.1:8b"]},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    assert "ollama" in result.output


def test_config_validate_valid(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test
spec:
  identity:
    display_name: Test
""")
    (tmp_path / "runtime.yaml").write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000
""")

    result = runner.invoke(app, ["config", "validate", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_config_validate_invalid_yaml(tmp_path):
    (tmp_path / "runtime.yaml").write_text(": invalid: yaml: [")

    result = runner.invoke(app, ["config", "validate", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "error" in result.output.lower() or "failed" in result.output.lower()


def test_peers_list():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": "0.7.0",
        "uptime_seconds": 100.0,
        "mode": "dev",
        "agents_loaded": 0,
        "pid": 1234,
        "services": {},
        "peers": [
            {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
            {"name": "worker-1", "url": "http://worker:8000", "services": ["agents", "tools"]},
        ],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["peers", "list"])
    assert result.exit_code == 0
    assert "inference-1" in result.output
    assert "worker-1" in result.output


def test_services_list():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": "0.7.0",
        "uptime_seconds": 100.0,
        "mode": "dev",
        "agents_loaded": 0,
        "pid": 1234,
        "services": {
            "api": True,
            "agents": True,
            "inference": False,
            "memory": True,
            "tools": True,
            "channels": False,
            "rag": False,
            "observability": True,
        },
        "peers": [],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["services"])
    assert result.exit_code == 0
    assert "agents" in result.output
    assert "inference" in result.output
