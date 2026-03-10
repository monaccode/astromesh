---
title: Developer Tools
description: CLI, Copilot, VS Code extension, and dashboard — everything you need to build agents.
---

Astromesh gives you a complete toolkit for building, running, and monitoring AI agents. This guide walks through the developer workflow from start to finish.

## The Workflow

```
Define → Run → Debug → Optimize → Deploy
  │        │       │         │         │
  YAML   CLI    Traces    Metrics   Docker/K8s
  │        │       │         │
  VS Code IntelliSense  Dashboard
```

## Step 1: Scaffold

Create a new agent in seconds:

```bash
astromeshctl new agent customer-support
```

This generates a ready-to-run YAML file in `config/agents/`. Open it in VS Code for IntelliSense — auto-completion and validation for every field.

## Step 2: Run

```bash
astromeshctl run customer-support "How do I reset my password?"
```

Or click the play button directly in VS Code on your `.agent.yaml` file.

## Step 3: Debug

See exactly what happened inside:

```bash
astromeshctl traces customer-support --last 5
```

Each trace shows the full execution tree — guardrails, memory, LLM calls, tool usage, and timings. In VS Code, the Traces panel shows this as an expandable tree in the sidebar.

## Step 4: Optimize

Check token usage and costs:

```bash
astromeshctl metrics customer-support
astromeshctl cost --window 24h
```

The Metrics Dashboard (in VS Code or at `/v1/dashboard/`) shows counters and histograms in real-time.

## Step 5: Ask the Copilot

Stuck on something? The built-in copilot knows your project:

```bash
astromeshctl ask "Why is my agent using so many tokens?"
```

Or use the Copilot Chat panel in VS Code for an interactive session.

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

## Tool Summary

| Tool | What it does |
|------|--------------|
| `astromeshctl` | CLI for everything — scaffold, run, debug, monitor |
| Copilot | AI assistant that knows Astromesh |
| VS Code Extension | IntelliSense, traces, metrics, workflow viz, copilot chat |
| Dashboard | Web UI at `/v1/dashboard/` |

:::tip[Future: Cluster Orchestration]
The VS Code extension is designed to connect to remote Astromesh clusters. In upcoming releases, you'll be able to deploy, monitor, and orchestrate agents across your production environment — all from your editor.
:::
