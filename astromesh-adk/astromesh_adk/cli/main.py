"""Astromesh ADK CLI."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="astromesh-adk", help="Astromesh Agent Development Kit CLI")
console = Console()


def _load_module(file_path: str):
    """Import a Python file as a module."""
    path = Path(file_path).resolve()
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    spec = importlib.util.spec_from_file_location("__adk_user_module__", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["__adk_user_module__"] = module
    spec.loader.exec_module(module)
    return module


def _discover_agents(module):
    """Find all AgentWrapper and Agent instances in a module."""
    from astromesh_adk.agent import AgentWrapper, Agent

    agents = []
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, AgentWrapper):
            agents.append(obj)
        elif isinstance(obj, type) and issubclass(obj, Agent) and obj is not Agent:
            agents.append(obj())
    return agents


def _parse_agent_ref(ref: str):
    """Parse 'file.py:agent_name' into (file_path, agent_name)."""
    if ":" in ref:
        file_path, agent_name = ref.rsplit(":", 1)
        return file_path, agent_name
    return ref, None


@app.command()
def list(file: str = typer.Argument(..., help="Python file with agent definitions")):
    """List all agents defined in a file."""
    module = _load_module(file)
    agents = _discover_agents(module)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Pattern", style="blue")
    table.add_column("Tools", style="yellow")

    for a in agents:
        tool_count = str(len(a.tools))
        table.add_row(a.name, a.model, a.pattern, tool_count)

    console.print(table)


@app.command()
def run(
    agent_ref: str = typer.Argument(..., help="agent file:name (e.g., agents.py:my_agent)"),
    query: str = typer.Argument(..., help="Query to send to the agent"),
    session: str = typer.Option("default", "--session", "-s", help="Session ID"),
):
    """Run an agent with a query."""
    file_path, agent_name = _parse_agent_ref(agent_ref)
    module = _load_module(file_path)
    agents = _discover_agents(module)

    target = None
    for a in agents:
        if agent_name is None or a.name == agent_name:
            target = a
            break

    if target is None:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        raise typer.Exit(1)

    async def _run():
        result = await target.run(query, session_id=session)
        console.print(f"\n[bold green]Answer:[/bold green] {result.answer}")
        if result.steps:
            console.print(f"\n[dim]Steps: {len(result.steps)} | Cost: ${result.cost:.4f} | Tokens: {result.tokens}[/dim]")

    asyncio.run(_run())


@app.command()
def chat(
    agent_ref: str = typer.Argument(..., help="agent file:name"),
    session: str = typer.Option("default", "--session", "-s", help="Session ID"),
):
    """Interactive chat with an agent."""
    file_path, agent_name = _parse_agent_ref(agent_ref)
    module = _load_module(file_path)
    agents = _discover_agents(module)

    target = None
    for a in agents:
        if agent_name is None or a.name == agent_name:
            target = a
            break

    if target is None:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Chat with {target.name}[/bold] (Ctrl+C to exit)\n")

    async def _chat():
        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if not user_input.strip():
                    continue
                result = await target.run(user_input, session_id=session)
                console.print(f"\n{result.answer}\n")
            except KeyboardInterrupt:
                console.print("\n[dim]Bye![/dim]")
                break

    asyncio.run(_chat())


@app.command()
def check(file: str = typer.Argument(..., help="Python file to validate")):
    """Validate agent definitions."""
    import os
    module = _load_module(file)
    agents = _discover_agents(module)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    from astromesh_adk.providers import parse_model_string, PROVIDER_REGISTRY

    for a in agents:
        issues = []

        # Check provider env vars
        provider_name, _ = parse_model_string(a.model)
        entry = PROVIDER_REGISTRY.get(provider_name)
        if entry and entry.get("env_var"):
            if not os.environ.get(entry["env_var"]):
                issues.append(f"Missing env var: {entry['env_var']}")

        # Check tools
        for t in a.tools:
            from astromesh_adk.tools import ToolDefinitionWrapper, Tool
            from astromesh_adk.mcp import MCPToolSet
            if isinstance(t, ToolDefinitionWrapper):
                pass  # OK
            elif isinstance(t, Tool):
                if not t.name:
                    issues.append("Tool class missing 'name'")
            elif isinstance(t, MCPToolSet):
                import shutil
                cmd = t.config.get("command")
                if cmd and not shutil.which(cmd):
                    issues.append(f"MCP command not found: {cmd}")

        status = "[green]v[/green]" if not issues else "[red]x[/red]"
        tool_count = len(a.tools)
        console.print(f"  {status} {a.name}: {provider_name} provider, {tool_count} tools")
        for issue in issues:
            console.print(f"    [yellow]! {issue}[/yellow]")


@app.command()
def dev(
    file: str = typer.Argument(..., help="Python file with agent definitions"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable hot reload"),
):
    """Start the development server."""
    console.print("[bold]Starting ADK dev server...[/bold]")
    console.print(f"  File: {file}")
    console.print(f"  Port: {port}")
    console.print(f"  Reload: {reload}")

    # Import here to avoid requiring FastAPI as a core dependency
    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError:
        console.print("[red]Dev server requires FastAPI and Uvicorn. Install with: pip install astromesh-adk[dev][/red]")
        raise typer.Exit(1)

    module = _load_module(file)
    agents = _discover_agents(module)

    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        raise typer.Exit(0)

    # Build a minimal FastAPI app
    dev_app = FastAPI(title="ADK Dev Server")

    @dev_app.get("/v1/health")
    def health():
        return {"status": "ok", "agents": [a.name for a in agents]}

    @dev_app.get("/v1/agents")
    def list_agents():
        return [{"name": a.name, "model": a.model, "description": a.description} for a in agents]

    @dev_app.post("/v1/agents/{agent_name}/run")
    async def run_agent(agent_name: str, body: dict):
        target = next((a for a in agents if a.name == agent_name), None)
        if not target:
            return {"error": f"Agent '{agent_name}' not found"}
        result = await target.run(
            body.get("query", ""),
            session_id=body.get("session_id", "default"),
            context=body.get("context"),
        )
        return {"answer": result.answer, "steps": result.steps}

    console.print(f"\n[bold green]Serving {len(agents)} agent(s) at http://localhost:{port}[/bold green]")
    for a in agents:
        console.print(f"  - {a.name} ({a.model})")

    uvicorn.run(dev_app, host="0.0.0.0", port=port, reload=reload)
