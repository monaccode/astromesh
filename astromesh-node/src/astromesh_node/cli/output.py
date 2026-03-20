"""Minimal output utilities for Node CLI commands."""

from rich.console import Console

console = Console()
error_console = Console(stderr=True)


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    error_console.print(f"[red]Error:[/red] {message}")
