"""astromeshctl — Astromesh OS CLI management tool."""

import typer

from astromesh import __version__
from cli.commands import (
    agents,
    ask,
    config,
    dev,
    doctor,
    init,
    mesh,
    metrics,
    new,
    peers,
    providers,
    run,
    services,
    status,
    tools,
    traces,
    validate,
)

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
app.add_typer(new.app, name="new")
app.command("init")(init.init_command)
app.command("validate")(validate.validate_command)
app.command("run")(run.run_command)
app.command("dev")(dev.dev_command)
app.add_typer(traces.app, name="traces")
app.add_typer(tools.app, name="tools")
app.command("trace")(traces.trace_command)
app.command("metrics")(metrics.metrics_command)
app.command("cost")(metrics.cost_command)
app.command("ask")(ask.ask_command)


@app.command()
def version():
    """Show astromesh version."""
    typer.echo(f"astromesh {__version__}")


if __name__ == "__main__":
    app()
