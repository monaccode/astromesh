"""astromeshctl tools — Tool discovery and testing commands."""

import json as json_mod

import typer

from astromesh_cli.client import api_get, api_post
from astromesh_cli.output import console, print_error, print_json, print_tool_list

app = typer.Typer(help="Discover and test tools.")


@app.command("list")
def tools_list_command(
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """List available built-in tools."""
    try:
        data = api_get("/v1/tools/builtin")
    except Exception as e:
        print_error(f"Failed to fetch tools: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    tools = data.get("tools", [])
    if not tools:
        console.print("[dim]No tools available.[/dim]")
        return

    print_tool_list(tools)


@app.command("test")
def tools_test_command(
    name: str = typer.Argument(..., help="Tool name to test"),
    args_json: str = typer.Argument("{}", help="Tool arguments as JSON string"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Test a tool with given arguments."""
    try:
        arguments = json_mod.loads(args_json)
    except json_mod.JSONDecodeError as e:
        print_error(f"Invalid JSON arguments: {e}")
        raise typer.Exit(code=1)

    try:
        data = api_post("/v1/tools/execute", json={"tool_name": name, "arguments": arguments})
    except Exception as e:
        print_error(f"Failed to execute tool: {e}")
        raise typer.Exit(code=1)

    if json_output:
        print_json(data)
        return

    status = data.get("status", "unknown")
    result = data.get("result", {})

    console.print(f"\n[bold]Tool:[/bold] {name}")
    console.print(
        f"[bold]Status:[/bold] [{'green' if status == 'ok' else 'red'}]{status}[/{'green' if status == 'ok' else 'red'}]"
    )
    console.print("[bold]Result:[/bold]")
    console.print_json(json_mod.dumps(result))
