"""validate y config validate: el exit code tiene que servir para cortar un pipeline de CI."""

import typer
from typer.testing import CliRunner

from astromesh_node.cli.commands import config as config_cmd
from astromesh_node.cli.commands.validate import validate_command

runner = CliRunner()


def _validate_app() -> typer.Typer:
    app = typer.Typer()
    app.command("validate")(validate_command)
    app.command("noop")(lambda: None)  # fuerza modo multi-comando
    return app


def _agent(path, kind="Agent"):
    (path / "agents").mkdir(exist_ok=True)
    (path / "agents" / "a.agent.yaml").write_text(
        f"apiVersion: astromesh/v1\nkind: {kind}\nmetadata: {{name: a}}\nspec: {{}}\n"
    )


def test_validate_exits_1_on_errors(tmp_path):
    (tmp_path / "runtime.yaml").write_text("spec: [sin cerrar")
    result = runner.invoke(_validate_app(), ["validate", "--path", str(tmp_path)])
    assert result.exit_code == 1, result.output


def test_validate_exits_0_when_clean(tmp_path):
    (tmp_path / "runtime.yaml").write_text(
        "apiVersion: astromesh/v1\nkind: RuntimeConfig\nmetadata: {name: default}\nspec: {}\n"
    )
    result = runner.invoke(_validate_app(), ["validate", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_config_validate_exits_1_on_errors(tmp_path):
    _agent(tmp_path, kind="Workflow")
    result = runner.invoke(config_cmd.app, ["--path", str(tmp_path)])
    assert result.exit_code == 1, result.output


def test_config_validate_exits_1_when_dir_missing(tmp_path):
    result = runner.invoke(config_cmd.app, ["--path", str(tmp_path / "nope")])
    assert result.exit_code == 1, result.output


def test_config_validate_exits_0_when_clean(tmp_path):
    _agent(tmp_path)
    result = runner.invoke(config_cmd.app, ["--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
