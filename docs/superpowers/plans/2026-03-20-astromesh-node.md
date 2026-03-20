# Astromesh Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract astromesh-os into a standalone `astromesh-node/` subproject with cross-platform support (Linux deb/rpm, macOS, Windows).

**Architecture:** Platform Adapter pattern — `ServiceManagerProtocol` and `InstallerProtocol` abstract init systems and filesystem conventions per OS. Daemon core is platform-agnostic; adapters handle systemd/launchd/Windows Service. Distributed as GitHub Release artifacts.

**Tech Stack:** Python 3.12+, hatchling, typer, rich, sdnotify (Linux), pywin32 (Windows), nfpm (.deb/.rpm), Astro/Starlight (docs)

**Spec:** `docs/superpowers/specs/2026-03-20-astromesh-node-design.md`

---

## File Structure

### New files to create

```
astromesh-node/
├── pyproject.toml
├── README.md
├── src/
│   └── astromesh_node/
│       ├── __init__.py
│       ├── daemon/
│       │   ├── __init__.py
│       │   ├── core.py              # Refactored from daemon/astromeshd.py (platform-agnostic)
│       │   └── config.py            # DaemonConfig + detect_config_dir (uses InstallerProtocol)
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py              # Moved from cli/main.py (updated imports)
│       │   └── commands/
│       │       ├── __init__.py
│       │       └── (17 command files moved from cli/commands/)
│       ├── platform/
│       │   ├── __init__.py
│       │   ├── base.py              # ServiceManagerProtocol + UnsupportedPlatformError
│       │   ├── detect.py            # get_service_manager() auto-detection
│       │   ├── foreground.py        # ForegroundManager (no-op, for dev/Docker)
│       │   ├── systemd.py           # SystemdManager (Linux)
│       │   ├── launchd.py           # LaunchdManager (macOS)
│       │   └── windows.py           # WindowsServiceManager (Windows)
│       └── installer/
│           ├── __init__.py
│           ├── base.py              # InstallerProtocol
│           ├── detect.py            # get_installer() auto-detection
│           ├── linux.py             # LinuxInstaller (FHS paths)
│           ├── macos.py             # MacOSInstaller (/Library/... paths)
│           └── windows.py           # WindowsInstaller (%ProgramData%/... paths)
├── packaging/
│   ├── nfpm.yaml                    # Moved + updated (deb + rpm targets)
│   ├── build-deb.sh                 # Moved + updated paths
│   ├── build-rpm.sh                 # New (mirrors build-deb.sh with rpm target)
│   ├── build-macos.sh               # New (creates .tar.gz + install.sh)
│   ├── build-windows.ps1            # New (creates .zip + install.ps1)
│   ├── systemd/
│   │   └── astromeshd.service       # Moved (unchanged)
│   ├── launchd/
│   │   └── com.astromesh.daemon.plist  # New
│   ├── windows/
│   │   └── astromeshd-service.py    # New (win32serviceutil wrapper)
│   └── scripts/
│       ├── preinstall.sh            # Moved (unchanged)
│       ├── postinstall.sh           # Moved (unchanged)
│       ├── preremove.sh             # Moved (unchanged)
│       ├── postremove.sh            # Moved (unchanged)
│       ├── install.sh               # Moved (standalone Linux installer)
│       └── install.ps1              # New (Windows installer)
├── config/
│   └── profiles/                    # Moved (7 YAML files)
└── tests/
    ├── conftest.py
    ├── test_platform_base.py
    ├── test_platform_detect.py
    ├── test_platform_foreground.py
    ├── test_platform_systemd.py
    ├── test_platform_launchd.py
    ├── test_platform_windows.py
    ├── test_installer_base.py
    ├── test_installer_linux.py
    ├── test_installer_macos.py
    ├── test_installer_windows.py
    ├── test_daemon_config.py
    └── test_daemon_core.py
```

### Files to modify in monorepo root

- `pyproject.toml` — Remove `astromeshd`/`astromeshctl` entry points and `cli`/`daemon` extras
- `.github/workflows/release.yml` — Remove deb build job
- `.github/workflows/ci.yml` — Remove `build-deb-test`, add astromesh-node tests
- `README.md` — Rename "Astromesh OS" → "Astromesh Node"
- `CHANGELOG.md` — Add migration note

### Files to delete from monorepo root (after move)

- `daemon/astromeshd.py`, `daemon/__init__.py`
- `cli/main.py`, `cli/commands/`, `cli/__init__.py`
- `packaging/` (entire directory)
- `nfpm.yaml`

### Docs-site changes

- Create: `docs-site/src/content/docs/node/` (8 pages)
- Create: `docs-site/src/components/NodeShowcase.astro`
- Modify: `docs-site/astro.config.mjs` (add Node sidebar section)
- Modify: `docs-site/src/content/docs/index.mdx` (add NodeShowcase)
- Replace: `docs-site/src/content/docs/deployment/astromesh-os.md` → redirect stub
- Modify: `docs-site/src/content/docs/getting-started/installation.md` → link to Node

---

## Task 1: Scaffold subproject and pyproject.toml

**Files:**
- Create: `astromesh-node/pyproject.toml`
- Create: `astromesh-node/README.md`
- Create: `astromesh-node/src/astromesh_node/__init__.py`

- [ ] **Step 1: Create subproject directory structure**

```bash
mkdir -p astromesh-node/src/astromesh_node
mkdir -p astromesh-node/tests
```

- [ ] **Step 2: Write pyproject.toml**

Create `astromesh-node/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "astromesh-node"
version = "0.1.0"
description = "Cross-platform system installer and daemon for the Astromesh agent runtime"
requires-python = ">=3.12"
license = {text = "Apache-2.0"}
dependencies = [
    "astromesh>=0.18.0",
    "typer>=0.12.0",
    "rich>=13.0.0",
    "pyyaml>=6.0",
]

[tool.uv.sources]
astromesh = { path = "..", editable = true }

[project.optional-dependencies]
systemd = ["sdnotify>=0.3.0"]
windows = ["pywin32>=306"]
dev = ["watchfiles>=0.21.0"]
test = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0", "pytest-cov>=5.0.0"]
all = ["astromesh-node[systemd,dev,test]"]

[project.scripts]
astromeshd = "astromesh_node.daemon.core:main"
astromeshctl = "astromesh_node.cli.main:app"

[project.entry-points."astromeshctl.plugins"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Write __init__.py**

Create `astromesh-node/src/astromesh_node/__init__.py`:

```python
"""Astromesh Node — Cross-platform system installer and daemon."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write README.md**

Create `astromesh-node/README.md`:

```markdown
# Astromesh Node

Cross-platform system installer and daemon for the Astromesh agent runtime.

Supports Linux (Debian/Ubuntu, RHEL/Fedora), macOS, and Windows.

## Quick Start

```bash
# Install from GitHub Release
sudo dpkg -i astromesh-node-0.1.0-amd64.deb    # Debian/Ubuntu
sudo rpm -i astromesh-node-0.1.0-amd64.rpm      # RHEL/Fedora

# Configure and start
sudo astromeshctl init --profile full
sudo systemctl start astromeshd
```

## Development

```bash
cd astromesh-node
uv sync --extra all
uv run pytest -v
```
```

- [ ] **Step 5: Verify pyproject.toml parses**

Run: `cd astromesh-node && python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])"`
Expected: `astromesh-node`

- [ ] **Step 6: Commit**

```bash
git add astromesh-node/
git commit -m "feat(node): scaffold astromesh-node subproject with pyproject.toml"
```

---

## Task 2: Platform abstraction — ServiceManagerProtocol + ForegroundManager

**Files:**
- Create: `astromesh-node/src/astromesh_node/platform/__init__.py`
- Create: `astromesh-node/src/astromesh_node/platform/base.py`
- Create: `astromesh-node/src/astromesh_node/platform/foreground.py`
- Create: `astromesh-node/src/astromesh_node/platform/detect.py`
- Test: `astromesh-node/tests/test_platform_base.py`
- Test: `astromesh-node/tests/test_platform_foreground.py`
- Test: `astromesh-node/tests/test_platform_detect.py`

- [ ] **Step 1: Write test for ServiceManagerProtocol conformance**

Create `astromesh-node/tests/conftest.py`:

```python
"""Shared fixtures for astromesh-node tests."""
```

Create `astromesh-node/tests/test_platform_base.py`:

```python
"""Tests for ServiceManagerProtocol."""

from astromesh_node.platform.base import ServiceManagerProtocol, UnsupportedPlatformError


def test_protocol_is_runtime_checkable():
    assert hasattr(ServiceManagerProtocol, "__protocol_attrs__") or hasattr(
        ServiceManagerProtocol, "__abstractmethods__"
    )


def test_unsupported_platform_error_is_exception():
    err = UnsupportedPlatformError("freebsd")
    assert isinstance(err, Exception)
    assert "freebsd" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-node && uv run pytest tests/test_platform_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh_node'`

- [ ] **Step 3: Write ServiceManagerProtocol**

Create `astromesh-node/src/astromesh_node/platform/__init__.py`:

```python
"""Platform abstraction layer for init system integration."""

from astromesh_node.platform.base import ServiceManagerProtocol, UnsupportedPlatformError
from astromesh_node.platform.detect import get_service_manager

__all__ = ["ServiceManagerProtocol", "UnsupportedPlatformError", "get_service_manager"]
```

Create `astromesh-node/src/astromesh_node/platform/base.py`:

```python
"""ServiceManagerProtocol — abstracts platform init systems."""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


class UnsupportedPlatformError(Exception):
    """Raised when the current platform is not supported."""


@runtime_checkable
class ServiceManagerProtocol(Protocol):
    """Abstraction of the platform's init system.

    Implementations: SystemdManager (Linux), LaunchdManager (macOS),
    WindowsServiceManager (Windows), ForegroundManager (dev/Docker).
    """

    async def notify_ready(self) -> None:
        """Signal to the init system that the daemon is ready."""
        ...

    async def notify_reload(self) -> None:
        """Signal that a config reload completed."""
        ...

    async def notify_stopping(self) -> None:
        """Signal that the daemon is shutting down."""
        ...

    async def install_service(self, profile: str) -> None:
        """Register astromeshd as a system service."""
        ...

    async def uninstall_service(self) -> None:
        """Unregister the system service."""
        ...

    async def service_status(self) -> dict[str, Any]:
        """Return service status (running, enabled, pid, uptime)."""
        ...

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        """Register a handler for config reload signals."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-node && uv run pytest tests/test_platform_base.py -v`
Expected: PASS

- [ ] **Step 5: Write test for ForegroundManager**

Create `astromesh-node/tests/test_platform_foreground.py`:

```python
"""Tests for ForegroundManager (no-op adapter)."""

import pytest

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.foreground import ForegroundManager


@pytest.fixture
def manager():
    return ForegroundManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_is_noop(manager):
    await manager.notify_ready()  # Should not raise


async def test_notify_reload_is_noop(manager):
    await manager.notify_reload()


async def test_notify_stopping_is_noop(manager):
    await manager.notify_stopping()


async def test_service_status_returns_foreground(manager):
    status = await manager.service_status()
    assert status["running"] is True
    assert status["mode"] == "foreground"


def test_register_reload_handler_stores_callback(manager):
    called = []
    manager.register_reload_handler(lambda: called.append(True))
    # Handler stored but not called — ForegroundManager doesn't trigger reloads
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd astromesh-node && uv run pytest tests/test_platform_foreground.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh_node.platform.foreground'`

- [ ] **Step 7: Write ForegroundManager**

Create `astromesh-node/src/astromesh_node/platform/foreground.py`:

```python
"""ForegroundManager — no-op ServiceManager for dev/Docker/foreground mode."""

from __future__ import annotations

import os
from typing import Any, Callable


class ForegroundManager:
    """No-op service manager for non-daemon contexts."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None

    async def notify_ready(self) -> None:
        pass

    async def notify_reload(self) -> None:
        pass

    async def notify_stopping(self) -> None:
        pass

    async def install_service(self, profile: str) -> None:
        raise RuntimeError("Cannot install service in foreground mode")

    async def uninstall_service(self) -> None:
        raise RuntimeError("Cannot uninstall service in foreground mode")

    async def service_status(self) -> dict[str, Any]:
        return {
            "running": True,
            "enabled": False,
            "pid": os.getpid(),
            "mode": "foreground",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd astromesh-node && uv run pytest tests/test_platform_foreground.py -v`
Expected: PASS

- [ ] **Step 9: Write test for detect.py**

Create `astromesh-node/tests/test_platform_detect.py`:

```python
"""Tests for platform auto-detection."""

from unittest.mock import patch

from astromesh_node.platform.base import UnsupportedPlatformError
from astromesh_node.platform.detect import get_service_manager
from astromesh_node.platform.foreground import ForegroundManager

import pytest


def test_foreground_flag_returns_foreground_manager():
    mgr = get_service_manager(foreground=True)
    assert isinstance(mgr, ForegroundManager)


def test_unsupported_platform_raises():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "freebsd"
        with pytest.raises(UnsupportedPlatformError, match="freebsd"):
            get_service_manager(foreground=False)


def test_linux_returns_systemd_manager():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "linux"
        mgr = get_service_manager(foreground=False)
        assert type(mgr).__name__ == "SystemdManager"


def test_darwin_returns_launchd_manager():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "darwin"
        mgr = get_service_manager(foreground=False)
        assert type(mgr).__name__ == "LaunchdManager"


def test_win32_returns_windows_manager():
    with patch("astromesh_node.platform.detect.sys") as mock_sys:
        mock_sys.platform = "win32"
        mgr = get_service_manager(foreground=False)
        assert type(mgr).__name__ == "WindowsServiceManager"
```

- [ ] **Step 10: Write detect.py**

Create `astromesh-node/src/astromesh_node/platform/detect.py`:

```python
"""Auto-detection of the platform's service manager."""

from __future__ import annotations

import sys

from astromesh_node.platform.base import ServiceManagerProtocol, UnsupportedPlatformError
from astromesh_node.platform.foreground import ForegroundManager


def get_service_manager(foreground: bool = False) -> ServiceManagerProtocol:
    """Return the appropriate ServiceManager for the current platform."""
    if foreground:
        return ForegroundManager()

    if sys.platform == "linux":
        from astromesh_node.platform.systemd import SystemdManager

        return SystemdManager()
    elif sys.platform == "darwin":
        from astromesh_node.platform.launchd import LaunchdManager

        return LaunchdManager()
    elif sys.platform == "win32":
        from astromesh_node.platform.windows import WindowsServiceManager

        return WindowsServiceManager()
    else:
        raise UnsupportedPlatformError(f"Platform {sys.platform} is not supported")
```

- [ ] **Step 11: Write test for ForegroundManager.install_service raises RuntimeError**

Add to `astromesh-node/tests/test_platform_foreground.py`:

```python
async def test_install_service_raises_in_foreground(manager):
    with pytest.raises(RuntimeError, match="foreground"):
        await manager.install_service("full")


async def test_uninstall_service_raises_in_foreground(manager):
    with pytest.raises(RuntimeError, match="foreground"):
        await manager.uninstall_service()
```

- [ ] **Step 12: Run base and foreground tests only**

Run: `cd astromesh-node && uv run pytest tests/test_platform_base.py tests/test_platform_foreground.py -v`
Expected: PASS

Note: `detect.py` and `test_platform_detect.py` are committed here but the detect tests that reference `SystemdManager`/`LaunchdManager`/`WindowsServiceManager` will not pass until Tasks 3-5 complete those adapters. This is intentional — the detect module uses lazy imports.

- [ ] **Step 13: Commit**

```bash
git add astromesh-node/src/astromesh_node/platform/ astromesh-node/tests/test_platform_*.py astromesh-node/tests/conftest.py
git commit -m "feat(node): add ServiceManagerProtocol, ForegroundManager, and platform detection"
```

---

## Task 3: Platform adapter — SystemdManager (Linux)

**Files:**
- Create: `astromesh-node/src/astromesh_node/platform/systemd.py`
- Test: `astromesh-node/tests/test_platform_systemd.py`

- [ ] **Step 1: Write tests for SystemdManager**

Create `astromesh-node/tests/test_platform_systemd.py`:

```python
"""Tests for SystemdManager (Linux systemd adapter)."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.systemd import SystemdManager


@pytest.fixture
def manager():
    return SystemdManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_calls_sdnotify(manager):
    mock_notifier = MagicMock()
    with patch.object(manager, "_get_notifier", return_value=mock_notifier):
        await manager.notify_ready()
        mock_notifier.notify.assert_called_once_with("READY=1")


async def test_notify_ready_noop_without_sdnotify(manager):
    with patch.object(manager, "_get_notifier", return_value=None):
        await manager.notify_ready()  # Should not raise


async def test_notify_stopping_calls_sdnotify(manager):
    mock_notifier = MagicMock()
    with patch.object(manager, "_get_notifier", return_value=mock_notifier):
        await manager.notify_stopping()
        mock_notifier.notify.assert_called_once_with("STOPPING=1")


async def test_notify_reload_calls_sdnotify(manager):
    mock_notifier = MagicMock()
    with patch.object(manager, "_get_notifier", return_value=mock_notifier):
        await manager.notify_reload()
        mock_notifier.notify.assert_called_once_with("RELOADING=1")


async def test_service_status_parses_systemctl(manager):
    systemctl_output = (
        "ActiveState=active\nSubState=running\nMainPID=1234\n"
        "ActiveEnterTimestamp=Thu 2026-03-20 10:00:00 UTC\n"
        "UnitFileState=enabled\n"
    )
    with patch("astromesh_node.platform.systemd.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (systemctl_output.encode(), b"")
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        status = await manager.service_status()
        assert status["running"] is True
        assert status["pid"] == 1234
        assert status["enabled"] is True


def test_register_reload_handler_sets_sighup(manager):
    callback = MagicMock()
    with patch("astromesh_node.platform.systemd.signal") as mock_signal:
        manager.register_reload_handler(callback)
        mock_signal.signal.assert_called_once()
        # First arg is SIGHUP
        args = mock_signal.signal.call_args
        assert args[0][0] == mock_signal.SIGHUP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-node && uv run pytest tests/test_platform_systemd.py -v`
Expected: FAIL

- [ ] **Step 3: Write SystemdManager**

Create `astromesh-node/src/astromesh_node/platform/systemd.py`:

```python
"""SystemdManager — Linux systemd service adapter."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.systemd")

SERVICE_NAME = "astromeshd.service"


class SystemdManager:
    """ServiceManager implementation for Linux systemd."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None

    def _get_notifier(self):
        """Return sdnotify notifier, or None if unavailable."""
        try:
            import sdnotify

            return sdnotify.SystemdNotifier()
        except ImportError:
            return None

    async def notify_ready(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("READY=1")
            logger.info("Notified systemd: READY")

    async def notify_reload(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("RELOADING=1")

    async def notify_stopping(self) -> None:
        notifier = self._get_notifier()
        if notifier:
            notifier.notify("STOPPING=1")

    async def install_service(self, profile: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "daemon-reload",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "enable", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Enabled %s", SERVICE_NAME)

    async def uninstall_service(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "disable", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Disabled %s", SERVICE_NAME)

    async def service_status(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "show", SERVICE_NAME,
            "--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,UnitFileState",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        props = {}
        for line in stdout.decode().strip().splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                props[key] = val

        return {
            "running": props.get("ActiveState") == "active",
            "sub_state": props.get("SubState", "unknown"),
            "pid": int(props["MainPID"]) if props.get("MainPID", "0") != "0" else None,
            "enabled": props.get("UnitFileState") == "enabled",
            "since": props.get("ActiveEnterTimestamp"),
            "mode": "systemd",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback

        def _handle_sighup(signum, frame):
            logger.info("Received SIGHUP, triggering config reload")
            if self._reload_handler:
                self._reload_handler()

        signal.signal(signal.SIGHUP, _handle_sighup)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-node && uv run pytest tests/test_platform_systemd.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-node/src/astromesh_node/platform/systemd.py astromesh-node/tests/test_platform_systemd.py
git commit -m "feat(node): add SystemdManager platform adapter for Linux"
```

---

## Task 4: Platform adapter — LaunchdManager (macOS)

**Files:**
- Create: `astromesh-node/src/astromesh_node/platform/launchd.py`
- Test: `astromesh-node/tests/test_platform_launchd.py`

- [ ] **Step 1: Write tests for LaunchdManager**

Create `astromesh-node/tests/test_platform_launchd.py`:

```python
"""Tests for LaunchdManager (macOS launchd adapter)."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.launchd import LaunchdManager


@pytest.fixture
def manager():
    return LaunchdManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_is_noop(manager):
    await manager.notify_ready()  # launchd assumes ready


async def test_notify_stopping_is_noop(manager):
    await manager.notify_stopping()


async def test_install_service_calls_launchctl(manager):
    with patch("astromesh_node.platform.launchd.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        with patch("astromesh_node.platform.launchd.shutil") as mock_shutil:
            with patch("astromesh_node.platform.launchd.Path") as mock_path:
                mock_path.return_value.exists.return_value = True
                await manager.install_service("full")


async def test_service_status_parses_launchctl(manager):
    launchctl_output = b'{\n\t"PID" = 1234;\n\t"Label" = "com.astromesh.daemon";\n};\n'
    with patch("astromesh_node.platform.launchd.asyncio") as mock_asyncio:
        proc = AsyncMock()
        proc.communicate.return_value = (launchctl_output, b"")
        proc.returncode = 0
        mock_asyncio.create_subprocess_exec = AsyncMock(return_value=proc)
        status = await manager.service_status()
        assert status["mode"] == "launchd"


def test_register_reload_handler_sets_sighup(manager):
    callback = MagicMock()
    with patch("astromesh_node.platform.launchd.signal") as mock_signal:
        manager.register_reload_handler(callback)
        mock_signal.signal.assert_called_once()
        assert mock_signal.signal.call_args[0][0] == mock_signal.SIGHUP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-node && uv run pytest tests/test_platform_launchd.py -v`
Expected: FAIL

- [ ] **Step 3: Write LaunchdManager**

Create `astromesh-node/src/astromesh_node/platform/launchd.py`:

```python
"""LaunchdManager — macOS launchd service adapter."""

from __future__ import annotations

import asyncio
import logging
import shutil
import signal
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.launchd")

PLIST_LABEL = "com.astromesh.daemon"
PLIST_DST = Path("/Library/LaunchDaemons") / f"{PLIST_LABEL}.plist"
PLIST_SRC = Path(__file__).parent.parent.parent.parent / "packaging" / "launchd" / f"{PLIST_LABEL}.plist"


class LaunchdManager:
    """ServiceManager implementation for macOS launchd."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None

    async def notify_ready(self) -> None:
        pass  # launchd assumes the process is ready once started

    async def notify_reload(self) -> None:
        pass  # Reload handled via SIGHUP in register_reload_handler

    async def notify_stopping(self) -> None:
        pass

    async def install_service(self, profile: str) -> None:
        if PLIST_SRC.exists():
            shutil.copy2(PLIST_SRC, PLIST_DST)
        proc = await asyncio.create_subprocess_exec(
            "launchctl", "load", "-w", str(PLIST_DST),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("Loaded %s", PLIST_LABEL)

    async def uninstall_service(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "launchctl", "unload", str(PLIST_DST),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if PLIST_DST.exists():
            PLIST_DST.unlink()
        logger.info("Unloaded %s", PLIST_LABEL)

    async def service_status(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "launchctl", "list", PLIST_LABEL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        pid = None
        running = False
        if proc.returncode == 0 and '"PID"' in output:
            running = True
            for line in output.splitlines():
                if '"PID"' in line:
                    pid = int("".join(c for c in line if c.isdigit()))
                    break

        return {
            "running": running,
            "enabled": PLIST_DST.exists(),
            "pid": pid,
            "mode": "launchd",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback

        def _handle_sighup(signum, frame):
            logger.info("Received SIGHUP, triggering config reload")
            if self._reload_handler:
                self._reload_handler()

        signal.signal(signal.SIGHUP, _handle_sighup)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-node && uv run pytest tests/test_platform_launchd.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh-node/src/astromesh_node/platform/launchd.py astromesh-node/tests/test_platform_launchd.py
git commit -m "feat(node): add LaunchdManager platform adapter for macOS"
```

---

## Task 5: Platform adapter — WindowsServiceManager

**Files:**
- Create: `astromesh-node/src/astromesh_node/platform/windows.py`
- Test: `astromesh-node/tests/test_platform_windows.py`

- [ ] **Step 1: Write tests for WindowsServiceManager**

Create `astromesh-node/tests/test_platform_windows.py`:

```python
"""Tests for WindowsServiceManager (Windows Service adapter)."""

import pytest
from unittest.mock import patch, MagicMock

from astromesh_node.platform.base import ServiceManagerProtocol
from astromesh_node.platform.windows import WindowsServiceManager


@pytest.fixture
def manager():
    return WindowsServiceManager()


def test_implements_protocol(manager):
    assert isinstance(manager, ServiceManagerProtocol)


async def test_notify_ready_is_noop_without_win32(manager):
    """notify_ready gracefully degrades when not running as Windows Service."""
    with patch.object(manager, "_service_handle", None):
        await manager.notify_ready()  # Should not raise


async def test_notify_stopping_is_noop_without_win32(manager):
    with patch.object(manager, "_service_handle", None):
        await manager.notify_stopping()


async def test_service_status_returns_dict(manager):
    with patch("astromesh_node.platform.windows.subprocess") as mock_sub:
        mock_sub.run.return_value = MagicMock(
            returncode=0,
            stdout="STATE              : 4  RUNNING\nPID                : 5678\n",
        )
        status = await manager.service_status()
        assert status["mode"] == "windows_service"


def test_register_reload_handler_stores_callback(manager):
    callback = MagicMock()
    manager.register_reload_handler(callback)
    assert manager._reload_handler == callback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd astromesh-node && uv run pytest tests/test_platform_windows.py -v`
Expected: FAIL

- [ ] **Step 3: Write WindowsServiceManager**

Create `astromesh-node/src/astromesh_node/platform/windows.py`:

```python
"""WindowsServiceManager — Windows Service adapter."""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Callable

logger = logging.getLogger("astromesh_node.platform.windows")

SERVICE_NAME = "astromeshd"
SERVICE_DISPLAY = "Astromesh Agent Runtime Daemon"


class WindowsServiceManager:
    """ServiceManager implementation for Windows Services."""

    def __init__(self) -> None:
        self._reload_handler: Callable[[], Any] | None = None
        self._service_handle = None

    async def notify_ready(self) -> None:
        # When running as a Windows Service, the service wrapper
        # (astromeshd-service.py) handles ReportServiceStatus(RUNNING).
        # This is a no-op from daemon core perspective.
        pass

    async def notify_reload(self) -> None:
        pass

    async def notify_stopping(self) -> None:
        pass

    async def install_service(self, profile: str) -> None:
        try:
            import win32serviceutil
            import win32service

            win32serviceutil.InstallService(
                None,  # class — handled by astromeshd-service.py
                SERVICE_NAME,
                SERVICE_DISPLAY,
                startType=win32service.SERVICE_AUTO_START,
            )
            logger.info("Installed Windows Service: %s", SERVICE_NAME)
        except ImportError:
            # Fallback: use sc.exe
            result = subprocess.run(
                ["sc", "create", SERVICE_NAME,
                 "binPath=", _get_service_binpath(),
                 "start=", "auto",
                 "DisplayName=", SERVICE_DISPLAY],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                logger.info("Installed Windows Service via sc.exe: %s", SERVICE_NAME)
            else:
                raise RuntimeError(f"Failed to install service: {result.stderr}")

    async def uninstall_service(self) -> None:
        try:
            import win32serviceutil

            win32serviceutil.RemoveService(SERVICE_NAME)
            logger.info("Removed Windows Service: %s", SERVICE_NAME)
        except ImportError:
            subprocess.run(
                ["sc", "delete", SERVICE_NAME],
                capture_output=True, text=True,
            )

    async def service_status(self) -> dict[str, Any]:
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            "sc", "query", SERVICE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()
        stdout = stdout_bytes.decode()
        running = "RUNNING" in stdout if proc.returncode == 0 else False
        pid = None
        for line in stdout.splitlines():
            if "PID" in line:
                pid = int("".join(c for c in line if c.isdigit()) or "0") or None
                break

        return {
            "running": running,
            "enabled": proc.returncode == 0,
            "pid": pid,
            "mode": "windows_service",
        }

    def register_reload_handler(self, callback: Callable[[], Any]) -> None:
        self._reload_handler = callback
        # Windows reload is handled by the service wrapper sending a custom
        # control code or via named pipe. No SIGHUP equivalent.


def _get_service_binpath() -> str:
    """Get the binpath for sc.exe create command."""
    import sys
    from pathlib import Path

    venv = Path(sys.executable).parent
    service_py = venv.parent / "packaging" / "windows" / "astromeshd-service.py"
    return f'"{sys.executable}" "{service_py}"'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd astromesh-node && uv run pytest tests/test_platform_windows.py -v`
Expected: PASS

- [ ] **Step 5: Run all platform detect tests**

Run: `cd astromesh-node && uv run pytest tests/test_platform_detect.py -v`
Expected: PASS (all three adapters now exist)

- [ ] **Step 6: Commit**

```bash
git add astromesh-node/src/astromesh_node/platform/windows.py astromesh-node/tests/test_platform_windows.py
git commit -m "feat(node): add WindowsServiceManager platform adapter"
```

---

## Task 6: Installer abstraction — InstallerProtocol + platform installers

**Files:**
- Create: `astromesh-node/src/astromesh_node/installer/__init__.py`
- Create: `astromesh-node/src/astromesh_node/installer/base.py`
- Create: `astromesh-node/src/astromesh_node/installer/detect.py`
- Create: `astromesh-node/src/astromesh_node/installer/linux.py`
- Create: `astromesh-node/src/astromesh_node/installer/macos.py`
- Create: `astromesh-node/src/astromesh_node/installer/windows.py`
- Test: `astromesh-node/tests/test_installer_base.py`
- Test: `astromesh-node/tests/test_installer_linux.py`
- Test: `astromesh-node/tests/test_installer_macos.py`
- Test: `astromesh-node/tests/test_installer_windows.py`

- [ ] **Step 1: Write test for InstallerProtocol**

Create `astromesh-node/tests/test_installer_base.py`:

```python
"""Tests for InstallerProtocol."""

from astromesh_node.installer.base import InstallerProtocol


def test_protocol_is_runtime_checkable():
    assert hasattr(InstallerProtocol, "__protocol_attrs__") or hasattr(
        InstallerProtocol, "__abstractmethods__"
    )
```

- [ ] **Step 2: Write InstallerProtocol and detect**

Create `astromesh-node/src/astromesh_node/installer/__init__.py`:

```python
"""Installer abstraction — platform-specific filesystem and service setup."""

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.detect import get_installer

__all__ = ["InstallerProtocol", "get_installer"]
```

Create `astromesh-node/src/astromesh_node/installer/base.py`:

```python
"""InstallerProtocol — abstracts platform-specific installation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class InstallerProtocol(Protocol):
    """Abstraction for platform-specific installation paths and actions."""

    def config_dir(self) -> Path: ...
    def data_dir(self) -> Path: ...
    def log_dir(self) -> Path: ...
    def bin_dir(self) -> Path: ...
    async def install(self, profile: str, dry_run: bool = False) -> None: ...
    async def uninstall(self, keep_data: bool = True) -> None: ...
    async def verify(self) -> list[str]: ...
```

Create `astromesh-node/src/astromesh_node/installer/detect.py`:

```python
"""Auto-detection of the platform's installer."""

from __future__ import annotations

import sys

from astromesh_node.installer.base import InstallerProtocol


def get_installer() -> InstallerProtocol:
    """Return the appropriate Installer for the current platform."""
    if sys.platform == "linux":
        from astromesh_node.installer.linux import LinuxInstaller

        return LinuxInstaller()
    elif sys.platform == "darwin":
        from astromesh_node.installer.macos import MacOSInstaller

        return MacOSInstaller()
    elif sys.platform == "win32":
        from astromesh_node.installer.windows import WindowsInstaller

        return WindowsInstaller()
    else:
        from astromesh_node.platform.base import UnsupportedPlatformError

        raise UnsupportedPlatformError(f"Platform {sys.platform} is not supported")
```

- [ ] **Step 3: Write tests for LinuxInstaller**

Create `astromesh-node/tests/test_installer_linux.py`:

```python
"""Tests for LinuxInstaller."""

from pathlib import Path

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.linux import LinuxInstaller


def test_implements_protocol():
    installer = LinuxInstaller()
    assert isinstance(installer, InstallerProtocol)


def test_config_dir():
    assert LinuxInstaller().config_dir() == Path("/etc/astromesh")


def test_data_dir():
    assert LinuxInstaller().data_dir() == Path("/var/lib/astromesh")


def test_log_dir():
    assert LinuxInstaller().log_dir() == Path("/var/log/astromesh")


def test_bin_dir():
    assert LinuxInstaller().bin_dir() == Path("/opt/astromesh/venv")


async def test_verify_returns_list():
    installer = LinuxInstaller()
    problems = await installer.verify()
    assert isinstance(problems, list)
```

- [ ] **Step 4: Write LinuxInstaller**

Create `astromesh-node/src/astromesh_node/installer/linux.py`:

```python
"""LinuxInstaller — FHS-compliant paths and Linux-specific setup."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("astromesh_node.installer.linux")


class LinuxInstaller:
    """Installer for Linux (Debian/Ubuntu, RHEL/Fedora)."""

    def config_dir(self) -> Path:
        return Path("/etc/astromesh")

    def data_dir(self) -> Path:
        return Path("/var/lib/astromesh")

    def log_dir(self) -> Path:
        return Path("/var/log/astromesh")

    def bin_dir(self) -> Path:
        return Path("/opt/astromesh/venv")

    async def install(self, profile: str, dry_run: bool = False) -> None:
        dirs = [
            self.config_dir(),
            self.data_dir() / "models",
            self.data_dir() / "memory",
            self.data_dir() / "data",
            self.log_dir() / "audit",
        ]
        for d in dirs:
            if dry_run:
                logger.info("[dry-run] mkdir %s", d)
            else:
                d.mkdir(parents=True, exist_ok=True)
                logger.info("Created %s", d)

    async def uninstall(self, keep_data: bool = True) -> None:
        import shutil

        if not keep_data:
            for d in [self.data_dir(), self.log_dir()]:
                if d.exists():
                    shutil.rmtree(d)
                    logger.info("Removed %s", d)

    async def verify(self) -> list[str]:
        problems = []
        for d in [self.config_dir(), self.data_dir(), self.log_dir()]:
            if not d.exists():
                problems.append(f"Directory missing: {d}")
        runtime_yaml = self.config_dir() / "runtime.yaml"
        if not runtime_yaml.exists():
            problems.append("Config missing: runtime.yaml (run 'astromeshctl init')")
        return problems
```

- [ ] **Step 5: Write MacOSInstaller**

Create `astromesh-node/tests/test_installer_macos.py`:

```python
"""Tests for MacOSInstaller."""

from pathlib import Path

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.macos import MacOSInstaller


def test_implements_protocol():
    assert isinstance(MacOSInstaller(), InstallerProtocol)


def test_config_dir():
    assert MacOSInstaller().config_dir() == Path("/Library/Application Support/Astromesh/config")


def test_data_dir():
    assert MacOSInstaller().data_dir() == Path("/Library/Application Support/Astromesh/data")


def test_log_dir():
    assert MacOSInstaller().log_dir() == Path("/Library/Logs/Astromesh")


def test_bin_dir():
    assert MacOSInstaller().bin_dir() == Path("/usr/local/opt/astromesh/venv")
```

Create `astromesh-node/src/astromesh_node/installer/macos.py`:

```python
"""MacOSInstaller — macOS-specific paths and setup."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("astromesh_node.installer.macos")


class MacOSInstaller:
    """Installer for macOS."""

    def config_dir(self) -> Path:
        return Path("/Library/Application Support/Astromesh/config")

    def data_dir(self) -> Path:
        return Path("/Library/Application Support/Astromesh/data")

    def log_dir(self) -> Path:
        return Path("/Library/Logs/Astromesh")

    def bin_dir(self) -> Path:
        return Path("/usr/local/opt/astromesh/venv")

    async def install(self, profile: str, dry_run: bool = False) -> None:
        dirs = [
            self.config_dir(),
            self.data_dir() / "models",
            self.data_dir() / "memory",
            self.data_dir() / "data",
            self.log_dir(),
        ]
        for d in dirs:
            if dry_run:
                logger.info("[dry-run] mkdir %s", d)
            else:
                d.mkdir(parents=True, exist_ok=True)
                logger.info("Created %s", d)

    async def uninstall(self, keep_data: bool = True) -> None:
        import shutil

        if not keep_data:
            for d in [self.data_dir(), self.log_dir()]:
                if d.exists():
                    shutil.rmtree(d)
                    logger.info("Removed %s", d)

    async def verify(self) -> list[str]:
        problems = []
        for d in [self.config_dir(), self.data_dir(), self.log_dir()]:
            if not d.exists():
                problems.append(f"Directory missing: {d}")
        runtime_yaml = self.config_dir() / "runtime.yaml"
        if not runtime_yaml.exists():
            problems.append("Config missing: runtime.yaml (run 'astromeshctl init')")
        return problems
```

- [ ] **Step 6: Write WindowsInstaller**

Create `astromesh-node/tests/test_installer_windows.py`:

```python
"""Tests for WindowsInstaller."""

from pathlib import Path
from unittest.mock import patch

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.windows import WindowsInstaller


def test_implements_protocol():
    assert isinstance(WindowsInstaller(), InstallerProtocol)


def test_config_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramData": "C:\\ProgramData"}
        installer = WindowsInstaller()
        assert installer.config_dir() == Path("C:\\ProgramData\\Astromesh\\config")


def test_bin_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramFiles": "C:\\Program Files"}
        installer = WindowsInstaller()
        assert installer.bin_dir() == Path("C:\\Program Files\\Astromesh\\venv")
```

Create `astromesh-node/src/astromesh_node/installer/windows.py`:

```python
"""WindowsInstaller — Windows-specific paths and setup."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("astromesh_node.installer.windows")


class WindowsInstaller:
    """Installer for Windows."""

    def _program_data(self) -> Path:
        return Path(os.environ.get("ProgramData", "C:\\ProgramData"))

    def _program_files(self) -> Path:
        return Path(os.environ.get("ProgramFiles", "C:\\Program Files"))

    def config_dir(self) -> Path:
        return self._program_data() / "Astromesh" / "config"

    def data_dir(self) -> Path:
        return self._program_data() / "Astromesh" / "data"

    def log_dir(self) -> Path:
        return self._program_data() / "Astromesh" / "logs"

    def bin_dir(self) -> Path:
        return self._program_files() / "Astromesh" / "venv"

    async def install(self, profile: str, dry_run: bool = False) -> None:
        dirs = [
            self.config_dir(),
            self.data_dir() / "models",
            self.data_dir() / "memory",
            self.data_dir() / "data",
            self.log_dir(),
        ]
        for d in dirs:
            if dry_run:
                logger.info("[dry-run] mkdir %s", d)
            else:
                d.mkdir(parents=True, exist_ok=True)
                logger.info("Created %s", d)

    async def uninstall(self, keep_data: bool = True) -> None:
        import shutil

        if not keep_data:
            for d in [self.data_dir(), self.log_dir()]:
                if d.exists():
                    shutil.rmtree(d)
                    logger.info("Removed %s", d)

    async def verify(self) -> list[str]:
        problems = []
        for d in [self.config_dir(), self.data_dir(), self.log_dir()]:
            if not d.exists():
                problems.append(f"Directory missing: {d}")
        runtime_yaml = self.config_dir() / "runtime.yaml"
        if not runtime_yaml.exists():
            problems.append("Config missing: runtime.yaml (run 'astromeshctl init')")
        return problems
```

- [ ] **Step 7: Run all installer tests**

Run: `cd astromesh-node && uv run pytest tests/test_installer_*.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add astromesh-node/src/astromesh_node/installer/ astromesh-node/tests/test_installer_*.py
git commit -m "feat(node): add InstallerProtocol with Linux, macOS, and Windows installers"
```

---

## Task 7: Daemon core refactor — extract from daemon/astromeshd.py

**Files:**
- Create: `astromesh-node/src/astromesh_node/daemon/__init__.py`
- Create: `astromesh-node/src/astromesh_node/daemon/config.py`
- Create: `astromesh-node/src/astromesh_node/daemon/core.py`
- Test: `astromesh-node/tests/test_daemon_config.py`
- Test: `astromesh-node/tests/test_daemon_core.py`

- [ ] **Step 1: Write tests for DaemonConfig**

Create `astromesh-node/tests/test_daemon_config.py`:

```python
"""Tests for daemon config loading and path detection."""

import pytest
from pathlib import Path
from unittest.mock import patch

from astromesh_node.daemon.config import DaemonConfig, detect_config_dir


def test_daemon_config_defaults():
    cfg = DaemonConfig()
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8000
    assert cfg.log_level == "info"


def test_daemon_config_from_dict():
    data = {
        "spec": {
            "api": {"host": "127.0.0.1", "port": 9000},
            "services": {"api": True, "agents": True},
            "peers": [{"name": "node2"}],
            "mesh": {"enabled": True},
        }
    }
    cfg = DaemonConfig.from_dict(data)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9000
    assert cfg.services == {"api": True, "agents": True}


def test_detect_config_dir_explicit():
    assert detect_config_dir("/custom/path") == "/custom/path"


def test_detect_config_dir_dev_mode(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "runtime.yaml").write_text("spec: {}")
    with patch("astromesh_node.daemon.config.Path.cwd", return_value=tmp_path):
        result = detect_config_dir(None)
        assert result == str(config_dir)
```

- [ ] **Step 2: Write DaemonConfig**

Create `astromesh-node/src/astromesh_node/daemon/__init__.py`:

```python
"""Astromesh daemon — platform-agnostic runtime."""
```

Create `astromesh-node/src/astromesh_node/daemon/config.py`:

```python
"""Daemon configuration loading and path detection."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from astromesh_node.installer.detect import get_installer


def _system_config_dir() -> str:
    """Return the system config dir for the current platform."""
    try:
        installer = get_installer()
        return str(installer.config_dir())
    except Exception:
        return "/etc/astromesh"  # Fallback for unknown platforms


@dataclass
class DaemonConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    services: dict[str, bool] = field(default_factory=dict)
    peers: list[dict] = field(default_factory=list)
    mesh: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> DaemonConfig:
        """Create config from parsed YAML dict."""
        spec = data.get("spec", {})
        api = spec.get("api", {})
        return cls(
            host=api.get("host", cls.host),
            port=api.get("port", cls.port),
            services=spec.get("services", {}),
            peers=spec.get("peers", []),
            mesh=spec.get("mesh", {}),
        )

    @classmethod
    def from_config_dir(cls, config_dir: str) -> DaemonConfig:
        """Load config from a directory containing runtime.yaml."""
        runtime_path = Path(config_dir) / "runtime.yaml"
        if not runtime_path.exists():
            return cls()
        data = yaml.safe_load(runtime_path.read_text()) or {}
        return cls.from_dict(data)


def detect_config_dir(explicit: str | None) -> str:
    """Auto-detect the config directory.

    Priority: explicit arg > system config > local ./config/ > system default.
    """
    if explicit:
        return explicit

    system_dir = _system_config_dir()
    if os.path.exists(os.path.join(system_dir, "runtime.yaml")):
        return system_dir

    local_config = Path.cwd() / "config"
    if (local_config / "runtime.yaml").exists():
        return str(local_config)

    return system_dir
```

- [ ] **Step 3: Run config tests**

Run: `cd astromesh-node && uv run pytest tests/test_daemon_config.py -v`
Expected: PASS

- [ ] **Step 4: Write test for daemon core**

Create `astromesh-node/tests/test_daemon_core.py`:

```python
"""Tests for daemon core — argument parsing."""

from astromesh_node.daemon.core import parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.config is None
    assert args.host is None
    assert args.port is None
    assert args.log_level == "info"
    assert args.foreground is False


def test_parse_args_foreground():
    args = parse_args(["--foreground"])
    assert args.foreground is True


def test_parse_args_config():
    args = parse_args(["--config", "/etc/astromesh"])
    assert args.config == "/etc/astromesh"
```

- [ ] **Step 5: Write daemon core**

Create `astromesh-node/src/astromesh_node/daemon/core.py`:

This is the refactored version of `daemon/astromeshd.py`. Key changes:
- Uses `ServiceManagerProtocol` instead of direct sdnotify
- Uses `detect_config_dir` from `daemon.config` (platform-aware)
- Adds `--foreground` flag
- No hardcoded paths

```python
"""astromeshd — Astromesh Agent Runtime Daemon (platform-agnostic)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from astromesh_node.daemon.config import DaemonConfig, detect_config_dir
from astromesh_node.installer.detect import get_installer
from astromesh_node.platform.detect import get_service_manager

logger = logging.getLogger("astromeshd")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="astromeshd",
        description="Astromesh Agent Runtime Daemon",
    )
    parser.add_argument("--config", type=str, default=None, help="Config directory")
    parser.add_argument("--host", type=str, default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument(
        "--log-level", type=str, default="info",
        choices=["debug", "info", "warning", "error"],
    )
    parser.add_argument(
        "--foreground", action="store_true",
        help="Run in foreground mode (no init system integration)",
    )
    parser.add_argument("--pid-file", type=str, default=None, help="PID file path")
    return parser.parse_args(argv)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _default_pid_file() -> str:
    """Return the default PID file path for the current platform."""
    try:
        installer = get_installer()
        return str(installer.data_dir() / "astromeshd.pid")
    except Exception:
        return "/var/lib/astromesh/data/astromeshd.pid"


def write_pid_file(pid_file: str) -> None:
    Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
    Path(pid_file).write_text(str(os.getpid()))


def remove_pid_file(pid_file: str) -> None:
    path = Path(pid_file)
    if path.exists():
        path.unlink()


async def run_daemon(args: argparse.Namespace) -> None:
    import uvicorn

    from astromesh.api.main import app
    from astromesh.api.routes import agents, system
    from astromesh.runtime.engine import AgentRuntime
    from astromesh.runtime.peers import PeerClient
    from astromesh.runtime.services import ServiceManager

    config_dir = detect_config_dir(args.config)
    daemon_config = DaemonConfig.from_config_dir(config_dir)

    host = args.host or daemon_config.host
    port = args.port or daemon_config.port
    pid_file = args.pid_file or _default_pid_file()

    # Platform service manager
    service_mgr = get_service_manager(foreground=args.foreground)

    # Create service manager and peer client
    service_manager = ServiceManager(daemon_config.services)
    peer_client = PeerClient(daemon_config.peers)

    # Create mesh if enabled
    mesh_manager = None
    elector = None
    from astromesh.mesh.config import MeshConfig

    mesh_config = MeshConfig.from_dict(daemon_config.mesh)
    if mesh_config.enabled:
        from astromesh.mesh.leader import LeaderElector
        from astromesh.mesh.manager import MeshManager

        mesh_manager = MeshManager(mesh_config, service_manager)
        elector = LeaderElector(mesh_manager)
        peer_client = PeerClient.from_mesh(mesh_manager)
        logger.info("Mesh enabled, node: %s", mesh_config.node_name)
        if daemon_config.peers:
            logger.warning("spec.peers ignored when mesh is enabled")

    enabled = service_manager.enabled_services()
    logger.info("Enabled services: %s", ", ".join(enabled))
    for warning in service_manager.validate():
        logger.warning("Config warning: %s", warning)
    if daemon_config.peers:
        logger.info("Peers: %s", ", ".join(p["name"] for p in daemon_config.peers))

    installer = get_installer()
    system_dir = str(installer.config_dir())
    mode = "system" if config_dir == system_dir else "dev"
    logger.info("Starting astromeshd in %s mode", mode)
    logger.info("Config directory: %s", config_dir)

    write_pid_file(pid_file)

    runtime = AgentRuntime(
        config_dir=config_dir,
        service_manager=service_manager,
        peer_client=peer_client,
    )
    await runtime.bootstrap()

    agents.set_runtime(runtime)
    system.set_runtime(runtime)

    from astromesh.api.routes import memory as memory_routes

    memory_routes.set_runtime(runtime)

    from astromesh.api.routes import mesh as mesh_routes

    mesh_routes.set_mesh(mesh_manager, elector)

    agent_count = len(runtime.list_agents())
    logger.info("Loaded %d agent(s)", agent_count)

    if mesh_manager:
        mesh_manager.update_agents([a["name"] for a in runtime.list_agents()])
        await mesh_manager.join()
        elector.elect()
        logger.info(
            "Mesh joined, cluster size: %d", len(mesh_manager.cluster_state().nodes)
        )

    runtime.mesh_manager = mesh_manager

    # Notify init system: ready
    await service_mgr.notify_ready()

    config = uvicorn.Config(
        app=app, host=host, port=port,
        log_level=args.log_level, access_log=True,
    )
    server = uvicorn.Server(config)

    loop = asyncio.get_event_loop()

    def handle_shutdown(sig, frame):
        logger.info("Received %s, shutting down...", signal.Signals(sig).name)
        server.should_exit = True

    if sys.platform != "win32":
        loop.add_signal_handler(
            signal.SIGTERM, lambda: handle_shutdown(signal.SIGTERM, None)
        )
        loop.add_signal_handler(
            signal.SIGINT, lambda: handle_shutdown(signal.SIGINT, None)
        )
    else:
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)

    # Register reload handler with platform adapter
    def _reload_config():
        logger.info("Config reload triggered")
        # Re-read config — actual reload logic can be expanded

    service_mgr.register_reload_handler(_reload_config)

    mesh_tasks = []
    if mesh_manager:

        async def _gossip_loop():
            while not server.should_exit:
                try:
                    await mesh_manager.gossip_once()
                except Exception as e:
                    logger.debug("Gossip error: %s", e)
                await asyncio.sleep(mesh_config.gossip_interval)

        async def _heartbeat_loop():
            while not server.should_exit:
                try:
                    await mesh_manager.heartbeat_once()
                except Exception as e:
                    logger.debug("Heartbeat error: %s", e)
                await asyncio.sleep(mesh_config.heartbeat_interval)

        mesh_tasks.append(asyncio.create_task(_gossip_loop()))
        mesh_tasks.append(asyncio.create_task(_heartbeat_loop()))

    try:
        await server.serve()
    finally:
        await service_mgr.notify_stopping()
        for task in mesh_tasks:
            task.cancel()
        if mesh_manager:
            await mesh_manager.leave()
            await mesh_manager.close()
        remove_pid_file(pid_file)
        logger.info("astromeshd stopped")


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)
    asyncio.run(run_daemon(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run daemon tests**

Run: `cd astromesh-node && uv run pytest tests/test_daemon_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add astromesh-node/src/astromesh_node/daemon/ astromesh-node/tests/test_daemon_*.py
git commit -m "feat(node): refactor daemon core to be platform-agnostic"
```

---

## Task 8: Move CLI to subproject

**Files:**
- Move: `cli/main.py` → `astromesh-node/src/astromesh_node/cli/main.py`
- Move: `cli/commands/*.py` → `astromesh-node/src/astromesh_node/cli/commands/`
- Move: `cli/client.py` → `astromesh-node/src/astromesh_node/cli/client.py`
- Move: `cli/output.py` → `astromesh-node/src/astromesh_node/cli/output.py`

- [ ] **Step 1: Create CLI directories**

```bash
mkdir -p astromesh-node/src/astromesh_node/cli/commands
```

- [ ] **Step 2: Copy CLI files to new location**

```bash
cp cli/main.py astromesh-node/src/astromesh_node/cli/main.py
cp cli/client.py astromesh-node/src/astromesh_node/cli/client.py
cp cli/output.py astromesh-node/src/astromesh_node/cli/output.py
cp cli/__init__.py astromesh-node/src/astromesh_node/cli/__init__.py
cp cli/commands/*.py astromesh-node/src/astromesh_node/cli/commands/
```

- [ ] **Step 3: Update imports in all CLI files**

In `astromesh-node/src/astromesh_node/cli/main.py`:
- Change `from cli.commands import ...` → `from astromesh_node.cli.commands import ...`
- Change `help="Astromesh OS CLI management tool."` → `help="Astromesh Node CLI management tool."`

In each `astromesh-node/src/astromesh_node/cli/commands/*.py`:
- Change `from cli.client import ...` → `from astromesh_node.cli.client import ...`
- Change `from cli.output import ...` → `from astromesh_node.cli.output import ...`
- Change any `from cli.commands import ...` → `from astromesh_node.cli.commands import ...`

- [ ] **Step 4: Verify imports parse correctly**

Run: `cd astromesh-node && python -c "from astromesh_node.cli.main import app; print(app.info.name)"`
Expected: `astromeshctl`

- [ ] **Step 5: Run CLI smoke test**

Run: `cd astromesh-node && uv run astromeshctl --help`
Expected: Shows help text with "Astromesh Node CLI management tool." and all subcommands listed.

- [ ] **Step 6: Commit**

```bash
git add astromesh-node/src/astromesh_node/cli/
git commit -m "feat(node): move CLI to astromesh-node subproject and update imports"
```

---

## Task 9: Move packaging and config to subproject

**Files:**
- Move: `packaging/` → `astromesh-node/packaging/`
- Move: `nfpm.yaml` → `astromesh-node/packaging/nfpm.yaml`
- Move: `config/profiles/` → `astromesh-node/config/profiles/`

- [ ] **Step 1: Copy packaging files**

```bash
cp -r packaging/ astromesh-node/packaging/
cp nfpm.yaml astromesh-node/packaging/nfpm.yaml
mkdir -p astromesh-node/config
cp -r config/profiles/ astromesh-node/config/profiles/
```

- [ ] **Step 2: Update nfpm.yaml for new package name and rpm support**

Edit `astromesh-node/packaging/nfpm.yaml`:
- Change `name: astromesh` → `name: astromesh-node`
- Add `replaces: [astromesh]` and `conflicts: [astromesh]` for upgrade path
- Update `src:` paths to be relative to `astromesh-node/`

- [ ] **Step 3: Update build-deb.sh paths**

Edit `astromesh-node/packaging/build-deb.sh`:
- Update version extraction to read from `astromesh-node/pyproject.toml`
- Update `uv pip install` to install from `astromesh-node/` directory
- Update `nfpm` config path to `packaging/nfpm.yaml`

- [ ] **Step 4: Create build-rpm.sh**

Create `astromesh-node/packaging/build-rpm.sh` — mirrors `build-deb.sh` but uses `nfpm package --packager rpm`.

- [ ] **Step 5: Create launchd plist**

Create `astromesh-node/packaging/launchd/com.astromesh.daemon.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.astromesh.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/opt/astromesh/venv/bin/astromeshd</string>
        <string>--config</string>
        <string>/Library/Application Support/Astromesh/config</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>UserName</key>
    <string>_astromesh</string>
    <key>StandardOutPath</key>
    <string>/Library/Logs/Astromesh/astromeshd.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Library/Logs/Astromesh/astromeshd.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/opt/astromesh/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

- [ ] **Step 6: Create Windows service wrapper**

Create `astromesh-node/packaging/windows/astromeshd-service.py`:

```python
"""Windows Service wrapper for astromeshd."""

import sys
import os

# Only import win32 on Windows
if sys.platform == "win32":
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil


    class AstromeshService(win32serviceutil.ServiceFramework):
        _svc_name_ = "astromeshd"
        _svc_display_name_ = "Astromesh Agent Runtime Daemon"
        _svc_description_ = "Runs the Astromesh AI agent runtime as a Windows service"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            from astromesh_node.daemon.core import main
            main()


    if __name__ == "__main__":
        win32serviceutil.HandleCommandLine(AstromeshService)
```

- [ ] **Step 7: Create build-macos.sh**

Create `astromesh-node/packaging/build-macos.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "Building astromesh-node ${VERSION} for macOS..."

STAGING="staging/macos"
rm -rf "$STAGING" dist/*.tar.gz
mkdir -p "$STAGING"

# Create venv and install
python3 -m venv "$STAGING/venv"
"$STAGING/venv/bin/pip" install --quiet ../ ./

# Copy packaging files
cp packaging/launchd/com.astromesh.daemon.plist "$STAGING/"
cp packaging/scripts/install.sh "$STAGING/"

# Create tarball
mkdir -p dist
tar czf "dist/astromesh-node-${VERSION}-macos.tar.gz" -C "$STAGING" .
echo "Built dist/astromesh-node-${VERSION}-macos.tar.gz"
```

- [ ] **Step 8: Create build-windows.ps1**

Create `astromesh-node/packaging/build-windows.ps1`:

```powershell
$ErrorActionPreference = "Stop"

$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
Write-Host "Building astromesh-node $version for Windows..."

$staging = "staging\windows"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null

# Create venv and install
python -m venv "$staging\venv"
& "$staging\venv\Scripts\pip" install --quiet ..\  .\[windows]

# Copy files
Copy-Item "packaging\windows\astromeshd-service.py" "$staging\"
Copy-Item "packaging\scripts\install.ps1" "$staging\"

# Create zip
New-Item -ItemType Directory -Path dist -Force | Out-Null
Compress-Archive -Path "$staging\*" -DestinationPath "dist\astromesh-node-$version-windows.zip" -Force
Write-Host "Built dist\astromesh-node-$version-windows.zip"
```

- [ ] **Step 9: Create install.ps1 for Windows**

Create `astromesh-node/packaging/scripts/install.ps1`:

```powershell
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

Write-Host "Installing Astromesh Node for Windows..."

$programFiles = $env:ProgramFiles
$programData = $env:ProgramData

# Create directories
$dirs = @(
    "$programData\Astromesh\config",
    "$programData\Astromesh\data\models",
    "$programData\Astromesh\data\memory",
    "$programData\Astromesh\data\data",
    "$programData\Astromesh\logs"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# Copy venv to ProgramFiles
$destVenv = "$programFiles\Astromesh\venv"
if (Test-Path "venv") {
    Copy-Item -Recurse -Force "venv" $destVenv
}

# Add to PATH
$binPath = "$destVenv\Scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($currentPath -notlike "*$binPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$binPath", "Machine")
    Write-Host "Added $binPath to system PATH"
}

Write-Host "Installation complete. Run 'astromeshctl init' to configure."
```

- [ ] **Step 10: Commit**

```bash
git add astromesh-node/packaging/ astromesh-node/config/
git commit -m "feat(node): move packaging and config profiles to subproject, add rpm/macOS/Windows builds"
```

---

## Task 10: Clean up monorepo root — remove migrated files and update references

**Files:**
- Modify: `pyproject.toml` (root)
- Delete: `daemon/`, `cli/`, `packaging/`, `nfpm.yaml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update root pyproject.toml**

Remove entry points and extras that belong to astromesh-node:
- Remove `[project.scripts]` entries for `astromeshd` and `astromeshctl`
- Remove `cli` and `daemon` from `[project.optional-dependencies]`
- Remove `cli` and `daemon` from the `all` extra

- [ ] **Step 2: Delete migrated directories**

```bash
rm -rf daemon/ cli/ packaging/ nfpm.yaml
```

- [ ] **Step 3: Rename "Astromesh OS" to "Astromesh Node" in README.md**

Search and replace all occurrences of "Astromesh OS" → "Astromesh Node" and "astromesh-os" → "astromesh-node" in `README.md`.

- [ ] **Step 4: Add migration note to CHANGELOG.md**

Add entry under a new section:

```markdown
### Changed
- **BREAKING**: Renamed "Astromesh OS" to "Astromesh Node" — daemon, CLI, and packaging extracted to `astromesh-node/` subproject
- Daemon (`astromeshd`) now supports Linux (systemd), macOS (launchd), and Windows (Windows Service)
- CLI (`astromeshctl`) imports updated — install via `astromesh-node` package
```

- [ ] **Step 5: Verify root project still works without daemon/cli**

Run: `uv sync && uv run pytest tests/ -v --ignore=tests/test_daemon* --ignore=tests/test_cli*`
Expected: PASS (core tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(node): remove migrated daemon/cli/packaging from monorepo root

BREAKING: astromeshd and astromeshctl now live in astromesh-node/ subproject.
Install via 'pip install ./astromesh-node' or from GitHub Releases."
```

---

## Task 11: CI workflows — release-node.yml and ci.yml updates

**Files:**
- Create: `.github/workflows/release-node.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Create release-node.yml**

Create `.github/workflows/release-node.yml`:

```yaml
name: Release Astromesh Node

on:
  push:
    tags: ["node-v*"]

permissions:
  contents: write

jobs:
  validate-tag:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
    steps:
      - uses: actions/checkout@v4
      - name: Extract and validate version
        id: version
        run: |
          TAG_VERSION="${GITHUB_REF#refs/tags/node-v}"
          PYPROJECT_VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('astromesh-node/pyproject.toml','rb'))['project']['version'])")
          if [ "$TAG_VERSION" != "$PYPROJECT_VERSION" ]; then
            echo "Tag version ($TAG_VERSION) != pyproject.toml ($PYPROJECT_VERSION)"
            exit 1
          fi
          echo "version=$TAG_VERSION" >> "$GITHUB_OUTPUT"

  build-linux:
    needs: validate-tag
    runs-on: ubuntu-latest
    strategy:
      matrix:
        arch: [amd64]
        format: [deb, rpm]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install nfpm
        run: |
          echo 'deb [trusted=yes] https://repo.goreleaser.com/apt/ /' | sudo tee /etc/apt/sources.list.d/goreleaser.list
          sudo apt update && sudo apt install -y nfpm
      - name: Build package
        working-directory: astromesh-node
        run: bash packaging/build-${{ matrix.format }}.sh
      - uses: actions/upload-artifact@v4
        with:
          name: astromesh-node-${{ matrix.arch }}.${{ matrix.format }}
          path: astromesh-node/dist/*.${{ matrix.format }}

  build-macos:
    needs: validate-tag
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build tarball
        working-directory: astromesh-node
        run: bash packaging/build-macos.sh
      - uses: actions/upload-artifact@v4
        with:
          name: astromesh-node-macos
          path: astromesh-node/dist/*.tar.gz

  build-windows:
    needs: validate-tag
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build zip
        working-directory: astromesh-node
        run: powershell packaging/build-windows.ps1
      - uses: actions/upload-artifact@v4
        with:
          name: astromesh-node-windows
          path: astromesh-node/dist/*.zip

  release:
    needs: [validate-tag, build-linux, build-macos, build-windows]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: artifacts/
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: node-v${{ needs.validate-tag.outputs.version }}
          name: Astromesh Node v${{ needs.validate-tag.outputs.version }}
          files: artifacts/**/*
          generate_release_notes: true
```

- [ ] **Step 2: Update release.yml — remove deb build job**

Remove the `build-deb` and related jobs from `.github/workflows/release.yml`. Keep Docker build job if it exists.

- [ ] **Step 3: Update ci.yml — replace deb test with node tests**

In `.github/workflows/ci.yml`:
- Remove `build-deb-test` job
- Add new job:

```yaml
  test-node:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Run tests
        working-directory: astromesh-node
        run: |
          uv sync --extra test
          uv run pytest -v
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "feat(ci): add release-node.yml workflow, update CI for astromesh-node"
```

---

## Task 12: Documentation site — new Astromesh Node section

**Files:**
- Create: `docs-site/src/content/docs/node/introduction.mdx`
- Create: `docs-site/src/content/docs/node/quick-start.mdx`
- Create: `docs-site/src/content/docs/node/installation/linux-debian.md`
- Create: `docs-site/src/content/docs/node/installation/linux-redhat.md`
- Create: `docs-site/src/content/docs/node/installation/macos.md`
- Create: `docs-site/src/content/docs/node/installation/windows.md`
- Create: `docs-site/src/content/docs/node/configuration.md`
- Create: `docs-site/src/content/docs/node/cli-reference.md`
- Create: `docs-site/src/content/docs/node/troubleshooting.md`
- Modify: `docs-site/astro.config.mjs`
- Modify: `docs-site/src/content/docs/deployment/astromesh-os.md`
- Modify: `docs-site/src/content/docs/getting-started/installation.md`

- [ ] **Step 1: Create node documentation directory**

```bash
mkdir -p docs-site/src/content/docs/node/installation
```

- [ ] **Step 2: Write introduction.mdx**

Create `docs-site/src/content/docs/node/introduction.mdx` with:
- What is Astromesh Node
- Supported platforms (Linux deb/rpm, macOS, Windows)
- Comparison with other deployment options (Docker, Kubernetes, from source)
- Architecture overview (daemon + CLI + platform adapters)

- [ ] **Step 3: Write quick-start.mdx**

Create `docs-site/src/content/docs/node/quick-start.mdx` with:
- Auto-detect OS snippet showing all 4 install paths
- `astromeshctl init --profile full`
- `systemctl start astromeshd` / `launchctl` / Windows Service start
- Verify with `astromeshctl status`

- [ ] **Step 4: Write per-platform installation guides**

Create the 4 files under `node/installation/` following the pattern from the existing `deployment/astromesh-os.md`:
- Prerequisites table
- Download from GitHub Releases
- Install command
- Configure and start
- Verify

- [ ] **Step 5: Write configuration.md**

Create `docs-site/src/content/docs/node/configuration.md`:
- runtime.yaml reference
- Profile descriptions (all 7)
- Paths per platform table
- Environment variables (.env file)

- [ ] **Step 6: Write cli-reference.md**

Create `docs-site/src/content/docs/node/cli-reference.md`:
- Full `astromeshctl` command reference
- Migrated from existing `reference/os/cli.md` content

- [ ] **Step 7: Write troubleshooting.md**

Create `docs-site/src/content/docs/node/troubleshooting.md`:
- Common issues per platform
- `astromeshctl doctor` usage
- Log locations per platform

- [ ] **Step 8: Add Node section to sidebar in astro.config.mjs**

Edit `docs-site/astro.config.mjs` to add the Astromesh Node section to the sidebar, between the existing sections (after Deployment, before Advanced, or alongside ADK/Cloud/Orbit).

```javascript
{
  label: 'Astromesh Node',
  items: [
    { label: 'Introduction', slug: 'node/introduction' },
    { label: 'Quick Start', slug: 'node/quick-start' },
    {
      label: 'Installation',
      items: [
        { label: 'Debian / Ubuntu', slug: 'node/installation/linux-debian' },
        { label: 'RHEL / Fedora', slug: 'node/installation/linux-redhat' },
        { label: 'macOS', slug: 'node/installation/macos' },
        { label: 'Windows', slug: 'node/installation/windows' },
      ],
    },
    { label: 'Configuration', slug: 'node/configuration' },
    { label: 'CLI Reference', slug: 'node/cli-reference' },
    { label: 'Troubleshooting', slug: 'node/troubleshooting' },
  ],
},
```

- [ ] **Step 9: Replace deployment/astromesh-os.md with redirect**

Replace content of `docs-site/src/content/docs/deployment/astromesh-os.md` with a stub that redirects to the new Node section:

```markdown
---
title: Astromesh Node (formerly Astromesh OS)
description: Redirected to the Astromesh Node section
---

This page has moved. See the [Astromesh Node documentation](/astromesh/node/introduction/).
```

- [ ] **Step 10: Update getting-started/installation.md**

Add a link/section pointing to Astromesh Node for system-level installation.

- [ ] **Step 11: Rename all "Astromesh OS" references in docs-site**

Search across all docs-site `.md`/`.mdx` files for "Astromesh OS" and replace with "Astromesh Node". Update `reference/os/` page titles as needed.

- [ ] **Step 12: Verify docs build**

Run: `cd docs-site && npm run build`
Expected: Build succeeds with no broken links

- [ ] **Step 13: Commit**

```bash
git add docs-site/
git commit -m "docs(node): add Astromesh Node section to docs-site, rename OS → Node"
```

---

## Task 13: NodeShowcase component for home page

**Files:**
- Create: `docs-site/src/components/NodeShowcase.astro`
- Modify: `docs-site/src/content/docs/index.mdx`

- [ ] **Step 1: Create NodeShowcase.astro**

Follow the pattern of `ADKShowcase.astro` and `OrbitShowcase.astro`. Show:
- 4 platform icons (Linux, macOS, Windows)
- Key features grid (System Service, CLI Management, 7 Profiles, Cross-platform)
- Install snippet
- Link to Node docs

- [ ] **Step 2: Add NodeShowcase to home page**

Edit `docs-site/src/content/docs/index.mdx` to import and render `NodeShowcase` alongside the existing showcases.

- [ ] **Step 3: Verify home page renders**

Run: `cd docs-site && npm run dev`
Check `http://localhost:4321/astromesh/` — NodeShowcase should appear.

- [ ] **Step 4: Commit**

```bash
git add docs-site/src/components/NodeShowcase.astro docs-site/src/content/docs/index.mdx
git commit -m "feat(docs): add NodeShowcase component to home page"
```

---

## Task 14: Doctor migration check + ARM64 CI note

**Files:**
- Modify: `astromesh-node/src/astromesh_node/cli/commands/doctor.py`

- [ ] **Step 1: Add migration check to doctor command**

In `doctor.py`, add a check that warns about stale Astromesh OS artifacts:

```python
# Check for stale astromesh-os package
import subprocess
result = subprocess.run(["dpkg", "-l", "astromesh"], capture_output=True, text=True)
if result.returncode == 0 and "astromesh" in result.stdout:
    warnings.append("Stale 'astromesh' package detected. Upgrade to astromesh-node.")
```

This only runs on Linux (guard with `sys.platform == "linux"`).

- [ ] **Step 2: Commit**

```bash
git add astromesh-node/src/astromesh_node/cli/commands/doctor.py
git commit -m "feat(node): add migration check to astromeshctl doctor"
```

**Note on ARM64 Linux builds:** The spec lists ARM64 `.deb`/`.rpm` artifacts. The `release-node.yml` workflow currently only builds `amd64`. ARM64 builds require either cross-compilation on `ubuntu-latest` or using `ubuntu-latest-arm64` runners (which are available on GitHub Actions). This can be added to the CI matrix in a follow-up by adding `arm64` to the `arch` matrix. Deferred to keep the initial implementation focused.

---

## Task 15: Global rename and final verification

**Files:**
- All files across the codebase

- [ ] **Step 1: Global search-and-replace**

Search the entire codebase for remaining "Astromesh OS" / "astromesh-os" references (excluding historical design docs in `docs/plans/2026-03-09-astromesh-os-*`):

```bash
grep -r "Astromesh OS\|astromesh-os" --include="*.py" --include="*.md" --include="*.mdx" --include="*.yaml" --include="*.yml" --include="*.toml" --include="*.json" --include="*.mjs" . | grep -v "docs/plans/2026-03-09-astromesh-os"
```

Replace any remaining occurrences.

- [ ] **Step 2: Run all subproject tests**

Run: `cd astromesh-node && uv sync --extra test && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Run root project tests**

Run: `uv sync && uv run pytest tests/ -v`
Expected: PASS (no regressions in core)

- [ ] **Step 4: Verify docs build**

Run: `cd docs-site && npm run build`
Expected: Clean build

- [ ] **Step 5: Run linter**

Run: `cd astromesh-node && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: No issues

- [ ] **Step 6: Commit any final fixes**

```bash
git add -A
git commit -m "chore(node): complete global rename Astromesh OS → Astromesh Node"
```

---

## Summary

| Task | Description | Est. Files |
|------|-------------|-----------|
| 1 | Scaffold subproject | 3 |
| 2 | ServiceManagerProtocol + ForegroundManager + detect | 6 |
| 3 | SystemdManager adapter | 2 |
| 4 | LaunchdManager adapter | 2 |
| 5 | WindowsServiceManager adapter | 2 |
| 6 | InstallerProtocol + 3 platform installers | 8 |
| 7 | Daemon core refactor | 4 |
| 8 | Move CLI to subproject | ~20 |
| 9 | Move packaging + config | ~15 |
| 10 | Clean monorepo root | 5 |
| 11 | CI workflows | 3 |
| 12 | Docs-site Node section | 12 |
| 13 | NodeShowcase component | 2 |
| 14 | Doctor migration check | 1 |
| 15 | Global rename + verification | all |
