"""Rich output helpers for astromeshctl."""

import json

from rich.console import Console
from rich.table import Table

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
