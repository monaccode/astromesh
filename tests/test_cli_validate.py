"""Tests for astromeshctl validate command."""

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_validate_valid_project(tmp_path):
    agents_dir = tmp_path / "config" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "test.agent.yaml").write_text(
        "apiVersion: astromesh/v1\nkind: Agent\nmetadata:\n  name: test\nspec:\n"
        "  identity:\n    display_name: Test\n"
    )
    (tmp_path / "config" / "runtime.yaml").write_text(
        "apiVersion: astromesh/v1\nkind: RuntimeConfig\nmetadata:\n  name: default\n"
    )
    result = runner.invoke(app, ["validate", "--path", str(tmp_path / "config")])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_invalid_yaml(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "runtime.yaml").write_text(": bad: [yaml")
    result = runner.invoke(app, ["validate", "--path", str(config_dir)])
    assert "error" in result.output.lower() or "failed" in result.output.lower()


def test_validate_missing_kind(tmp_path):
    agents_dir = tmp_path / "config" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "bad.agent.yaml").write_text("apiVersion: astromesh/v1\nmetadata:\n  name: bad\n")
    result = runner.invoke(app, ["validate", "--path", str(tmp_path / "config")])
    assert "error" in result.output.lower() or "failed" in result.output.lower()


def test_validate_nonexistent_path(tmp_path):
    result = runner.invoke(app, ["validate", "--path", str(tmp_path / "nonexistent")])
    assert "error" in result.output.lower() or "does not exist" in result.output.lower()
