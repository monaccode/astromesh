---
title: CLI Commands
description: Complete command reference for astromeshd and astromeshctl
---

Quick-reference for every command available in the Astromesh CLI tools.

## astromeshd

The daemon process. Bootstraps the runtime, starts the API server, and manages the agent lifecycle.

| Command | Description |
|---------|-------------|
| `astromeshd` | Start the daemon with auto-detected configuration |
| `astromeshd --config PATH` | Start with an explicit configuration directory |
| `astromeshd --port PORT` | Override the API server port (default: `8000`) |
| `astromeshd --host HOST` | Override the bind address (default: `0.0.0.0`) |
| `astromeshd --log-level LEVEL` | Set logging level: `debug`, `info`, `warning`, `error` (default: `info`) |
| `astromeshd --pid-file PATH` | Custom PID file location (default: `/var/run/astromesh/astromeshd.pid`) |
| `astromeshd --workers N` | Number of Uvicorn worker processes (default: `1`) |

### Examples

```bash
# Development: debug logging, default config
astromeshd --log-level debug

# Production: explicit config, custom port
astromeshd --config /etc/astromesh --port 9000

# Multiple workers behind a load balancer
astromeshd --workers 4 --port 8000
```

For detailed daemon documentation, see [Daemon (astromeshd)](/astromesh/reference/os/daemon/).

## astromeshctl

The CLI client. Communicates with a running daemon via the REST API.

### Global Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--host URL` | `http://localhost:8000` | Address of the Astromesh daemon to connect to |
| `--json` | `false` | Output in machine-readable JSON format |
| `--help` | -- | Show help for any command or subcommand |

### Status & Health

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl status` | -- | Show daemon version, uptime, mode, PID, and agent count |
| `astromeshctl doctor` | -- | Run health checks on runtime, providers, and backends |

### Agent Management

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl agents list` | -- | List all loaded agents with model, orchestration pattern, and status |

### Provider Management

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl providers list` | -- | List configured providers with health status, latency, and circuit breaker state |

### Configuration

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl config validate` | `--config PATH` | Validate runtime.yaml and agent YAML files without starting the daemon |
| `astromeshctl init` | `--dev`, `--non-interactive`, `--output PATH` | Interactive configuration wizard to generate runtime.yaml and agent templates |

**`init` flags:**

| Flag | Description |
|------|-------------|
| `--dev` | Generate development defaults (in-memory backends, debug logging, Ollama) |
| `--non-interactive` | Use all defaults without prompting (for CI/scripts) |
| `--output PATH` | Directory to write config files (default: `./config/`) |

### Service Management

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl services` | -- | List services enabled on this node and their status |

### Mesh (Cluster) Commands

These commands require mesh mode to be enabled.

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl peers list` | -- | List known peer nodes with address, status, and last seen time |
| `astromeshctl mesh status` | -- | Show cluster overview: node count, leader, alive/suspect/dead breakdown |
| `astromeshctl mesh nodes` | -- | Detailed node table with agent assignments, active requests, CPU, and memory |
| `astromeshctl mesh leave` | `--force` | Gracefully leave the cluster (drain requests, notify peers) |

**`mesh leave` flags:**

| Flag | Description |
|------|-------------|
| `--force` | Leave immediately without draining active requests |

### Usage Examples

```bash
# Check if the daemon is running
astromeshctl status

# Run health checks
astromeshctl doctor

# List agents in JSON format
astromeshctl agents list --json

# Validate config before deploying
astromeshctl config validate --config /etc/astromesh

# Connect to a remote daemon
astromeshctl --host http://10.0.1.10:8000 status

# Check mesh cluster health
astromeshctl mesh status

# Generate dev config non-interactively
astromeshctl init --dev --non-interactive

# View detailed node info in mesh
astromeshctl mesh nodes --json
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (daemon unreachable, invalid arguments) |
| `2` | Configuration validation failed |
| `3` | Agent not found |
| `4` | Mesh operation failed (not in mesh mode, node not found) |
