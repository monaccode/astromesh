"""astromeshctl doctor command."""

import subprocess
import sys

import typer
from rich.table import Table

from astromesh_node.cli.client import api_get
from astromesh_node.cli.output import console, print_error, print_json

app = typer.Typer()

STATUS_ICONS = {
    "ok": "[green]OK[/green]",
    "degraded": "[yellow]DEGRADED[/yellow]",
    "error": "[red]ERROR[/red]",
    "unavailable": "[red]UNAVAILABLE[/red]",
}


def _check_stale_astromesh_package() -> str | None:
    """Return a warning string if the old 'astromesh' deb package is still installed."""
    if sys.platform != "linux":
        return None
    try:
        result = subprocess.run(
            ["dpkg", "-l", "astromesh"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "astromesh" in result.stdout:
            # Ensure it's the old package, not the new astromesh-node package
            if "astromesh-node" not in result.stdout:
                return (
                    "Stale 'astromesh' package detected. "
                    "Upgrade to astromesh-node: sudo dpkg -i astromesh-node-*.deb"
                )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # dpkg not available or timed out
    return None


@app.callback(invoke_without_command=True)
def doctor(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Run system health checks."""
    migration_warning = _check_stale_astromesh_package()
    if migration_warning:
        console.print(f"[yellow]WARNING:[/yellow] {migration_warning}\n")

    try:
        data = api_get("/v1/system/doctor")
        if json:
            print_json(data)
            return

        healthy = data["healthy"]
        header = "[green]System Healthy[/green]" if healthy else "[red]System Unhealthy[/red]"
        console.print(f"\n{header}\n")

        table = Table()
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        table.add_column("Message", style="dim")

        for name, check in data["checks"].items():
            status_display = STATUS_ICONS.get(check["status"], check["status"])
            table.add_row(name, status_display, check.get("message", ""))

        console.print(table)
    except Exception:
        print_error("Daemon not reachable at configured URL.")
        raise typer.Exit(code=0)
