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
| Python | 3.12+ (bundled by the package) | `python3 --version` |
| Architecture | x86_64 or aarch64 | `uname -m` |
| Network | Outbound to LLM provider or local Ollama | — |

## Download the Package

Download the latest `.rpm` package from GitHub Releases:

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_x86_64.rpm
```

For ARM64 / aarch64 (e.g., AWS Graviton):

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_aarch64.rpm
```

To download a specific version:

```bash
curl -LO https://github.com/monaccode/astromesh/releases/download/v0.18.0/astromesh_0.18.0_x86_64.rpm
```

## Install

**RHEL 9 / CentOS Stream / AlmaLinux / Rocky Linux:**

```bash
sudo dnf install ./astromesh_latest_x86_64.rpm
```

**Fedora:**

```bash
sudo dnf install ./astromesh_latest_x86_64.rpm
```

**Legacy (rpm directly):**

```bash
sudo rpm -i astromesh_latest_x86_64.rpm
```

Expected output:

```
Preparing...                          ################################# [100%]
Updating / installing...
   1:astromesh-0.18.0                 ################################# [100%]
Creating system user 'astromesh'...
Creating directories...
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
Platform: linux/x86_64
```

## Configure

Run the interactive wizard to generate your configuration:

```bash
sudo astromeshctl init
```

For a non-interactive setup with a specific profile:

```bash
sudo astromeshctl init --profile full --provider ollama --model llama3.1:8b --non-interactive
```

This creates:

- `/etc/astromesh/runtime.yaml` — daemon configuration
- `/etc/astromesh/providers.yaml` — LLM provider connections
- `/etc/astromesh/agents/default.agent.yaml` — default agent definition

See [Configuration](/astromesh/node/configuration/) for the full `runtime.yaml` schema and all 7 profiles.

## SELinux Considerations

On RHEL/CentOS systems with SELinux enforcing, the package installs the appropriate SELinux policy module. If you encounter denials:

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
     Loaded: loaded (/usr/lib/systemd/system/astromeshd.service; enabled)
     Active: active (running) since Fri 2026-03-20 10:00:00 UTC; 5s ago
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
| `/usr/lib/systemd/system/astromeshd.service` | systemd unit file |

## Upgrade

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_x86_64.rpm
sudo dnf upgrade ./astromesh_latest_x86_64.rpm
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
sudo dnf remove astromesh
```

To remove all configuration and data:

```bash
sudo rm -rf /etc/astromesh /var/lib/astromesh /var/log/astromesh
sudo userdel astromesh
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common Linux issues
