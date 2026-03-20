---
title: "Install on Debian / Ubuntu"
description: "Install Astromesh Node as a systemd service on Debian and Ubuntu"
---

This guide covers installing Astromesh Node on Debian-based Linux distributions (Debian 12+, Ubuntu 22.04+).

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Debian / Ubuntu | Debian 12+ / Ubuntu 22.04+ | `lsb_release -a` |
| systemd | 250+ | `systemctl --version` |
| Python | 3.12+ (bundled by the package) | `python3 --version` |
| Architecture | amd64 or arm64 | `dpkg --print-architecture` |
| Network | Outbound to LLM provider or local Ollama | — |

## Download the Package

Download the latest `.deb` package from GitHub Releases:

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_amd64.deb
```

For ARM64 (e.g., Raspberry Pi, AWS Graviton):

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_arm64.deb
```

To download a specific version, replace `latest` with the version tag (e.g., `v0.18.0`):

```bash
curl -LO https://github.com/monaccode/astromesh/releases/download/v0.18.0/astromesh_0.18.0_amd64.deb
```

## Install

```bash
sudo apt install ./astromesh_latest_amd64.deb
```

Expected output:

```
Reading package lists... Done
Setting up astromesh (0.18.0) ...
Creating system user 'astromesh'...
Creating directories...
  /etc/astromesh/
  /var/lib/astromesh/
  /var/log/astromesh/
  /opt/astromesh/
Installing Python virtual environment...
Installing systemd service...
astromesh installed successfully.
```

Verify the installation:

```bash
astromeshctl version
```

Expected output:

```
Astromesh Node v0.18.0
Daemon:   /opt/astromesh/bin/astromeshd
CLI:      /opt/astromesh/bin/astromeshctl
Python:   3.12.x
Platform: linux/amd64
```

## Configure

Run the interactive wizard to generate your configuration:

```bash
sudo astromeshctl init
```

This creates:

- `/etc/astromesh/runtime.yaml` — daemon configuration (services, API, log level)
- `/etc/astromesh/providers.yaml` — LLM provider connections
- `/etc/astromesh/agents/default.agent.yaml` — default agent definition

To reinitialize with a specific profile non-interactively:

```bash
sudo astromeshctl init --profile full --provider ollama --model llama3.1:8b --non-interactive
```

See [Configuration](/astromesh/node/configuration/) for the full `runtime.yaml` schema and all 7 profiles.

## Start the Service

Enable and start the daemon with systemd:

```bash
sudo systemctl enable astromeshd
sudo systemctl start astromeshd
```

Check service status:

```bash
sudo systemctl status astromeshd
```

Expected output:

```
● astromeshd.service - Astromesh Agent Runtime Daemon
     Loaded: loaded (/etc/systemd/system/astromeshd.service; enabled)
     Active: active (running) since Mon 2026-03-20 10:00:00 UTC; 5s ago
   Main PID: 4521 (astromeshd)
     Status: "Ready — 1 agent(s) loaded"
     Memory: 128.0M
```

## Verify

```bash
astromeshctl status
```

```bash
curl http://localhost:8000/v1/health
```

## Log Access

```bash
# Follow live logs
sudo journalctl -u astromeshd -f

# Last 100 lines
sudo journalctl -u astromeshd -n 100

# Only errors
sudo journalctl -u astromeshd -p err
```

## Filesystem Paths

| Path | Purpose |
|------|---------|
| `/etc/astromesh/` | Configuration files |
| `/var/lib/astromesh/` | Persistent state (memory, models) |
| `/var/log/astromesh/` | Log files |
| `/opt/astromesh/bin/` | `astromeshd` and `astromeshctl` binaries |
| `/etc/systemd/system/astromeshd.service` | systemd unit file |

## Upgrade

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_amd64.deb
sudo apt install ./astromesh_latest_amd64.deb
```

The package restarts the service automatically. Verify:

```bash
astromeshctl version
astromeshctl status
```

## Uninstall

```bash
sudo systemctl stop astromeshd
sudo systemctl disable astromeshd
sudo apt remove astromesh
```

To remove all configuration and data:

```bash
sudo apt purge astromesh
sudo rm -rf /etc/astromesh /var/lib/astromesh /var/log/astromesh
sudo userdel astromesh
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common Linux issues
