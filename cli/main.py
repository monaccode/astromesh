"""astromeshctl — Astromesh OS CLI management tool."""

import typer

from astromesh import __version__
from cli.commands import agents, config, doctor, providers, status

app = typer.Typer(
    name="astromeshctl",
    help="Astromesh OS CLI management tool.",
    no_args_is_help=True,
)

app.add_typer(status.app, name="status")
app.add_typer(doctor.app, name="doctor")
app.add_typer(agents.app, name="agents")
app.add_typer(providers.app, name="providers")


@app.command()
def version():
    """Show astromesh version."""
    typer.echo(f"astromesh {__version__}")


if __name__ == "__main__":
    app()
