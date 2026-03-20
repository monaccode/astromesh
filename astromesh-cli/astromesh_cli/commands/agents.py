"""astromeshctl agents commands."""

import typer
from rich.table import Table

from astromesh_cli.client import api_get
from astromesh_cli.output import console, print_error, print_json

app = typer.Typer(help="Manage agents.")


@app.command("list")
def list_agents(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List loaded agents."""
    try:
        data = api_get("/v1/agents")
        if json:
            print_json(data)
            return

        agents = data.get("agents", [])
        if not agents:
            console.print("[dim]No agents loaded.[/dim]")
            return

        table = Table(title="Loaded Agents")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Namespace", style="dim")

        for agent in agents:
            table.add_row(
                agent.get("name", ""),
                agent.get("version", ""),
                agent.get("namespace", ""),
            )

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
