---
title: "Install on macOS"
description: "Install Astromesh Node as a launchd service on macOS"
---

This guide covers installing Astromesh Node on macOS 13 (Ventura) and later.

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| macOS | 13 (Ventura)+ | `sw_vers -productVersion` |
| Architecture | Apple silicon (`arm64`) or Intel (`x86_64`) since **v0.1.10**; up to v0.1.9, Apple silicon only | `uname -m` |
| Python | None — the archive carries its own CPython 3.12 in `/usr/local/opt/astromesh/python` (since **v0.1.9**) | — |
| Network | Outbound to LLM provider or local Ollama | — |

## Download

Node archives are attached to the `node-v*` releases on GitHub (the repository's "latest" release is the core, so `releases/latest/download/...` does not find them). There is one archive per architecture, `arm64` (Apple silicon) and `x86_64` (Intel); `uname -m` picks the right one:

```bash
VERSION=0.1.10
ARCH=$(uname -m)
curl -LO https://github.com/monaccode/astromesh/releases/download/node-v${VERSION}/astromesh-node-${VERSION}-macos-${ARCH}.tar.gz
```

Up to v0.1.9 there was a single `astromesh-node-<version>-macos.tar.gz`, built for Apple silicon only.

## Install

The archive has no top-level folder, so extract it into one and run the installer script:

```bash
mkdir astromesh-node
tar -xzf astromesh-node-${VERSION}-macos-${ARCH}.tar.gz -C astromesh-node
cd astromesh-node
sudo ./install.sh
```

The installer:

1. Copies the bundled CPython and the virtualenv to `/usr/local/opt/astromesh/{python,venv}/`, replacing any previous copy, and symlinks `astromeshd` and `astromeshctl` into `/usr/local/bin/`
2. Creates `/Library/Application Support/Astromesh/{config,data}` and `/Library/Logs/Astromesh/`
3. Creates the `_astromesh` system user (no login shell)
4. Copies the launchd plist to `/Library/LaunchDaemons/com.astromesh.daemon.plist` (it does not load it)

Verify the installation:

```bash
astromeshctl version
```

Expected output:

```
astromesh-cli 0.3.1
astromesh core 0.61.0
```

## Gatekeeper (macOS Security)

On first run, macOS Gatekeeper may block the binaries because they are not from the Mac App Store. To allow them:

```bash
sudo xattr -d com.apple.quarantine /usr/local/bin/astromeshd
sudo xattr -d com.apple.quarantine /usr/local/bin/astromeshctl
```

Or open System Settings > Privacy & Security and click "Allow Anyway" after the first blocked execution.

## Configure

The launchd plist starts the daemon with `--config "/Library/Application Support/Astromesh/config"`, but `sudo astromeshctl init` writes to `/etc/astromesh/` when run as root. Run the wizard in dev mode from the Astromesh folder so it writes where the daemon reads:

```bash
cd "/Library/Application Support/Astromesh"
sudo astromeshctl init --dev
```

For a non-interactive setup:

```bash
sudo astromeshctl init --dev --role full --non-interactive
```

This creates `config/runtime.yaml` and `config/providers.yaml`. The macOS archive ships neither role profiles nor sample agents, so the wizard writes an empty `runtime.yaml` (all services on, port 8000 — the `full` defaults) and no agents: add your `*.agent.yaml` files to `config/agents/`. An API key you enter goes to `/Library/Application Support/Astromesh/.env`, which launchd does not read — set it in the plist's `EnvironmentVariables` instead.

See [Configuration](/astromesh/node/configuration/) for the full schema.

## Start the Service

Load and start the launchd daemon:

```bash
sudo launchctl load /Library/LaunchDaemons/com.astromesh.daemon.plist
```

To stop:

```bash
sudo launchctl unload /Library/LaunchDaemons/com.astromesh.daemon.plist
```

The daemon is configured with `KeepAlive = true` — launchd restarts it automatically if it exits, and loads it at boot once installed in `/Library/LaunchDaemons/`.

## Verify

```bash
astromeshctl status
```

```bash
curl http://localhost:8000/v1/health
```

## Log Access

launchd writes the daemon's stdout and stderr to `/Library/Logs/Astromesh/`:

```bash
tail -f /Library/Logs/Astromesh/astromeshd.err.log
tail -f /Library/Logs/Astromesh/astromeshd.out.log
```

## Filesystem Paths

| Path | Purpose |
|------|---------|
| `/Library/Application Support/Astromesh/config/` | Configuration files |
| `/Library/Application Support/Astromesh/data/` | Persistent state |
| `/Library/Logs/Astromesh/` | Log files |
| `/usr/local/opt/astromesh/venv/` | Virtualenv (`astromeshd`, `astromeshctl` symlinked into `/usr/local/bin/`) |
| `/Library/LaunchDaemons/com.astromesh.daemon.plist` | launchd unit |

:::caution[Archives up to v0.1.8]
They packaged a virtualenv built on the CI runner, and every command failed with `bad interpreter` on a real Mac. Use **v0.1.9** or later.
:::

## Upgrade

Unload the daemon, then download, extract and run `sudo ./install.sh` as above — since **v0.1.9** it replaces the old `python/` and `venv/` itself. The installer does not reload the daemon; load it yourself:

```bash
sudo launchctl unload /Library/LaunchDaemons/com.astromesh.daemon.plist
# download + extract + sudo ./install.sh
sudo launchctl load /Library/LaunchDaemons/com.astromesh.daemon.plist
```

## Uninstall

```bash
sudo launchctl unload /Library/LaunchDaemons/com.astromesh.daemon.plist
sudo rm /Library/LaunchDaemons/com.astromesh.daemon.plist
sudo rm /usr/local/bin/astromeshd /usr/local/bin/astromeshctl
sudo rm -rf /usr/local/opt/astromesh
```

To remove all configuration and data:

```bash
sudo rm -rf "/Library/Application Support/Astromesh" /Library/Logs/Astromesh
sudo dscl . -delete /Users/_astromesh
```

## Next Steps

- [Configuration](/astromesh/node/configuration/) — Customize runtime.yaml and profiles
- [CLI Reference](/astromesh/node/cli-reference/) — Full astromeshctl reference
- [Troubleshooting](/astromesh/node/troubleshooting/) — Common macOS issues
