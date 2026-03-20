"""astromeshctl config commands."""

from pathlib import Path

import typer
import yaml

from astromesh_node.cli.output import console, print_error

app = typer.Typer(help="Configuration management.")


@app.command("validate")
def validate(
    path: str = typer.Option("./config", "--path", help="Config directory to validate"),
):
    """Validate configuration files without starting the daemon."""
    config_dir = Path(path)
    errors: list[str] = []
    files_checked = 0

    if not config_dir.exists():
        print_error(f"Config directory not found: {path}")
        raise typer.Exit(code=0)

    # Check runtime.yaml
    runtime_file = config_dir / "runtime.yaml"
    if runtime_file.exists():
        files_checked += 1
        try:
            data = yaml.safe_load(runtime_file.read_text())
            if not isinstance(data, dict):
                errors.append(f"{runtime_file}: not a valid YAML mapping")
        except yaml.YAMLError as e:
            errors.append(f"{runtime_file}: {e}")

    # Check providers.yaml
    providers_file = config_dir / "providers.yaml"
    if providers_file.exists():
        files_checked += 1
        try:
            yaml.safe_load(providers_file.read_text())
        except yaml.YAMLError as e:
            errors.append(f"{providers_file}: {e}")

    # Check channels.yaml
    channels_file = config_dir / "channels.yaml"
    if channels_file.exists():
        files_checked += 1
        try:
            yaml.safe_load(channels_file.read_text())
        except yaml.YAMLError as e:
            errors.append(f"{channels_file}: {e}")

    # Check agent files
    agents_dir = config_dir / "agents"
    if agents_dir.exists():
        for f in agents_dir.glob("*.agent.yaml"):
            files_checked += 1
            try:
                data = yaml.safe_load(f.read_text())
                if not isinstance(data, dict):
                    errors.append(f"{f}: not a valid YAML mapping")
                elif data.get("kind") != "Agent":
                    errors.append(f"{f}: kind must be 'Agent', got '{data.get('kind')}'")
            except yaml.YAMLError as e:
                errors.append(f"{f}: {e}")

    # Check RAG files
    rag_dir = config_dir / "rag"
    if rag_dir.exists():
        for f in rag_dir.glob("*.rag.yaml"):
            files_checked += 1
            try:
                yaml.safe_load(f.read_text())
            except yaml.YAMLError as e:
                errors.append(f"{f}: {e}")

    # Report
    if errors:
        console.print(f"\n[red]Validation failed[/red] ({len(errors)} error(s)):\n")
        for err in errors:
            console.print(f"  [red]x[/red] {err}")
    else:
        console.print(f"\n[green]Configuration valid[/green] ({files_checked} file(s) checked).")
