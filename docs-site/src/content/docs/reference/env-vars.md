---
title: Environment Variables
description: Complete reference of all environment variables
---

This page lists every environment variable recognized by Astromesh, grouped by category.

## Docker Entrypoint

These variables are read by the Docker entrypoint script to configure container startup.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_ROLE` | `full` | Node role. Values: `full` (API + runtime), `api` (API only), `worker` (runtime only) |
| `ASTROMESH_MESH_ENABLED` | `false` | Enable Maia mesh networking. Set to `true` to join a cluster |
| `ASTROMESH_NODE_NAME` | `$(hostname)` | Unique node name for mesh identification |
| `ASTROMESH_SEEDS` | (empty) | Comma-separated list of seed node URLs for mesh discovery (e.g., `10.0.1.10:8001,10.0.1.11:8001`) |
| `ASTROMESH_PORT` | `8000` | Port for the HTTP API server |
| `ASTROMESH_AUTO_CONFIG` | `true` | Automatically generate runtime.yaml from environment variables on first start. Set to `false` to skip config generation and use existing files |

## Runtime

These variables affect runtime behavior regardless of deployment method.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_CONFIG_DIR` | (auto-detect) | Explicit path to the configuration directory. Overrides auto-detection (see [Daemon reference](/astromesh/reference/os/daemon/)) |
| `ASTROMESH_FORCE_PYTHON` | (unset) | Set to `1` to disable Rust native extensions and use pure-Python fallbacks. Useful for debugging or environments where Rust extensions cannot be compiled |
| `ASTROMESH_LOG_LEVEL` | `info` | Logging level: `debug`, `info`, `warning`, `error` |
| `ASTROMESH_LOG_FORMAT` | `text` | Log format: `text` (human-readable) or `json` (structured) |

## Provider API Keys

API keys and endpoints for LLM providers. Only configure the providers you intend to use.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required for OpenAI) | OpenAI API key. Starts with `sk-` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL. Override for Azure OpenAI or local proxies |
| `ANTHROPIC_API_KEY` | (required for Anthropic) | Anthropic API key |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server endpoint. Change when Ollama runs on a different host or port |
| `GOOGLE_API_KEY` | (required for Google) | Google AI (Gemini) API key |

## Memory Backends

Connection strings for memory storage backends.

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL for conversational memory and caching |
| `DATABASE_URL` | (none) | PostgreSQL connection string for episodic memory and durable storage (e.g., `postgresql://user:pass@localhost:5432/astromesh`) |
| `CHROMA_HOST` | `localhost` | ChromaDB server host for semantic memory |
| `CHROMA_PORT` | `8000` | ChromaDB server port |

## WhatsApp Channel

Required when using the WhatsApp channel adapter. All four variables must be set for the webhook to function.

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_VERIFY_TOKEN` | (required) | Token used to verify the webhook with Meta during setup. You choose this value and enter it in the Meta developer dashboard |
| `WHATSAPP_ACCESS_TOKEN` | (required) | Meta Graph API access token for sending messages. Obtained from the Meta developer dashboard |
| `WHATSAPP_PHONE_NUMBER_ID` | (required) | Phone number ID associated with your WhatsApp Business account |
| `WHATSAPP_APP_SECRET` | (required) | App secret used to validate incoming webhook request signatures (X-Hub-Signature-256 header) |

## Mesh (Maia)

Configuration for mesh networking when `ASTROMESH_MESH_ENABLED=true`.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_MESH_BIND_PORT` | `8001` | Port for inter-node gossip communication |
| `ASTROMESH_MESH_GOSSIP_INTERVAL` | `2000` | Gossip interval in milliseconds |
| `ASTROMESH_MESH_HEARTBEAT_INTERVAL` | `5000` | Heartbeat interval in milliseconds |
| `ASTROMESH_MESH_SUSPECT_THRESHOLD` | `15000` | Milliseconds without heartbeat before marking node suspect |
| `ASTROMESH_MESH_DEAD_THRESHOLD` | `30000` | Milliseconds without heartbeat before marking node dead |

## Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (none) | OpenTelemetry collector endpoint for traces and metrics |
| `OTEL_SERVICE_NAME` | `astromesh` | Service name reported in traces |

## Precedence

When the same setting is configurable via both an environment variable and a YAML config file, the environment variable takes precedence. This allows overriding config file values in deployment environments without modifying files.

```
Environment variable  (highest priority)
       ↓
CLI flag (--port, --log-level, etc.)
       ↓
runtime.yaml values
       ↓
Built-in defaults     (lowest priority)
```
