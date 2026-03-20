# Astromesh Node — The Daemon & CLI

**What it does:** Turns Astromesh from a Python library into a system service that starts on boot, stays running, and can be managed from the terminal.

**Related docs:** [Nodes](ASTROMESH_NODES.md) · [Maia](ASTROMESH_MAIA.md) · [Architecture](GENERAL_ARCHITECTURE.md)

---

## The Big Picture

Without Astromesh Node, you run agents like this:

```bash
uv run uvicorn astromesh.api.main:app --reload
```

That works for development. But in production you want a proper service that:

- Starts automatically when the server boots
- Writes a PID file so you can monitor it
- Handles shutdown signals gracefully (SIGTERM, SIGINT)
- Reports readiness to systemd
- Has a CLI tool for quick status checks and diagnostics

Astromesh Node adds two things: the **daemon** (`astromeshd`) and the **CLI** (`astromeshctl`).

---

## How It Works

```
You (terminal)                    The Server
     │                                │
     │  astromeshd                    │
     │  ─────────►  Reads config/     │
     │              Loads agents      │
     │              Starts API        │
     │              Writes PID file   │
     │              Tells systemd ✓   │
     │                                │
     │  astromeshctl status           │
     │  ─────────►  GET /v1/system/status
     │  ◄─────────  uptime, agents, version
     │                                │
     │  astromeshctl doctor           │
     │  ─────────►  GET /v1/system/doctor
     │  ◄─────────  health checks ✓/✗
```

### The Daemon — `astromeshd`

This is the process that runs your agents. When you start it:

1. **Finds config** — Looks for `runtime.yaml` in `/etc/astromesh/` (production) or `./config/` (development). You can also pass `--config /path/to/dir`.
2. **Reads runtime.yaml** — Gets host, port, enabled services, peers.
3. **Bootstraps the runtime** — Loads all `*.agent.yaml` files, wires up providers, memory, tools.
4. **Starts the API** — FastAPI + Uvicorn on the configured host:port.
5. **Writes PID file** — At `/var/lib/astromesh/data/astromeshd.pid` (overridable).
6. **Notifies systemd** — Sends `READY=1` so systemd knows it's alive.

```bash
# Auto-detect config (tries /etc/astromesh/, then ./config/)
astromeshd

# Explicit config directory
astromeshd --config /etc/astromesh

# Override port
astromeshd --port 9000

# Debug logging
astromeshd --log-level debug
```

### The CLI — `astromeshctl`

This is your remote control. It talks to the running daemon via HTTP.

```bash
# Is the daemon running? How many agents are loaded?
astromeshctl status

# Are providers healthy? Any connectivity issues?
astromeshctl doctor

# What agents are loaded?
astromeshctl agents list

# What model providers are configured?
astromeshctl providers list

# Is my runtime.yaml valid? (doesn't need a running daemon)
astromeshctl config validate

# Machine-readable output for scripts
astromeshctl status --json
```

Every command supports `--json` for scripting and automation.

---

## Config Auto-Detection

The daemon figures out where to look for config files:

| Priority | Path | When |
|----------|------|------|
| 1 | `--config /your/path` | You told it explicitly |
| 2 | `/etc/astromesh/` | System install (production) |
| 3 | `./config/` | Local directory (development) |

In **system mode** (`/etc/astromesh/`), the full filesystem layout is:

```
/etc/astromesh/          Config files (runtime.yaml, agents/, providers.yaml)
/var/lib/astromesh/      State (PID file, data)
/var/log/astromesh/      Logs
/opt/astromesh/          Application binaries
```

In **dev mode** (`./config/`), everything lives in your project directory.

---

## systemd Integration

For production Linux servers, Astromesh Node ships a systemd unit file:

```ini
# /etc/systemd/system/astromeshd.service
[Unit]
Description=Astromesh Agent Runtime Daemon
After=network.target

[Service]
Type=notify                    # Waits for READY=1
ExecStart=/opt/astromesh/bin/astromeshd
Restart=on-failure

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
# Install and start
sudo packaging/install.sh
sudo systemctl enable astromeshd
sudo systemctl start astromeshd

# Check status
sudo systemctl status astromeshd
astromeshctl status
```

The install script creates a dedicated `astromesh` user, sets up the filesystem layout, and configures permissions.

---

## API Endpoints

Astromesh Node adds two system endpoints to the API:

| Endpoint | What it returns |
|----------|----------------|
| `GET /v1/system/status` | Version, uptime, mode (system/dev), PID, agent count |
| `GET /v1/system/doctor` | Health checks for runtime and each configured provider |

```bash
curl http://localhost:8000/v1/system/status
# {"version": "0.8.0", "uptime_seconds": 3600, "mode": "dev", "agents_loaded": 3}

curl http://localhost:8000/v1/system/doctor
# {"healthy": true, "checks": {"runtime": {"status": "ok"}, ...}}
```

---

## When to Use What

| I want to... | Use |
|-------------|-----|
| Develop locally | `uv run uvicorn astromesh.api.main:app --reload` |
| Run in production (Linux) | `astromeshd` with systemd |
| Run in Docker | `astromeshd` as container entrypoint |
| Quick health check | `astromeshctl status` or `astromeshctl doctor` |

---

## What's Next

Astromesh Node gives you a single node running all services. To split services across multiple nodes, see [Astromesh Nodes](ASTROMESH_NODES.md). To let nodes discover each other automatically, see [Astromesh Maia](ASTROMESH_MAIA.md).
