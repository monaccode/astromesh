---
title: Developer Tools
description: CLI, Copilot, VS Code extension, and dashboard — everything you need to build agents.
---

Astromesh gives you a complete toolkit for building, running, and monitoring AI agents. Three tools, one workflow — from YAML to production.

## The Workflow

```
Define → Run → Debug → Optimize → Deploy
  │        │       │         │         │
  YAML   CLI    Traces    Metrics   Docker/K8s
  │        │       │         │
  VS Code IntelliSense  Dashboard
```

---

## astromeshctl — The CLI

Your command center. 16 commands that cover the full agent lifecycle.

### Step 1: Scaffold

```bash
astromeshctl new agent customer-support
```

Generates a ready-to-run YAML file in `config/agents/`. Open it in VS Code for instant IntelliSense.

### Step 2: Run

```bash
astromeshctl run customer-support "How do I reset my password?"
```

Executes the agent against your local runtime. Output streams to the terminal.

### Step 3: Debug

```bash
astromeshctl traces customer-support --last 5
```

Full execution trees — guardrails, memory lookups, LLM calls, tool usage, and timings. Every step visible.

### Step 4: Monitor

```bash
astromeshctl metrics customer-support
astromeshctl cost --window 24h
```

Token usage, latency histograms, and cost tracking. Catch expensive patterns before they hit production.

### Step 5: Diagnose

```bash
astromeshctl doctor
```

Checks runtime, providers, memory backends, and connectivity. One command to know if everything is healthy.

> Full reference: [CLI Commands](/astromesh/reference/cli-commands/)

---

## Copilot — AI That Knows Your Project

An AI assistant embedded in both CLI and VS Code. It reads your agent configs, understands your runtime, and answers questions in context.

```bash
astromeshctl ask "Why is my agent using so many tokens?"
```

```bash
astromeshctl ask "Add a RAG pipeline to my support agent"
```

```bash
astromeshctl ask "Explain the last trace for sales-qualifier"
```

The Copilot doesn't just answer generic questions — it inspects your actual YAML files, runtime state, and trace history to give specific answers.

In VS Code, open the **Copilot Chat** panel for an interactive session with the same capabilities.

---

## VS Code Extension — Your Editor as Mission Control

Seven features that turn VS Code into a full agent development environment.

| Feature | What it does |
|---------|-------------|
| **YAML IntelliSense** | Auto-complete and validation for `.agent.yaml` and `.workflow.yaml` |
| **▶ Play Button** | Run agents directly from the editor title bar |
| **Traces Panel** | Expandable span trees in the sidebar, auto-refreshing |
| **Metrics Dashboard** | Real-time counters and histograms in a webview |
| **Workflow Visualizer** | DAG visualization of workflow steps |
| **Copilot Chat** | AI assistant panel with full project context |
| **Diagnostics** | `astromesh doctor` results in the output channel |

### Install

Search **"Astromesh"** in the VS Code marketplace, or:

```bash
code --install-extension monaccode.astromesh
```

> Full reference: [VS Code Extension](/astromesh/reference/os/vscode-extension/)

---

## Multi-Agent Workflows

When one agent isn't enough, compose them:

```yaml
tools:
  - name: qualify-lead
    type: agent
    agent: sales-qualifier
```

Or define a full pipeline in Workflow YAML:

```bash
astromeshctl new workflow lead-pipeline
astromeshctl run lead-pipeline --workflow --input '{"company": "Acme"}'
```

Visualize the DAG in VS Code with the Workflow Visualizer.

---

## Quick Reference

| Tool | What it does | Where |
|------|-------------|-------|
| `astromeshctl` | Scaffold, run, debug, monitor, deploy | Terminal |
| Copilot | AI assistant that knows your project | Terminal + VS Code |
| VS Code Extension | IntelliSense, traces, metrics, workflow viz, copilot | VS Code |
| Dashboard | Web UI for metrics and traces | `/v1/dashboard/` |

:::tip[Future: Cluster Orchestration]
The VS Code extension is designed to connect to remote Astromesh clusters. In upcoming releases, you'll deploy, monitor, and orchestrate agents across production environments — all from your editor.
:::
