"""astromeshctl status command."""

import typer

from astromesh_cli.client import api_get
from astromesh_cli.output import print_error, print_json, print_status_table

app = typer.Typer()


@app.callback(invoke_without_command=True)
def status(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Show daemon status."""
    try:
        data = api_get("/v1/system/status")
        if json:
            print_json(data)
        else:
            print_status_table(data)
    except Exception:
        print_error("Daemon not reachable at configured URL.")
        raise typer.Exit(code=0)
