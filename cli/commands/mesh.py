"""astromeshctl mesh commands."""

import typer
from rich.table import Table

from cli.client import api_get, api_post
from cli.output import console, print_error, print_json

app = typer.Typer(help="Mesh cluster management.")


@app.command("status")
def mesh_status(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Show mesh cluster summary."""
    try:
        data = api_get("/v1/mesh/state")
        if json:
            print_json(data)
            return

        nodes = data.get("nodes", [])
        leader_id = data.get("leader_id")
        leader_name = ""
        for n in nodes:
            if n.get("node_id") == leader_id:
                leader_name = n.get("name", leader_id)
                break

        console.print("[bold]Mesh Cluster[/bold]")
        console.print(f"  Nodes:   {len(nodes)}")
        console.print(f"  Leader:  {leader_name or 'none'}")
        console.print(f"  Version: {data.get('version', 0)}")

        alive = sum(1 for n in nodes if n.get("status") == "alive")
        suspect = sum(1 for n in nodes if n.get("status") == "suspect")
        dead = sum(1 for n in nodes if n.get("status") == "dead")
        console.print(f"  Alive:   {alive}  Suspect: {suspect}  Dead: {dead}")
    except Exception:
        print_error("Mesh not enabled or daemon not reachable.")
        raise typer.Exit(code=0)


@app.command("nodes")
def mesh_nodes(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List all nodes in the mesh."""
    try:
        data = api_get("/v1/mesh/state")
        if json:
            print_json(data)
            return

        nodes = data.get("nodes", [])
        leader_id = data.get("leader_id")

        if not nodes:
            console.print("[dim]No nodes in mesh.[/dim]")
            return

        table = Table(title="Mesh Nodes")
        table.add_column("Name", style="cyan")
        table.add_column("URL", style="green")
        table.add_column("Services", style="dim")
        table.add_column("Agents", style="dim")
        table.add_column("Load", style="yellow")
        table.add_column("Status")
        table.add_column("Leader")

        for node in nodes:
            services = ", ".join(node.get("services", []))
            agents = ", ".join(node.get("agents", []))
            load = node.get("load", {})
            load_str = f"CPU:{load.get('cpu_percent', 0):.0f}% Req:{load.get('active_requests', 0)}"
            status = node.get("status", "unknown")
            status_display = {
                "alive": "[green]alive[/green]",
                "suspect": "[yellow]suspect[/yellow]",
                "dead": "[red]dead[/red]",
            }.get(status, status)
            is_leader = "[bold green]YES[/bold green]" if node.get("node_id") == leader_id else ""

            table.add_row(
                node.get("name", ""),
                node.get("url", ""),
                services,
                agents,
                load_str,
                status_display,
                is_leader,
            )

        console.print(table)
    except Exception:
        print_error("Mesh not enabled or daemon not reachable.")
        raise typer.Exit(code=0)


@app.command("leave")
def mesh_leave():
    """Gracefully leave the mesh."""
    try:
        api_post("/v1/mesh/leave", json={"node_id": "self"})
        console.print("[green]Left mesh successfully.[/green]")
    except Exception:
        print_error("Failed to leave mesh.")
        raise typer.Exit(code=0)
