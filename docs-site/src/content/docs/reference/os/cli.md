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

---

## Scaffolding Commands

### `astromeshctl new agent <name>`

Generate a new agent YAML configuration file.

```
$ astromeshctl new agent my-bot --provider openai --model gpt-4o --orchestration plan_and_execute
╭─ astromesh new agent ────────────────────────────╮
│ Created agent: ./config/agents/my-bot.agent.yaml │
│                                                  │
│   Provider: openai                               │
│   Model: gpt-4o                                  │
│   Pattern: plan_and_execute                      │
╰──────────────────────────────────────────────────╯
```

| Flag | Default | Description |
|------|---------|-------------|
| `--provider` | `ollama` | LLM provider |
| `--model` | `llama3.1:8b` | Model name |
| `--orchestration` | `react` | Orchestration pattern |
| `--tools` | -- | Tools to include (repeatable) |
| `--output-dir` | `./config/agents` | Output directory |
| `--force` | `false` | Overwrite existing file |

### `astromeshctl new workflow <name>`

Generate a new workflow YAML configuration file.

```
$ astromeshctl new workflow data-pipeline
╭─ astromesh new workflow ─────────────────────────────────────────╮
│ Created workflow: ./config/workflows/data-pipeline.workflow.yaml │
╰──────────────────────────────────────────────────────────────────╯
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `./config/workflows` | Output directory |
| `--force` | `false` | Overwrite existing file |

### `astromeshctl new tool <name>`

Scaffold a new custom tool as a Python file. The name should be in `snake_case`.

```
$ astromeshctl new tool web_scraper --description "Scrape web pages"
╭─ astromesh new tool ─────────────────────────╮
│ Created tool: ./web_scraper.py               │
│                                              │
│   Class: WebScraperTool                      │
│   Description: Scrape web pages              │
╰──────────────────────────────────────────────╯
```

| Flag | Default | Description |
|------|---------|-------------|
| `--description` | `A custom tool` | Tool description |
| `--output-dir` | `.` | Output directory |
| `--force` | `false` | Overwrite existing file |

---

## Execution Commands

### `astromeshctl run <agent> "query"`

Execute an agent with a query via the local API server.

```
$ astromeshctl run support-agent "What are your business hours?"
╭─ support-agent ──────────────────────────────────────────╮
│ Our business hours are Monday through Friday, 9 AM to    │
│ 5 PM EST. We're closed on weekends and major holidays.   │
╰── trace: abc-123 | tokens: 342 ──────────────────────────╯
```

| Flag | Default | Description |
|------|---------|-------------|
| `--session` | auto-generated UUID | Session ID for multi-turn conversations |
| `--json` | `false` | Output raw JSON response |
| `--timeout` | `60.0` | Request timeout in seconds |
| `--workflow` | `false` | Run as workflow instead of agent (Sub-project 4) |
| `--input` | -- | Workflow input data as JSON string |

### `astromeshctl dev`

Start the Astromesh development server with hot-reload. Watches `astromesh/` and `config/` directories for changes and automatically restarts.

```
$ astromeshctl dev
╭─ astromesh dev ──────────────────────────────╮
│ Astromesh Dev Server                         │
│                                              │
│   Host:   0.0.0.0                            │
│   Port:   8000                               │
│   Config: ./config                           │
│   Reload: enabled                            │
╰──────────────────────────────────────────────╯
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Bind host |
| `--port` | `8000` | Bind port |
| `--config` | `./config` | Config directory |
| `--no-open` | `false` | Skip opening browser |

---

## Observability Commands

### `astromeshctl traces list <agent>`

List recent execution traces for an agent.

```
$ astromeshctl traces list support-agent --last 5
```

| Flag | Default | Description |
|------|---------|-------------|
| `--last` | `10` | Number of recent traces to show |
| `--json` | `false` | Output raw JSON |

### `astromeshctl trace <trace_id>`

Show detailed trace information with a span tree visualization.

```
$ astromeshctl trace abc-123-def-456
```

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | `false` | Output raw JSON |

### `astromeshctl metrics`

Show aggregated runtime metrics for all agents or a specific agent.

```
$ astromeshctl metrics --agent support-agent
```

| Flag | Default | Description |
|------|---------|-------------|
| `--agent` | -- | Filter by agent name |
| `--json` | `false` | Output raw JSON |

### `astromeshctl cost`

Show a cost summary across all agents and providers.

```
$ astromeshctl cost
```

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | `false` | Output raw JSON |

---

## Tool Commands

### `astromeshctl tools list`

List all available built-in tools registered in the runtime.

```
$ astromeshctl tools list
```

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | `false` | Output raw JSON |

### `astromeshctl tools test <name> '<args>'`

Test a tool in isolation by calling it with JSON arguments.

```
$ astromeshctl tools test get_current_time '{}'
Tool:   get_current_time
Status: ok
Result:
{
  "datetime": "2026-03-10T14:23:45Z"
}
```

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | `false` | Output raw JSON |

The second argument is a JSON string with the tool's input arguments. Use `'{}'` for tools that take no arguments.

---

## Validation

### `astromeshctl validate`

Validate all YAML configuration files under the project config directory. Checks for valid YAML syntax, required fields (`apiVersion`, `kind`, `metadata.name`), and correct `kind` values based on file naming conventions.

```
$ astromeshctl validate
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ File                              ┃ Status ┃ Message ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ config/agents/support.agent.yaml  │ valid  │ OK      │
│ config/agents/hello.agent.yaml    │ valid  │ OK      │
│ config/runtime.yaml               │ valid  │ OK      │
└───────────────────────────────────┴────────┴─────────┘

All files valid: 3 file(s) checked
```

| Flag | Default | Description |
|------|---------|-------------|
| `--path` | `./config` | Path to config directory |

---

## Copilot

### `astromeshctl ask "question"`

Ask the Astromesh Copilot a question. The copilot is a built-in agent (`astromesh-copilot`) that can validate configs, explain traces, suggest tools, and help debug provider issues.

```
$ astromeshctl ask "What orchestration pattern should I use for a research agent?"
╭─ Astromesh Copilot ──────────────────────────────────────╮
│ For a research agent, I'd recommend the                  │
│ `plan_and_execute` pattern. It first generates a plan    │
│ of steps, then executes each step sequentially...        │
╰── trace: cop-789 ────────────────────────────────────────╯
```

| Flag | Default | Description |
|------|---------|-------------|
| `--context` | -- | Path to a context file (must be under `config/` or `docs/`, max 100KB) |
| `--dry-run` | `false` | Run in dry-run mode (no side effects) |
| `--session` | auto-generated UUID | Session ID for multi-turn conversation |
| `--json` | `false` | Output raw JSON |

**Example with context file:**

```bash
astromeshctl ask "Is this agent config correct?" --context config/agents/hello.agent.yaml
```

The copilot will read the file and include its contents as context when answering your question.
