"""astromeshctl validate — Validate all project YAML configurations."""

from pathlib import Path

import typer
import yaml
from rich.table import Table

from astromesh_node.cli.output import console

# Expected 'kind' values for file name patterns
KIND_EXPECTATIONS: dict[str, str] = {
    ".agent.yaml": "Agent",
    ".workflow.yaml": "Workflow",
    "providers.yaml": "ProviderConfig",
    "runtime.yaml": "RuntimeConfig",
    "channels.yaml": "ChannelConfig",
}


def _expected_kind(filename: str) -> str | None:
    """Return the expected 'kind' value based on the file name, or None if unknown."""
    for suffix, kind in KIND_EXPECTATIONS.items():
        if filename.endswith(suffix):
            return kind
    return None


def validate_yaml_files(config_path: Path) -> list[dict]:
    """Validate all YAML files under the given config path.

    Returns a list of dicts with keys: file, status, message.
    """
    results: list[dict] = []

    if not config_path.exists():
        results.append(
            {"file": str(config_path), "status": "error", "message": "Path does not exist"}
        )
        return results

    yaml_files = list(config_path.rglob("*.yaml")) + list(config_path.rglob("*.yml"))
    if not yaml_files:
        results.append(
            {"file": str(config_path), "status": "warning", "message": "No YAML files found"}
        )
        return results

    for filepath in sorted(yaml_files):
        try:
            content = filepath.read_text()
            data = yaml.safe_load(content)

            if not isinstance(data, dict):
                results.append(
                    {
                        "file": str(filepath),
                        "status": "error",
                        "message": "Not a valid YAML mapping",
                    }
                )
                continue

            errors: list[str] = []

            # Check apiVersion
            if "apiVersion" not in data:
                errors.append("Missing 'apiVersion'")

            # Check kind
            if "kind" not in data:
                errors.append("Missing 'kind'")
            else:
                expected = _expected_kind(filepath.name)
                if expected and data["kind"] != expected:
                    errors.append(f"Expected kind '{expected}', got '{data['kind']}'")

            # Check metadata.name
            metadata = data.get("metadata", {})
            if not isinstance(metadata, dict) or "name" not in metadata:
                errors.append("Missing 'metadata.name'")

            if errors:
                results.append(
                    {
                        "file": str(filepath),
                        "status": "error",
                        "message": "; ".join(errors),
                    }
                )
            else:
                results.append({"file": str(filepath), "status": "valid", "message": "OK"})

        except yaml.YAMLError as e:
            results.append(
                {"file": str(filepath), "status": "error", "message": f"YAML parse error: {e}"}
            )

    return results


def validate_command(
    path: str = typer.Option("./config", "--path", help="Path to config directory"),
) -> None:
    """Validate all project YAML configurations."""
    config_path = Path(path)
    results = validate_yaml_files(config_path)

    table = Table(title="Configuration Validation")
    table.add_column("File", style="cyan", max_width=60)
    table.add_column("Status", style="bold")
    table.add_column("Message")

    error_count = 0
    valid_count = 0

    for r in results:
        status_style = "green" if r["status"] == "valid" else "red"
        table.add_row(
            r["file"],
            f"[{status_style}]{r['status']}[/{status_style}]",
            r["message"],
        )
        if r["status"] == "error":
            error_count += 1
        elif r["status"] == "valid":
            valid_count += 1

    console.print(table)

    if error_count > 0:
        console.print(
            f"\n[red]Validation failed:[/red] {error_count} error(s), {valid_count} valid"
        )
    else:
        console.print(f"\n[green]All files valid:[/green] {valid_count} file(s) checked")
