# Astromesh OS — Phase 1 Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/astromesh-os

---

## Overview

Astromesh OS adds a **system layer** on top of the existing Astromesh runtime. It does not replace any existing component — it wraps and extends.

The goal is to transform Astromesh from a Python library with an API into a **system-level runtime daemon** with CLI management, filesystem conventions, and systemd integration.

**Scope (Phase 1):** Daemon + CLI + Filesystem layout + systemd
**Out of scope:** Container runtime (containerd), Rust migration, multi-node mesh

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Repository | Monorepo (same repo) | Small team, fast iteration, no cross-repo friction |
| Daemon language | Python | Runtime is Python async, maximum reuse, systemd handles supervision |
| CLI language | Python (Typer + Rich) | Autocomplete, colored tables, minimal code |
| Process model | Single-process async | Agents are I/O-bound (LLM calls, DB queries), one event loop handles hundreds concurrently |
| CLI ↔ Daemon IPC | HTTP via existing FastAPI API | Zero new communication code, reuses all existing endpoints |
| CLI framework | Typer >= 0.12 + Rich >= 13 | Declarative, type hints, auto-generated help, tables and colors |

---

## Architecture

```
+------------------------------------------+
| astromeshctl (CLI)                       |
|   -> HTTP client against localhost API   |
+------------------------------------------+
| astromeshd (daemon)                      |
|   -> systemd managed                    |
|   -> single-process async               |
|   -> boots AgentRuntime + FastAPI        |
|   -> PID file, graceful shutdown         |
|   -> config from /etc/astromesh/         |
+------------------------------------------+
| AgentRuntime (existing, unchanged)       |
|   ModelRouter, MemoryManager,            |
|   ToolRegistry, Guardrails, Patterns     |
+------------------------------------------+
| Infrastructure (Ollama, PG, Redis...)    |
+------------------------------------------+
```

The daemon is a **supervisor** that:
1. Reads configuration from `/etc/astromesh/` (system mode) or `./config/` (dev mode)
2. Initializes `AgentRuntime` with that config
3. Starts the API server (embedded uvicorn, single process)
4. Manages lifecycle (graceful shutdown on SIGTERM, config reload on SIGHUP)
5. Exposes health/status via the API
6. Notifies systemd when ready (sd_notify)

---

## Filesystem Layout

```
/etc/astromesh/                    # Configuration (read-only at runtime)
+-- runtime.yaml                   # Daemon config (host, port, log level)
+-- providers.yaml                 # LLM providers
+-- channels.yaml                  # Channel adapters
+-- agents/                        # Agent definitions
|   +-- *.agent.yaml
+-- rag/                           # RAG pipelines
    +-- *.rag.yaml

/var/lib/astromesh/                # Persistent state
+-- models/                        # Local models (Ollama, GGUF)
+-- memory/                        # SQLite DBs, FAISS indices
+-- data/                          # Runtime state (PID file)

/var/log/astromesh/                # Logs
+-- astromeshd.log                 # Daemon log (rotated by systemd/logrotate)
+-- audit/                         # Execution audit trail

/opt/astromesh/                    # Binaries and runtime
+-- bin/                           # astromeshd, astromeshctl
+-- lib/                           # Python venv with dependencies
```

### Permissions

- System user: `astromesh:astromesh`
- `/etc/astromesh/` — `root:astromesh 750` (sensitive config, readable by daemon)
- `/var/lib/astromesh/` — `astromesh:astromesh 755` (daemon writes here)
- `/var/log/astromesh/` — `astromesh:astromesh 755`

### Dev Mode Detection

The daemon auto-detects where it runs:
- If `/etc/astromesh/runtime.yaml` exists → system mode
- Otherwise → dev mode (uses `./config/`, logs to stdout)

---

## Components

### 1. astromeshd — Daemon

**Location:** `daemon/astromeshd.py`

Responsibilities:
- Parse args (`--config`, `--port`, `--log-level`, `--pid-file`)
- Load config from `/etc/astromesh/` or `./config/` (dev mode)
- Initialize `AgentRuntime`
- Start embedded uvicorn (single process, async)
- Write PID file
- Signal handling: `SIGTERM` → graceful shutdown, `SIGHUP` → reload config
- Health watchdog for systemd (`sd_notify`)

### 2. astromeshctl — CLI

**Location:** `cli/`

Commands:

| Command | Action | Source |
|---------|--------|--------|
| `status` | Daemon state, uptime, loaded agents | `GET /v1/system/status` |
| `doctor` | Health check (providers, memory, connectivity) | `GET /v1/system/doctor` |
| `agents list` | List loaded agents | `GET /v1/agents` |
| `agents info <name>` | Agent detail | `GET /v1/agents/{name}` |
| `providers list` | Providers and their state | `GET /v1/providers` |
| `providers health` | Health check all providers | `GET /v1/providers/health` |
| `config validate` | Validate YAML config without starting daemon | local (no HTTP) |
| `version` | Astromesh version | local |

Output: Rich tables with colors, status icons. JSON output via `--json` flag.

### 3. New API Endpoints

**Location:** `astromesh/api/system.py`

- `GET /v1/system/status` — uptime, version, loaded agents count, memory usage, mode (dev/system)
- `GET /v1/system/doctor` — checks each provider, memory backend, channel adapter; returns structured report

### 4. systemd Unit

**Location:** `packaging/systemd/astromeshd.service`

```ini
[Unit]
Description=Astromesh Agent Runtime Daemon
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=notify
User=astromesh
Group=astromesh
ExecStart=/opt/astromesh/bin/astromeshd --config /etc/astromesh/
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
WatchdogSec=30

[Install]
WantedBy=multi-user.target
```

### 5. Installation Script

**Location:** `packaging/install.sh`

Creates system user, directories, symlinks, sets permissions. Enables and starts systemd service.

---

## New Directory Structure

```
daemon/                    # astromeshd
+-- __init__.py
+-- astromeshd.py

cli/                       # astromeshctl
+-- __init__.py
+-- main.py                # Typer app entry point
+-- commands/
|   +-- status.py
|   +-- doctor.py
|   +-- agents.py
|   +-- providers.py
|   +-- config.py
+-- output.py              # Rich formatting helpers

packaging/
+-- systemd/
|   +-- astromeshd.service
+-- install.sh

astromesh/api/
+-- system.py              # New /v1/system/* endpoints
```

---

## New Dependencies

```toml
[project.optional-dependencies]
cli = ["typer>=0.12.0", "rich>=13.0.0"]
daemon = ["sdnotify>=0.3.0"]
```

Added as optional extras. Core package unchanged.

---

## Future Phases (Not Implemented)

### Phase 2 — Container Runtime (containerd)

Integrate containerd for isolated execution of tools and agents.

**Scope:**
- Tools execute inside OCI containers (not in-process)
- Agents can optionally run in container isolation
- `astromeshd` manages container lifecycle (create, start, stop, logs) via containerd gRPC API
- Per-agent resource policies: cgroups limits (CPU, memory), seccomp profiles
- New CLI commands: `astromeshctl containers list|logs|stop`
- Container image registry for tool images

**Architecture:**
```
astromeshd
+-- ContainerManager
    +-- containerd gRPC client
    +-- image pull/cache
    +-- container lifecycle
    +-- resource policy enforcement (cgroups)
    +-- seccomp profile loading
```

**Config extension (agents YAML):**
```yaml
spec:
  isolation:
    mode: container          # none | container
    image: astromesh/tools:latest
    resources:
      cpu: "0.5"
      memory: "512Mi"
    seccomp: default
```

**Dependencies:** `containerd` gRPC bindings (likely Rust or Go shim)

### Phase 3 — Rust Migration

Rewrite system-level components in Rust for robustness and distribution.

**Scope:**
- `astromeshd` supervisor in Rust: signal handling, PID management, process supervision
- `astromeshctl` as static Rust binary (distribute without Python)
- Unix domain socket at `/var/run/astromesh/astromeshd.sock` for privileged management
- Python runtime maintained as worker process managed by Rust supervisor
- Native containerd integration via Rust gRPC client

**Architecture:**
```
astromeshd (Rust)
+-- signal handler
+-- PID file manager
+-- Unix socket listener (privileged mgmt)
+-- Python worker supervisor
    +-- spawns Python runtime process
    +-- health monitoring
    +-- restart on failure
```

### Phase 4 — Astromesh Mesh

Distributed multi-node agent execution.

**Scope:**
- Agent scheduling across multiple nodes
- Service discovery between daemons (mDNS or etcd)
- Shared memory infrastructure (distributed Redis, CRDTs)
- Workload migration and rebalancing
- `astromeshctl nodes list|join|leave`
