"""astromeshctl run — Execute agents and workflows."""

import uuid
from typing import Optional

import typer
from rich.panel import Panel

from cli.client import api_post_with_timeout
from cli.output import console, print_error, print_json


def run_command(
    name: str = typer.Argument(..., help="Agent name to run"),
    query: str = typer.Argument("", help="Query to send to the agent"),
    session: Optional[str] = typer.Option(None, "--session", help="Session ID (auto-generated if not set)"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON response"),
    timeout: float = typer.Option(60.0, "--timeout", help="Request timeout in seconds"),
    workflow: bool = typer.Option(False, "--workflow", help="Run as workflow instead of agent"),
    input_data: Optional[str] = typer.Option(None, "--input", help="Workflow input data (JSON)"),
) -> None:
    """Execute an agent with a query or run a workflow."""
    if workflow:
        console.print(
            "[yellow]Workflow execution is not yet implemented (Sub-project 4).[/yellow]"
        )
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
