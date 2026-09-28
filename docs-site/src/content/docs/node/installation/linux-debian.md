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
| Python | 3.12+ as the system `python3` (package dependency) | `python3 --version` |
| Architecture | amd64 only | `dpkg --print-architecture` |
| Network | Outbound to LLM provider or local Ollama | — |

## Download the Package

Node packages are attached to the `node-v*` releases on GitHub (the repository's "latest" release is the core, so `releases/latest/download/...` does not find them):

```bash
VERSION=0.1.7
curl -LO https://github.com/monaccode/astromesh/releases/download/node-v${VERSION}/astromesh-node_${VERSION}_amd64.deb
```

## Install

```bash
sudo apt install ./astromesh-node_${VERSION}_amd64.deb
```

The package creates the `astromesh` system user, installs the virtualenv in `/opt/astromesh/venv/`, the config in `/etc/astromesh/` and the systemd unit, and enables the unit without starting it.

Verify the installation:

```bash
astromeshctl version
```

Expected output:

```
astromesh-cli 0.3.1
astromesh core 0.59.0
```

## Configure

Run the interactive wizard to generate your configuration:

```bash
sudo astromeshctl init
```

This creates, in `/etc/astromesh/`:

- `runtime.yaml` — daemon configuration (services, API, peers/mesh)
- `providers.yaml` — LLM provider connections
- `.env` — the provider API key, if you entered one (loaded by the systemd unit)

The package already installs sample agents in `/etc/astromesh/agents/`. For a non-interactive setup:

```bash
sudo astromeshctl init --role full --non-interactive
```

:::caution[The wizard does not find its role profile in a packaged install]
It prints `Profile not found` and writes an empty `runtime.yaml`. Copy the profile the package ships instead: `sudo cp /etc/astromesh/profiles/full.yaml /etc/astromesh/runtime.yaml` (or `gateway`, `worker`, `inference`, `mesh-*`).
:::

See [Configuration](/astromesh/node/configuration/) for the full `runtime.yaml` schema and the roles.

## Start the Service

The package enables the unit but does not start it:

```bash
sudo systemctl start astromeshd
```

Check service status:

```bash
sudo systemctl status astromeshd
```

Expected output:

```
● astromeshd.service - Astromesh Agent Runtime Daemon
     Loaded: loaded (/lib/systemd/system/astromeshd.service; enabled)
     Active: active (running) since Mon 2026-03-20 10:00:00 UTC; 5s ago
   Main PID: 4521 (astromeshd)
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
| `/var/log/astromesh/` | Audit logs (daemon logs go to journald) |
| `/opt/astromesh/venv/` | Virtualenv; `astromeshd` and `astromeshctl` are symlinked into `/usr/bin/` |
| `/lib/systemd/system/astromeshd.service` | systemd unit file |

## Upgrade

```bash
VERSION=0.1.7
curl -LO https://github.com/monaccode/astromesh/releases/download/node-v${VERSION}/astromesh-node_${VERSION}_amd64.deb
sudo apt install ./astromesh-node_${VERSION}_amd64.deb
```

Upgrading stops the service (the old package's pre-remove script) and does not start it again. Start it and verify:

```bash
sudo systemctl start astromeshd
astromeshctl version
astromeshctl status
```

## Uninstall

```bash
sudo apt remove astromesh-node
```

Removing stops and disables the service. To also remove configuration, data, logs, the virtualenv and the `astromesh` user:

```bash
sudo apt purge astromesh-node
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common Linux issues
