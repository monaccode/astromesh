"""Rich output helpers for astromeshctl."""

import json

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()
error_console = Console(stderr=True)


def print_status_table(data: dict) -> None:
    table = Table(title="Astromesh Daemon Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version", data["version"])
    table.add_row("PID", str(data.get("pid", "N/A")))
    table.add_row("Mode", data["mode"])
    table.add_row("Uptime", f"{data['uptime_seconds']:.1f}s")
    table.add_row("Agents Loaded", str(data["agents_loaded"]))

    console.print(table)


def print_error(message: str) -> None:
    error_console.print(f"[red]Error:[/red] {message}")


def print_json(data: dict) -> None:
    console.print_json(json.dumps(data))


def print_trace_list(traces: list[dict]) -> None:
    """Render a table of traces."""
    table = Table(title="Traces")
    table.add_column("Trace ID", style="cyan", width=12)
    table.add_column("Agent", style="green")
    table.add_column("Started At")
    table.add_column("Duration", justify="right")
    table.add_column("Status", style="bold")

    for t in traces:
        trace_id = t.get("trace_id", "")[:8]
        agent = t.get("agent", "")
        started = t.get("started_at", "")
        duration = f"{t.get('duration_ms', 0)}ms"
        status = t.get("status", "")
        status_style = "green" if status == "ok" else "red"
        table.add_row(
            trace_id, agent, started, duration, f"[{status_style}]{status}[/{status_style}]"
        )

    console.print(table)


def _add_spans_to_tree(tree: Tree, spans: list[dict]) -> None:
    """Recursively add spans to a Rich tree."""
    for span in spans:
        name = span.get("name", "unknown")
        duration = span.get("duration_ms", 0)
        branch = tree.add(f"{name} ({duration}ms)")
        children = span.get("children", [])
        if children:
            _add_spans_to_tree(branch, children)


def print_trace_tree(trace: dict) -> None:
    """Render a trace as a span tree."""
    trace_id = trace.get("trace_id", "unknown")
    agent = trace.get("agent", "unknown")
    tree = Tree(f"[bold cyan]Trace {trace_id}[/bold cyan] (agent: {agent})")

    spans = trace.get("spans", [])
    _add_spans_to_tree(tree, spans)

    console.print(tree)


def print_metrics_table(data: dict) -> None:
    """Render metrics as tables for counters and histograms."""
    counters = data.get("counters", {})
    histograms = data.get("histograms", {})

    if counters:
        table = Table(title="Counters")
        table.add_column("Name", style="cyan")
        table.add_column("Value", justify="right", style="green")
        for name, value in counters.items():
            table.add_row(name, str(value))
        console.print(table)

    if histograms:
        table = Table(title="Histograms")
        table.add_column("Name", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Avg", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")
        for name, stats in histograms.items():
            table.add_row(
                name,
                str(stats.get("count", 0)),
                f"{stats.get('avg', 0):.2f}",
                str(stats.get("min", 0)),
                str(stats.get("max", 0)),
            )
        console.print(table)

    if not counters and not histograms:
        console.print("[dim]No metrics data available.[/dim]")


def print_cost_table(data: dict) -> None:
    """Render cost-focused metrics table."""
    histograms = data.get("histograms", {})
    counters = data.get("counters", {})

    table = Table(title="Cost Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")

    # Show cost counters
    for name, value in counters.items():
        if "cost" in name.lower():
            table.add_row(name, f"${value:.4f}" if isinstance(value, float) else str(value))

    # Show cost histograms
    for name, stats in histograms.items():
        if "cost" in name.lower():
            table.add_row(f"{name} (count)", str(stats.get("count", 0)))
            table.add_row(f"{name} (total)", f"${stats.get('sum', 0):.4f}")
            table.add_row(f"{name} (avg)", f"${stats.get('avg', 0):.4f}")

    console.print(table)


def print_tool_list(tools: list[dict]) -> None:
    """Render a table of available tools."""
    table = Table(title="Available Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("Parameters", style="dim")

    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "")
        params = tool.get("parameters", {})
        param_names = ", ".join(params.keys()) if isinstance(params, dict) else ""
        table.add_row(name, desc, param_names)

    console.print(table)
