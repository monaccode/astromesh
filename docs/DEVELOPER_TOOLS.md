# Developer Tools

Astromesh includes a complete developer toolkit for building, running, and monitoring AI agents.

## CLI (`astromeshctl`)

The CLI is the primary interface for all operations:

| Command | Description |
|---------|-------------|
| `new agent <name>` | Scaffold a new agent YAML |
| `new workflow <name>` | Scaffold a workflow YAML |
| `new tool <name>` | Scaffold a custom tool |
| `run <agent> "query"` | Execute an agent |
| `run <name> --workflow` | Execute a workflow |
| `dev` | Hot-reload development server |
| `traces <agent> --last N` | View recent traces |
| `trace <id>` | Inspect a trace span tree |
| `metrics <agent>` | View agent metrics |
| `cost --window 24h` | Cost summary |
| `tools list` | List available tools |
| `tools test <name> '{}'` | Test a tool in isolation |
| `validate` | Validate all project YAMLs |
| `doctor` | Check system health |
| `ask "question"` | Ask the copilot |

Install: `uv sync --extra cli`

## Copilot

The copilot is an Astromesh agent that helps you build agents. It can:

- Answer configuration questions
- Debug execution traces
- Suggest optimizations
- Generate YAML scaffolding

Usage: `astromeshctl ask "How do I add memory to my agent?"`

## VS Code Extension

Install from the marketplace or from a `.vsix` file.

Features:

- **YAML IntelliSense** — auto-completion for `.agent.yaml` and `.workflow.yaml`
- **Run Agent** — play button on agent files
- **Workflow Visualizer** — DAG view of workflow steps
- **Traces Panel** — sidebar with expandable span trees
- **Metrics Dashboard** — webview with counters and histograms
- **Copilot Chat** — interactive chat panel
- **Diagnostics** — system health check

Settings:
- `astromesh.cliPath` — path to CLI binary (default: `astromeshctl`)
- `astromesh.daemonUrl` — daemon URL (default: `http://localhost:8000`)

## Dashboard

Built-in web UI at `http://localhost:8000/v1/dashboard/` with:

- Counter metrics
- Histogram tables
- Recent traces with status
- Workflow list

Auto-refreshes every 10 seconds.
