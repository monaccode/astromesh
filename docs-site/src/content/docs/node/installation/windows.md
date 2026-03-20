---
title: "Install on Windows"
description: "Install Astromesh Node as a Windows Service on Windows 10/11 and Windows Server"
---

This guide covers installing Astromesh Node as a Windows Service on Windows 10/11 and Windows Server 2019/2022.

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Windows | 10 21H2+ / 11 / Server 2019+ | `winver` |
| PowerShell | 5.1+ (included in Windows) | `$PSVersionTable.PSVersion` |
| Architecture | x64 or arm64 | `echo %PROCESSOR_ARCHITECTURE%` |
| Python | 3.12+ (bundled by the installer) | — |
| Network | Outbound to LLM provider or local Ollama | — |

Administrator privileges are required for installation.

## Download

Download the latest `.zip` package from GitHub Releases.

**PowerShell:**

```powershell
Invoke-WebRequest `
  -Uri https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_windows_amd64.zip `
  -OutFile astromesh.zip
```

**Or download via browser:** visit the [GitHub Releases page](https://github.com/monaccode/astromesh/releases/latest) and download `astromesh_latest_windows_amd64.zip`.

## Install

Extract the archive and run the installer script as Administrator:

```powershell
# Extract
Expand-Archive -Path astromesh.zip -DestinationPath .\astromesh

# Open an Administrator PowerShell and run the installer
cd .\astromesh
.\install.ps1
```

If PowerShell script execution is blocked, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

The installer:

1. Copies `astromeshd.exe` and `astromeshctl.exe` to `C:\Program Files\Astromesh\bin\`
2. Creates configuration and data directories
3. Registers the `AstromeshDaemon` Windows Service
4. Adds `C:\Program Files\Astromesh\bin\` to the system `PATH`

Expected output:

```
Installing Astromesh Node v0.18.0...
Creating directories...
  C:\ProgramData\Astromesh\config\
  C:\ProgramData\Astromesh\data\
  C:\ProgramData\Astromesh\logs\
Installing binaries...
Installing Python environment...
Registering Windows Service 'AstromeshDaemon'...
astromesh installed successfully.

Run 'astromeshctl init' to configure.
```

Open a new terminal (to pick up the PATH update) and verify:

```powershell
astromeshctl version
```

Expected output:

```
Astromesh Node v0.18.0
Daemon:   C:\Program Files\Astromesh\bin\astromeshd.exe
CLI:      C:\Program Files\Astromesh\bin\astromeshctl.exe
Python:   3.12.x
Platform: windows/amd64
```

## Configure

Run the interactive wizard (from an Administrator terminal):

```powershell
astromeshctl init
```

For a non-interactive setup:

```powershell
astromeshctl init --profile full --provider ollama --model llama3.1:8b --non-interactive
```

This creates:

- `C:\ProgramData\Astromesh\config\runtime.yaml`
- `C:\ProgramData\Astromesh\config\providers.yaml`
- `C:\ProgramData\Astromesh\config\agents\default.agent.yaml`

See [Configuration](/astromesh/node/configuration/) for the full schema.

## Start the Service

```powershell
# Start the service
Start-Service AstromeshDaemon

# Set to start automatically on boot
Set-Service AstromeshDaemon -StartupType Automatic
```

Or use the Services console (`services.msc`) — find `Astromesh Daemon` and start it.

To stop:

```powershell
Stop-Service AstromeshDaemon
```

## Verify

```powershell
astromeshctl status
```

```powershell
Invoke-RestMethod http://localhost:8000/v1/health
```

## Windows Firewall

To allow external access to the API (optional, only needed if accessing from other machines):

```powershell
New-NetFirewallRule `
  -DisplayName "Astromesh API" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8000 `
  -Action Allow
```

## Log Access

Logs are written to `C:\ProgramData\Astromesh\logs\`:

```powershell
# Follow live logs
Get-Content "C:\ProgramData\Astromesh\logs\astromeshd.log" -Wait -Tail 50

# View errors
Select-String -Path "C:\ProgramData\Astromesh\logs\astromeshd.log" -Pattern "ERROR"

# Windows Event Log
Get-EventLog -LogName Application -Source AstromeshDaemon -Newest 50
```

## Filesystem Paths

| Path | Purpose |
|------|---------|
| `C:\ProgramData\Astromesh\config\` | Configuration files |
| `C:\ProgramData\Astromesh\data\` | Persistent state (memory, models) |
| `C:\ProgramData\Astromesh\logs\` | Log files |
| `C:\Program Files\Astromesh\bin\` | `astromeshd.exe` and `astromeshctl.exe` |

## Upgrade

```powershell
# Download new version
Invoke-WebRequest `
  -Uri https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_windows_amd64.zip `
  -OutFile astromesh.zip

Expand-Archive -Path astromesh.zip -DestinationPath .\astromesh -Force
cd .\astromesh
.\install.ps1
```

The installer stops the service, upgrades binaries, and restarts the service.

## Uninstall

```powershell
# Stop and remove the service
Stop-Service AstromeshDaemon
sc.exe delete AstromeshDaemon

# Remove binaries
Remove-Item "C:\Program Files\Astromesh" -Recurse -Force
```

To remove all configuration and data:

```powershell
Remove-Item "C:\ProgramData\Astromesh" -Recurse -Force
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common Windows issues
