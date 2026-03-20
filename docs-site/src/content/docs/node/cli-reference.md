---
title: "CLI Reference"
description: "Complete astromeshctl command reference for Astromesh Node"
---

`astromeshctl` is the command-line interface for managing an Astromesh Node. It communicates with the running `astromeshd` daemon over HTTP (default: `http://localhost:8000`).

## Global Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `localhost` | Daemon host |
| `--port` | `8000` | Daemon port |
| `--json` | false | Output in JSON format (all commands) |
| `--config` | platform default | Path to config directory |
| `--help` | — | Show help |
| `--version` | — | Show version |

## `astromeshctl version`

Print version information.

```bash
astromeshctl version
```

Output:

```
Astromesh Node v0.18.0
Daemon:   /opt/astromesh/bin/astromeshd
CLI:      /opt/astromesh/bin/astromeshctl
Python:   3.12.x
Platform: linux/amd64
```

## `astromeshctl init`

Interactive configuration wizard. Generates `runtime.yaml`, `providers.yaml`, and a default agent.

```bash
sudo astromeshctl init [flags]
```

| Flag | Description |
|------|-------------|
| `--profile <name>` | Pre-select a profile (`full`, `gateway`, `worker`, `inference`, `minimal`, `rag`, `edge`) |
| `--provider <name>` | Pre-select a provider (`ollama`, `openai`, `anthropic`, `groq`, `gemini`, `onnx`) |
| `--model <name>` | Pre-select a model |
| `--non-interactive` | Skip prompts; use provided flags and defaults |
| `--output <dir>` | Write config to a custom directory |

Example:

```bash
sudo astromeshctl init --profile worker --provider openai --model gpt-4o --non-interactive
```

## `astromeshctl status`

Display the current runtime status.

```bash
astromeshctl status [--json]
```

Output:

```
┌──────────────────────────────────────┐
│         Astromesh Status             │
├──────────────┬───────────────────────┤
│ Status       │ ● Running             │
│ Version      │ 0.18.0                │
│ Uptime       │ 4h 12m 33s            │
│ Profile      │ full                  │
│ PID          │ 4521                  │
│ Agents       │ 3 loaded              │
│ Providers    │ 2 healthy, 0 degraded │
│ Memory       │ 156.0 MB              │
└──────────────┴───────────────────────┘
```

JSON output:

```json
{
  "status": "running",
  "version": "0.18.0",
  "uptime_seconds": 15153,
  "profile": "full",
  "pid": 4521,
  "agents_loaded": 3,
  "providers": { "healthy": 2, "degraded": 0 },
  "memory_mb": 156.0
}
```

## `astromeshctl start`

Start the daemon service (delegates to the platform service manager).

```bash
sudo astromeshctl start
```

## `astromeshctl stop`

Stop the daemon service gracefully.

```bash
sudo astromeshctl stop
```

## `astromeshctl restart`

Restart the daemon service.

```bash
sudo astromeshctl restart
```

## `astromeshctl reload`

Reload configuration without restarting (sends SIGHUP on Linux/macOS).

```bash
sudo astromeshctl reload
```

## `astromeshctl doctor`

Run a full health diagnostics check.

```bash
astromeshctl doctor [--json]
```

Output:

```
Astromesh Doctor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OK  Daemon          Running (PID 4521)
OK  API Server      Responding on :8000
OK  Provider: ollama   Connected (llama3.1:8b available)
OK  Provider: openai   Connected (gpt-4o available)
OK  Memory: sqlite     /var/lib/astromesh/memory/conversations.db
OK  Config             All files valid

Result: Healthy
```

## `astromeshctl logs`

Tail the daemon logs.

```bash
astromeshctl logs [flags]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--follow` / `-f` | false | Follow log output |
| `--lines` / `-n` | 50 | Number of lines to show |
| `--level` | all | Filter by log level (`debug`, `info`, `warning`, `error`) |

Example:

```bash
astromeshctl logs -f -n 100
astromeshctl logs --level error
```

## `astromeshctl agents`

Manage agents loaded by the daemon.

### `astromeshctl agents list`

```bash
astromeshctl agents list [--json]
```

Output:

```
┌──────────────┬──────────────────────────┬──────────────────┬─────────┐
│ Name         │ Description              │ Model            │ Pattern │
├──────────────┼──────────────────────────┼──────────────────┼─────────┤
│ default      │ Default assistant        │ ollama/llama3.1:8b │ react │
│ researcher   │ Research assistant       │ openai/gpt-4o    │ react   │
│ summarizer   │ Document summarizer      │ openai/gpt-4o    │ pipeline│
└──────────────┴──────────────────────────┴──────────────────┴─────────┘
```

### `astromeshctl agents info <name>`

```bash
astromeshctl agents info default [--json]
```

### `astromeshctl agents reload`

Reload all agent definitions from disk (equivalent to `astromeshctl reload`):

```bash
sudo astromeshctl agents reload
```

## `astromeshctl providers`

### `astromeshctl providers list`

```bash
astromeshctl providers list [--json]
```

Output:

```
┌─────────┬────────┬─────────────────────────┬──────────┐
│ Name    │ Type   │ Endpoint                │ Status   │
├─────────┼────────┼─────────────────────────┼──────────┤
│ ollama  │ ollama │ http://localhost:11434  │ ● Healthy│
│ openai  │ openai │ https://api.openai.com  │ ● Healthy│
└─────────┴────────┴─────────────────────────┴──────────┘
```

### `astromeshctl providers health`

Run health checks on all configured providers:

```bash
astromeshctl providers health [--json]
```

## `astromeshctl config`

### `astromeshctl config validate`

Validate configuration files without starting the daemon:

```bash
astromeshctl config validate [--config <dir>]
```

Output:

```
Validating /etc/astromesh/runtime.yaml ... OK
Validating /etc/astromesh/providers.yaml ... OK
Validating /etc/astromesh/agents/default.agent.yaml ... OK

All configuration files are valid.
```

### `astromeshctl config show`

Print the merged active configuration:

```bash
astromeshctl config show [--json]
```

### `astromeshctl config edit`

Open the config directory in the system editor:

```bash
sudo astromeshctl config edit
```

## `astromeshctl memory`

### `astromeshctl memory stats`

Display memory backend usage:

```bash
astromeshctl memory stats [--json]
```

### `astromeshctl memory clear <agent>`

Clear conversational memory for a specific agent:

```bash
astromeshctl memory clear default
astromeshctl memory clear --all    # Clear for all agents
```

## `astromeshctl tools`

### `astromeshctl tools list`

List all registered tools:

```bash
astromeshctl tools list [--json]
```

## JSON Output

All commands support `--json` for scripting and automation:

```bash
astromeshctl status --json | jq '.agents_loaded'
astromeshctl providers list --json | jq '.[] | select(.status == "healthy") | .name'
```
