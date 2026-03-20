---
title: The Astromesh Ecosystem
description: How the core runtime, ADK, CLI, Node, Forge, and Orbit work together
---

Astromesh is not a single tool — it's an **ecosystem of six components** designed to cover the full lifecycle of AI agents: define, build, run, deploy, and manage. The core runtime is the foundation, and five satellite projects extend it for specific use cases.

You can use just the core runtime with YAML config files, or combine it with the ADK for Python-first development, the CLI for managing nodes and clusters, Node for system-level deployment, Forge for visual agent building, or Orbit for cloud provisioning.

## Components at a Glance

| Component | What it does | Package | Version |
|-----------|-------------|---------|---------|
| **Core Runtime** | Multi-model agent engine with 6 orchestration patterns, memory, tools, and guardrails | `astromesh` | v0.18.0 |
| **ADK** | Python-first agent SDK with decorators, CLI, and hot reload | `astromesh-adk` | v0.1.5 |
| **CLI** | Standalone CLI tool for managing nodes and clusters | `astromesh-cli` | v0.1.0 |
| **Node** | Cross-platform system installer and daemon (Linux, macOS, Windows) | `astromesh-node` | v0.1.0 |
| **Forge** | Visual agent builder — drag-and-drop wizard, canvas, and templates | `astromesh-forge` | v0.1.0 |
| **Orbit** | Cloud-native IaC deployment — generates Terraform for GCP (AWS/Azure planned) | `astromesh-orbit` | v0.1.0 |

## How They Relate

```
     ┌──────────┐                              ┌────────────┐
     │ Astromesh │    ┌──────────────┐    ┌─────┴──────┐
     │    ADK    │───>│  Astromesh   │<───│  Astromesh  │
     │  (build)  │    │ Core Runtime │    │   Orbit     │
     └──────────┘    │  (engine)    │    │  (deploy)   │
                      └──┬───────┬──┘    └────────────┘
     ┌──────────┐        │       │
     │ Astromesh │        │       │
     │   Forge   │────────┘       │ runs on
     │ (visual)  │         ┌──────┴──────┐
     └──────────┘         │  Astromesh  │
                           │    Node     │
                           │ (install)   │
                           └──────┬──────┘
                                  │ managed by
                           ┌──────┴──────┐
                           │  Astromesh  │
                           │    CLI      │
                           │  (manage)   │
                           └─────────────┘
```

- **ADK** builds agents in Python → generates YAML that the **Core Runtime** understands
- **Forge** provides a visual drag-and-drop interface for building agents (wizard + canvas)
- **Core Runtime** is the engine — loads agents, routes to LLM providers, executes orchestration patterns
- **Node** installs the runtime as a native system service (`astromeshd`)
- **CLI** provides the `astromeshctl` management interface for nodes and clusters
- **Orbit** provisions cloud infrastructure (GCP today, AWS/Azure planned) with Terraform

## When to Use What

| I want to... | Use... |
|-------------|--------|
| Define agents with YAML and run the runtime directly | [**Astromesh Core**](/astromesh/getting-started/quickstart/) |
| Define agents with Python decorators and a CLI | [**Astromesh ADK**](/astromesh/adk/introduction/) |
| Manage nodes and clusters from the command line | [**Astromesh CLI**](/astromesh/cli/introduction/) |
| Install as a system service on Linux, macOS, or Windows | [**Astromesh Node**](/astromesh/node/introduction/) |
| Deploy in containers or Kubernetes | [**Docker / Helm**](/astromesh/deployment/docker-single/) (part of core) |
| Provision cloud infrastructure with Terraform | [**Astromesh Orbit**](/astromesh/orbit/introduction/) |
| Build agents visually with drag-and-drop | [**Astromesh Forge**](/astromesh/forge/introduction/) |

## Deployment Layers

The ecosystem forms a layered stack. You choose your entry point at each layer:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 4: Infrastructure       →  Orbit (Terraform)      │
│          System Service       →  Node (deb/rpm/...)     │
│          Containers           →  Docker / Helm          │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Management           →  CLI (astromeshctl)     │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Agent Runtime        →  Astromesh Core         │
├─────────────────────────────────────────────────────────┤
│ Layer 1: Agent Definition     →  YAML, ADK, or Forge   │
└─────────────────────────────────────────────────────────┘
```

**Layer 1** is where you define your agents — YAML files, ADK Python decorators, or Forge's visual builder. All three produce the same agent definitions.

**Layer 2** is the runtime engine that loads agents, connects to LLM providers, manages memory, and executes orchestration patterns (ReAct, PlanAndExecute, etc.).

**Layer 3** is the management layer — `astromeshctl` controls running nodes and clusters.

**Layer 4** is how you deploy the runtime. Pick the one that fits your infrastructure: Node for bare-metal/VM, Docker for containers, Helm for Kubernetes, or Orbit for cloud-managed infrastructure.

## Next Steps

| Component | Start here |
|-----------|-----------|
| Core Runtime | [Quick Start](/astromesh/getting-started/quickstart/) — run your first agent in 5 minutes |
| ADK | [ADK Introduction](/astromesh/adk/introduction/) — Python-first agent development |
| CLI | [CLI Introduction](/astromesh/cli/introduction/) — manage nodes and clusters from the terminal |
| Node | [Node Introduction](/astromesh/node/introduction/) — install as a system service |
| Forge | [Forge Introduction](/astromesh/forge/introduction/) — visual agent builder |
| Orbit | [Orbit Introduction](/astromesh/orbit/introduction/) — provision cloud infrastructure |
