"""astromeshctl — Astromesh OS CLI management tool."""

import typer

from astromesh import __version__
from cli.commands import agents, config, doctor, init, mesh, peers, providers, services, status

app = typer.Typer(
    name="astromeshctl",
    help="Astromesh OS CLI management tool.",
    no_args_is_help=True,
)

app.add_typer(status.app, name="status")
app.add_typer(doctor.app, name="doctor")
app.add_typer(agents.app, name="agents")
app.add_typer(providers.app, name="providers")
app.add_typer(config.app, name="config")
app.add_typer(mesh.app, name="mesh")
app.add_typer(peers.app, name="peers")
app.add_typer(services.app, name="services")
app.command("init")(init.init_command)


@app.command()
def version():
    """Show astromesh version."""
    typer.echo(f"astromesh {__version__}")


if __name__ == "__main__":
    app()
