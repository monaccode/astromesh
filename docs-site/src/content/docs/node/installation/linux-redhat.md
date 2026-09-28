---
title: "Install on RHEL / Fedora"
description: "Install Astromesh Node as a systemd service on RHEL, Fedora, and CentOS"
---

This guide covers installing Astromesh Node on RPM-based Linux distributions: RHEL 9+, Fedora 38+, CentOS Stream 9+, and AlmaLinux/Rocky Linux 9+.

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| RHEL / Fedora / CentOS | RHEL 9+ / Fedora 38+ | `cat /etc/os-release` |
| systemd | 250+ | `systemctl --version` |
| Python | 3.12+ as the system `python3` (package dependency) | `python3 --version` |
| Architecture | x86_64 only | `uname -m` |
| Network | Outbound to LLM provider or local Ollama | — |

## Download the Package

Node packages are attached to the `node-v*` releases on GitHub (the repository's "latest" release is the core, so `releases/latest/download/...` does not find them):

```bash
VERSION=0.1.6
curl -LO https://github.com/monaccode/astromesh/releases/download/node-v${VERSION}/astromesh-node-${VERSION}-1.x86_64.rpm
```

## Install

```bash
sudo dnf install ./astromesh-node-${VERSION}-1.x86_64.rpm
```

:::caution[Declared dependencies]
The package is built from the same nfpm manifest as the `.deb` and declares `python3 >= 3.12` and `python3-venv`. RHEL 9's default `python3` is 3.9 and no RPM repository names a `python3-venv` package, so `dnf` may refuse the install until the dependency is provided.
:::

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

For a non-interactive setup:

```bash
sudo astromeshctl init --role full --non-interactive
```

This creates `/etc/astromesh/runtime.yaml`, `providers.yaml` and, if you entered a provider API key, `.env` (loaded by the systemd unit). The package already installs sample agents in `/etc/astromesh/agents/`.

:::caution[The wizard does not find its role profile in a packaged install]
It prints `Profile not found` and writes an empty `runtime.yaml`. Copy the profile the package ships instead: `sudo cp /etc/astromesh/profiles/full.yaml /etc/astromesh/runtime.yaml` (or `gateway`, `worker`, `inference`, `mesh-*`).
:::

See [Configuration](/astromesh/node/configuration/) for the full `runtime.yaml` schema and the roles.

## SELinux Considerations

The package ships no SELinux policy module. On systems with SELinux enforcing, if you encounter denials:

```bash
# Check for SELinux denials
sudo ausearch -c astromeshd -m avc

# Generate a local policy module if needed
sudo ausearch -c astromeshd -m avc | audit2allow -M astromesh_local
sudo semodule -i astromesh_local.pp
```

## Firewall (firewalld)

To allow external access to the API port:

```bash
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

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
     Active: active (running) since Fri 2026-03-20 10:00:00 UTC; 5s ago
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
VERSION=0.1.6
curl -LO https://github.com/monaccode/astromesh/releases/download/node-v${VERSION}/astromesh-node-${VERSION}-1.x86_64.rpm
sudo dnf upgrade ./astromesh-node-${VERSION}-1.x86_64.rpm
```

The old package's pre-remove script runs after the new one is installed, so the upgrade leaves the service stopped **and disabled**. Re-enable and start it, then verify:

```bash
sudo systemctl enable --now astromeshd
astromeshctl version
astromeshctl status
```

## Uninstall

```bash
sudo dnf remove astromesh-node
```

Removing stops and disables the service.

To remove all configuration and data:

```bash
sudo rm -rf /etc/astromesh /var/lib/astromesh /var/log/astromesh /opt/astromesh
sudo userdel astromesh
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common Linux issues
