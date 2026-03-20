"""astromeshctl traces/trace — Observability trace commands."""


import typer

from astromesh_node.cli.client import api_get, api_get_params
from astromesh_node.cli.output import console, print_error, print_json, print_trace_list, print_trace_tree

app = typer.Typer(help="View execution traces.")


@app.command("list")
def traces_list_command(
    agent: str = typer.Argument(..., help="Agent name to filter traces"),
    last: int = typer.Option(10, "--last", help="Number of recent traces to show"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """List recent traces for an agent."""
    try:
        data = api_get_params("/v1/traces/", params={"agent": agent, "limit": last})
    except Exception as e:
        print_error(f"Failed to fetch traces: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    traces = data.get("traces", [])
    if not traces:
        console.print("[dim]No traces found.[/dim]")
        return

    print_trace_list(traces)


def trace_command(
    trace_id: str = typer.Argument(..., help="Trace ID to inspect"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Show detailed trace with span tree."""
    try:
        data = api_get(f"/v1/traces/{trace_id}")
    except Exception as e:
        print_error(f"Failed to fetch trace: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    print_trace_tree(data)
