"""astromeshctl providers commands."""

import typer
from rich.table import Table

from astromesh_node.cli.client import api_get
from astromesh_node.cli.output import console, print_error, print_json

app = typer.Typer(help="Manage model providers.")


@app.command("list")
def list_providers(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List configured providers."""
    try:
        data = api_get("/v1/providers")
        if json:
            print_json(data)
            return

        providers = data.get("providers", [])
        if not providers:
            console.print("[dim]No providers configured.[/dim]")
            return

        table = Table(title="Model Providers")
        table.add_column("Name", style="cyan")
        table.add_column("Endpoint", style="green")
        table.add_column("Models", style="dim")

        for p in providers:
            models = ", ".join(p.get("models", []))
            table.add_row(p.get("name", ""), p.get("endpoint", ""), models)

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
