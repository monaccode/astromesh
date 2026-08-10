# astromeshctl

<p align="center">
  <a href="https://monaccode.github.io/astromesh/#ecosystem"><img src="https://img.shields.io/badge/astromesh-operate-f59e0b?labelColor=161b22" alt="Astromesh · Operate"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/ci.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-cli.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-cli.yml/badge.svg" alt="CLI Release"></a>
  <a href="https://pypi.org/project/astromesh-cli/"><img src="https://img.shields.io/pypi/v/astromesh-cli?label=astromeshctl%20PyPI" alt="CLI PyPI"></a>
  <a href="https://test.pypi.org/project/astromesh-cli/"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Ftest.pypi.org%2Fpypi%2Fastromesh-cli%2Fjson&query=%24.info.version&label=CLI%20TestPyPI" alt="CLI TestPyPI"></a>
  <a href="https://github.com/monaccode/astromesh/blob/develop/LICENSE"><img src="https://img.shields.io/github/license/monaccode/astromesh" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
</p>

The terminal interface to an Astromesh node: agents, config, mesh state, profiles, and more.

## Install

```bash
pip install astromesh-cli
```

## Quick start

```bash
# Check versions
astromeshctl version

# Talk to a running node
astromeshctl status
astromeshctl agents list
astromeshctl ask "What agents are running?"

# Run an agent
astromeshctl run my-agent "Hello"

# Inspect traces and metrics
astromeshctl traces list
astromeshctl metrics
astromeshctl cost
```

## Commands

| Command | Purpose |
|---------|---------|
| `status` | Node health and summary |
| `doctor` | Diagnostics |
| `agents` | List, create, and manage agents |
| `providers` | Manage LLM providers |
| `mesh` / `peers` | Mesh networking |
| `services` | Service discovery |
| `run` | Run an agent |
| `dev` | Local development server |
| `traces` / `trace` | Execution traces |
| `tools` | Tool registry |
| `metrics` / `cost` | Usage and cost |
| `ask` | Ask the node a question |
| `new` | Scaffold new resources |

Plugins can extend `astromeshctl` via the `astromeshctl.plugins` entry point. For example, `astromesh-node` and `astromesh-orbit` register themselves this way.

## Documentation

- [CLI Commands](../docs-site/src/content/docs/reference/cli-commands.md)
- [Astromesh Docs](https://monaccode.github.io/astromesh/)

## License

Apache-2.0
