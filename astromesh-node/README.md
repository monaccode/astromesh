# Astromesh Node

<p align="center">
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-node.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-node.yml/badge.svg" alt="Node Release"></a>
  <a href="https://github.com/monaccode/astromesh/releases?q=node&expanded=true"><img src="https://img.shields.io/github/v/release/monaccode/astromesh?include_prereleases&label=release" alt="GitHub Release"></a>
  <a href="https://pypi.org/project/astromesh/"><img src="https://img.shields.io/pypi/v/astromesh?label=runtime" alt="Astromesh Runtime"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
</p>

Cross-platform system installer and daemon for the Astromesh agent runtime.

Supports Linux (Debian/Ubuntu, RHEL/Fedora), macOS, and Windows.

## Quick Start

```bash
# Install from GitHub Release
sudo apt install ./astromesh-node_0.1.10_amd64.deb     # Debian/Ubuntu
sudo dnf install ./astromesh-node-0.1.10-1.x86_64.rpm  # RHEL/Fedora

# Configure and start
sudo astromeshctl init --role full --non-interactive
sudo systemctl start astromeshd
```

## Development

```bash
cd astromesh-node
uv sync --extra all
uv run pytest -v
```
