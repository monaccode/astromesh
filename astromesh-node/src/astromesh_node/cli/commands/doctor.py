"""astromeshctl doctor command."""

import typer
from rich.table import Table

from astromesh_node.cli.client import api_get
from astromesh_node.cli.output import console, print_error, print_json

app = typer.Typer()

STATUS_ICONS = {
    "ok": "[green]OK[/green]",
    "degraded": "[yellow]DEGRADED[/yellow]",
    "error": "[red]ERROR[/red]",
    "unavailable": "[red]UNAVAILABLE[/red]",
}


@app.callback(invoke_without_command=True)
def doctor(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Run system health checks."""
    try:
        data = api_get("/v1/system/doctor")
        if json:
            print_json(data)
            return

        healthy = data["healthy"]
        header = "[green]System Healthy[/green]" if healthy else "[red]System Unhealthy[/red]"
        console.print(f"\n{header}\n")

        table = Table()
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        table.add_column("Message", style="dim")

        for name, check in data["checks"].items():
            status_display = STATUS_ICONS.get(check["status"], check["status"])
            table.add_row(name, status_display, check.get("message", ""))

        console.print(table)
    except Exception:
        print_error("Daemon not reachable at configured URL.")
        raise typer.Exit(code=0)
