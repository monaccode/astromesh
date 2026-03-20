# Astromesh Ecosystem Documentation — Design Spec

**Date:** 2026-03-20
**Status:** Draft
**Author:** Claude + User

## Overview

Create a central "Ecosystem" page in the docs-site that explains how the 5 Astromesh components (Core, ADK, Node, Orbit, Cloud) relate to each other. Also update the README with a missing Node section and an ecosystem summary table.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Audience | Both new users and technical users | Page starts high-level, then goes deep |
| Location | `getting-started/ecosystem.md` | Natural onboarding flow after "What is Astromesh?", `.md` consistent with section |
| Approach | Narrative page with diagrams and tables | No new Astro components needed, matches existing style |
| README | Add ecosystem table + Node section | Fill the gap, follow existing pattern |

## 1. New Page: `docs-site/src/content/docs/getting-started/ecosystem.md`

**Frontmatter:**
```yaml
---
title: "The Astromesh Ecosystem"
description: "How the core runtime, ADK, Node, Cloud, and Orbit work together"
---
```

**Sidebar position:** After "What is Astromesh?", before "Installation".

### Page structure

1. **The Big Picture** (2 paragraphs)
   - Astromesh is an ecosystem of 5 components
   - Core runtime is the foundation; 4 satellite projects extend it for specific use cases

2. **Components at a Glance** (table)

   | Component | What it does | Package | Version |
   |-----------|-------------|---------|---------|
   | Core Runtime | Multi-model agent engine with 6 orchestration patterns, memory, tools, guardrails | `astromesh` | 0.18.0 |
   | ADK | Python-first agent SDK with decorators, CLI, and hot reload | `astromesh-adk` | 0.1.5 |
   | Node | Cross-platform system installer and daemon (Linux, macOS, Windows) | `astromesh-node` | 0.1.0 |
   | Orbit | Cloud-native IaC deployment — generates Terraform for GCP (AWS/Azure planned) | `astromesh-orbit` | 0.1.0 |
   | Cloud | Managed multi-tenant platform with REST API and Studio UI | `astromesh-cloud` | 0.1.0 |

3. **How They Relate** (ASCII architecture diagram)

   Shows: ADK builds agents → Core Runtime runs them → Node installs as service / Orbit provisions infra / Cloud hosts managed

   ```
                       ┌─────────────┐
                       │  Astromesh   │
                       │   Cloud ☁️   │
                       │  (managed)   │
                       └──────┬──────┘
                              │ hosts
           ┌──────────────────┼──────────────────┐
           │                  │                  │
      ┌────┴─────┐    ┌──────┴──────┐    ┌─────┴──────┐
      │ Astromesh │    │  Astromesh  │    │  Astromesh  │
      │   ADK 🐍  │───▶│ Core Runtime│◀───│  Orbit 🚀  │
      │  (build)  │    │  (engine)   │    │  (deploy)   │
      └──────────┘    └──────┬──────┘    └────────────┘
                             │ runs on
                      ┌──────┴──────┐
                      │  Astromesh  │
                      │   Node 🖥️   │
                      │ (install)   │
                      └─────────────┘
   ```

4. **When to Use What** (decision table)

   | I want to... | Use... |
   |-------------|--------|
   | Define agents with YAML and run the runtime | **Astromesh Core** |
   | Define agents with Python decorators | **Astromesh ADK** |
   | Install as a system service (Linux/macOS/Windows) | **Astromesh Node** |
   | Deploy in containers/Kubernetes | **Docker / Helm** (part of core) |
   | Provision cloud infrastructure with Terraform | **Astromesh Orbit** |
   | Managed multi-tenant platform with Studio UI | **Astromesh Cloud** |

5. **Deployment Layers** (layered view)

   ```
   ┌─────────────────────────────────────────────────┐
   │ Layer 4: Managed Platform    → Astromesh Cloud   │
   ├─────────────────────────────────────────────────┤
   │ Layer 3: Infrastructure      → Orbit (Terraform) │
   │          System Service      → Node (deb/rpm/...)│
   │          Containers          → Docker / Helm     │
   ├─────────────────────────────────────────────────┤
   │ Layer 2: Agent Runtime       → Core (uvicorn)    │
   ├─────────────────────────────────────────────────┤
   │ Layer 1: Agent Definition    → YAML or ADK Python│
   └─────────────────────────────────────────────────┘
   ```

6. **Next Steps** — Links to each subproject's introduction page

## 2. Sidebar Update

In `docs-site/astro.config.mjs`, add the ecosystem page to the Getting Started section:

```javascript
{ label: 'What is Astromesh?', slug: 'getting-started/what-is-astromesh' },
{ label: 'The Ecosystem', slug: 'getting-started/ecosystem' },
{ label: 'Installation', slug: 'getting-started/installation' },
```

## 3. README.md Updates

### 3a. Ecosystem summary table

Add immediately before the `## Astromesh ADK` heading in `README.md`:

```markdown
## Ecosystem

| Component | Description | Package | Status |
|-----------|-------------|---------|--------|
| **Core Runtime** | Multi-model agent engine with 6 orchestration patterns | `astromesh` | v0.18.0 |
| **ADK** | Python-first agent SDK with decorators and CLI | `astromesh-adk` | v0.1.5 |
| **Node** | Cross-platform system installer and daemon | `astromesh-node` | v0.1.0 |
| **Orbit** | Cloud-native IaC deployment with Terraform | `astromesh-orbit` | v0.1.0 |
| **Cloud** | Managed multi-tenant platform with Studio UI | `astromesh-cloud` | v0.1.0 |
```

### 3b. Astromesh Node section

Add a dedicated section immediately after the `## Astromesh ADK` section (before `## Astromesh Cloud`), following the same pattern:

```markdown
## Astromesh Node

Cross-platform system installer and daemon — deploy Astromesh as a native service.

**Supported platforms:** Linux (Debian/Ubuntu, RHEL/Fedora), macOS, Windows

\```bash
# Debian/Ubuntu
sudo dpkg -i astromesh-node-0.1.0-amd64.deb
sudo astromeshctl init --profile full
sudo systemctl start astromeshd
\```

**Key features:** System service integration (systemd/launchd/Windows Service), CLI management (astromeshctl), 7 deployment profiles, cross-platform packaging
```

## 4. "What is Astromesh?" Page Update

Add a paragraph at the end of `docs-site/src/content/docs/getting-started/what-is-astromesh.md` linking to the ecosystem page:

```markdown
## The Broader Ecosystem

The core runtime is one part of a larger ecosystem. Astromesh includes a Python SDK (ADK), a system installer (Node), cloud provisioning (Orbit), and a managed platform (Cloud). See [The Ecosystem](/astromesh/getting-started/ecosystem/) for how they all fit together.
```

## Non-Goals

- No new Astro components (use markdown/mdx tables and code blocks)
- No changes to the existing ADK/Cloud/Orbit/Node documentation pages
- No interactive features (just static documentation)

## Notes

- Version numbers in the ecosystem table will go stale. Update them on each release or consider a build-time injection in the future.
- ASCII diagrams use emoji for decoration. Plain-text alternatives are acceptable if rendering is an issue in some environments.
