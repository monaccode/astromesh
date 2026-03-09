"""astromeshctl — Astromesh OS CLI management tool."""

import typer

from astromesh import __version__
from cli.commands import status

app = typer.Typer(
    name="astromeshctl",
    help="Astromesh OS CLI management tool.",
    no_args_is_help=True,
)

app.add_typer(status.app, name="status")


@app.command()
def version():
    """Show astromesh version."""
    typer.echo(f"astromesh {__version__}")


if __name__ == "__main__":
    app()
