"""Tests for astromeshctl traces, trace, metrics, and cost commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_traces_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "traces": [
            {
                "trace_id": "abc",
                "agent": "support-agent",
                "started_at": "2026-03-10T10:00:00",
                "duration_ms": 1200,
                "status": "ok",
            },
            {
                "trace_id": "def",
                "agent": "support-agent",
                "started_at": "2026-03-10T09:00:00",
                "duration_ms": 800,
                "status": "ok",
            },
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["traces", "list", "support-agent", "--last", "10"])
    assert result.exit_code == 0
    assert "abc" in result.output


def test_trace_detail():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "trace_id": "abc",
        "agent": "support-agent",
        "spans": [
            {
                "name": "agent.run",
                "duration_ms": 1200,
                "children": [
                    {"name": "model.complete", "duration_ms": 900, "children": []},
                    {"name": "tool.web_search", "duration_ms": 250, "children": []},
                ],
            },
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["trace", "abc"])
    assert result.exit_code == 0
    assert "agent.run" in result.output


def test_metrics():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "counters": {"agent.runs": 42, "tool.calls": 108},
        "histograms": {
            "agent.latency_ms": {"count": 42, "avg": 1100.5, "min": 200, "max": 5000}
        },
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["metrics"])
    assert result.exit_code == 0
    assert "agent.runs" in result.output or "42" in result.output


def test_cost():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "counters": {"cost.total_usd": 0},
        "histograms": {"agent.cost_usd": {"count": 10, "sum": 0.45, "avg": 0.045}},
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.get", return_value=mock_resp):
        result = runner.invoke(app, ["cost"])
    assert result.exit_code == 0
