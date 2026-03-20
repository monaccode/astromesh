---
title: "Install on macOS"
description: "Install Astromesh Node as a launchd service on macOS"
---

This guide covers installing Astromesh Node on macOS 13 (Ventura) and later, on both Apple Silicon (arm64) and Intel (x86_64).

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| macOS | 13 (Ventura)+ | `sw_vers -productVersion` |
| Architecture | arm64 or x86_64 | `uname -m` |
| Python | 3.12+ (bundled by the installer) | `python3 --version` |
| Network | Outbound to LLM provider or local Ollama | — |

## Download

Download the appropriate archive for your architecture from GitHub Releases.

**Apple Silicon (M1/M2/M3/M4):**

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_darwin_arm64.tar.gz
```

**Intel Mac:**

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_darwin_amd64.tar.gz
```

## Install

Extract and run the installer script:

```bash
tar -xzf astromesh_latest_darwin_arm64.tar.gz
cd astromesh_latest_darwin_arm64
sudo ./install.sh
```

The installer:

1. Copies `astromeshd` and `astromeshctl` to `/usr/local/bin/`
2. Creates the `_astromesh` system user (no login shell)
3. Creates configuration and data directories
4. Installs the launchd plist to `/Library/LaunchDaemons/com.astromesh.astromeshd.plist`

Expected output:

```
Installing Astromesh Node v0.18.0...
Creating system user '_astromesh'...
Creating directories...
  /etc/astromesh/
  /var/lib/astromesh/
  /var/log/astromesh/
Installing binaries to /usr/local/bin/...
Installing Python virtual environment...
Installing launchd daemon...
astromesh installed successfully.

Run 'sudo astromeshctl init' to configure.
```

Verify the installation:

```bash
astromeshctl version
```

Expected output:

```
Astromesh Node v0.18.0
Daemon:   /usr/local/bin/astromeshd
CLI:      /usr/local/bin/astromeshctl
Python:   3.12.x
Platform: darwin/arm64
```

## Gatekeeper (macOS Security)

On first run, macOS Gatekeeper may block the binaries because they are not from the Mac App Store. To allow them:

```bash
sudo xattr -d com.apple.quarantine /usr/local/bin/astromeshd
sudo xattr -d com.apple.quarantine /usr/local/bin/astromeshctl
```

Or open System Settings > Privacy & Security and click "Allow Anyway" after the first blocked execution.

## Configure

Run the interactive wizard:

```bash
sudo astromeshctl init
```

For a non-interactive setup:

```bash
sudo astromeshctl init --profile full --provider ollama --model llama3.1:8b --non-interactive
```

This creates:

- `/etc/astromesh/runtime.yaml`
- `/etc/astromesh/providers.yaml`
- `/etc/astromesh/agents/default.agent.yaml`

See [Configuration](/astromesh/node/configuration/) for the full schema.

## Start the Service

Load and start the launchd daemon:

```bash
sudo launchctl load /Library/LaunchDaemons/com.astromesh.astromeshd.plist
```

To stop:

```bash
sudo launchctl unload /Library/LaunchDaemons/com.astromesh.astromeshd.plist
```

The daemon is configured with `KeepAlive = true` — launchd restarts it automatically if it exits.

To enable start-at-boot (the plist is already in `/Library/LaunchDaemons/`, so it loads at boot by default once loaded).

## Verify

```bash
astromeshctl status
```

```bash
curl http://localhost:8000/v1/health
```

## Log Access

Logs are written to `/var/log/astromesh/`:

```bash
# Follow live logs
tail -f /var/log/astromesh/astromeshd.log

# View errors
grep ERROR /var/log/astromesh/astromeshd.log

# System console logs (launchd)
log show --predicate 'process == "astromeshd"' --last 1h
```

## Filesystem Paths

| Path | Purpose |
|------|---------|
| `/etc/astromesh/` | Configuration files |
| `/var/lib/astromesh/` | Persistent state (memory, models) |
| `/var/log/astromesh/` | Log files |
| `/usr/local/bin/astromeshd` | Daemon binary |
| `/usr/local/bin/astromeshctl` | CLI binary |
| `/Library/LaunchDaemons/com.astromesh.astromeshd.plist` | launchd unit |

## Upgrade

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_latest_darwin_arm64.tar.gz
tar -xzf astromesh_latest_darwin_arm64.tar.gz
cd astromesh_latest_darwin_arm64
sudo ./install.sh
```

The installer unloads and reloads the launchd daemon automatically.

## Uninstall

```bash
sudo launchctl unload /Library/LaunchDaemons/com.astromesh.astromeshd.plist
sudo rm /Library/LaunchDaemons/com.astromesh.astromeshd.plist
sudo rm /usr/local/bin/astromeshd /usr/local/bin/astromeshctl
```

To remove all configuration and data:

```bash
sudo rm -rf /etc/astromesh /var/lib/astromesh /var/log/astromesh
sudo dscl . -delete /Users/_astromesh
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common macOS issues
