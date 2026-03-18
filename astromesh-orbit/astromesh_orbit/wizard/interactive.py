"""Interactive wizard for orbit init."""

from __future__ import annotations

from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Prompt

from astromesh_orbit.wizard.defaults import PRESETS, build_orbit_yaml

console = Console()

GCP_REGIONS = [
    "us-central1",
    "us-east1",
    "us-west1",
    "europe-west1",
    "europe-west4",
    "asia-east1",
    "asia-southeast1",
    "southamerica-east1",
]


def run_wizard(output_path: Path = Path("orbit.yaml")) -> Path:
    """Run the interactive wizard. Returns path to the generated orbit.yaml."""
    console.print("\n  [cyan bold]🛰️  Astromesh Orbit — Cloud Deployment Setup[/]\n")

    # Provider
    provider = Prompt.ask(
        "  Cloud provider",
        choices=["gcp"],
        default="gcp",
    )

    # GCP-specific
    project = Prompt.ask("  GCP Project ID")
    region = Prompt.ask("  Region", choices=GCP_REGIONS, default="us-central1")

    # Name and environment
    name = Prompt.ask("  Deployment name", default="my-astromesh")
    environment = Prompt.ask(
        "  Environment", choices=["dev", "staging", "production"], default="dev"
    )

    # Preset
    console.print()
    for key, p in PRESETS.items():
        cost = p["estimated_cost"]
        ha = "HA" if p["database"]["high_availability"] else "no HA"
        cache = p["cache"]["memory_gb"]
        console.print(f"    [bold]{key}[/] (~${cost}/mo) — {ha}, {cache}GB cache")
    console.print()
    preset = Prompt.ask("  Preset", choices=list(PRESETS.keys()), default="starter")

    data = build_orbit_yaml(
        name=name,
        environment=environment,
        provider=provider,
        project=project,
        region=region,
        preset=preset,
    )

    output_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    console.print(f"\n  [green]✓[/] {output_path} written\n")

    # Append .orbit/ to .gitignore
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".orbit/" not in content:
            with gitignore.open("a") as f:
                f.write("\n# Astromesh Orbit working directory\n.orbit/\n")
            console.print("  [green]✓[/] .orbit/ added to .gitignore\n")
    else:
        gitignore.write_text("# Astromesh Orbit working directory\n.orbit/\n")
        console.print("  [green]✓[/] .gitignore created with .orbit/\n")

    console.print("  Next steps:")
    console.print("    astromeshctl orbit plan     # Preview infrastructure")
    console.print("    astromeshctl orbit apply    # Deploy to GCP\n")

    return output_path
