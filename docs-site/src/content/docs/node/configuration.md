---
title: "Configuration"
description: "runtime.yaml reference, profiles, filesystem paths, and environment variables for Astromesh Node"
---

Astromesh Node is configured through `runtime.yaml` and an optional `.env` file. The `astromeshctl init` wizard generates both. This page documents all configuration options.

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
    port: 8000              # HTTP port
    log_level: info         # debug | info | warning | error

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

## The 7 Profiles

Profiles are pre-configured `runtime.yaml` templates. Select one during `astromeshctl init --profile <name>`.

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

### `minimal` — Lightweight Single Agent

```yaml
spec:
  services:
    api: true
    agents: true
    inference: false
    memory: false
    tools: false
    channels: false
    rag: false
    observability: false
```

**Use when:** Small-footprint deployments, IoT, or edge devices with constrained resources.

### `rag` — Document Retrieval

```yaml
spec:
  services:
    api: true
    agents: true
    inference: false
    memory: true
    tools: false
    channels: false
    rag: true
    observability: true
```

**Use when:** Dedicated document Q&A or knowledge-base node.

### `edge` — Offline / Air-Gapped

```yaml
spec:
  services:
    api: true
    agents: true
    inference: true
    memory: false
    tools: false
    channels: false
    rag: false
    observability: false
```

**Use when:** Isolated environments with no outbound internet access, using bundled local models.

## Filesystem Paths by Platform

| Resource | Linux | macOS | Windows |
|----------|-------|-------|---------|
| Configuration | `/etc/astromesh/` | `/etc/astromesh/` | `C:\ProgramData\Astromesh\config\` |
| State / Data | `/var/lib/astromesh/` | `/var/lib/astromesh/` | `C:\ProgramData\Astromesh\data\` |
| Logs | `/var/log/astromesh/` | `/var/log/astromesh/` | `C:\ProgramData\Astromesh\logs\` |
| Binaries | `/opt/astromesh/bin/` | `/usr/local/bin/` | `C:\Program Files\Astromesh\bin\` |
| Service unit | `/etc/systemd/system/astromeshd.service` | `/Library/LaunchDaemons/com.astromesh.astromeshd.plist` | Windows Service Registry |

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

Secrets and overrides can be set in `<config-dir>/.env`. The daemon loads this file automatically at startup.

```bash
# LLM Provider API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=gsk_...

# Memory Backends
REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://user:pass@localhost:5432/astromesh

# Channel Adapters
WHATSAPP_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...

# Runtime Overrides
ASTROMESH_LOG_LEVEL=debug           # Override log level from runtime.yaml
ASTROMESH_PORT=9000                 # Override API port
ASTROMESH_FORCE_PYTHON=1            # Disable Rust native extensions
```

Environment variables take precedence over values in `runtime.yaml`.

### Referencing Environment Variables in YAML

Any YAML value can reference an environment variable using `${VAR_NAME}` syntax:

```yaml
# providers.yaml
providers:
  - name: openai
    type: openai
    api_key: "${OPENAI_API_KEY}"
    model: gpt-4o
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

See the [Deployment: Astromesh Node](/astromesh/node/introduction/) reference for a full 3-node example.

## Reload Configuration

On Linux and macOS, you can reload configuration without restarting the daemon:

```bash
# Linux
sudo systemctl reload astromeshd

# macOS
sudo kill -HUP $(pgrep astromeshd)
```

This sends `SIGHUP` to the daemon, which reloads agent definitions and provider config without dropping active connections.

On Windows, restart the service:

```powershell
Restart-Service AstromeshDaemon
```

## Validate Configuration

Before starting or after making changes:

```bash
astromeshctl config validate
```

Expected output:

```
Validating /etc/astromesh/runtime.yaml ... OK
Validating /etc/astromesh/providers.yaml ... OK
Validating /etc/astromesh/agents/default.agent.yaml ... OK

All configuration files are valid.
```
