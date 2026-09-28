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
| Architecture | x64 | `echo %PROCESSOR_ARCHITECTURE%` |
| Python | 3.12+ | `python --version` |
| Network | Outbound to LLM provider or local Ollama | — |

Administrator privileges are required for installation.

## Download

Node archives are attached to the `node-v*` releases on GitHub (the repository's "latest" release is the core, so `releases/latest/download/...` does not find them):

```powershell
$Version = "0.1.3"
Invoke-WebRequest `
  -Uri "https://github.com/monaccode/astromesh/releases/download/node-v$Version/astromesh-node-$Version-windows.zip" `
  -OutFile astromesh-node.zip
```

## Install

Extract the archive and run the installer script as Administrator:

```powershell
Expand-Archive -Path astromesh-node.zip -DestinationPath .\astromesh-node
cd .\astromesh-node
.\install.ps1
```

If PowerShell script execution is blocked, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

The installer:

1. Creates `C:\ProgramData\Astromesh\config\`, `data\` and `logs\`
2. Copies the virtualenv to `C:\Program Files\Astromesh\venv\`
3. Adds `C:\Program Files\Astromesh\venv\Scripts\` to the system `PATH`

It does **not** register the Windows Service — see [Register and start the service](#register-and-start-the-service).

Open a new terminal (to pick up the PATH update) and verify:

```powershell
astromeshctl version
```

Expected output:

```
astromesh-cli 0.3.1
astromesh core 0.59.0
```

## Configure

`astromeshctl init` only writes to the system directory on Unix when run as root; on Windows it always writes to `.\config`. Run it from `C:\ProgramData\Astromesh` so that lands in the directory the daemon reads:

```powershell
cd C:\ProgramData\Astromesh
astromeshctl init --dev
```

For a non-interactive setup:

```powershell
astromeshctl init --dev --role full --non-interactive
```

This creates `config\runtime.yaml` and `config\providers.yaml`. The Windows archive ships neither role profiles nor sample agents, so `runtime.yaml` is empty (all services on, port 8000 — the `full` defaults) and `config\agents\` starts empty: add your `*.agent.yaml` files there. An API key you enter goes to `C:\ProgramData\Astromesh\.env`, which the service does not read — set it as a system environment variable instead.

See [Configuration](/astromesh/node/configuration/) for the full schema.

## Register and start the service

The service wrapper `astromeshd-service.py` ships in the archive (not in the installed venv). From the extracted folder, as Administrator:

```powershell
& "$env:ProgramFiles\Astromesh\venv\Scripts\python.exe" .\astromeshd-service.py --startup auto install
Start-Service astromeshd
```

The service is named `astromeshd` (display name "Astromesh Agent Runtime Daemon"). To stop it:

```powershell
Stop-Service astromeshd
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

The service writes no log file. To see the daemon's output, stop the service and run it in a terminal:

```powershell
astromeshd --foreground
```

## Filesystem Paths

| Path | Purpose |
|------|---------|
| `C:\ProgramData\Astromesh\config\` | Configuration files |
| `C:\ProgramData\Astromesh\data\` | Persistent state |
| `C:\Program Files\Astromesh\venv\` | Virtualenv (`Scripts\astromeshd.exe`, `Scripts\astromeshctl.exe`) |

## Upgrade

`install.ps1` does not stop the service, and copying over an existing venv nests the new one inside it. Stop the service and remove the old venv first:

```powershell
Stop-Service astromeshd
Remove-Item "C:\Program Files\Astromesh\venv" -Recurse -Force
# download + Expand-Archive + .\install.ps1 as above
Start-Service astromeshd
```

## Uninstall

```powershell
# Stop and remove the service
Stop-Service astromeshd
sc.exe delete astromeshd

# Remove the virtualenv
Remove-Item "C:\Program Files\Astromesh" -Recurse -Force
```

Also remove `C:\Program Files\Astromesh\venv\Scripts` from the system `PATH`. To remove all configuration and data:

```powershell
Remove-Item "C:\ProgramData\Astromesh" -Recurse -Force
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common Windows issues
