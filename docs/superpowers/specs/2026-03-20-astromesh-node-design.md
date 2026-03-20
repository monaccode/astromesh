# Astromesh Node — Design Spec

**Date:** 2026-03-20
**Status:** Draft
**Author:** Claude + User

## Overview

Rename "Astromesh OS" to "Astromesh Node" and extract it as a standalone subproject within the monorepo (like ADK and Orbit). Universalize the installer and daemon to support Linux (Debian/Ubuntu + Red Hat-based), macOS, and Windows as first-class platforms.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Project location | Subproject in monorepo (`astromesh-node/`) | Follows ADK/Orbit pattern, coordinated releases |
| Architecture | Platform Adapters (ServiceManagerProtocol) | Clean abstraction, consistent UX, follows ProviderProtocol pattern |
| Distribution | GitHub Releases artifacts (no APT/YUM/Homebrew repos) | Direct download from Git releases |
| Binary names | Keep `astromeshd` and `astromeshctl` | Already established identity, "node" is the project name not the command |
| Profiles | All 7 profiles on all platforms (full, gateway, worker, inference, mesh-gateway, mesh-worker, mesh-inference) | No platform restrictions |
| Docs | New top-level section in docs-site | Consistent with ADK/Cloud/Orbit sections |
| Implementation | All 4 platforms at once | User preference, design supports it cleanly |

## 1. Subproject Structure

```
astromesh-node/
├── pyproject.toml                      # Package: astromesh-node
├── README.md
├── src/
│   └── astromesh_node/
│       ├── __init__.py
│       ├── daemon/
│       │   ├── __init__.py
│       │   ├── core.py                 # AstromeshDaemon (platform-agnostic main loop)
│       │   └── config.py               # runtime.yaml loading, system/dev mode detection
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py                 # Typer app (astromeshctl)
│       │   └── commands/               # 17 existing command modules
│       ├── platform/
│       │   ├── __init__.py
│       │   ├── base.py                 # ServiceManagerProtocol
│       │   ├── detect.py               # Auto-detection of platform
│       │   ├── systemd.py              # Linux adapter
│       │   ├── launchd.py              # macOS adapter
│       │   └── windows.py              # Windows adapter
│       └── installer/
│           ├── __init__.py
│           ├── base.py                 # InstallerProtocol
│           ├── linux.py                # FHS paths, user creation
│           ├── macos.py                # /Library/... paths
│           └── windows.py              # ProgramFiles paths
├── packaging/
│   ├── nfpm.yaml                       # .deb + .rpm config
│   ├── build-deb.sh
│   ├── build-rpm.sh
│   ├── build-macos.sh                  # .tar.gz with install script
│   ├── build-windows.ps1               # .zip with install script
│   ├── systemd/
│   │   └── astromeshd.service
│   ├── launchd/
│   │   └── com.astromesh.daemon.plist
│   ├── windows/
│   │   └── astromeshd-service.py       # win32serviceutil wrapper
│   └── scripts/                        # pre/post install scripts
├── config/
│   └── profiles/                       # full, gateway, worker, inference, mesh-gateway, mesh-worker, mesh-inference
└── tests/
```

## 2. ServiceManagerProtocol

Runtime-checkable Protocol that abstracts the platform's init system. The daemon core calls these methods without knowing which platform it runs on.

```python
@runtime_checkable
class ServiceManagerProtocol(Protocol):
    async def notify_ready(self) -> None: ...
    async def notify_reload(self) -> None: ...
    async def notify_stopping(self) -> None: ...
    async def install_service(self, profile: str) -> None: ...
    async def uninstall_service(self) -> None: ...
    async def service_status(self) -> dict: ...
    def register_reload_handler(self, callback) -> None: ...
```

### Implementation mapping

| Method | systemd (Linux) | launchd (macOS) | Windows Service |
|--------|----------------|-----------------|-----------------|
| `notify_ready` | `sd_notify("READY=1")` | Implicit (launchd assumes ready) | `ReportServiceStatus(RUNNING)` |
| `notify_reload` | `sd_notify("RELOADING=1")` | No-op (SIGHUP handled via `register_reload_handler`) | No-op |
| `notify_stopping` | `sd_notify("STOPPING=1")` | No-op | `ReportServiceStatus(STOP_PENDING)` |
| `install_service` | Copy .service + `systemctl enable` | Copy .plist + `launchctl load` | `win32serviceutil.InstallService` |
| `uninstall_service` | `systemctl disable` + remove .service | `launchctl unload` + remove .plist | `win32serviceutil.RemoveService` |
| `service_status` | `systemctl show` parsing | `launchctl list` parsing | `QueryServiceStatus` |
| `register_reload_handler` | `signal.signal(SIGHUP, ...)` | `signal.signal(SIGHUP, ...)` | Named pipe or custom event |

### Auto-detection (`detect.py`)

```python
def get_service_manager(foreground: bool = False) -> ServiceManagerProtocol:
    if foreground:
        return ForegroundManager()  # No-op adapter for dev/Docker/foreground mode
    if sys.platform == "linux":
        return SystemdManager()
    elif sys.platform == "darwin":
        return LaunchdManager()
    elif sys.platform == "win32":
        return WindowsServiceManager()
    else:
        raise UnsupportedPlatformError(f"Platform {sys.platform} is not supported")
```

A `ForegroundManager` no-op adapter is included for dev mode, Docker containers, and `astromeshd --foreground` usage.

## 3. InstallerProtocol

Handles directory creation, users, permissions, and platform-specific file locations.

```python
@runtime_checkable
class InstallerProtocol(Protocol):
    def config_dir(self) -> Path: ...
    def data_dir(self) -> Path: ...
    def log_dir(self) -> Path: ...
    def bin_dir(self) -> Path: ...
    async def install(self, profile: str) -> None: ...
    async def uninstall(self, keep_data: bool = True) -> None: ...
    async def verify(self) -> list[str]: ...  # Returns list of problems; empty = all OK
```

### Filesystem layout per platform

| Resource | Linux (FHS) | macOS | Windows |
|----------|-------------|-------|---------|
| Config | `/etc/astromesh/` | `/Library/Application Support/Astromesh/config/` | `%ProgramData%\Astromesh\config\` |
| Data | `/var/lib/astromesh/` | `/Library/Application Support/Astromesh/data/` | `%ProgramData%\Astromesh\data\` |
| Logs | `/var/log/astromesh/` | `/Library/Logs/Astromesh/` | `%ProgramData%\Astromesh\logs\` |
| Binaries | `/opt/astromesh/venv/` | `/usr/local/opt/astromesh/venv/` | `%ProgramFiles%\Astromesh\venv\` |
| PID | `/var/lib/astromesh/data/astromeshd.pid` | `/Library/Application Support/Astromesh/data/astromeshd.pid` | `%ProgramData%\Astromesh\data\astromeshd.pid` |

### System users

- **Linux**: `astromesh:astromesh` (no login shell, already exists)
- **macOS**: `_astromesh` (macOS daemon convention with underscore prefix)
- **Windows**: Runs as `Local Service` (no custom user creation needed)

### Unified install command

```bash
# All platforms (with appropriate privileges)
astromeshctl install --profile full
```

Internally detects platform, runs the corresponding installer, copies configs, creates directories, registers the service, and optionally starts it.

## 4. Packaging and Release Artifacts

### Artifacts per release

| Artifact | Platform | Format |
|----------|----------|--------|
| `astromesh-node-{ver}-amd64.deb` | Debian/Ubuntu x64 | .deb (nfpm) |
| `astromesh-node-{ver}-amd64.rpm` | RHEL/Fedora/CentOS x64 | .rpm (nfpm) |
| `astromesh-node-{ver}-arm64.deb` | Debian/Ubuntu ARM64 | .deb (nfpm) |
| `astromesh-node-{ver}-arm64.rpm` | RHEL/Fedora ARM64 | .rpm (nfpm) |
| `astromesh-node-{ver}-macos.tar.gz` | macOS (Python-only, works on Intel + Apple Silicon) | Tarball + install.sh |
| `astromesh-node-{ver}-windows.zip` | Windows x64 | Zip + install.ps1 |

All artifacts published to GitHub Releases, downloaded directly.

### Installation flow per platform

```bash
# Debian/Ubuntu
wget .../astromesh-node-{ver}-amd64.deb
sudo dpkg -i astromesh-node-{ver}-amd64.deb
sudo astromeshctl install --profile full

# RHEL/Fedora
wget .../astromesh-node-{ver}-amd64.rpm
sudo rpm -i astromesh-node-{ver}-amd64.rpm
sudo astromeshctl install --profile full

# macOS
curl -LO .../astromesh-node-{ver}-macos.tar.gz
tar xzf astromesh-node-{ver}-macos.tar.gz
sudo ./install.sh
sudo astromeshctl install --profile full

# Windows (elevated PowerShell)
Invoke-WebRequest .../astromesh-node-{ver}-windows.zip -OutFile astromesh-node.zip
Expand-Archive astromesh-node.zip -DestinationPath "$env:ProgramFiles\Astromesh"
.\install.ps1
astromeshctl install --profile full
```

### CI workflow (`release-node.yml`)

- **Trigger**: tag `node-v*`
- **Jobs** (parallel): build-deb, build-rpm (matrix amd64/arm64), build-macos, build-windows
- **Runners**: `ubuntu-latest` (Linux), `macos-latest` (macOS), `windows-latest` (Windows)
- Each job builds its artifact and uploads to the GitHub Release

## 5. Daemon Core Refactor

The current `astromeshd.py` (277 lines) has systemd logic mixed with runtime bootstrap. The refactor separates into two layers:

### `daemon/core.py` — Platform-agnostic logic

- Bootstrap AgentRuntime from config
- Start uvicorn/FastAPI server
- Graceful shutdown loop
- Config reload logic (re-read YAMLs, re-bootstrap)
- Mesh clustering (gossip + heartbeat) if enabled
- Delegates lifecycle notifications to `ServiceManagerProtocol`

### `daemon/config.py` — Mode detection and paths

- No longer hardcodes `/etc/astromesh/` or `/var/lib/astromesh/`
- Uses the detected platform's `InstallerProtocol` to resolve paths
- Maintains `./config/` fallback in dev mode

### Key change

```python
# Before (coupled to systemd)
import sdnotify
n = sdnotify.SystemdNotifier()
n.notify("READY=1")
signal.signal(signal.SIGHUP, reload_handler)

# After (platform-agnostic)
from astromesh_node.platform.detect import get_service_manager

service_mgr = get_service_manager()
await service_mgr.notify_ready()
service_mgr.register_reload_handler(reload_handler)
```

The `astromeshd` entry point remains as a script importing `daemon.core:main`. On Windows, an additional `astromeshd-service.py` wrapper extends `win32serviceutil.ServiceFramework` and calls the same `daemon.core:main` internally.

## 6. Documentation Site — New "Astromesh Node" Section

### Pages

```
docs-site/src/content/docs/node/
├── introduction.mdx
├── quick-start.mdx
├── installation/
│   ├── linux-debian.md
│   ├── linux-redhat.md
│   ├── macos.md
│   └── windows.md
├── configuration.md
├── cli-reference.md
└── troubleshooting.md
```

### Sidebar configuration

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

### Impact on existing docs

- `deployment/astromesh-os.md` → replaced with redirect/link to `node/introduction`
- `reference/os/` → daemon and CLI pages migrate to Node section; vscode-extension stays in reference
- `getting-started/installation.md` → updated to link to Node section
- All references to "Astromesh OS" renamed to "Astromesh Node" across the site

### New component

`NodeShowcase.astro` for the home page, similar to `ADKShowcase.astro` and `OrbitShowcase.astro`, showcasing the 4 supported platforms.

## 7. Migration Plan

### Files that move

| Origin | Destination |
|--------|-------------|
| `daemon/astromeshd.py` | `astromesh-node/src/astromesh_node/daemon/core.py` (refactored) |
| `cli/main.py` + `cli/commands/` | `astromesh-node/src/astromesh_node/cli/` |
| `packaging/` | `astromesh-node/packaging/` |
| `nfpm.yaml` | `astromesh-node/packaging/nfpm.yaml` |
| `config/profiles/` | `astromesh-node/config/profiles/` |

### New files

- `astromesh-node/pyproject.toml` — independent package with dependency on `astromesh`
- `astromesh-node/src/astromesh_node/platform/` — full platform abstraction module
- `astromesh-node/src/astromesh_node/installer/` — full installer module
- `astromesh-node/packaging/build-rpm.sh`, `build-macos.sh`, `build-windows.ps1`
- `astromesh-node/packaging/launchd/`, `packaging/windows/`
- `.github/workflows/release-node.yml` — dedicated release CI

### Monorepo root changes

- `pyproject.toml`: remove `astromeshd` and `astromeshctl` entry points, remove `cli` and `daemon` extras
- `.github/workflows/release.yml`: remove deb build job (migrates to `release-node.yml`)
- `.github/workflows/ci.yml`: remove `build-deb-test` job, add subproject tests
- `README.md`: rename "Astromesh OS" → "Astromesh Node" everywhere
- `CHANGELOG.md`: migration note

### Global renaming

All occurrences of "astromesh-os" / "Astromesh OS" in the codebase renamed to "astromesh-node" / "Astromesh Node". Historical design docs in `docs/plans/2026-03-09-astromesh-os-*` kept as-is for reference.

## 8. Upgrade Path for Existing Installations

Existing Linux installations (Astromesh OS .deb) need a migration path:

1. The new `astromesh-node` .deb package declares `Replaces: astromesh-os` and `Conflicts: astromesh-os` in nfpm config
2. `dpkg -i astromesh-node-{ver}.deb` automatically handles the transition
3. Config files in `/etc/astromesh/` are preserved (same paths)
4. systemd service name stays `astromeshd.service` (no change)
5. `astromeshctl doctor` gains a migration check that warns about stale Astromesh OS artifacts

This means existing users can upgrade in-place with no manual migration steps.

## 9. Subproject pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "astromesh-node"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "astromesh>=0.18.0",
    "typer>=0.12.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
systemd = ["sdnotify>=0.3.0"]
windows = ["pywin32>=306"]

[project.scripts]
astromeshd = "astromesh_node.daemon.core:main"
astromeshctl = "astromesh_node.cli.main:app"
```

Platform-specific dependencies (`sdnotify`, `pywin32`) are optional extras. The packaging scripts include the appropriate extra for each platform.

## 10. Windows Entry Points

On Windows, `astromeshd` and `astromeshctl` are installed as console_scripts via pip/uv, which automatically generates `.exe` wrappers in the venv's `Scripts/` directory. The `install.ps1` script adds this directory to the system PATH. When running as a Windows Service, the `astromeshd-service.py` wrapper in `packaging/windows/` is registered via `win32serviceutil` and invokes `daemon.core:main` internally.

## Non-Goals

The following are explicitly out of scope for this spec:

- APT/YUM/Homebrew/winget package repositories (distribution is GitHub Releases only)
- ARM64 builds for macOS or Windows
- Rust native extensions in the macOS/Windows packages (Python fallback is used; Rust extensions remain Linux-only for now)
- GUI installer for any platform
- Auto-update mechanism

## Testing Strategy

- **Unit tests**: Each platform adapter mocked (no real systemd/launchd/win32 in CI)
- **Integration tests**: `astromeshctl install --profile full --dry-run` validates the full flow without side effects. The `--dry-run` flag is a CLI option that routes to `InstallerProtocol.install()` with a dry-run mode that logs actions without executing them.
- **CI matrix**: Test on ubuntu-latest, macos-latest, windows-latest
- **Package tests**: Build artifacts in CI, verify they contain expected files
- **Log management**: Linux uses journald (systemd native); macOS uses unified logging (`os_log`); Windows uses Windows Event Log. No custom log rotation needed — each platform's native logging handles it.
