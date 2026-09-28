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
| `ASTROMESH_PERSIST_AGENTS` | `1` (enabled) | When `1` (default), agents created or updated via the HTTP API are written to `agents/<name>.agent.yaml` under `ASTROMESH_CONFIG_DIR`. Set to `0`, `false`, or `no` to keep agents in memory only (typical for tests). See [Forge, API & on-disk agents](/astromesh/configuration/forge-api-storage/) |
| `ASTROMESH_TEMPLATES_DIR` | (unset) | Optional extra directory of `*.template.yaml` files for Forge (`GET /v1/templates`). Merged with bundled and config paths; overrides earlier sources when template names match. See [Forge, API & on-disk agents](/astromesh/configuration/forge-api-storage/) |
| `ASTROMESH_FORCE_PYTHON` | (unset) | Set to `1` to disable Rust native extensions and use pure-Python fallbacks. Useful for debugging or environments where Rust extensions cannot be compiled |
| `ASTROMESH_SKIP_RUNTIME` | (unset) | `1`/`true`/`yes` skips bootstrapping `AgentRuntime` in the API lifespan (tests) |
| `ASTROMESH_CORS_ORIGINS` | `*` | Comma-separated list of allowed CORS origins for the API |
| `ASTROMESH_NEXUS_URL` | (unset) | Where Nexus lives. Required by the [`send_message`](/astromesh/reference/core/builtin-tools/) builtin tool |
| `ASTROMESH_SSE_POLL_INTERVAL` | `1.0` | Seconds between event-queue polls on the agent-channel SSE stream |
| `ASTROMESH_SSE_KEEPALIVE_EVERY` | `15` | Seconds between SSE keepalive comments |
| `ASTROMESH_SSE_IDLE_EXIT_AFTER` | `30` | Seconds of idle before the SSE stream closes |

## Logging

`astromesh.logging_config.setup_logging()` runs when the API module is imported.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_LOG_LEVEL` | `DEBUG` | Level for the `astromesh` logger tree: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `ASTROMESH_LOG_THIRDPARTY_LEVEL` | `WARNING` | Level cap for noisy libraries (`httpx`, `httpcore`, `openai`, …) |
| `ASTROMESH_LOG_FORMAT` | `%(asctime)s \| %(levelname)-8s \| %(name)s \| %(message)s` | Python `logging` format string |
| `ASTROMESH_LOG_DATEFMT` | `%Y-%m-%dT%H:%M:%S` | `strftime` format for `%(asctime)s` |
| `ASTROMESH_LOG_CONFIGURE` | (unset) | `0`/`false`/`no` skips the setup entirely (custom handlers, tests) |

Uvicorn's own access/error logs are still controlled by `uvicorn --log-level`.

## Provider API Keys

The runtime reads no provider key by a fixed name. Each provider block names the variable that holds its key with `api_key_env`; for `openai_compat` (and `openai`, `azure_openai`) it defaults to `OPENAI_API_KEY`. The LiteLLM provider also reads `api_key_env`, and LiteLLM itself picks up its usual per-vendor variables (`ANTHROPIC_API_KEY`, …). See [Providers](/astromesh/configuration/providers/).

## Memory Backends

Memory connection strings are not read from the environment by name: they go in the agent YAML (for example `memory.conversational.connection.url`, which has no default), where `${VAR}` references are substituted from the environment.

## WhatsApp Channel

Required when using the WhatsApp channel adapter. All four variables must be set for the webhook to function.

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_VERIFY_TOKEN` | (required) | Token used to verify the webhook with Meta during setup. You choose this value and enter it in the Meta developer dashboard |
| `WHATSAPP_ACCESS_TOKEN` | (required) | Meta Graph API access token for sending messages. Obtained from the Meta developer dashboard |
| `WHATSAPP_PHONE_NUMBER_ID` | (required) | Phone number ID associated with your WhatsApp Business account |
| `WHATSAPP_APP_SECRET` | (required) | App secret used to validate incoming webhook request signatures (X-Hub-Signature-256 header) |

## Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTROMESH_OTLP_ENABLED` | (unset) | `1`/`true`/`yes` turns on OTLP export. An explicit `observability.otlp.enabled` in config takes precedence |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector endpoint. Sets only the endpoint — never enables export on its own |

Mesh (Maia) timing is configured in `runtime.yaml`, not through environment variables; see [Maia internals](/astromesh/advanced/maia-internals/).

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
