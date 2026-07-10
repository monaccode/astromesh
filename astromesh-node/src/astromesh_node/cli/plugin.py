"""Node CLI plugin — registers init/validate/config/centinela into astromeshctl."""

import typer

from astromesh_node.cli.commands import centinela, config, init, validate


def register(app: typer.Typer) -> None:
    """Plugin entry point — called by astromeshctl plugin discovery."""
    app.add_typer(config.app, name="config")
    app.add_typer(centinela.app, name="centinela")
    app.command("init")(init.init_command)
    app.command("validate")(validate.validate_command)
