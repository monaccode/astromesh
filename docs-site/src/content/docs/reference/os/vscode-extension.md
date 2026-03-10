---
title: VS Code Extension
description: YAML IntelliSense, workflow visualization, traces, metrics, and copilot — all inside VS Code.
---

Astromesh ships a VS Code extension that brings the full developer experience into your editor. The extension wraps `astromeshctl` — no business logic runs in VS Code itself.

## Installation

Install from the VS Code marketplace:

1. Open VS Code
2. Press `Ctrl+Shift+X` (Extensions)
3. Search for "Astromesh"
4. Click Install

Or install from VSIX:

```bash
code --install-extension astromesh-0.1.0.vsix
```

### Prerequisites

- Astromesh daemon running (`astromeshd` or `uv run uvicorn astromesh.api.main:app`)
- `astromeshctl` in PATH
- [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for IntelliSense

## Features

### YAML IntelliSense

The extension provides JSON Schemas for `*.agent.yaml` and `*.workflow.yaml` files. With the YAML extension installed, you get:

- Auto-completion for all fields
- Validation errors on invalid values
- Hover documentation for each property

Works automatically — no configuration needed.

### Run Agent

Open any `.agent.yaml` file and click the play button in the editor title bar. The extension:

1. Extracts the agent name from the YAML
2. Prompts for a query
3. Runs `astromeshctl run <agent> "<query>" --json`
4. Shows the response in the Output panel

You can also run via Command Palette: `Astromesh: Run Agent`.

### Workflow Visualizer

Open a `.workflow.yaml` file and click the play button. A webview panel opens showing your workflow as a visual DAG:

- Agent steps in green
- Tool steps in yellow
- Switch steps in purple
- Error handlers and goto labels shown inline

### Traces Panel

The Astromesh activity bar icon opens the Traces sidebar. It shows recent execution traces as an expandable tree:

- Root level: trace ID, agent name, duration
- Expand to see individual spans with timing
- Auto-refreshes every 10 seconds (configurable)
- Click refresh icon to update manually

### Metrics Dashboard

Run `Astromesh: Metrics Dashboard` to open a webview showing:

- Counter metrics (agent runs, tool calls, tokens)
- Histogram metrics (latency, iterations)
- Auto-refreshes every 10 seconds

### Copilot Chat

Run `Astromesh: Ask Copilot` to open an interactive chat panel. The copilot can help with:

- Agent configuration questions
- Debugging trace issues
- Workflow design
- Tool usage examples

### Diagnostics

Run `Astromesh: Diagnostics` to check system health. Equivalent to `astromeshctl doctor`.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `astromesh.cliPath` | `astromeshctl` | Path to the CLI binary |
| `astromesh.daemonUrl` | `http://localhost:8000` | Astromesh daemon URL |
| `astromesh.traces.autoRefresh` | `true` | Auto-refresh traces panel |
| `astromesh.traces.refreshInterval` | `10` | Refresh interval in seconds |
