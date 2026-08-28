---
title: Ecosystem Components & Dependencies
description: Component registry, monorepo dependency graph, and main-vs-develop status for the Astromesh ecosystem
---

This page tracks the **components that make up the Astromesh ecosystem**, how they relate to each other, and the **dependency graph between the packages in the monorepo**. It is kept in sync with [`docs/ECOSYSTEM_DEPENDENCIES.md`](https://github.com/monaccode/astromesh/blob/develop/docs/ECOSYSTEM_DEPENDENCIES.md) in the repository.

:::tip
For the high-level introduction to the ecosystem, see [The Astromesh Ecosystem](/astromesh/getting-started/ecosystem/). This page focuses on the package-level dependency graph and release state.
:::

## 1. Component registry

### 1.1 Packages inside this monorepo

These directories ship from this repository on their own tags and versions.

| Component | Package | Directory | `main` version | `develop` version | Version source | Min Python / Runtime |
|-----------|---------|-----------|----------------|-------------------|----------------|----------------------|
| **Core Runtime** | `astromesh` | `astromesh/` | `0.45.0` | `0.45.0` | `astromesh/__init__.py` | Python 3.12 |
| **Glyph** | `astromesh-glyph` | `astromesh-glyph/` | `0.1.2` | `0.1.2` | `astromesh_glyph/__init__.py` | Python 3.12 |
| **ADK** | `astromesh-adk` | `astromesh-adk/` | `0.3.0` | `0.3.0` | `astromesh_adk/__init__.py` | Python 3.12 |
| **CLI** | `astromesh-cli` | `astromesh-cli/` | `0.3.0` | `0.3.0` | `astromesh_cli/__init__.py` | Python 3.12 |
| **Node** | `astromesh-node` | `astromesh-node/` | `0.1.2` | `0.1.2` | `src/astromesh_node/__init__.py` | Python 3.12 |
| **Orbit** | `astromesh-orbit` | `astromesh-orbit/` | `0.4.1` | `0.4.1` | `astromesh_orbit/__init__.py` | Python 3.12 |
| **Forge** | `astromesh-forge` | `astromesh-forge/` | `0.24.0` | `0.24.0` | `package.json` | Node 22.12 |
| **Docs site** | `docs-site` | `docs-site/` | `0.1.0` | `0.1.0` | `package.json` | Node (site build) |
| **VS Code extension** | `vscode-extension` | `vscode-extension/` | `0.1.0` | `0.1.0` | `package.json` | Node (build) |
| **Native extension** | `astromesh-native` | `native/` | `0.1.0` | `0.1.0` | `Cargo.toml` | Rust |

### 1.2 Satellite repositories

These components are part of the Astromesh ecosystem but live in their own repositories. Their versions are recorded in `docs-site/src/data/ecosystem.ts`, which feeds the ecosystem map, release ledger, and status board on the documentation site.

| Component | Repository | Current version | Ecosystem group | Status |
|-----------|------------|-----------------|-----------------|--------|
| **Cortex** | [`astromesh-cortex`](https://github.com/monaccode/astromesh-cortex) | `0.19.0` | Author | Shipped |
| **Leia** | [`astromesh-leia`](https://github.com/monaccode/astromesh-leia) | `0.5.0` | Author | Shipped |
| **Herald** | [`astromesh-herald`](https://github.com/monaccode/astromesh-herald) | `0.1.0` | Reach | Shipped |
| **OS** | [`astromesh-os`](https://github.com/monaccode/astromesh-os) | `0.10.1` | Ship | Shipped |
| **Prisma** | [`astromesh-prisma`](https://github.com/monaccode/astromesh-prisma) | `0.1.0` | Ship | In development |
| **Nexus** | [`astromesh-nexus`](https://github.com/monaccode/astromesh-nexus) | `0.11.0` | Operate | Shipped |
| **Nebula** | [`astromesh-nebula`](https://github.com/monaccode/astromesh-nebula) | `0.1.0` | Models | Preview |

## 2. Dependency graph (monorepo)

The core runtime sits at the center. Every Python package that needs to run agents declares a runtime dependency on `astromesh`. Optional extras on the core pull in `astromesh-glyph` for the `glyph` orchestration pattern.

```mermaid
flowchart TB
    subgraph author["Author"]
        adk["astromesh-adk"]
        forge["astromesh-forge"]
    end

    subgraph runtime["Runtime"]
        core["astromesh"]
        glyph["astromesh-glyph"]
    end

    subgraph ship["Ship"]
        cli["astromesh-cli"]
        node["astromesh-node"]
    end

    subgraph operate["Operate"]
        orbit["astromesh-orbit"]
    end

    adk -->|>=0.30.0| core
    cli -->|>=0.36.0| core
    node -->|>=0.18.0| core
    node -->|>=0.1.0| cli
    core -.optional: extra glyph.->|>=0.1.0| glyph
    orbit -.plugin for.-> cli
```

### 2.1 Detailed dependency matrix

| Consumer package | Declared dependency | Minimum version | Notes |
|------------------|---------------------|-----------------|-------|
| `astromesh-adk` | `astromesh` | `>=0.30.0` | Editable path source in the monorepo (`..`) |
| `astromesh-cli` | `astromesh` | `>=0.36.0` | Editable path source in the monorepo (`..`) |
| `astromesh-node` | `astromesh` | `>=0.18.0` | Editable path source in the monorepo (`..`) |
| `astromesh-node` | `astromesh-cli` | `>=0.1.0` | Editable path source (`../astromesh-cli`) |
| `astromesh` | `astromesh-glyph` | `>=0.1.0` | Optional extra only (`astromesh[glyph]`); editable path source in the monorepo |

### 2.2 Plugin wiring

- `astromesh-cli` exposes the `astromeshctl.plugins` entry point.
- `astromesh-node` registers `node = astromesh_node.cli.plugin:register`.
- `astromesh-orbit` registers `orbit = astromesh_orbit.cli:register`.

This means `astromesh-node` and `astromesh-orbit` extend the same CLI binary (`astromeshctl`) when they are installed alongside `astromesh-cli`.

## 3. How the components relate

### 3.1 Authoring layer

All authoring tools produce the same agent spec that the core runtime understands:

- **ADK** — Python decorators + project CLI. Generates YAML under the hood.
- **Forge** — Browser-based visual builder, served by the node at `/forge`.
- **Cortex** — Desktop IDE (own repo).
- **Leia** — Natural-language operations plugin for Claude Code (own repo).

### 3.2 Execution layer

- **Core Runtime** — Loads YAML agents, routes roles to models, runs orchestration patterns, manages memory/tools/guardrails.
- **Glyph** — Optional action-language pattern inside the runtime. Requires the `glyph` extra or a local editable install.

### 3.3 Reach layer

- **Herald** (own repo) — Communications gateway. Inbound WhatsApp messages invoke agents; agents reach people back through the same outbox. Herald sits in front of Nexus, not the runtime directly.
- The core runtime also has a built-in WhatsApp channel adapter for self-hosted deployments.

### 3.4 Ship layer

- **Node** — Native system service installer/deb/rpm/pkg/Windows service.
- **OS** (own repo) — Immutable Linux appliance image.
- **Orbit** — Terraform-based cloud infrastructure (GCP first).
- **Prisma** (own repo, in development) — Reconciles agent specs into cloud-managed AI primitives instead of running the runtime.

### 3.5 Operate layer

- **CLI** — `astromeshctl`, the terminal interface to a node.
- **Nexus** (own repo) — Multi-tenant control plane: publishes agents, dispatches runs, meters and bills.

### 3.6 Models layer

- **Nebula** (own repo) — Open-model foundry that trains, gates, and publishes the models the runtime routes to.

## 4. `main` vs `develop` status

Last merge from `develop` to `main`: **v0.45.0**.

`main` and `develop` are level. The versions in section 1.1 are the versions on both
branches; when they diverge, the difference is a core release in flight and this line says
so.

### 4.1 What the v0.41.0 → v0.45.0 run carried

Five core releases, all of them runtime behaviour rather than site changes. Each is
described in full in [`CHANGELOG.md`](https://github.com/monaccode/astromesh/blob/main/CHANGELOG.md):

| Version | What landed |
|---------|-------------|
| `0.41.0` | PRAXIS as a declarative catalog integration — three actions, no runtime code. |
| `0.42.0` | The **confirmation gate**: an action declared in `confirm:` does not run until a person writes a literal yes. Plus `praxis_cobranzas`. |
| `0.43.0` | A tool key the runtime does not read stops being ignored in silence — it warns, naming the agent, the tool and the keys. |
| `0.44.0` | **Conversational memory was dead code.** No agent had memory with any backend, and the spans still reported `ok`. Fixed, and an unbuildable backend now degrades with a warning that names it. |
| `0.44.1` / `0.44.2` | `0.44.0` never reached PyPI (version mismatch gate); the model provider's error body now propagates instead of a bare `400 Bad Request`. |
| `0.45.0` | `praxis_inmobiliaria` and `praxis_mecanicos` — the second had been declared by a live template that the runtime was silently skipping. |

### 4.2 Release flow

1. Update `CHANGELOG.md` under `[Unreleased]`.
2. Run `cz bump` on `develop` to bump `astromesh` (it moves `pyproject.toml` and `astromesh/__init__.py` together).
3. Re-lock `uv.lock` in the root, `astromesh-node/` and `astromesh-cli/` — all three record the core version, and CI installs with `uv sync --locked`.
4. Merge `develop` into `main` and push the tag `vX.Y.Z`. Pushing the tag publishes to PyPI.

## 5. Keeping this page current

When a package version changes:

1. Update its version in the package's own `pyproject.toml` / `package.json` / `Cargo.toml` and its `__init__.py`.
2. Update `docs-site/src/data/ecosystem.ts` (the source of truth for the site map and release ledger).
3. Update `docs/ECOSYSTEM_DEPENDENCIES.md` in the repository root.
4. Update this page if the prose description of a component changed.
