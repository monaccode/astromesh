"""Tests for astromeshctl mesh commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()

MESH_STATE = {
    "leader_id": "node-1",
    "version": 5,
    "nodes": [
        {
            "node_id": "node-1",
            "name": "gateway",
            "url": "http://gw:8000",
            "services": ["api", "agents"],
            "agents": ["support-agent"],
            "status": "alive",
            "load": {"cpu_percent": 42.0, "active_requests": 3},
        },
        {
            "node_id": "node-2",
            "name": "worker",
            "url": "http://worker:8000",
            "services": ["inference"],
            "agents": [],
            "status": "alive",
            "load": {"cpu_percent": 78.0, "active_requests": 7},
        },
    ],
}


def test_mesh_status():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MESH_STATE
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "status"])
    assert result.exit_code == 0
    assert "Nodes:   2" in result.output
    assert "gateway" in result.output


def test_mesh_nodes():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MESH_STATE
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "nodes"])
    assert result.exit_code == 0
    assert "gateway" in result.output
    assert "alive" in result.output


def test_mesh_leave():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "leave"])
    assert result.exit_code == 0
    assert "Left mesh successfully" in result.output


def test_mesh_status_not_enabled():
    with patch("cli.client.httpx.get", side_effect=Exception("Connection refused")):
        result = runner.invoke(app, ["mesh", "status"])
    assert result.exit_code == 0
    assert "not enabled" in result.output.lower() or "error" in result.output.lower()
