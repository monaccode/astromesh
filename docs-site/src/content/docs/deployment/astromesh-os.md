---
title: "Astromesh OS"
description: "Production deployment with daemon, systemd, and CLI"
---

This guide covers deploying Astromesh as a system-level service using the `astromeshd` daemon, `astromeshctl` CLI, and systemd integration. This is the recommended approach for single-server production deployments on Linux.

## What and Why

Astromesh OS wraps the Astromesh runtime with a system layer that provides:

- **`astromeshd`** -- a daemon process that boots the agent runtime, manages lifecycle (graceful shutdown, config reload), writes a PID file, and integrates with systemd via `sd_notify`
- **`astromeshctl`** -- a CLI that communicates with the daemon over HTTP, providing colored status tables, health checks, and configuration validation
- **Filesystem conventions** -- standardized paths for config, data, and logs that follow Linux FHS
- **systemd integration** -- automatic start on boot, restart on failure, watchdog health checks, and structured logging via journald

This is the right choice when you want a production-ready single-server deployment with proper process supervision, without the overhead of containers or Kubernetes.

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Ubuntu / Debian | 22.04+ | `lsb_release -a` |
| systemd | 250+ | `systemctl --version` |
| Python | 3.12+ (provided by APT package) | `python3 --version` |
| Network | Outbound to LLM provider or local Ollama | -- |

## Step-by-step Setup

### 1. Install via GitHub Release package

Download and install the latest `.deb` package:

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_<VERSION>_amd64.deb
sudo apt install ./astromesh_<VERSION>_amd64.deb
```

Expected output:

```
Reading package lists... Done
Setting up astromesh (0.10.0) ...
Creating system user 'astromesh'...
Creating directories...
  /etc/astromesh/
  /var/lib/astromesh/
  /var/log/astromesh/
  /opt/astromesh/
Installing Python virtual environment...
Installing systemd service...
astromesh installed successfully.
```

Verify the installation:

```bash
astromeshctl version
```

Expected output:

```
Astromesh v0.10.0
Daemon: /opt/astromesh/bin/astromeshd
CLI:    /opt/astromesh/bin/astromeshctl
Python: 3.12.x
```

### 2. Run the init wizard

The init wizard generates configuration files in `/etc/astromesh/`:

```bash
sudo astromeshctl init
```

Expected output:

```
🔧 Astromesh Init Wizard

? Select deployment profile:
  > full         All services on one node
    gateway      API gateway only
    worker       Agent execution + tools
    inference    LLM inference only

? Select profile: full
? Select provider: Ollama (local)
? Ollama endpoint: http://localhost:11434
? Select model: llama3.1:8b
? Enable memory? Yes
? Memory backend: SQLite (local)
? Enable observability? No

✅ Configuration written to /etc/astromesh/
   - /etc/astromesh/runtime.yaml
   - /etc/astromesh/providers.yaml
   - /etc/astromesh/agents/default.agent.yaml
```

### 3. Profiles explained

The init wizard offers pre-built profiles that control which services activate on the node:

| Profile | Services enabled | Use case |
|---------|-----------------|----------|
| `full` | api, agents, inference, memory, tools, channels, rag, observability | Single-node, everything on one machine |
| `gateway` | api, channels, observability | Public entry point, routes to workers |
| `worker` | api, agents, tools, memory, rag, observability | Agent execution, delegates inference |
| `inference` | api, inference, observability | Dedicated LLM inference node |

Profiles are regular `runtime.yaml` files with pre-configured `spec.services` sections. You can customize any profile after generation.

### 4. Start the service

```bash
sudo systemctl enable astromeshd
sudo systemctl start astromeshd
```

Expected output:

```
Created symlink /etc/systemd/system/multi-user.target.wants/astromeshd.service →
  /etc/systemd/system/astromeshd.service.
```

Check the service status:

```bash
sudo systemctl status astromeshd
```

Expected output:

```
● astromeshd.service - Astromesh Agent Runtime Daemon
     Loaded: loaded (/etc/systemd/system/astromeshd.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-03-09 10:00:00 UTC; 5s ago
   Main PID: 4521 (astromeshd)
     Status: "Ready — 1 agent(s) loaded"
      Tasks: 8 (limit: 4567)
     Memory: 128.0M
     CGroup: /system.slice/astromeshd.service
             └─4521 /opt/astromesh/bin/astromeshd --config /etc/astromesh/

Mar 09 10:00:00 server astromeshd[4521]: INFO     Loading config from /etc/astromesh/
Mar 09 10:00:00 server astromeshd[4521]: INFO     Loaded 1 agent(s): default
Mar 09 10:00:00 server astromeshd[4521]: INFO     Providers: ollama (healthy)
Mar 09 10:00:00 server astromeshd[4521]: INFO     API server listening on 0.0.0.0:8000
Mar 09 10:00:00 server astromeshd[4521]: INFO     Ready.
```

### 5. View logs

```bash
# Follow live logs
sudo journalctl -u astromeshd -f

# Last 100 lines
sudo journalctl -u astromeshd -n 100

# Logs since last boot
sudo journalctl -u astromeshd -b

# Logs in a time range
sudo journalctl -u astromeshd --since "2026-03-09 10:00:00" --until "2026-03-09 11:00:00"
```

## systemd Service

The systemd unit file installed by the package:

```ini
[Unit]
Description=Astromesh Agent Runtime Daemon
After=network.target

[Service]
Type=notify
ExecStart=/opt/astromesh/bin/astromeshd
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Key behaviors:

- **`Type=notify`** -- the daemon signals systemd when it is ready via `sd_notify`, so dependent services wait until Astromesh is fully initialized
- **`Restart=on-failure`** -- systemd restarts the daemon automatically if it crashes
- **`ProtectSystem=strict`** -- the filesystem is read-only except for explicitly allowed paths
- **`ProtectHome=true`** -- no access to `/home` directories
- **Signal handling** -- `SIGTERM` triggers graceful shutdown, `SIGHUP` reloads configuration

### Reload configuration without restart

```bash
sudo systemctl reload astromeshd
```

This sends `SIGHUP` to the daemon, which reloads agent definitions and provider config without dropping active connections.

## Filesystem Layout

```
/etc/astromesh/                    # Configuration (read-only at runtime)
├── runtime.yaml                   # Daemon config (host, port, log level, services)
├── providers.yaml                 # LLM provider connections
├── channels.yaml                  # Channel adapters
├── agents/                        # Agent definitions
│   └── *.agent.yaml
└── rag/                           # RAG pipeline definitions
    └── *.rag.yaml

/var/lib/astromesh/                # Persistent state (daemon writes here)
├── models/                        # Local models (Ollama, GGUF files)
├── memory/                        # SQLite databases, FAISS indices
└── data/                          # Runtime state (PID file)

/var/log/astromesh/                # Logs
├── astromeshd.log                 # Daemon log (rotated by logrotate)
└── audit/                         # Agent execution audit trail

/opt/astromesh/                    # Binaries and runtime
├── bin/                           # astromeshd, astromeshctl
└── lib/                           # Python virtual environment
```

### Permissions

| Path | Owner | Mode | Purpose |
|------|-------|------|---------|
| `/etc/astromesh/` | `root:astromesh` | `750` | Sensitive config, readable by daemon |
| `/var/lib/astromesh/` | `astromesh:astromesh` | `755` | Daemon writes state here |
| `/var/log/astromesh/` | `astromesh:astromesh` | `755` | Log files |
| `/opt/astromesh/` | `root:root` | `755` | Read-only binaries |

## Verification

### Health check

```bash
curl http://localhost:8000/health
```

Expected output:

```json
{
  "status": "healthy",
  "version": "0.10.0"
}
```

### CLI status

```bash
astromeshctl status
```

Expected output:

```
┌──────────────────────────────────────┐
│         Astromesh Status             │
├──────────────┬───────────────────────┤
│ Status       │ ● Running             │
│ Version      │ 0.10.0                │
│ Uptime       │ 2h 34m                │
│ Mode         │ system                │
│ PID          │ 4521                  │
│ Agents       │ 1 loaded              │
│ Providers    │ 1 healthy, 0 degraded │
│ Memory       │ 128.0 MB              │
└──────────────┴───────────────────────┘
```

### Doctor (full health check)

```bash
astromeshctl doctor
```

Expected output:

```
Astromesh Doctor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Daemon          Running (PID 4521)
✅ API Server      Responding on :8000
✅ Provider: ollama   Connected (llama3.1:8b available)
✅ Memory: sqlite     /var/lib/astromesh/memory/conversations.db
⚠️  Memory: redis     Not configured
⚠️  Memory: postgres  Not configured

Result: Healthy (2 warnings)
```

## CLI Operations

### Agent management

```bash
# List loaded agents
astromeshctl agents list
```

Expected output:

```
┌──────────┬─────────────────────────┬──────────────────┬─────────┐
│ Name     │ Description             │ Model            │ Pattern │
├──────────┼─────────────────────────┼──────────────────┼─────────┤
│ default  │ Default assistant agent │ ollama/llama3.1:8b │ react │
└──────────┴─────────────────────────┴──────────────────┴─────────┘
```

```bash
# Agent detail
astromeshctl agents info default
```

### Provider management

```bash
# List providers
astromeshctl providers list
```

Expected output:

```
┌─────────┬────────┬─────────────────────────┬──────────┐
│ Name    │ Type   │ Endpoint                │ Status   │
├─────────┼────────┼─────────────────────────┼──────────┤
│ ollama  │ ollama │ http://localhost:11434  │ ● Healthy│
└─────────┴────────┴─────────────────────────┴──────────┘
```

### Configuration validation

Validate config files without starting the daemon:

```bash
astromeshctl config validate
```

Expected output:

```
Validating /etc/astromesh/runtime.yaml ... ✅
Validating /etc/astromesh/providers.yaml ... ✅
Validating /etc/astromesh/agents/default.agent.yaml ... ✅

All configuration files are valid.
```

### JSON output

All CLI commands support `--json` for scripting and automation:

```bash
astromeshctl status --json
```

Expected output:

```json
{
  "status": "running",
  "version": "0.10.0",
  "uptime_seconds": 9240,
  "mode": "system",
  "pid": 4521,
  "agents_loaded": 1,
  "providers": {
    "healthy": 1,
    "degraded": 0
  }
}
```

## Multi-Node Setup

For deployments across multiple machines, configure each node with a different profile and static peer references.

### Example: 3-node deployment

**Machine A -- Gateway (192.168.1.10)**

```yaml
# /etc/astromesh/runtime.yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: gateway
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: false
    inference: false
    memory: false
    tools: false
    channels: true
    rag: false
    observability: true
  peers:
    - name: worker-1
      url: http://192.168.1.11:8000
      services: [agents, tools, memory, rag]
    - name: inference-1
      url: http://192.168.1.12:8000
      services: [inference]
```

**Machine B -- Worker (192.168.1.11)**

```yaml
# /etc/astromesh/runtime.yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: worker
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: true
    inference: false
    memory: true
    tools: true
    channels: false
    rag: true
    observability: true
  peers:
    - name: inference-1
      url: http://192.168.1.12:8000
      services: [inference]
```

**Machine C -- Inference (192.168.1.12)**

```yaml
# /etc/astromesh/runtime.yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: inference
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: false
    inference: true
    memory: false
    tools: false
    channels: false
    rag: false
    observability: true
  peers: []
```

Install Astromesh on each machine, copy the appropriate `runtime.yaml`, and start the service:

```bash
# On each machine
sudo systemctl enable astromeshd
sudo systemctl start astromeshd
```

Verify the mesh from the gateway:

```bash
curl http://192.168.1.10:8000/health
```

Expected output:

```json
{
  "status": "healthy",
  "version": "0.10.0"
}
```

The gateway forwards agent execution requests to the worker, which forwards inference requests to the inference node. All communication happens over HTTP via the existing API.

## Upgrading

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_<VERSION>_amd64.deb
sudo apt install ./astromesh_<VERSION>_amd64.deb
```

Expected output:

```
Setting up astromesh (0.11.0) ...
Restarting astromeshd...
astromesh upgraded to 0.11.0.
```

The package handles service restart automatically. To verify:

```bash
astromeshctl status
```

## Uninstalling

```bash
sudo systemctl stop astromeshd
sudo systemctl disable astromeshd
sudo apt remove astromesh
```

This removes the binaries and systemd unit. Configuration and data directories are preserved. To remove everything:

```bash
sudo apt purge astromesh
sudo rm -rf /etc/astromesh /var/lib/astromesh /var/log/astromesh
sudo userdel astromesh
```

## Troubleshooting

### Service will not start

```bash
sudo systemctl status astromeshd
sudo journalctl -u astromeshd -n 50
```

Common causes:

**Port already in use:**

```
ERROR: [Errno 98] Address already in use: ('0.0.0.0', 8000)
```

Find what is using port 8000:

```bash
sudo ss -tlnp | grep 8000
```

Either stop the conflicting process or change the port in `/etc/astromesh/runtime.yaml`.

**Config syntax error:**

```
ERROR: Failed to parse /etc/astromesh/runtime.yaml: expected ':', line 5
```

Validate the config:

```bash
astromeshctl config validate
```

Fix the YAML syntax error and restart:

```bash
sudo systemctl restart astromeshd
```

### Permission errors

```
PermissionError: [Errno 13] Permission denied: '/var/lib/astromesh/memory/conversations.db'
```

Fix ownership:

```bash
sudo chown -R astromesh:astromesh /var/lib/astromesh
sudo chown -R astromesh:astromesh /var/log/astromesh
```

### Config validation fails

```bash
astromeshctl config validate
```

```
Validating /etc/astromesh/runtime.yaml ... ❌
  Error: Unknown field 'servics' in spec — did you mean 'services'?
```

Fix the typo in the config file and validate again.

### Stale PID file

```
ERROR: PID file /var/lib/astromesh/data/astromeshd.pid exists but process 4521 is not running
```

The daemon did not shut down cleanly. Remove the stale PID file and restart:

```bash
sudo rm /var/lib/astromesh/data/astromeshd.pid
sudo systemctl restart astromeshd
```

### Provider connection failures

```
ERROR: Provider 'ollama' health check failed: Connection refused
```

Check that the provider is running and accessible:

```bash
# For Ollama
curl http://localhost:11434/api/tags

# For OpenAI
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

The model router circuit breaker trips after 3 consecutive failures and enters a 60-second cooldown. Check provider status:

```bash
astromeshctl providers list
```

### Viewing detailed daemon logs

```bash
# All logs, full output
sudo journalctl -u astromeshd --no-pager

# Only errors
sudo journalctl -u astromeshd -p err

# Follow live with timestamps
sudo journalctl -u astromeshd -f -o short-precise
```
