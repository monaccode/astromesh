"""astromeshctl metrics/cost — Aggregated metrics and cost summary."""

from typing import Optional

import typer

from astromesh_cli.client import api_get
from astromesh_cli.output import print_cost_table, print_error, print_json, print_metrics_table


def metrics_command(
    agent: Optional[str] = typer.Option(None, "--agent", help="Filter by agent name"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Show aggregated runtime metrics."""
    try:
        data = api_get("/v1/metrics/")
    except Exception as e:
        print_error(f"Failed to fetch metrics: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    print_metrics_table(data)


def cost_command(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Show cost summary."""
    try:
        data = api_get("/v1/metrics/")
    except Exception as e:
        print_error(f"Failed to fetch metrics: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    print_cost_table(data)
