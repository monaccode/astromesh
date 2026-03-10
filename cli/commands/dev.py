"""astromeshctl dev — Hot-reload development server."""

import typer
from rich.panel import Panel

from cli.output import console


def _launch_uvicorn(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = True,
    reload_dirs: list[str] | None = None,
) -> None:
    """Launch uvicorn with the given configuration."""
    import uvicorn

    uvicorn.run(
        "astromesh.api.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=reload_dirs or ["astromesh", "config"],
    )


def dev_command(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", help="Bind port"),
    config: str = typer.Option("./config", "--config", help="Config directory"),
    no_open: bool = typer.Option(False, "--no-open", help="Skip opening browser"),
) -> None:
    """Start the Astromesh dev server with hot-reload."""
    banner = (
        f"[bold cyan]Astromesh Dev Server[/bold cyan]\n\n"
        f"  Host:   {host}\n"
        f"  Port:   {port}\n"
        f"  Config: {config}\n"
        f"  Reload: enabled"
    )
    console.print(Panel(banner, title="astromesh dev", border_style="cyan"))

    _launch_uvicorn(host=host, port=port, reload=True, reload_dirs=["astromesh", "config"])
