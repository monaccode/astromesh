---
title: Daemon (astromeshd)
description: The Astromesh daemon process
---

`astromeshd` is the daemon process that turns the Astromesh library into a long-running system service. It bootstraps the runtime, starts the API server, and integrates with process supervisors like systemd.

## What It Does

The daemon wraps `AgentRuntime` with process management concerns:

- Loads configuration from disk
- Bootstraps the full runtime (agents, providers, memory, tools)
- Starts the FastAPI/Uvicorn HTTP server
- Writes a PID file for process management
- Sends readiness notification to systemd
- Handles graceful shutdown on SIGTERM/SIGINT

## Startup Sequence

```
astromeshd started
       │
       ▼
┌──────────────────────┐
│ 1. Find config dir   │  --config flag > /etc/astromesh > ./config/
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 2. Read runtime.yaml │  Global settings: port, log level, providers
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 3. Bootstrap runtime │  Scan agents/, load channels, wire services
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 4. Start API server  │  Uvicorn on configured host:port
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 5. Write PID file    │  /var/run/astromesh/astromeshd.pid
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 6. Notify systemd    │  sd_notify(READY=1)
└──────────────────────┘
           │
           ▼
     Serving requests
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config PATH` | (auto-detect) | Explicit path to configuration directory |
| `--port PORT` | `8000` | Port for the HTTP API server |
| `--host HOST` | `0.0.0.0` | Bind address for the HTTP server |
| `--log-level LEVEL` | `info` | Logging level: `debug`, `info`, `warning`, `error` |
| `--pid-file PATH` | `/var/run/astromesh/astromeshd.pid` | Path to write the PID file |
| `--workers N` | `1` | Number of Uvicorn worker processes |

### Examples

```bash
# Start with defaults (auto-detect config)
astromeshd

# Explicit config directory and debug logging
astromeshd --config /etc/astromesh --log-level debug

# Custom port and PID file
astromeshd --port 9000 --pid-file /tmp/astromesh.pid
```

## Config Auto-Detection

When `--config` is not provided, the daemon searches for a configuration directory in this order:

| Priority | Path | Typical Use |
|----------|------|-------------|
| 1 | `--config` flag value | Explicit override |
| 2 | `$ASTROMESH_CONFIG_DIR` | Environment variable override |
| 3 | `/etc/astromesh/` | System-wide installation (Linux packages) |
| 4 | `./config/` | Local development, Docker containers |

The first path that exists and contains a `runtime.yaml` file is used. If none is found, the daemon exits with an error.

## PID File

The daemon writes its process ID to a PID file after the API server is ready. This enables process managers and init systems to track and signal the process.

**Default location:** `/var/run/astromesh/astromeshd.pid`

The PID file is removed on graceful shutdown. If the daemon crashes, a stale PID file may remain -- `astromeshd` checks for and cleans up stale PID files on startup.

## systemd Integration

The daemon integrates with systemd using the `sd_notify` protocol.

**Example unit file (`/etc/systemd/system/astromesh.service`):**

```ini
[Unit]
Description=Astromesh Agent Runtime
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=notify
ExecStart=/usr/bin/astromeshd --config /etc/astromesh
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
User=astromesh
Group=astromesh
RuntimeDirectory=astromesh
PIDFile=/var/run/astromesh/astromeshd.pid

[Install]
WantedBy=multi-user.target
```

| systemd Feature | Support |
|-----------------|---------|
| `Type=notify` | Yes -- daemon sends `READY=1` after API server is listening |
| `ExecReload` | SIGHUP triggers config reload (re-scan agents, reload YAML) |
| `Restart=on-failure` | Automatic restart on non-zero exit |
| Watchdog | Not currently supported |

## Filesystem Layout

| Path | Description |
|------|-------------|
| `/usr/bin/astromeshd` | Daemon binary (installed via APT/pip) |
| `/usr/bin/astromeshctl` | CLI binary |
| `/etc/astromesh/` | System configuration directory |
| `/etc/astromesh/runtime.yaml` | Global runtime configuration |
| `/etc/astromesh/agents/` | Agent YAML definitions |
| `/etc/astromesh/channels.yaml` | Channel adapter configuration |
| `/var/run/astromesh/astromeshd.pid` | PID file |
| `/var/log/astromesh/` | Log files (when file logging is enabled) |
| `/var/lib/astromesh/` | Persistent data (vector stores, episodic logs) |

## Graceful Shutdown

On receiving SIGTERM or SIGINT:

1. Stop accepting new requests
2. Wait for in-flight requests to complete (30-second timeout)
3. Close MCP server connections
4. Flush pending memory writes
5. Remove PID file
6. Exit with code 0
