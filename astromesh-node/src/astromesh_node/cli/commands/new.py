"""astromeshctl new — Scaffold new agents, workflows, and tools."""

from pathlib import Path
from typing import Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from astromesh_node.cli.output import console, print_error

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "cli" / "templates"

app = typer.Typer(help="Scaffold new agents, workflows, and tools.")


def _get_jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), keep_trailing_newline=True)


def render_agent_template(
    name: str,
    provider: str = "ollama",
    model: str = "llama3.1:8b",
    orchestration_pattern: str = "react",
    tools: list[str] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    description: str = "",
) -> str:
    """Render an agent YAML template."""
    env = _get_jinja_env()
    template = env.get_template("agent.yaml.j2")
    display_name = name.replace("-", " ").replace("_", " ").title()
    return template.render(
        name=name,
        display_name=display_name,
        description=description or f"Agent {display_name}",
        provider=provider,
        model=model,
        orchestration_pattern=orchestration_pattern,
        tools=tools or [],
        temperature=temperature,
        max_tokens=max_tokens,
    )


def render_workflow_template(
    name: str,
    description: str = "",
) -> str:
    """Render a workflow YAML template."""
    env = _get_jinja_env()
    template = env.get_template("workflow.yaml.j2")
    return template.render(
        name=name,
        description=description or f"Workflow {name}",
    )


def render_tool_template(
    name: str,
    description: str = "A custom tool",
) -> str:
    """Render a tool Python file template."""
    env = _get_jinja_env()
    template = env.get_template("tool.py.j2")
    # Convert snake_case name to PascalCase class name
    class_name = "".join(part.capitalize() for part in name.split("_"))
    return template.render(
        name=name,
        description=description,
        class_name=class_name,
    )


@app.command("agent")
def new_agent(
    name: str = typer.Argument(..., help="Agent name (e.g., my-bot)"),
    provider: str = typer.Option("ollama", "--provider", help="LLM provider"),
    model: str = typer.Option("llama3.1:8b", "--model", help="Model name"),
    orchestration: str = typer.Option("react", "--orchestration", help="Orchestration pattern"),
    tools: Optional[list[str]] = typer.Option(None, "--tools", help="Tools to include"),
    output_dir: str = typer.Option("./config/agents", "--output-dir", help="Output directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
) -> None:
    """Scaffold a new agent YAML configuration."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{name}.agent.yaml"

    if dest.exists() and not force:
        print_error(f"File already exists: {dest}. Use --force to overwrite.")
        raise typer.Exit(code=0)

    content = render_agent_template(
        name=name,
        provider=provider,
        model=model,
        orchestration_pattern=orchestration,
        tools=tools,
    )
    dest.write_text(content)
    console.print(
        Panel(
            f"[green]Created agent:[/green] {dest}\n\n"
            f"  Provider: {provider}\n"
            f"  Model: {model}\n"
            f"  Pattern: {orchestration}",
            title="astromesh new agent",
            border_style="green",
        )
    )


@app.command("workflow")
def new_workflow(
    name: str = typer.Argument(..., help="Workflow name"),
    output_dir: str = typer.Option("./config/workflows", "--output-dir", help="Output directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
) -> None:
    """Scaffold a new workflow YAML configuration."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{name}.workflow.yaml"

    if dest.exists() and not force:
        print_error(f"File already exists: {dest}. Use --force to overwrite.")
        raise typer.Exit(code=0)

    content = render_workflow_template(name=name)
    dest.write_text(content)
    console.print(
        Panel(
            f"[green]Created workflow:[/green] {dest}",
            title="astromesh new workflow",
            border_style="green",
        )
    )


@app.command("tool")
def new_tool(
    name: str = typer.Argument(..., help="Tool name (snake_case)"),
    description: str = typer.Option("A custom tool", "--description", help="Tool description"),
    output_dir: str = typer.Option(".", "--output-dir", help="Output directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
) -> None:
    """Scaffold a new custom tool Python file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{name}.py"

    if dest.exists() and not force:
        print_error(f"File already exists: {dest}. Use --force to overwrite.")
        raise typer.Exit(code=0)

    content = render_tool_template(name=name, description=description)
    dest.write_text(content)
    console.print(
        Panel(
            f"[green]Created tool:[/green] {dest}\n\n"
            f"  Class: {name.replace('_', ' ').title().replace(' ', '')}Tool\n"
            f"  Description: {description}",
            title="astromesh new tool",
            border_style="green",
        )
    )
