"""Orbit CLI — registers as astromeshctl plugin."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from astromesh_orbit.config import OrbitConfig
from astromesh_orbit.providers.gcp.provider import GCPProvider
from astromesh_orbit.terraform.runner import TerraformNotFoundError
from astromesh_orbit.wizard.interactive import run_wizard

console = Console()
orbit_app = typer.Typer(
    name="orbit", help="Cloud-native deployment for Astromesh.", no_args_is_help=True
)

PROVIDERS = {"gcp": GCPProvider}
ORBIT_DIR = Path(".orbit")
GENERATED_DIR = ORBIT_DIR / "generated"


def _load_config(config_path: str) -> OrbitConfig:
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Error:[/] {path} not found. Run 'astromeshctl orbit init' first.")
        raise typer.Exit(1)
    return OrbitConfig.from_yaml(path)


def _get_provider(config: OrbitConfig):
    name = config.spec.provider.name
    if name not in PROVIDERS:
        console.print(
            f"[red]Error:[/] Provider '{name}' not supported. Available: {list(PROVIDERS.keys())}"
        )
        raise typer.Exit(1)
    return PROVIDERS[name]()


@orbit_app.command()
def init(
    provider: str = typer.Option("gcp", help="Cloud provider"),
    preset: Optional[str] = typer.Option(None, help="Preset: starter or pro"),
):
    """Interactive setup — generates orbit.yaml."""
    run_wizard()


@orbit_app.command()
def plan(config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml")):
    """Preview infrastructure changes."""

    async def _plan():
        cfg = _load_config(config)
        prov = _get_provider(cfg)

        console.print("\n  [cyan bold]Orbit Deployment Plan[/]\n")

        # Validate
        console.print("  Validating...", end="")
        validation = await prov.validate(cfg)
        if not validation.ok:
            console.print(" [red]FAILED[/]\n")
            for c in validation.checks:
                icon = "[green]\u2713[/]" if c.passed else "[red]\u2717[/]"
                console.print(f"    {icon} {c.message}")
                if c.remediation:
                    console.print(f"      \u2192 {c.remediation}")
            raise typer.Exit(1)
        console.print(" [green]OK[/]")

        # Generate and plan
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        await prov.generate(cfg, GENERATED_DIR)
        try:
            from astromesh_orbit.terraform.runner import TerraformRunner

            runner = TerraformRunner()
            await runner.check_installed()
            from astromesh_orbit.terraform.backend import ensure_gcs_state_bucket

            await ensure_gcs_state_bucket(
                cfg.spec.provider.project, cfg.spec.provider.region, cfg.metadata.name
            )
            await runner.init(GENERATED_DIR)
            result = await runner.plan(GENERATED_DIR)
            console.print(f"\n  Resources to create: {len(result.resources_to_create)}")
            console.print(f"  Resources to update: {len(result.resources_to_update)}")
            console.print(f"  Resources to destroy: {len(result.resources_to_destroy)}")
            if result.estimated_monthly_cost:
                console.print(f"  Estimated cost: ~${result.estimated_monthly_cost}/month")
        except TerraformNotFoundError as e:
            console.print(f"\n  [red]{e}[/]")
            raise typer.Exit(1)

    asyncio.run(_plan())


@orbit_app.command()
def apply(
    config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip confirmation"),
):
    """Deploy infrastructure to the cloud."""

    async def _apply():
        cfg = _load_config(config)
        prov = _get_provider(cfg)
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

        console.print("\n  [cyan bold]Astromesh Orbit \u2014 Deploying[/]\n")

        try:
            result = await prov.provision(cfg, GENERATED_DIR)
        except RuntimeError as e:
            console.print(f"  [red]Error:[/] {e}")
            raise typer.Exit(1)

        console.print("\n  [green bold]\u2713 Deployment complete![/]\n")

        table = Table(title="Endpoints")
        table.add_column("Service", style="cyan")
        table.add_column("URL", style="green")
        for svc, url in result.endpoints.items():
            if url:
                table.add_row(svc, url)
        console.print(table)
        console.print(f"\n  Environment file: {result.env_file}\n")

    asyncio.run(_apply())


@orbit_app.command()
def status(config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml")):
    """Show deployment status."""

    async def _status():
        cfg = _load_config(config)
        prov = _get_provider(cfg)
        ds = await prov.status(cfg)

        table = Table(title="Deployment Status")
        table.add_column("Resource", style="cyan")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("URL", style="dim")
        for r in ds.resources:
            color = "green" if r.status == "running" else "red"
            table.add_row(r.name, r.resource_type, f"[{color}]{r.status}[/]", r.url or "\u2014")
        console.print(table)
        console.print(f"\n  State bucket: {ds.state_bucket}")

    asyncio.run(_status())


@orbit_app.command()
def destroy(
    config: str = typer.Option("orbit.yaml", help="Path to orbit.yaml"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip confirmation"),
):
    """Destroy all provisioned infrastructure."""

    async def _destroy():
        cfg = _load_config(config)
        prov = _get_provider(cfg)

        if not auto_approve:
            typer.confirm("This will destroy ALL infrastructure. Continue?", abort=True)

        console.print("\n  [yellow]Destroying infrastructure...[/]\n")
        await prov.destroy(cfg, GENERATED_DIR)
        console.print("  [green]\u2713 All resources destroyed.[/]\n")

    asyncio.run(_destroy())


@orbit_app.command()
def eject(output_dir: str = typer.Option("./orbit-terraform", help="Output directory")):
    """Export standalone Terraform files."""

    async def _eject():
        cfg = _load_config("orbit.yaml")
        prov = _get_provider(cfg)
        result = await prov.eject(cfg, Path(output_dir))
        console.print(f"\n  [green]\u2713[/] Terraform files exported to {result}/")
        console.print("  These are standalone \u2014 no Orbit dependency.\n")
        console.print("  Next steps:")
        console.print(f"    cd {output_dir}")
        console.print("    terraform plan")
        console.print("    terraform apply\n")

    asyncio.run(_eject())


def register(app: typer.Typer) -> None:
    """Plugin entry point — called by astromeshctl plugin discovery."""
    app.add_typer(orbit_app, name="orbit")
