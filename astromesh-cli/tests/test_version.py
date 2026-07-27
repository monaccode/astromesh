from typer.testing import CliRunner
from astromesh_cli.main import app

runner = CliRunner()


def test_version_reports_cli_and_core():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "cli" in result.stdout.lower()
    assert "core" in result.stdout.lower()
