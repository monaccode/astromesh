"""astromeshctl init — Interactive setup wizard."""

import os
import shutil
import socket
from pathlib import Path

import httpx
import typer
import yaml
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from astromesh import __version__
from astromesh_node.cli.output import console, print_error

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
PROFILES_DIR = PROJECT_ROOT / "config" / "profiles"
AGENTS_SRC_DIR = PROJECT_ROOT / "config" / "agents"

ROLES = {
    "full": {
        "services": "All (API, agents, inference, memory, tools, channels, RAG)",
        "use_case": "Single-node or development",
    },
    "gateway": {
        "services": "API, channels, observability",
        "use_case": "Edge / request routing",
    },
    "worker": {
        "services": "Agents, memory, tools, RAG, observability",
        "use_case": "Agent execution backend",
    },
    "inference": {
        "services": "Inference, observability",
        "use_case": "Dedicated model serving",
    },
}

PROVIDER_CHOICES = ["ollama", "openai", "anthropic", "skip"]


def _detect_config_dir(dev: bool) -> tuple[Path, str]:
    """Detect whether to use system or dev config directory.

    Returns (config_dir, mode) where mode is 'system' or 'dev'.
    """
    if dev:
        return Path("./config"), "dev"
    if os.geteuid() == 0 if hasattr(os, "geteuid") else False:
        return Path("/etc/astromesh"), "system"
    return Path("./config"), "dev"


def _show_welcome(mode: str) -> None:
    """Step 1: Welcome banner with version and detected mode."""
    banner = (
        f"[bold cyan]Astromesh OS[/bold cyan] v{__version__}\n"
        f"Interactive Setup Wizard\n\n"
        f"Mode: [bold]{'System (/etc/astromesh/)' if mode == 'system' else 'Dev (./config/)'}[/bold]"
    )
    console.print(Panel(banner, title="astromeshctl init", border_style="cyan"))


def _check_existing_config(config_dir: Path) -> bool:
    """Check for existing runtime.yaml; return True if wizard should proceed."""
    runtime_file = config_dir / "runtime.yaml"
    if runtime_file.exists():
        console.print(
            f"\n[yellow]Existing configuration found:[/yellow] {runtime_file}"
        )
        if not Confirm.ask("Reconfigure? This will overwrite existing files", default=False):
            console.print("[dim]Aborted.[/dim]")
            return False
    return True


def _select_role(role: str | None, non_interactive: bool) -> str:
    """Step 2: Select node role."""
    console.print("\n[bold]Step 1:[/bold] Select Node Role\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Role", style="cyan", width=12)
    table.add_column("Services", width=50)
    table.add_column("Recommended Use", width=30)

    for name, info in ROLES.items():
        table.add_row(name, info["services"], info["use_case"])

    console.print(table)

    if role and role in ROLES:
        console.print(f"\n  Using provided role: [bold]{role}[/bold]")
        return role

    if non_interactive:
        console.print("\n  Using default role: [bold]full[/bold]")
        return "full"

    chosen = Prompt.ask(
        "\nSelect role",
        choices=list(ROLES.keys()),
        default="full",
    )
    return chosen


def _configure_provider(
    config_dir: Path, non_interactive: bool
) -> dict | None:
    """Step 3: Configure primary provider. Returns provider config dict or None."""
    console.print("\n[bold]Step 2:[/bold] Configure Primary Provider\n")

    if non_interactive:
        console.print("  Using default provider: [bold]ollama[/bold] (no connectivity check)")
        return _build_provider_config("ollama")

    choice = Prompt.ask(
        "Select provider",
        choices=PROVIDER_CHOICES,
        default="ollama",
    )

    if choice == "skip":
        console.print("  [dim]Skipping provider configuration.[/dim]")
        return None

    if choice == "ollama":
        console.print("  Checking Ollama connectivity... ", end="")
        try:
            resp = httpx.get("http://localhost:11434/api/version", timeout=2.0)
            resp.raise_for_status()
            version_info = resp.json().get("version", "unknown")
            console.print(f"[green]connected[/green] (v{version_info})")
        except Exception:
            console.print("[yellow]not reachable[/yellow]")
            console.print("  [dim]Ollama not running — config will be written anyway.[/dim]")
        return _build_provider_config("ollama")

    if choice in ("openai", "anthropic"):
        env_var = "OPENAI_API_KEY" if choice == "openai" else "ANTHROPIC_API_KEY"
        existing = os.environ.get(env_var)
        if existing:
            console.print(f"  [green]{env_var} already set in environment.[/green]")
            api_key = existing
        else:
            api_key = Prompt.ask(f"  Enter {env_var}", password=True)
        return _build_provider_config(choice, api_key=api_key, env_var=env_var)

    return None


def _build_provider_config(
    provider: str, api_key: str | None = None, env_var: str | None = None
) -> dict:
    """Build a providers.yaml-compatible dict for the chosen provider."""
    provider_spec: dict = {"type": provider}

    if provider == "ollama":
        provider_spec["endpoint"] = "http://localhost:11434"
        provider_spec["models"] = ["llama3.1:8b"]
        provider_spec["health_check_interval"] = 30
    elif provider == "openai":
        provider_spec["type"] = "openai_compat"
        provider_spec["endpoint"] = "https://api.openai.com/v1"
        provider_spec["api_key_env"] = "OPENAI_API_KEY"
        provider_spec["models"] = ["gpt-4o", "gpt-4o-mini"]
    elif provider == "anthropic":
        provider_spec["api_key_env"] = "ANTHROPIC_API_KEY"
        provider_spec["models"] = ["claude-sonnet-4-20250514"]

    config: dict = {
        "apiVersion": "astromesh/v1",
        "kind": "ProviderConfig",
        "metadata": {"name": "default-providers"},
        "spec": {
            "providers": {provider: provider_spec},
            "routing": {
                "default_strategy": "cost_optimized",
                "fallback_enabled": True,
                "circuit_breaker": {
                    "failure_threshold": 3,
                    "recovery_timeout": 60,
                },
            },
        },
    }

    return {
        "config": config,
        "api_key": api_key,
        "env_var": env_var,
    }


def _configure_mesh(
    role: str, non_interactive: bool
) -> dict | None:
    """Step 4: Mesh configuration. Returns mesh config dict or None."""
    if role == "full":
        return None

    console.print("\n[bold]Step 3:[/bold] Mesh Configuration\n")

    if non_interactive:
        console.print("  [dim]Skipping mesh configuration (non-interactive).[/dim]")
        return None

    if not Confirm.ask("Join a mesh cluster?", default=False):
        return None

    default_name = socket.gethostname()
    node_name = Prompt.ask("  Node name", default=default_name)
    seeds_raw = Prompt.ask(
        "  Seed node URLs (comma-separated)",
        default="",
    )
    seeds = [s.strip() for s in seeds_raw.split(",") if s.strip()]

    return {
        "enabled": True,
        "node_name": node_name,
        "bind": "0.0.0.0:8000",
        "seeds": seeds,
        "heartbeat_interval": 5,
        "gossip_interval": 2,
        "gossip_fanout": 3,
        "failure_timeout": 15,
        "dead_timeout": 30,
    }


def _write_configs(
    config_dir: Path,
    role: str,
    provider_result: dict | None,
    mesh_config: dict | None,
) -> list[str]:
    """Step 5: Write all configuration files. Returns list of written file paths."""
    console.print("\n[bold]Step 4:[/bold] Writing Configuration\n")

    config_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    # --- runtime.yaml from profile ---
    profile_file = PROFILES_DIR / f"{role}.yaml"
    runtime_dest = config_dir / "runtime.yaml"
    if profile_file.exists():
        runtime_data = yaml.safe_load(profile_file.read_text())
    else:
        print_error(f"Profile not found: {profile_file}")
        runtime_data = {}

    # Merge mesh config if provided
    if mesh_config and runtime_data.get("spec"):
        runtime_data["spec"]["mesh"] = mesh_config
        # Remove peers if switching to mesh
        runtime_data["spec"].pop("peers", None)

    runtime_dest.write_text(yaml.dump(runtime_data, default_flow_style=False, sort_keys=False))
    written.append(str(runtime_dest))

    # --- providers.yaml ---
    if provider_result:
        providers_dest = config_dir / "providers.yaml"
        providers_dest.write_text(
            yaml.dump(
                provider_result["config"],
                default_flow_style=False,
                sort_keys=False,
            )
        )
        written.append(str(providers_dest))

        # --- .env for API keys ---
        if provider_result.get("api_key") and provider_result.get("env_var"):
            env_file = config_dir.parent / ".env" if config_dir.name == "config" else config_dir / ".env"
            env_lines: list[str] = []
            if env_file.exists():
                env_lines = env_file.read_text().splitlines()
            # Replace or append the key
            env_var = provider_result["env_var"]
            api_key = provider_result["api_key"]
            found = False
            for i, line in enumerate(env_lines):
                if line.startswith(f"{env_var}="):
                    env_lines[i] = f"{env_var}={api_key}"
                    found = True
                    break
            if not found:
                env_lines.append(f"{env_var}={api_key}")
            env_file.write_text("\n".join(env_lines) + "\n")
            written.append(str(env_file))

    # --- agents/ directory + sample agents ---
    agents_dest = config_dir / "agents"
    agents_dest.mkdir(parents=True, exist_ok=True)
    if AGENTS_SRC_DIR.exists():
        for agent_file in AGENTS_SRC_DIR.glob("*.agent.yaml"):
            dest = agents_dest / agent_file.name
            if not dest.exists():
                shutil.copy2(agent_file, dest)
                written.append(str(dest))

    # Show summary table
    table = Table(title="Files Written", show_header=True, header_style="bold green")
    table.add_column("File", style="cyan")
    table.add_column("Description")

    for f in written:
        fname = Path(f).name
        if fname == "runtime.yaml":
            desc = f"Runtime config (role: {role})"
        elif fname == "providers.yaml":
            desc = "Provider configuration"
        elif fname == ".env":
            desc = "Environment variables (API keys)"
        elif fname.endswith(".agent.yaml"):
            desc = "Sample agent definition"
        else:
            desc = "Configuration file"
        table.add_row(f, desc)

    console.print(table)
    return written


def _validate_config(config_dir: Path) -> bool:
    """Step 6: Validate written configuration files."""
    console.print("\n[bold]Step 5:[/bold] Validating Configuration\n")

    errors: list[str] = []
    files_checked = 0

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

    if errors:
        console.print(f"  [red]Validation failed[/red] ({len(errors)} error(s)):\n")
        for err in errors:
            console.print(f"    [red]x[/red] {err}")
        return False

    console.print(f"  [green]Configuration valid[/green] ({files_checked} file(s) checked).")
    return True


def _offer_start(mode: str) -> None:
    """Step 7: Suggest how to start the daemon."""
    console.print("\n[bold]Step 6:[/bold] Next Steps\n")

    if mode == "system":
        console.print("  Start the daemon with:\n")
        console.print("    [bold cyan]sudo systemctl start astromeshd[/bold cyan]\n")
        console.print("  Or enable on boot:\n")
        console.print("    [bold cyan]sudo systemctl enable --now astromeshd[/bold cyan]\n")
    else:
        console.print("  Start the daemon with:\n")
        console.print("    [bold cyan]astromeshd --config ./config[/bold cyan]\n")
        console.print("  Or using make:\n")
        console.print("    [bold cyan]make dev-single[/bold cyan]\n")

    console.print("[green]Setup complete![/green]\n")


app = typer.Typer(help="Interactive setup wizard.")


@app.command("init")
def init_command(
    role: str = typer.Option(None, "--role", help="Node role: full, gateway, worker, inference"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Accept all defaults"),
    dev: bool = typer.Option(False, "--dev", help="Force dev mode (local ./config/)"),
) -> None:
    """Initialize Astromesh configuration with an interactive wizard."""
    # Validate role option early if provided
    if role and role not in ROLES:
        print_error(f"Invalid role '{role}'. Choose from: {', '.join(ROLES.keys())}")
        raise typer.Exit(code=1)

    # Step 1: Welcome + detect mode
    config_dir, mode = _detect_config_dir(dev)
    _show_welcome(mode)

    # Check existing config
    if not non_interactive and not _check_existing_config(config_dir):
        raise typer.Exit(code=0)

    # Step 2: Select role
    chosen_role = _select_role(role, non_interactive)

    # Step 3: Configure provider
    provider_result = _configure_provider(config_dir, non_interactive)

    # Step 4: Mesh configuration
    mesh_config = _configure_mesh(chosen_role, non_interactive)

    # Step 5: Write config files
    _write_configs(config_dir, chosen_role, provider_result, mesh_config)

    # Step 6: Validate
    _validate_config(config_dir)

    # Step 7: Offer to start
    _offer_start(mode)
