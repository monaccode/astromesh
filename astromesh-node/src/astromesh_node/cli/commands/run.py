"""astromeshctl run — Execute agents and workflows."""

import json
import uuid
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from astromesh_node.cli.client import api_post_with_timeout
from astromesh_node.cli.output import console, print_error, print_json


def run_command(
    name: str = typer.Argument(..., help="Agent or workflow name to run"),
    query: str = typer.Argument("", help="Query to send to the agent"),
    session: Optional[str] = typer.Option(
        None, "--session", help="Session ID (auto-generated if not set)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON response"),
    timeout: float = typer.Option(60.0, "--timeout", help="Request timeout in seconds"),
    workflow: bool = typer.Option(False, "--workflow", help="Run as workflow instead of agent"),
    input_data: Optional[str] = typer.Option(None, "--input", help="Workflow input data (JSON)"),
) -> None:
    """Execute an agent with a query or run a workflow."""
    if workflow:
        _run_workflow(name, query, input_data, json_output, timeout)
        return

    if not query:
        print_error("Query is required when running an agent.")
        raise typer.Exit(code=1)

    session_id = session or str(uuid.uuid4())

    try:
        data = api_post_with_timeout(
            f"/v1/agents/{name}/run",
            json={"query": query, "session_id": session_id},
            timeout=timeout,
        )
    except Exception as e:
        print_error(f"Failed to run agent '{name}': {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    response_text = data.get("response", "")
    trace_id = data.get("trace_id", "N/A")
    tokens = data.get("tokens_used", "N/A")

    console.print(
        Panel(
            response_text,
            title=f"[cyan]{name}[/cyan]",
            subtitle=f"trace: {trace_id} | tokens: {tokens}",
            border_style="blue",
        )
    )


def _run_workflow(
    name: str, query: str, input_data: str | None, json_output: bool, timeout: float
) -> None:
    """Execute a workflow via the API."""
    if input_data:
        try:
            trigger = json.loads(input_data)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON in --input: {e}")
            raise typer.Exit(code=1)
        payload = {"trigger": trigger, "query": query}
    else:
        payload = {"query": query}

    try:
        data = api_post_with_timeout(
            f"/v1/workflows/{name}/run",
            json=payload,
            timeout=timeout,
        )
    except Exception as e:
        print_error(f"Failed to run workflow '{name}': {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    status = data.get("status", "unknown")
    duration = data.get("duration_ms", 0)
    output = data.get("output", {})
    steps = data.get("steps", {})

    # Build step summary table
    table = Table(title="Steps", show_header=True)
    table.add_column("Step", style="cyan")
    table.add_column("Status")
    for step_name, step_info in steps.items():
        step_status = step_info.get("status", "unknown")
        style = "green" if step_status == "success" else "red"
        table.add_row(step_name, f"[{style}]{step_status}[/{style}]")

    answer = output.get("answer", str(output)) if isinstance(output, dict) else str(output)
    console.print(
        Panel(
            answer,
            title=f"[cyan]workflow:{name}[/cyan]",
            subtitle=f"status: {status} | {duration:.0f}ms",
            border_style="green" if status == "completed" else "red",
        )
    )
    if steps:
        console.print(table)
