# Astromesh for VS Code

The official VS Code extension for [Astromesh](https://github.com/monaccode/astromesh) — AI Agent Runtime Platform.

## Features

### YAML IntelliSense
Auto-completion and validation for `*.agent.yaml` and `*.workflow.yaml` files. Requires the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml).

### Run Agent
Click the play button on any `.agent.yaml` file to execute the agent. Results appear in the output panel.

### Workflow Visualizer
Open a `.workflow.yaml` file and click the play button to see a visual DAG of your workflow steps.

### Traces Panel
Expandable span tree in the sidebar showing recent execution traces with auto-refresh.

### Metrics Dashboard
Webview panel displaying counters and histograms from the Astromesh runtime.

### Copilot Chat
Interactive chat panel powered by `astromesh ask` — get help building and debugging agents.

### Diagnostics
Run `Astromesh: Diagnostics` to check daemon status, providers, and connections.

## Requirements

- [Astromesh](https://github.com/monaccode/astromesh) installed and running
- `astromeshctl` available in PATH (or configure `astromesh.cliPath`)
- [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for IntelliSense

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `astromesh.cliPath` | `astromeshctl` | Path to CLI binary |
| `astromesh.daemonUrl` | `http://localhost:8000` | Daemon URL |
| `astromesh.traces.autoRefresh` | `true` | Auto-refresh traces |
| `astromesh.traces.refreshInterval` | `10` | Refresh interval (seconds) |
