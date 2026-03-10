"""Tests for astromeshctl ask (copilot) command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_ask_sends_query_to_copilot():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": "To create a new agent, run: astromesh new agent my-bot",
        "trace_id": "copilot-123",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["ask", "How do I create a new agent?"])
    assert result.exit_code == 0
    assert "astromesh new agent" in result.output


def test_ask_with_context_file(tmp_path, monkeypatch):
    # Create a config subdir so the path validation passes
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "test.agent.yaml"
    config_file.write_text("apiVersion: astromesh/v1\nkind: Agent\n")

    # Monkeypatch cwd so the validation sees config/ as allowed
    monkeypatch.chdir(tmp_path)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "The agent config looks valid.", "trace_id": "x"}
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(
            app, ["ask", "Review this config", "--context", str(config_file)]
        )
    assert result.exit_code == 0


def test_ask_dry_run():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": "Dry run: would create agent",
        "trace_id": "x",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("cli.client.httpx.post", return_value=mock_resp):
        result = runner.invoke(app, ["ask", "Create an agent for me", "--dry-run"])
    assert result.exit_code == 0


def test_ask_rejects_context_outside_allowed_dirs(tmp_path, monkeypatch):
    # Create a file outside config/ and docs/
    bad_file = tmp_path / "secrets.txt"
    bad_file.write_text("super secret")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["ask", "Read this", "--context", str(bad_file)]
    )
    assert result.exit_code == 1 or "error" in result.output.lower()
