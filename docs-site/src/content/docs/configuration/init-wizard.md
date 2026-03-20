---
title: Init Wizard
description: Interactive setup with astromeshctl init
---

The `astromeshctl init` command launches an interactive wizard that generates Astromesh configuration files based on your answers. Instead of writing YAML by hand, the wizard walks you through each decision and produces ready-to-use config files.

## Development vs System Mode

The wizard runs in two modes depending on how you invoke it:

```bash
# Development mode — writes config to ./config/ in the current directory
astromeshctl init --dev

# System mode — writes config to /etc/astromesh/ (requires root)
sudo astromeshctl init
```

| Mode | Config directory | Use case |
|------|-----------------|----------|
| `--dev` | `./config/` | Local development, testing, CI |
| System (default) | `/etc/astromesh/` | Production servers, Astromesh Node |

In development mode, all generated files land in a `config/` directory relative to your project root. In system mode, files are written to `/etc/astromesh/`, which is where `astromeshd` (the daemon) looks by default.

## Wizard Walkthrough

The wizard asks five groups of questions in sequence. Each group generates or updates specific config files.

### Step 1: Role Selection

```
? Select this node's role:
  > standalone (full)
    gateway
    worker
    inference
```

Your role determines which services run on this node:

| Role | What it does | Services enabled |
|------|-------------|-----------------|
| **standalone (full)** | All-in-one deployment — API, agents, inference, memory, tools, channels, RAG, observability | All |
| **gateway** | Entry point that routes requests to workers. Handles external channels (WhatsApp, etc.) and observability | api, channels, observability |
| **worker** | Runs agents, tools, memory, and RAG pipelines. Does not serve inference or external channels | api, agents, memory, tools, rag, observability |
| **inference** | Dedicated LLM inference node. Serves model requests only | api, inference, observability |

The wizard writes a `runtime.yaml` using the corresponding [profile](/astromesh/configuration/profiles/) for the selected role.

### Step 2: Provider Configuration

```
? Which LLM providers do you want to enable?
  [x] Ollama (local)
  [ ] OpenAI-compatible API
  [ ] vLLM
  [ ] llama.cpp
  [ ] HuggingFace TGI
  [ ] ONNX Runtime
```

For each selected provider, the wizard asks follow-up questions:

- **Ollama** — endpoint URL (default: `http://localhost:11434`), models to pull
- **OpenAI-compatible** — endpoint URL, environment variable name for the API key (e.g., `OPENAI_API_KEY`), model names
- **vLLM** — endpoint URL, model identifier
- **llama.cpp** — endpoint URL
- **HuggingFace TGI** — endpoint URL, model name
- **ONNX Runtime** — local model path

The wizard generates `providers.yaml` with all selected providers and a default routing configuration:

```yaml
apiVersion: astromesh/v1
kind: ProviderConfig
metadata:
  name: default-providers

spec:
  providers:
    ollama:
      type: ollama
      endpoint: "http://localhost:11434"
      models:
        - "llama3.1:8b"
      health_check_interval: 30

  routing:
    default_strategy: cost_optimized
    fallback_enabled: true
    circuit_breaker:
      failure_threshold: 3
      recovery_timeout: 60
```

### Step 3: Mesh Mode

```
? Enable Maia mesh networking? (y/N)
```

If you answer **yes**, the wizard asks for seed node URLs:

```
? Enter seed node URLs (comma-separated, empty if this is the first node):
  > http://gateway:8000
```

This adds the `mesh` section to `runtime.yaml`:

```yaml
spec:
  mesh:
    enabled: true
    node_name: worker
    bind: "0.0.0.0:8000"
    seeds:
      - http://gateway:8000
    heartbeat_interval: 5
    gossip_interval: 2
    gossip_fanout: 3
    failure_timeout: 15
    dead_timeout: 30
```

If you answer **no**, mesh networking is disabled and the node operates standalone or with static peers.

### Step 4: Memory Backend

```
? Select the default memory backend:
  > SQLite (no external dependencies)
    Redis
    PostgreSQL
```

| Backend | Best for | Requires |
|---------|----------|----------|
| **SQLite** | Development, single-node deployments | Nothing (built-in) |
| **Redis** | Production with TTL-based expiry, fast reads | Running Redis instance |
| **PostgreSQL** | Production with durable storage, complex queries | Running PostgreSQL instance |

For Redis and PostgreSQL, the wizard asks for connection details (host, port, database name, credentials). These are written as environment variable references in the generated agent YAML templates.

### Step 5: Observability

```
? Enable OpenTelemetry observability? (Y/n)
```

If enabled, the wizard sets `services.observability: true` in `runtime.yaml`. It optionally asks for the OTLP exporter endpoint (default: `http://localhost:4317`) and generates the corresponding environment variable hints.

## Generated Files

After completing all steps, the wizard produces the following files:

| File | Generated when |
|------|---------------|
| `runtime.yaml` | Always |
| `providers.yaml` | Always |
| `channels.yaml` | Role is gateway or standalone |
| `agents/example.agent.yaml` | Role is worker or standalone |

The wizard prints a summary of all generated files and their locations:

```
✓ Generated config/runtime.yaml
✓ Generated config/providers.yaml
✓ Generated config/channels.yaml
✓ Generated config/agents/example.agent.yaml

Your Astromesh node is configured. Start with:
  uv run uvicorn astromesh.api.main:app --host 0.0.0.0 --port 8000
```

## Non-Interactive Mode

For CI pipelines and automated provisioning, use the `--non-interactive` flag with explicit options:

```bash
astromeshctl init --non-interactive \
  --role worker \
  --providers ollama \
  --ollama-endpoint http://ollama:11434 \
  --memory-backend redis \
  --redis-url redis://redis:6379 \
  --mesh-enabled \
  --mesh-seeds http://gateway:8000 \
  --observability \
  --dev
```

Every wizard question has a corresponding CLI flag. Run `astromeshctl init --help` for the full list.

## Example: Full Wizard Run

Here is a complete wizard session generating a standalone development configuration:

```
$ astromeshctl init --dev

Astromesh Configuration Wizard
==============================

? Select this node's role: standalone (full)
? Which LLM providers do you want to enable? Ollama (local)
? Ollama endpoint URL: http://localhost:11434
? Ollama models to configure: llama3.1:8b, nomic-embed-text
? Enable Maia mesh networking? No
? Select the default memory backend: SQLite
? Enable OpenTelemetry observability? Yes

Generating configuration...

✓ Generated config/runtime.yaml
✓ Generated config/providers.yaml
✓ Generated config/channels.yaml
✓ Generated config/agents/example.agent.yaml

Your Astromesh node is configured. Start with:
  uv run uvicorn astromesh.api.main:app --host 0.0.0.0 --port 8000
```

The generated `runtime.yaml` uses the `full` profile with all services enabled. The `providers.yaml` contains the Ollama provider with the specified endpoint and models. An example agent YAML file is created to help you get started quickly.
