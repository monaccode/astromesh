import pytest
from typer.testing import CliRunner
from astromesh_adk.cli.main import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "astromesh-adk" in result.output.lower() or "agent" in result.output.lower()


def test_cli_list_help():
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "file" in result.output.lower()


def test_cli_run_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0


def test_cli_check_help():
    result = runner.invoke(app, ["check", "--help"])
    assert result.exit_code == 0


def test_cli_dev_help():
    result = runner.invoke(app, ["dev", "--help"])
    assert result.exit_code == 0
