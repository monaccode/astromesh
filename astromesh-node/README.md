# Astromesh Node

Cross-platform system installer and daemon for the Astromesh agent runtime.

Supports Linux (Debian/Ubuntu, RHEL/Fedora), macOS, and Windows.

## Quick Start

```bash
# Install from GitHub Release
sudo dpkg -i astromesh-node-0.1.0-amd64.deb    # Debian/Ubuntu
sudo rpm -i astromesh-node-0.1.0-amd64.rpm      # RHEL/Fedora

# Configure and start
sudo astromeshctl init --profile full
sudo systemctl start astromeshd
```

## Development

```bash
cd astromesh-node
uv sync --extra all
uv run pytest -v
```
