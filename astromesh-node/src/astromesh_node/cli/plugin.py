"""Node CLI plugin — registers init/validate/config into astromeshctl."""

import typer

from astromesh_node.cli.commands import config, init, validate


def register(app: typer.Typer) -> None:
    """Plugin entry point — called by astromeshctl plugin discovery."""
    app.add_typer(config.app, name="config")
    app.command("init")(init.init_command)
    app.command("validate")(validate.validate_command)
