---
title: CLI (astromeshctl)
description: Command-line interface reference
---

`astromeshctl` is the command-line interface for inspecting and managing a running Astromesh daemon. It communicates with `astromeshd` via the REST API.

## Global Flags

These flags apply to all commands:

| Flag | Default | Description |
|------|---------|-------------|
| `--host URL` | `http://localhost:8000` | Address of the Astromesh daemon |
| `--json` | `false` | Output in machine-readable JSON instead of human-friendly tables |
| `--help` | -- | Show help for any command |

## Commands

### `astromeshctl status`

Show daemon status including version, uptime, mode, and agent count.

```
$ astromeshctl status
Astromesh v0.10.0
Status:    running
Mode:      standalone
PID:       48291
Uptime:    2h 14m 32s
Agents:    3 loaded
Providers: 2 healthy, 0 degraded
```

### `astromeshctl doctor`

Run health checks against the runtime, providers, and backends. Reports issues with actionable suggestions.

```
$ astromeshctl doctor
✓ Runtime         healthy
✓ OpenAI          healthy (avg latency: 420ms)
✓ Anthropic       healthy (avg latency: 380ms)
✓ Redis           healthy
✗ ChromaDB        unreachable (connection refused on localhost:8000)
  → Check that ChromaDB is running: docker start chroma

3 healthy, 0 degraded, 1 failing
```

### `astromeshctl agents list`

List all loaded agents with their status and configuration.

```
$ astromeshctl agents list
NAME          MODEL              ORCHESTRATION     STATUS
assistant     openai/gpt-4o      react             ready
researcher    anthropic/claude   plan_and_execute   ready
support       ollama/llama3      react             ready
```

### `astromeshctl providers list`

List all configured LLM providers and their health status.

```
$ astromeshctl providers list
PROVIDER    MODEL          STATUS    LATENCY   CIRCUIT
openai      gpt-4o         healthy   420ms     closed
anthropic   claude-sonnet  healthy   380ms     closed
ollama      llama3         healthy   120ms     closed
```

### `astromeshctl config validate`

Validate configuration files without starting the daemon. Checks `runtime.yaml` and all agent YAML files for schema errors.

```
$ astromeshctl config validate
Validating /etc/astromesh/runtime.yaml ... ok
Validating agents/assistant.agent.yaml ... ok
Validating agents/researcher.agent.yaml ... ok
Validating agents/support.agent.yaml ... ok

All configuration files are valid.
```

```
$ astromeshctl config validate
Validating /etc/astromesh/runtime.yaml ... ok
Validating agents/broken.agent.yaml ... FAILED
  → spec.model.primary.provider: required field missing
  → spec.orchestration.pattern: unknown pattern "invalid"

1 error(s) found.
```

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to configuration directory (uses same auto-detection as `astromeshd` if omitted) |

### `astromeshctl services`

List services enabled on this node.

```
$ astromeshctl services
SERVICE        STATUS
api            running
memory         running
tools          running
rag            running
mesh           disabled
```

### `astromeshctl peers list`

List known peer nodes (mesh mode only).

```
$ astromeshctl peers list
NODE            ADDRESS              STATUS    LAST SEEN
node-alpha      10.0.1.10:8000       alive     2s ago
node-beta       10.0.1.11:8000       alive     1s ago
node-gamma      10.0.1.12:8000       suspect   18s ago
```

### `astromeshctl mesh status`

Show cluster overview (mesh mode only).

```
$ astromeshctl mesh status
Cluster:     astromesh-prod
Nodes:       3 total (2 alive, 1 suspect, 0 dead)
Leader:      node-alpha
This node:   node-beta
Gossip:      converged
```

### `astromeshctl mesh nodes`

Show detailed node table with agent assignments and load (mesh mode only).

```
$ astromeshctl mesh nodes
NODE            ROLE      AGENTS              ACTIVE REQS   CPU    MEM
node-alpha      leader    assistant,support    12            34%    1.2G
node-beta       worker    researcher           5             22%    0.8G
node-gamma      worker    assistant            0             8%     0.6G
```

### `astromeshctl mesh leave`

Gracefully leave the cluster. Drains active requests and notifies peers before departing.

```
$ astromeshctl mesh leave
Draining 3 active requests...
Notifying peers...
Left cluster successfully.
```

| Flag | Description |
|------|-------------|
| `--force` | Leave immediately without draining requests |

### `astromeshctl init`

Interactive configuration wizard that generates `runtime.yaml` and agent templates.

```
$ astromeshctl init
Welcome to Astromesh setup!

? Select providers to configure:
  [x] OpenAI
  [ ] Anthropic
  [x] Ollama (local)

? Default orchestration pattern: react
? Enable mesh mode? No

Configuration written to ./config/
  → runtime.yaml
  → agents/assistant.agent.yaml

Run 'astromeshd' to start.
```

| Flag | Description |
|------|-------------|
| `--dev` | Generate development-friendly defaults (in-memory backends, debug logging, Ollama provider) |
| `--non-interactive` | Use all defaults without prompting. Suitable for CI/scripts |
| `--output PATH` | Directory to write config files. Default: `./config/` |
