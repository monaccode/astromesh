# Astromesh Installation Guide

## APT Repository (Recommended)

### 1. Add the repository

```bash
curl -fsSL https://monaccode.github.io/astromesh/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/astromesh.gpg
echo "deb [signed-by=/usr/share/keyrings/astromesh.gpg] https://monaccode.github.io/astromesh stable main" | sudo tee /etc/apt/sources.list.d/astromesh.list
sudo apt update && sudo apt install astromesh
```

### 2. Configure

Edit the provider configuration with your API keys:

```bash
sudo nano /etc/astromesh/providers.yaml
```

Review and adjust the runtime configuration:

```bash
sudo nano /etc/astromesh/runtime.yaml
```

### 3. Start the service

```bash
sudo systemctl start astromeshd
sudo systemctl status astromeshd
```

### 4. Verify

```bash
astromeshctl status
```

## Post-Install

### File locations

| Path | Description |
|------|-------------|
| `/etc/astromesh/` | Configuration files (preserved on upgrade) |
| `/opt/astromesh/venv/` | Python virtual environment |
| `/var/lib/astromesh/` | Runtime data (models, memory, data) |
| `/var/log/astromesh/` | Logs and audit trail |
| `/usr/bin/astromeshd` | Daemon binary (symlink) |
| `/usr/bin/astromeshctl` | CLI tool (symlink) |

### Agent configuration

Agent definitions are in `/etc/astromesh/agents/`. Each `.agent.yaml` file defines an agent with its model, tools, prompts, and orchestration settings.

### Installing additional dependencies

The base package includes minimal dependencies. To add ML or vector store backends, install them into the Astromesh venv:

```bash
sudo /opt/astromesh/venv/bin/pip install torch faiss-cpu sentence-transformers
```

## Upgrading

```bash
sudo apt update && sudo apt upgrade astromesh
```

Your configuration files in `/etc/astromesh/` are preserved during upgrades. If a new version ships updated defaults, apt will ask how to handle the difference.

## Uninstalling

### Keep data and configuration

```bash
sudo apt remove astromesh
```

This removes the package but preserves `/var/lib/astromesh`, `/var/log/astromesh`, `/etc/astromesh`, and the `astromesh` user.

### Remove everything

```bash
sudo apt purge astromesh
```

This removes all files, data, logs, and the `astromesh` system user.

## Manual Installation

Download the `.deb` directly from [GitHub Releases](https://github.com/monaccode/astromesh/releases):

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_<VERSION>_amd64.deb
sudo dpkg -i astromesh_*_amd64.deb
sudo apt-get -f install  # resolve dependencies if needed
```

## Requirements

- Ubuntu 22.04+ / Debian 12+
- Python 3.12+
- systemd
