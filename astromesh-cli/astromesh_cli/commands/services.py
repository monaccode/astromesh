"""astromeshctl services command."""

import typer
from rich.table import Table

from astromesh_cli.client import api_get
from astromesh_cli.output import console, print_error, print_json

app = typer.Typer()

STATUS_DISPLAY = {
    True: "[green]ENABLED[/green]",
    False: "[dim]DISABLED[/dim]",
}


@app.callback(invoke_without_command=True)
def services(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Show enabled services on this node."""
    try:
        data = api_get("/v1/system/status")
        if json:
            print_json({"services": data.get("services", {})})
            return

        svc = data.get("services", {})
        if not svc:
            console.print("[dim]No service information available.[/dim]")
            return

        table = Table(title="Node Services")
        table.add_column("Service", style="cyan")
        table.add_column("Status")

        for name, enabled in svc.items():
            table.add_row(name, STATUS_DISPLAY.get(enabled, str(enabled)))

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
