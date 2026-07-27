"""astromeshctl run — Execute agents and workflows."""

import json
import uuid
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from astromesh_cli.client import api_post_with_timeout
from astromesh_cli.output import console, print_error, print_json


def _format_run_output(data: dict) -> tuple[str, str, list[dict]]:
    """Extrae (texto, subtítulo, filas by_model) de la respuesta de /run.

    Prefiere el contrato del core v0.36.0 (answer + usage{tokens_in, tokens_out,
    by_model}); cae a los campos legacy (response + tokens_used) si no está.
    """
    text = data.get("answer") or data.get("response", "")
    trace_id = data.get("trace_id", "N/A")
    usage = data.get("usage")
    if isinstance(usage, dict):
        tin = usage.get("tokens_in", 0)
        tout = usage.get("tokens_out", 0)
        tokens = tin + tout
        by_model = usage.get("by_model") or []
    else:
        tokens = data.get("tokens_used", "N/A")
        by_model = []
    rows = [m for m in by_model if isinstance(m, dict)]
    subtitle = f"trace: {trace_id} | tokens: {tokens}"
    return text, subtitle, rows


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

    text, subtitle, by_model_rows = _format_run_output(data)
    console.print(
        Panel(
            text,
            title=f"[cyan]{name}[/cyan]",
            subtitle=subtitle,
            border_style="blue",
        )
    )
    if by_model_rows:
        table = Table(title="Por modelo", show_header=True)
        for col in ("Provider", "Model", "Role", "Calls", "In", "Out", "Cost"):
            table.add_column(col, style="cyan" if col == "Provider" else None)
        for r in by_model_rows:
            cost = r.get("cost", 0.0) or 0.0
            table.add_row(
                r.get("provider", ""), r.get("model", ""), r.get("role", ""),
                str(r.get("calls", 0)), str(r.get("tokens_in", 0)), str(r.get("tokens_out", 0)),
                f"${cost:.4f}" if cost else "—",
            )
        console.print(table)


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
