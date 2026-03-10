# Astromesh OS Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add system-level daemon (`astromeshd`), CLI (`astromeshctl`), filesystem layout, systemd unit, and system API endpoints to transform Astromesh into an OS-level runtime.

**Architecture:** `astromeshd` is a single-process async Python daemon that wraps the existing `AgentRuntime` and embedded uvicorn. `astromeshctl` is a Typer CLI that talks to the daemon via HTTP. New `/v1/system/*` endpoints expose status and diagnostics. systemd manages the daemon lifecycle.

**Tech Stack:** Python 3.12+, Typer >= 0.12, Rich >= 13, sdnotify >= 0.3, uvicorn, FastAPI, pytest + httpx

**Design doc:** `docs/plans/2026-03-09-astromesh-os-design.md`

---

## Task 1: Add new dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:16-35` (optional-dependencies section)

**Step 1: Add cli and daemon optional dependency groups**

Add after the `mcp` line (line 32) and before `all`:

```toml
cli = ["typer>=0.12.0", "rich>=13.0.0"]
daemon = ["sdnotify>=0.3.0"]
```

Update the `all` extra to include `cli` and `daemon`:

```toml
all = [
    "astromesh[redis,postgres,sqlite,chromadb,qdrant,faiss,embeddings,onnx,observability,mcp,cli,daemon]",
]
```

**Step 2: Add console_scripts entry points**

Add after `[build-system]` section:

```toml
[project.scripts]
astromeshd = "daemon.astromeshd:main"
astromeshctl = "cli.main:app"
```

**Step 3: Verify install**

Run: `uv sync --extra cli --extra daemon`
Expected: installs typer, rich, sdnotify without errors

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add cli and daemon optional dependencies"
```

---

## Task 2: System API endpoints

**Files:**
- Create: `astromesh/api/routes/system.py`
- Modify: `astromesh/api/main.py`
- Create: `tests/test_system_api.py`

**Step 1: Write the failing tests**

Create `tests/test_system_api.py`:

```python
"""Tests for /v1/system/* API endpoints."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_system_status_no_runtime(client):
    """Status endpoint returns basic info even without runtime."""
    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "uptime_seconds" in data
    assert data["mode"] in ("dev", "system")
    assert "agents_loaded" in data


async def test_system_status_with_runtime(client):
    """Status endpoint returns agent count when runtime is set."""
    from astromesh.api.routes import system

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = [
        {"name": "agent1"},
        {"name": "agent2"},
    ]
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_loaded"] == 2

    # Cleanup
    system.set_runtime(None)


async def test_system_doctor_no_runtime(client):
    """Doctor endpoint works without runtime, reports no checks."""
    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is False
    assert "runtime" in data["checks"]
    assert data["checks"]["runtime"]["status"] == "unavailable"


async def test_system_doctor_with_runtime(client):
    """Doctor endpoint checks providers when runtime is available."""
    from astromesh.api.routes import system

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = [{"name": "a1"}]
    mock_runtime._agents = {"a1": MagicMock()}

    # Mock the router's providers
    mock_provider = AsyncMock()
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_runtime._agents["a1"]._router._providers = {"ollama": mock_provider}

    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["runtime"]["status"] == "ok"

    # Cleanup
    system.set_runtime(None)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_system_api.py -v`
Expected: FAIL (module `astromesh.api.routes.system` does not exist)

**Step 3: Implement system routes**

Create `astromesh/api/routes/system.py`:

```python
"""System management endpoints for Astromesh OS."""

import os
import time

from fastapi import APIRouter
from pydantic import BaseModel

from astromesh import __version__

router = APIRouter(prefix="/system", tags=["system"])

_runtime = None
_start_time = time.time()


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class CheckResult(BaseModel):
    status: str
    message: str = ""


class StatusResponse(BaseModel):
    version: str
    uptime_seconds: float
    mode: str
    agents_loaded: int
    pid: int


class DoctorResponse(BaseModel):
    healthy: bool
    checks: dict[str, CheckResult]


def _detect_mode() -> str:
    """Detect if running in system mode or dev mode."""
    if os.path.exists("/etc/astromesh/runtime.yaml"):
        return "system"
    return "dev"


@router.get("/status", response_model=StatusResponse)
async def system_status():
    agents_loaded = 0
    if _runtime:
        agents_loaded = len(_runtime.list_agents())

    return StatusResponse(
        version=__version__,
        uptime_seconds=round(time.time() - _start_time, 2),
        mode=_detect_mode(),
        agents_loaded=agents_loaded,
        pid=os.getpid(),
    )


@router.get("/doctor", response_model=DoctorResponse)
async def system_doctor():
    checks: dict[str, CheckResult] = {}

    # Check runtime
    if not _runtime:
        checks["runtime"] = CheckResult(status="unavailable", message="Runtime not initialized")
        return DoctorResponse(healthy=False, checks=checks)

    checks["runtime"] = CheckResult(status="ok", message="Runtime initialized")

    # Check providers (best effort, don't fail the whole doctor)
    providers_checked = set()
    for agent in _runtime._agents.values():
        if hasattr(agent, "_router") and hasattr(agent._router, "_providers"):
            for name, provider in agent._router._providers.items():
                if name not in providers_checked:
                    providers_checked.add(name)
                    try:
                        healthy = await provider.health_check()
                        checks[f"provider:{name}"] = CheckResult(
                            status="ok" if healthy else "degraded",
                            message=f"Provider {name} health check",
                        )
                    except Exception as e:
                        checks[f"provider:{name}"] = CheckResult(
                            status="error", message=str(e)
                        )

    all_ok = all(c.status == "ok" for c in checks.values())
    return DoctorResponse(healthy=all_ok, checks=checks)
```

**Step 4: Register the route in main.py**

In `astromesh/api/main.py`, add the import and router:

```python
from astromesh.api.routes import agents, memory, tools, rag, whatsapp, system
```

Add after the last `include_router` line:

```python
app.include_router(system.router, prefix="/v1")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_system_api.py -v`
Expected: ALL PASS

**Step 6: Run existing tests to verify no regressions**

Run: `uv run pytest tests/test_api.py -v`
Expected: ALL PASS

**Step 7: Lint**

Run: `uv run ruff check astromesh/api/routes/system.py tests/test_system_api.py`
Run: `uv run ruff format astromesh/api/routes/system.py tests/test_system_api.py`

**Step 8: Commit**

```bash
git add astromesh/api/routes/system.py astromesh/api/main.py tests/test_system_api.py
git commit -m "feat: add /v1/system/status and /v1/system/doctor endpoints"
```

---

## Task 3: astromeshd daemon

**Files:**
- Create: `daemon/__init__.py`
- Create: `daemon/astromeshd.py`
- Create: `tests/test_daemon.py`

**Step 1: Write the failing tests**

Create `tests/test_daemon.py`:

```python
"""Tests for astromeshd daemon."""

import signal
import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from daemon.astromeshd import (
    detect_config_dir,
    write_pid_file,
    remove_pid_file,
    DaemonConfig,
    parse_args,
)


def test_detect_config_dir_dev_mode(tmp_path):
    """In dev mode, uses ./config/ if it exists."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "runtime.yaml").write_text("apiVersion: astromesh/v1")

    with patch("daemon.astromeshd.Path.cwd", return_value=tmp_path):
        result = detect_config_dir(None)
    assert result == str(config_dir)


def test_detect_config_dir_system_mode(tmp_path):
    """In system mode, uses /etc/astromesh/ if it exists."""
    etc_dir = tmp_path / "etc" / "astromesh"
    etc_dir.mkdir(parents=True)
    (etc_dir / "runtime.yaml").write_text("apiVersion: astromesh/v1")

    with patch("daemon.astromeshd.SYSTEM_CONFIG_DIR", str(etc_dir)):
        result = detect_config_dir(None)
    assert result == str(etc_dir)


def test_detect_config_dir_explicit():
    """Explicit --config overrides auto-detection."""
    result = detect_config_dir("/custom/path")
    assert result == "/custom/path"


def test_write_and_remove_pid_file(tmp_path):
    """PID file is written and cleaned up."""
    pid_file = tmp_path / "astromeshd.pid"
    write_pid_file(str(pid_file))
    assert pid_file.exists()
    assert pid_file.read_text().strip() == str(os.getpid())

    remove_pid_file(str(pid_file))
    assert not pid_file.exists()


def test_daemon_config_from_yaml(tmp_path):
    """DaemonConfig loads from runtime.yaml."""
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "127.0.0.1"
    port: 9000
""")
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.host == "127.0.0.1"
    assert config.port == 9000


def test_daemon_config_defaults(tmp_path):
    """DaemonConfig uses defaults when no runtime.yaml."""
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.host == "0.0.0.0"
    assert config.port == 8000


def test_parse_args_defaults():
    """Default args are sensible."""
    args = parse_args([])
    assert args.config is None
    assert args.port is None
    assert args.host is None
    assert args.log_level == "info"


def test_parse_args_custom():
    """Custom args override defaults."""
    args = parse_args(["--config", "/etc/astromesh", "--port", "9000", "--log-level", "debug"])
    assert args.config == "/etc/astromesh"
    assert args.port == 9000
    assert args.log_level == "debug"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: FAIL (module `daemon.astromeshd` does not exist)

**Step 3: Implement the daemon**

Create `daemon/__init__.py`:

```python
"""Astromesh OS daemon."""
```

Create `daemon/astromeshd.py`:

```python
"""astromeshd — Astromesh Agent Runtime Daemon.

Usage:
    astromeshd                          # Auto-detect config dir
    astromeshd --config /etc/astromesh  # Explicit config dir
    astromeshd --port 9000              # Override port
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SYSTEM_CONFIG_DIR = "/etc/astromesh"
DEFAULT_PID_FILE = "/var/lib/astromesh/data/astromeshd.pid"

logger = logging.getLogger("astromeshd")


@dataclass
class DaemonConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    pid_file: str = DEFAULT_PID_FILE

    @classmethod
    def from_config_dir(cls, config_dir: str) -> "DaemonConfig":
        """Load daemon config from runtime.yaml in config_dir."""
        runtime_path = Path(config_dir) / "runtime.yaml"
        if not runtime_path.exists():
            return cls()

        data = yaml.safe_load(runtime_path.read_text()) or {}
        spec = data.get("spec", {})
        api = spec.get("api", {})

        return cls(
            host=api.get("host", cls.host),
            port=api.get("port", cls.port),
        )


def detect_config_dir(explicit: str | None) -> str:
    """Detect config directory: explicit > /etc/astromesh > ./config."""
    if explicit:
        return explicit

    if os.path.exists(os.path.join(SYSTEM_CONFIG_DIR, "runtime.yaml")):
        return SYSTEM_CONFIG_DIR

    local_config = Path.cwd() / "config"
    if local_config.exists():
        return str(local_config)

    return SYSTEM_CONFIG_DIR


def write_pid_file(pid_file: str) -> None:
    """Write current PID to file."""
    Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
    Path(pid_file).write_text(str(os.getpid()))


def remove_pid_file(pid_file: str) -> None:
    """Remove PID file if it exists."""
    path = Path(pid_file)
    if path.exists():
        path.unlink()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse daemon command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="astromeshd",
        description="Astromesh Agent Runtime Daemon",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Config directory (default: auto-detect)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind host (default: from runtime.yaml or 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: from runtime.yaml or 8000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level (default: info)",
    )
    parser.add_argument(
        "--pid-file",
        type=str,
        default=None,
        help="PID file path (default: /var/lib/astromesh/data/astromeshd.pid)",
    )
    return parser.parse_args(argv)


def setup_logging(level: str) -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def run_daemon(args: argparse.Namespace) -> None:
    """Main daemon async entry point."""
    import uvicorn

    from astromesh.api.main import app
    from astromesh.api.routes import agents, system
    from astromesh.runtime.engine import AgentRuntime

    config_dir = detect_config_dir(args.config)
    daemon_config = DaemonConfig.from_config_dir(config_dir)

    # CLI args override config file
    host = args.host or daemon_config.host
    port = args.port or daemon_config.port
    pid_file = args.pid_file or daemon_config.pid_file

    mode = "system" if config_dir == SYSTEM_CONFIG_DIR else "dev"
    logger.info("Starting astromeshd in %s mode", mode)
    logger.info("Config directory: %s", config_dir)

    # Write PID file
    write_pid_file(pid_file)

    # Bootstrap runtime
    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()

    # Inject runtime into route modules
    agents.set_runtime(runtime)
    system.set_runtime(runtime)

    agent_count = len(runtime.list_agents())
    logger.info("Loaded %d agent(s)", agent_count)

    # Notify systemd if available
    try:
        import sdnotify

        notifier = sdnotify.SystemdNotifier()
        notifier.notify("READY=1")
        logger.info("Notified systemd: READY")
    except ImportError:
        pass

    # Run uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=args.log_level,
        access_log=True,
    )
    server = uvicorn.Server(config)

    # Handle signals for graceful shutdown
    loop = asyncio.get_event_loop()

    def handle_shutdown(sig, frame):
        logger.info("Received %s, shutting down...", signal.Signals(sig).name)
        server.should_exit = True

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, lambda: handle_shutdown(signal.SIGTERM, None))
        loop.add_signal_handler(signal.SIGINT, lambda: handle_shutdown(signal.SIGINT, None))
    else:
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)

    try:
        await server.serve()
    finally:
        remove_pid_file(pid_file)
        logger.info("astromeshd stopped")


def main() -> None:
    """Entry point for astromeshd."""
    args = parse_args()
    setup_logging(args.log_level)
    asyncio.run(run_daemon(args))


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check daemon/ tests/test_daemon.py`
Run: `uv run ruff format daemon/ tests/test_daemon.py`

**Step 6: Commit**

```bash
git add daemon/ tests/test_daemon.py
git commit -m "feat: add astromeshd daemon with config detection and PID management"
```

---

## Task 4: astromeshctl CLI — core + status command

**Files:**
- Create: `cli/__init__.py`
- Create: `cli/main.py`
- Create: `cli/client.py`
- Create: `cli/output.py`
- Create: `cli/commands/__init__.py`
- Create: `cli/commands/status.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
"""Tests for astromeshctl CLI."""

from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_version():
    """Version command prints version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.5.0" in result.output


def test_status_daemon_running():
    """Status shows daemon info when reachable."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": "0.5.0",
        "uptime_seconds": 123.45,
        "mode": "dev",
        "agents_loaded": 3,
        "pid": 12345,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "0.5.0" in result.output
    assert "dev" in result.output


def test_status_daemon_not_running():
    """Status shows error when daemon is unreachable."""
    with patch("cli.client.httpx.get", side_effect=Exception("Connection refused")):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not reachable" in result.output.lower() or "error" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL (module `cli.main` does not exist)

**Step 3: Implement CLI core**

Create `cli/__init__.py`:

```python
"""Astromesh OS CLI — astromeshctl."""
```

Create `cli/commands/__init__.py`:

```python
```

Create `cli/client.py`:

```python
"""HTTP client for communicating with astromeshd."""

import httpx

DEFAULT_URL = "http://localhost:8000"


def get_base_url() -> str:
    """Get daemon base URL from env or default."""
    import os

    return os.environ.get("ASTROMESH_DAEMON_URL", DEFAULT_URL)


def api_get(path: str) -> dict:
    """Make a GET request to the daemon API. Raises on failure."""
    url = f"{get_base_url()}{path}"
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    return resp.json()
```

Create `cli/output.py`:

```python
"""Rich output helpers for astromeshctl."""

from rich.console import Console
from rich.table import Table

console = Console()
error_console = Console(stderr=True)


def print_status_table(data: dict) -> None:
    """Print daemon status as a Rich table."""
    table = Table(title="Astromesh Daemon Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version", data["version"])
    table.add_row("PID", str(data.get("pid", "N/A")))
    table.add_row("Mode", data["mode"])
    table.add_row("Uptime", f"{data['uptime_seconds']:.1f}s")
    table.add_row("Agents Loaded", str(data["agents_loaded"]))

    console.print(table)


def print_error(message: str) -> None:
    """Print an error message."""
    error_console.print(f"[red]Error:[/red] {message}")


def print_json(data: dict) -> None:
    """Print data as formatted JSON."""
    import json

    console.print_json(json.dumps(data))
```

Create `cli/commands/status.py`:

```python
"""astromeshctl status command."""

import typer

from cli.client import api_get
from cli.output import print_status_table, print_error, print_json

app = typer.Typer()


@app.callback(invoke_without_command=True)
def status(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Show daemon status."""
    try:
        data = api_get("/v1/system/status")
        if json:
            print_json(data)
        else:
            print_status_table(data)
    except Exception:
        print_error("Daemon not reachable at configured URL.")
        raise typer.Exit(code=0)
```

Create `cli/main.py`:

```python
"""astromeshctl — Astromesh OS CLI management tool."""

import typer

from astromesh import __version__
from cli.commands import status

app = typer.Typer(
    name="astromeshctl",
    help="Astromesh OS CLI management tool.",
    no_args_is_help=True,
)

app.add_typer(status.app, name="status")


@app.command()
def version():
    """Show astromesh version."""
    typer.echo(f"astromesh {__version__}")


if __name__ == "__main__":
    app()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check cli/ tests/test_cli.py`
Run: `uv run ruff format cli/ tests/test_cli.py`

**Step 6: Commit**

```bash
git add cli/ tests/test_cli.py
git commit -m "feat: add astromeshctl CLI with status and version commands"
```

---

## Task 5: astromeshctl — doctor command

**Files:**
- Create: `cli/commands/doctor.py`
- Modify: `cli/main.py` (add doctor command)
- Modify: `tests/test_cli.py` (add doctor tests)

**Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_doctor_healthy():
    """Doctor shows healthy when all checks pass."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "healthy": True,
        "checks": {
            "runtime": {"status": "ok", "message": "Runtime initialized"},
            "provider:ollama": {"status": "ok", "message": "Provider ollama health check"},
        },
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "ok" in result.output.lower()


def test_doctor_unhealthy():
    """Doctor shows issues when checks fail."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "healthy": False,
        "checks": {
            "runtime": {"status": "unavailable", "message": "Runtime not initialized"},
        },
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "unavailable" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_doctor_healthy -v`
Expected: FAIL

**Step 3: Implement doctor command**

Create `cli/commands/doctor.py`:

```python
"""astromeshctl doctor command."""

import typer
from rich.table import Table

from cli.client import api_get
from cli.output import console, print_error, print_json

app = typer.Typer()

STATUS_ICONS = {
    "ok": "[green]OK[/green]",
    "degraded": "[yellow]DEGRADED[/yellow]",
    "error": "[red]ERROR[/red]",
    "unavailable": "[red]UNAVAILABLE[/red]",
}


@app.callback(invoke_without_command=True)
def doctor(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Run system health checks."""
    try:
        data = api_get("/v1/system/doctor")
        if json:
            print_json(data)
            return

        healthy = data["healthy"]
        header = "[green]System Healthy[/green]" if healthy else "[red]System Unhealthy[/red]"
        console.print(f"\n{header}\n")

        table = Table()
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        table.add_column("Message", style="dim")

        for name, check in data["checks"].items():
            status_display = STATUS_ICONS.get(check["status"], check["status"])
            table.add_row(name, status_display, check.get("message", ""))

        console.print(table)
    except Exception:
        print_error("Daemon not reachable at configured URL.")
        raise typer.Exit(code=0)
```

**Step 4: Register in main.py**

In `cli/main.py`, add:

```python
from cli.commands import status, doctor
```

And:

```python
app.add_typer(doctor.app, name="doctor")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add cli/commands/doctor.py cli/main.py tests/test_cli.py
git commit -m "feat: add astromeshctl doctor command"
```

---

## Task 6: astromeshctl — agents and providers commands

**Files:**
- Create: `cli/commands/agents.py`
- Create: `cli/commands/providers.py`
- Modify: `cli/main.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_agents_list():
    """Agents list shows loaded agents."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "agents": [
            {"name": "support-agent", "version": "1.0.0", "namespace": "support"},
            {"name": "sales-agent", "version": "0.2.0", "namespace": "sales"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["agents", "list"])
    assert result.exit_code == 0
    assert "support-agent" in result.output
    assert "sales-agent" in result.output


def test_providers_list():
    """Providers list shows configured providers."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "providers": [
            {"name": "ollama", "endpoint": "http://localhost:11434", "models": ["llama3.1:8b"]},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    assert "ollama" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_agents_list -v`
Expected: FAIL

**Step 3: Implement agents command**

Create `cli/commands/agents.py`:

```python
"""astromeshctl agents commands."""

import typer
from rich.table import Table

from cli.client import api_get
from cli.output import console, print_error, print_json

app = typer.Typer(help="Manage agents.")


@app.command("list")
def list_agents(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List loaded agents."""
    try:
        data = api_get("/v1/agents")
        if json:
            print_json(data)
            return

        agents = data.get("agents", [])
        if not agents:
            console.print("[dim]No agents loaded.[/dim]")
            return

        table = Table(title="Loaded Agents")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Namespace", style="dim")

        for agent in agents:
            table.add_row(
                agent.get("name", ""),
                agent.get("version", ""),
                agent.get("namespace", ""),
            )

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
```

Create `cli/commands/providers.py`:

```python
"""astromeshctl providers commands."""

import typer
from rich.table import Table

from cli.client import api_get
from cli.output import console, print_error, print_json

app = typer.Typer(help="Manage model providers.")


@app.command("list")
def list_providers(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List configured providers."""
    try:
        data = api_get("/v1/providers")
        if json:
            print_json(data)
            return

        providers = data.get("providers", [])
        if not providers:
            console.print("[dim]No providers configured.[/dim]")
            return

        table = Table(title="Model Providers")
        table.add_column("Name", style="cyan")
        table.add_column("Endpoint", style="green")
        table.add_column("Models", style="dim")

        for p in providers:
            models = ", ".join(p.get("models", []))
            table.add_row(p.get("name", ""), p.get("endpoint", ""), models)

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
```

**Step 4: Register in main.py**

In `cli/main.py`, add imports and registrations:

```python
from cli.commands import status, doctor, agents, providers

app.add_typer(agents.app, name="agents")
app.add_typer(providers.app, name="providers")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add cli/commands/agents.py cli/commands/providers.py cli/main.py tests/test_cli.py
git commit -m "feat: add astromeshctl agents and providers commands"
```

---

## Task 7: astromeshctl — config validate command

**Files:**
- Create: `cli/commands/config.py`
- Modify: `cli/main.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_config_validate_valid(tmp_path):
    """Config validate reports valid config."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test
spec:
  identity:
    display_name: Test
""")
    (tmp_path / "runtime.yaml").write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000
""")

    result = runner.invoke(app, ["config", "validate", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_config_validate_invalid_yaml(tmp_path):
    """Config validate catches invalid YAML."""
    (tmp_path / "runtime.yaml").write_text(": invalid: yaml: [")

    result = runner.invoke(app, ["config", "validate", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "error" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_config_validate_valid -v`
Expected: FAIL

**Step 3: Implement config validate**

Create `cli/commands/config.py`:

```python
"""astromeshctl config commands."""

from pathlib import Path

import typer
import yaml

from cli.output import console, print_error

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
        console.print(
            f"\n[green]Configuration valid[/green] ({files_checked} file(s) checked)."
        )
```

**Step 4: Register in main.py**

In `cli/main.py`:

```python
from cli.commands import status, doctor, agents, providers, config

app.add_typer(config.app, name="config")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add cli/commands/config.py cli/main.py tests/test_cli.py
git commit -m "feat: add astromeshctl config validate command"
```

---

## Task 8: systemd unit and install script

**Files:**
- Create: `packaging/systemd/astromeshd.service`
- Create: `packaging/install.sh`

**Step 1: Create systemd unit file**

Create `packaging/systemd/astromeshd.service`:

```ini
[Unit]
Description=Astromesh Agent Runtime Daemon
Documentation=https://github.com/monaccode/astromesh
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=notify
User=astromesh
Group=astromesh
ExecStart=/opt/astromesh/bin/astromeshd --config /etc/astromesh/
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
WatchdogSec=30

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/astromesh /var/log/astromesh
PrivateTmp=yes

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=astromeshd

[Install]
WantedBy=multi-user.target
```

**Step 2: Create install script**

Create `packaging/install.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Astromesh OS installation script
# Usage: sudo bash install.sh

ASTROMESH_USER="astromesh"
ASTROMESH_GROUP="astromesh"

echo "=== Astromesh OS Installer ==="

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

# Create system user
if ! id -u "$ASTROMESH_USER" &>/dev/null; then
    echo "Creating system user: $ASTROMESH_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$ASTROMESH_USER"
fi

# Create directories
echo "Creating directories..."
mkdir -p /etc/astromesh/agents
mkdir -p /etc/astromesh/rag
mkdir -p /var/lib/astromesh/models
mkdir -p /var/lib/astromesh/memory
mkdir -p /var/lib/astromesh/data
mkdir -p /var/log/astromesh/audit
mkdir -p /opt/astromesh/bin
mkdir -p /opt/astromesh/lib

# Set permissions
echo "Setting permissions..."
chown root:$ASTROMESH_GROUP /etc/astromesh -R
chmod 750 /etc/astromesh -R
chown $ASTROMESH_USER:$ASTROMESH_GROUP /var/lib/astromesh -R
chmod 755 /var/lib/astromesh -R
chown $ASTROMESH_USER:$ASTROMESH_GROUP /var/log/astromesh -R
chmod 755 /var/log/astromesh -R

# Copy config if not present
if [[ ! -f /etc/astromesh/runtime.yaml ]]; then
    echo "Installing default configuration..."
    cp -n config/runtime.yaml /etc/astromesh/ 2>/dev/null || true
    cp -n config/providers.yaml /etc/astromesh/ 2>/dev/null || true
    cp -n config/channels.yaml /etc/astromesh/ 2>/dev/null || true
    cp -rn config/agents/* /etc/astromesh/agents/ 2>/dev/null || true
fi

# Install systemd service
echo "Installing systemd service..."
cp packaging/systemd/astromeshd.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /etc/astromesh/runtime.yaml"
echo "  2. Configure providers in /etc/astromesh/providers.yaml"
echo "  3. Add agents to /etc/astromesh/agents/"
echo "  4. Start the daemon: systemctl start astromeshd"
echo "  5. Enable on boot: systemctl enable astromeshd"
echo "  6. Check status: astromeshctl status"
```

**Step 3: Make install script executable**

Run: `chmod +x packaging/install.sh`

**Step 4: Commit**

```bash
git add packaging/
git commit -m "feat: add systemd unit and installation script"
```

---

## Task 9: Wire entry points and integration test

**Files:**
- Modify: `pyproject.toml` (ensure scripts work)
- Create: `tests/test_daemon_integration.py`

**Step 1: Write integration test**

Create `tests/test_daemon_integration.py`:

```python
"""Integration tests for astromeshd + astromeshctl."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from astromesh.api.main import app
from astromesh.api.routes import system
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture
async def bootstrapped_client(tmp_path):
    """Client with a bootstrapped runtime."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()
    system.set_runtime(runtime)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    system.set_runtime(None)


async def test_status_with_bootstrapped_runtime(bootstrapped_client):
    """Status endpoint reflects bootstrapped agents."""
    resp = await bootstrapped_client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_loaded"] == 1
    assert data["version"] == "0.5.0"


async def test_doctor_with_bootstrapped_runtime(bootstrapped_client):
    """Doctor reports runtime as ok when bootstrapped."""
    resp = await bootstrapped_client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["runtime"]["status"] == "ok"
```

**Step 2: Run integration test**

Run: `uv run pytest tests/test_daemon_integration.py -v`
Expected: ALL PASS

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS (no regressions)

**Step 4: Lint everything**

Run: `uv run ruff check daemon/ cli/ astromesh/api/routes/system.py tests/test_daemon.py tests/test_cli.py tests/test_system_api.py tests/test_daemon_integration.py`
Run: `uv run ruff format daemon/ cli/ astromesh/api/routes/system.py tests/test_daemon.py tests/test_cli.py tests/test_system_api.py tests/test_daemon_integration.py`

**Step 5: Commit**

```bash
git add tests/test_daemon_integration.py
git commit -m "test: add daemon integration tests with bootstrapped runtime"
```

---

## Task Summary

| Task | Component | Dependencies | Can Parallelize |
|------|-----------|-------------|-----------------|
| 1 | pyproject.toml deps | None | Independent |
| 2 | System API endpoints | None | Independent |
| 3 | astromeshd daemon | Task 1 (deps), Task 2 (system routes) | After 1+2 |
| 4 | CLI core + status | Task 1 (deps), Task 2 (API) | After 1+2 |
| 5 | CLI doctor command | Task 4 | After 4 |
| 6 | CLI agents + providers | Task 4 | After 4, parallel with 5 |
| 7 | CLI config validate | Task 4 | After 4, parallel with 5+6 |
| 8 | systemd + install | None | Independent |
| 9 | Integration tests | Task 2, 3 | After 2+3 |

**Parallelization plan:**
- **Wave 1:** Tasks 1, 2, 8 (all independent)
- **Wave 2:** Tasks 3, 4 (both depend on 1+2)
- **Wave 3:** Tasks 5, 6, 7 (all depend on 4, parallel with each other)
- **Wave 4:** Task 9 (integration)
