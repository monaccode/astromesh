"""astromeshctl ask — Copilot CLI interface."""

import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.markdown import Markdown
from rich.panel import Panel

from astromesh_cli.client import api_post_with_timeout
from astromesh_cli.output import console, print_error, print_json

COPILOT_AGENT = "astromesh-copilot"
MAX_CONTEXT_SIZE = 100 * 1024  # 100KB
ALLOWED_CONTEXT_PREFIXES = ("config", "docs")


def _validate_context_path(path: Path) -> bool:
    """Validate that a context file path is safe to read.

    Must be under ./config/ or ./docs/, must exist, and must be < 100KB.
    """
    try:
        resolved = path.resolve()
        cwd = Path.cwd().resolve()

        # Check that the path is under an allowed prefix
        relative = resolved.relative_to(cwd)
        parts = relative.parts
        if not parts or parts[0] not in ALLOWED_CONTEXT_PREFIXES:
            print_error(f"Context file must be under config/ or docs/. Got: {relative}")
            return False
    except (ValueError, OSError):
        print_error(f"Context file path is not within the project directory: {path}")
        return False

    if not path.exists():
        print_error(f"Context file does not exist: {path}")
        return False

    if not path.is_file():
        print_error(f"Context path is not a file: {path}")
        return False

    if path.stat().st_size > MAX_CONTEXT_SIZE:
        print_error(f"Context file too large (max 100KB): {path}")
        return False

    return True


def ask_command(
    query: str = typer.Argument(..., help="Question or request for the copilot"),
    context: Optional[str] = typer.Option(
        None, "--context", help="Path to a context file (must be under config/ or docs/)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run in dry-run mode (no side effects)"),
    session: Optional[str] = typer.Option(
        None, "--session", help="Session ID for multi-turn conversation"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Ask the Astromesh Copilot a question."""
    full_query = query
    context_content = None

    if context:
        context_path = Path(context)
        if not _validate_context_path(context_path):
            raise typer.Exit(code=1)
        context_content = context_path.read_text()
        full_query = f"{query}\n\n---\nContext from {context}:\n{context_content}"

    session_id = session or str(uuid.uuid4())

    metadata: dict = {}
    if context_content:
        metadata["context_file"] = context_content
    if dry_run:
        metadata["dry_run"] = True

    try:
        data = api_post_with_timeout(
            f"/v1/agents/{COPILOT_AGENT}/run",
            json={
                "query": full_query,
                "session_id": session_id,
                "metadata": metadata,
            },
            timeout=60.0,
        )
    except Exception as e:
        print_error(f"Failed to reach copilot: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    response_text = data.get("response", "")
    trace_id = data.get("trace_id", "N/A")

    console.print(
        Panel(
            Markdown(response_text),
            title="[cyan]Astromesh Copilot[/cyan]",
            subtitle=f"trace: {trace_id}",
            border_style="cyan",
        )
    )
