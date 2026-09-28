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
| `astromeshd --port PORT` | Override the API server port (default: `runtime.yaml`, else `8000`) |
| `astromeshd --host HOST` | Override the bind address (default: `runtime.yaml`, else `0.0.0.0`) |
| `astromeshd --log-level LEVEL` | Set logging level: `debug`, `info`, `warning`, `error` (default: `info`) |
| `astromeshd --pid-file PATH` | Custom PID file location (default: `astromeshd.pid` in the platform data dir, `/var/lib/astromesh/` on Linux) |
| `astromeshd --foreground` | Run in foreground mode, without init-system integration |

### Examples

```bash
# Development: debug logging, default config
astromeshd --log-level debug

# Production: explicit config, custom port
astromeshd --config /etc/astromesh --port 9000

# Foreground, no init-system integration
astromeshd --foreground
```

For detailed daemon documentation, see [Daemon (astromeshd)](/astromesh/reference/os/daemon/).

## astromeshctl

The CLI client. Communicates with a running daemon via the REST API.

### Connecting to the daemon

There are no global flags besides `--help` (and shell completion). The daemon address comes from the `ASTROMESH_DAEMON_URL` environment variable (default `http://localhost:8000`). JSON output is a per-command `--json` flag.

`init`, `validate`, `config` and `centinela` are not part of `astromesh-cli` itself: they are registered by the `astromesh-node` plugin (`astromeshctl.plugins` entry point), and `orbit` by `astromesh-orbit`. Install those packages to get them. `astromeshctl version` prints the CLI and core versions.

### Status & Health

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl status` | `--json` | Show daemon version, uptime, mode, PID, and agent count |
| `astromeshctl doctor` | `--json` | Run health checks on runtime, providers, and backends |
| `astromeshctl version` | -- | Show the `astromesh-cli` and `astromesh` core versions |

### Agent Management

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl agents list` | `--json` | List all loaded agents with model, orchestration pattern, and status |

### Provider Management

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl providers list` | `--json` | List configured providers with health status, latency, and circuit breaker state |

### Configuration & Validation

Provided by the `astromesh-node` plugin.

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl config validate` | `--path PATH` | Validate runtime.yaml and agent YAML files without starting the daemon |
| `astromeshctl init` | `--role`, `--dev`, `--non-interactive` | Interactive configuration wizard to generate runtime.yaml and agent templates |
| `astromeshctl validate` | `--path PATH` | Validate all project YAML configs (checks syntax, required fields, kind matching) |

**`init` flags:**

| Flag | Description |
|------|-------------|
| `--role` | Node role: `full`, `gateway`, `worker`, `inference` |
| `--dev` | Force dev mode (writes to local `./config/`) |
| `--non-interactive` | Accept all defaults without prompting (for CI/scripts) |

**`validate` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `./config` | Path to config directory to validate |

### Scaffolding

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl new agent <name>` | `--provider`, `--model`, `--orchestration`, `--tools`, `--output-dir`, `--force` | Generate a new agent YAML configuration |
| `astromeshctl new workflow <name>` | `--output-dir`, `--force` | Generate a new workflow YAML configuration |
| `astromeshctl new tool <name>` | `--description`, `--output-dir`, `--force` | Scaffold a new custom tool Python file |

**`new agent` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--provider` | `ollama` | LLM provider |
| `--model` | `llama3.1:8b` | Model name |
| `--orchestration` | `react` | Orchestration pattern |
| `--tools` | -- | Tools to include (repeatable) |
| `--output-dir` | `./config/agents` | Output directory |
| `--force` | `false` | Overwrite existing file |

**`new workflow` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `./config/workflows` | Output directory |
| `--force` | `false` | Overwrite existing file |

**`new tool` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--description` | `A custom tool` | Tool description |
| `--output-dir` | `.` | Output directory |
| `--force` | `false` | Overwrite existing file |

### Execution

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl run <agent> "query"` | `--session`, `--json`, `--timeout`, `--workflow`, `--input` | Execute an agent with a query |
| `astromeshctl dev` | `--host`, `--port`, `--config`, `--no-open` | Start the dev server with hot-reload |

**`run` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--session` | auto-generated UUID | Session ID for multi-turn conversations |
| `--json` | `false` | Output raw JSON response |
| `--timeout` | `60.0` | Request timeout in seconds |
| `--workflow` | `false` | Run as workflow instead of agent |
| `--input` | -- | Workflow input data as JSON string |

**`dev` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Bind host |
| `--port` | `8000` | Bind port |
| `--config` | `./config` | Config directory |
| `--no-open` | `false` | Skip opening browser |

### Observability

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl traces list <agent>` | `--last`, `--json` | List recent traces for an agent |
| `astromeshctl trace <trace_id>` | `--json` | Show detailed trace with span tree |
| `astromeshctl metrics` | `--agent`, `--json` | Show aggregated runtime metrics |
| `astromeshctl cost` | `--json` | Show cost summary |

**`traces list` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--last` | `10` | Number of recent traces to show |
| `--json` | `false` | Output raw JSON |

### Tools

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl tools list` | `--json` | List all available built-in tools |
| `astromeshctl tools test <name> '<args>'` | `--json` | Test a tool in isolation with JSON arguments |

### Copilot

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl ask "question"` | `--context`, `--dry-run`, `--session`, `--json` | Ask the built-in Astromesh Copilot |

**`ask` flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--context` | -- | Path to a context file (must be under `config/` or `docs/`, max 100KB) |
| `--dry-run` | `false` | Run in dry-run mode (no side effects) |
| `--session` | auto-generated UUID | Session ID for multi-turn conversation |
| `--json` | `false` | Output raw JSON |

### Service Management

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl services` | `--json` | List services enabled on this node and their status |

### Mesh (Cluster) Commands

These commands require mesh mode to be enabled.

| Command | Flags | Description |
|---------|-------|-------------|
| `astromeshctl peers list` | `--json` | List known peer nodes with address, status, and last seen time |
| `astromeshctl mesh status` | `--json` | Show cluster overview: node count, leader, alive/suspect/dead breakdown |
| `astromeshctl mesh nodes` | `--json` | Detailed node table with agent assignments, active requests, CPU, and memory |
| `astromeshctl mesh leave` | -- | Gracefully leave the cluster (notify peers) |

### Usage Examples

```bash
# Check if the daemon is running
astromeshctl status

# Run health checks
astromeshctl doctor

# Scaffold a new agent
astromeshctl new agent my-bot --provider openai --model gpt-4o

# Scaffold a workflow and a custom tool
astromeshctl new workflow data-pipeline
astromeshctl new tool web_scraper --description "Scrape web pages"

# Start the dev server with hot-reload
astromeshctl dev

# Run an agent from the CLI
astromeshctl run support-agent "What are your business hours?"

# Run an agent and get JSON output
astromeshctl run support-agent "Hello" --json

# Validate all config files
astromeshctl validate

# View recent traces for an agent
astromeshctl traces list support-agent --last 5

# Inspect a specific trace
astromeshctl trace abc-123-def-456

# View metrics and cost
astromeshctl metrics --agent support-agent
astromeshctl cost

# List and test tools
astromeshctl tools list
astromeshctl tools test get_current_time '{}'

# Ask the copilot for help
astromeshctl ask "What pattern should I use for a research agent?"
astromeshctl ask "Is this config valid?" --context config/agents/my-bot.agent.yaml

# List agents in JSON format
astromeshctl agents list --json

# Validate config before deploying
astromeshctl config validate --path /etc/astromesh

# Connect to a remote daemon
ASTROMESH_DAEMON_URL=http://10.0.1.10:8000 astromeshctl status

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
| `0` | Success — and also when the daemon is unreachable for the read-only commands (`status`, `doctor`, `agents list`, `providers list`, `services`, `peers list`, `mesh …`) and when `new` refuses to overwrite a file: they print the error and exit `0` |
| `1` | Error in `run`, `traces list`, `trace`, `metrics`, `cost`, `tools`, `ask` |
| `2` | Invalid arguments (Typer usage error); also `centinela` failures |

`validate` and `config validate` print the errors they find but exit `0`: don't rely on their exit code as a CI gate.
