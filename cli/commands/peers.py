"""astromeshctl peers commands."""

import typer
from rich.table import Table

from cli.client import api_get
from cli.output import console, print_error, print_json

app = typer.Typer(help="Manage peer nodes.")


@app.command("list")
def list_peers(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List configured peer nodes."""
    try:
        data = api_get("/v1/system/status")
        if json:
            print_json({"peers": data.get("peers", [])})
            return

        peers = data.get("peers", [])
        if not peers:
            console.print("[dim]No peers configured.[/dim]")
            return

        table = Table(title="Peer Nodes")
        table.add_column("Name", style="cyan")
        table.add_column("URL", style="green")
        table.add_column("Services", style="dim")

        for peer in peers:
            services = ", ".join(peer.get("services", []))
            table.add_row(peer.get("name", ""), peer.get("url", ""), services)

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
