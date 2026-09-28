---
title: "Configuration"
description: "runtime.yaml reference, profiles, filesystem paths, and environment variables for Astromesh Node"
---

Astromesh Node is configured through `runtime.yaml` and an optional `.env` file. The `astromeshctl init` wizard generates both (the `.env` only when you enter a provider API key). This page documents all configuration options.

## runtime.yaml Schema

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: my-node             # Identifier for this node

spec:
  # API server settings
  api:
    host: "0.0.0.0"         # Bind address (use 127.0.0.1 for local-only)
    port: 8000              # HTTP port (log level is the astromeshd --log-level flag)

  # Services to activate on this node
  services:
    api: true               # REST API + WebSocket server
    agents: true            # Agent execution engine
    inference: true         # Local LLM inference (Ollama, ONNX)
    memory: true            # Memory manager (conversational, semantic, episodic)
    tools: true             # Tool registry and execution
    channels: false         # Channel adapters (WhatsApp, etc.)
    rag: false              # RAG pipelines
    observability: false    # OpenTelemetry + Prometheus

  # Optional: remote peer nodes (for multi-node setups)
  peers: []
```

## Roles and Profiles

Profiles are pre-configured `runtime.yaml` templates. `astromeshctl init --role <name>` offers four of them — `full`, `gateway`, `worker`, `inference`. The packages also ship `mesh-gateway`, `mesh-worker` and `mesh-inference` (the same services with a `spec.mesh` block instead of static `peers`) in `/etc/astromesh/profiles/` on Linux; the wizard does not offer those, so copy them by hand.

### `full` — All Services on One Node

```yaml
spec:
  services:
    api: true
    agents: true
    inference: true
    memory: true
    tools: true
    channels: true
    rag: true
    observability: true
```

**Use when:** Single-server deployment, development, or small production workloads.

### `gateway` — API Gateway

```yaml
spec:
  services:
    api: true
    agents: false
    inference: false
    memory: false
    tools: false
    channels: true
    rag: false
    observability: true
```

**Use when:** Public entry point that routes requests to worker nodes.

### `worker` — Agent Execution

```yaml
spec:
  services:
    api: true
    agents: true
    inference: false
    memory: true
    tools: true
    channels: false
    rag: true
    observability: true
```

**Use when:** Agent execution node in a multi-node cluster; delegates inference to a dedicated inference node.

### `inference` — LLM Inference Only

```yaml
spec:
  services:
    api: true
    agents: false
    inference: true
    memory: false
    tools: false
    channels: false
    rag: false
    observability: true
```

**Use when:** GPU-accelerated inference node dedicated to running local models.

## Filesystem Paths by Platform

| Resource | Linux | macOS | Windows |
|----------|-------|-------|---------|
| Configuration | `/etc/astromesh/` | `/Library/Application Support/Astromesh/config/` | `C:\ProgramData\Astromesh\config\` |
| State / Data | `/var/lib/astromesh/` | `/Library/Application Support/Astromesh/data/` | `C:\ProgramData\Astromesh\data\` |
| Logs | journald (`/var/log/astromesh/` for audit) | `/Library/Logs/Astromesh/` | — |
| Virtualenv | `/opt/astromesh/venv/` (symlinked into `/usr/bin/`) | `/usr/local/opt/astromesh/venv/` (symlinked into `/usr/local/bin/`) | `C:\Program Files\Astromesh\venv\` (`Scripts\` added to PATH) |
| Service | `/lib/systemd/system/astromeshd.service` | `/Library/LaunchDaemons/com.astromesh.daemon.plist` | Windows service `astromeshd` |

### Configuration Directory Layout

```
<config-dir>/
├── runtime.yaml             # Daemon configuration
├── providers.yaml           # LLM provider connections
├── channels.yaml            # Channel adapters (optional)
├── agents/                  # Agent definitions
│   └── *.agent.yaml
└── rag/                     # RAG pipeline definitions (optional)
    └── *.rag.yaml
```

## Environment Variables

The daemon does not read a `.env` file itself. On Linux the systemd unit loads `/etc/astromesh/.env` (`EnvironmentFile=-/etc/astromesh/.env`), which is where `astromeshctl init` stores a provider API key. On macOS and Windows, set variables in the launchd plist or the service's environment.

```bash
# /etc/astromesh/.env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
ASTROMESH_FORCE_PYTHON=1            # Disable Rust native extensions
```

Host and port come from `runtime.yaml` or the `astromeshd` flags, not from environment variables. See [Environment Variables](/astromesh/reference/env-vars/) for everything the runtime reads.

Providers name the variable that holds their key with `api_key_env`, which is what the wizard writes:

```yaml
# providers.yaml
spec:
  providers:
    openai:
      type: openai_compat
      endpoint: https://api.openai.com/v1
      api_key_env: OPENAI_API_KEY
      models: [gpt-4o, gpt-4o-mini]
```

## Multi-Node Configuration

For multi-node deployments, configure `spec.peers` to point each node to its peers:

```yaml
# Gateway node (runtime.yaml)
spec:
  services:
    api: true
    channels: true
  peers:
    - name: worker-1
      url: http://192.168.1.11:8000
      services: [agents, tools, memory, rag]
    - name: inference-1
      url: http://192.168.1.12:8000
      services: [inference]
```


## Applying Changes

Restart the daemon after changing configuration:

```bash
sudo systemctl restart astromeshd        # Linux
```

```powershell
Restart-Service astromeshd               # Windows
```

On macOS, unload and load the plist.

`systemctl reload astromeshd` (or `SIGHUP`, on Linux and macOS) reloads **agents and RAG pipelines** from `agents/` and `rag/` without restarting — available since astromesh-node **v0.1.5** (core **v0.60.0**). Everything is rebuilt aside and swapped at once: a cycle between agents or a chain that doesn't compile leaves the running agents untouched; an agent that fails to build goes `draft` with its error (see `astromeshctl agents list`) without taking the others down; a paused agent stays paused. In-flight runs finish on the old agent. `runtime.yaml` (host, port, services, mesh, peers) and `providers.yaml` are **not** reloaded — restart for those; the daemon logs a warning if `runtime.yaml` changed. With `ASTROMESH_PERSIST_AGENTS=0` the reload is refused, because the disk is not where the agents live.

## Validate Configuration

Before starting or after making changes (`--path` defaults to `./config`):

```bash
astromeshctl config validate --path /etc/astromesh
```

Expected output:

```
Configuration valid (12 file(s) checked).
```

It exits `0` even when it reports errors.
