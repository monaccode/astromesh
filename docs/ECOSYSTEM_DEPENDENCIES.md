# Astromesh Ecosystem — Components, Relations, and Dependencies

This document tracks the **components that make up the Astromesh ecosystem**, how they relate to each other, and the **dependency graph between the packages in this monorepo**. It is meant to be kept in sync with:

- The high-level [Ecosystem page](https://monaccode.github.io/astromesh/getting-started/ecosystem/) on the documentation site.
- The technical [Ecosystem Components & Dependencies](https://monaccode.github.io/astromesh/architecture/ecosystem-dependencies/) page on the documentation site.

> **Versioning rule:** This is a monorepo of independently versioned packages. A release of the core runtime does **not** bump any other package unless that package itself changed. Each package carries its own changelog and its own tag.

---

## 1. Component registry

### 1.1 Packages inside this monorepo

These directories ship from this repository on their own tags and versions.

| Component | Package | Directory | Version | Version source | Min Python |
|-----------|---------|-----------|---------|----------------|------------|
| **Core Runtime** | `astromesh` | `astromesh/` | `0.50.0` | `astromesh/__init__.py` | 3.12 |
| **Glyph** | `astromesh-glyph` | `astromesh-glyph/` | `0.1.2` | `astromesh_glyph/__init__.py` | 3.12 |
| **ADK** | `astromesh-adk` | `astromesh-adk/` | `0.3.0` | `astromesh_adk/__init__.py` | 3.12 |
| **CLI** | `astromesh-cli` | `astromesh-cli/` | `0.3.0` | `astromesh_cli/__init__.py` | 3.12 |
| **Node** | `astromesh-node` | `astromesh-node/` | `0.1.2` | `src/astromesh_node/__init__.py` | 3.12 |
| **Orbit** | `astromesh-orbit` | `astromesh-orbit/` | `0.4.1` | `astromesh_orbit/__init__.py` | 3.12 |
| **Forge** | `astromesh-forge` | `astromesh-forge/` | `0.24.0` | `package.json` | Node 22.12 |
| **Docs site** | `docs-site` | `docs-site/` | `0.1.0` | `package.json` | Node (site build) |
| **VS Code extension** | `vscode-extension` | `vscode-extension/` | `0.1.0` | `package.json` | Node (build) |
| **Native extension** | `astromesh-native` | `native/` | `0.1.0` | `Cargo.toml` | Rust |

### 1.2 Satellite repositories

These components are part of the Astromesh ecosystem but live in their own repositories. Their versions are recorded in `docs-site/src/data/ecosystem.ts`, which feeds the ecosystem map, release ledger, and status board on the documentation site.

| Component | Repository | Current version | Ecosystem group | Status |
|-----------|------------|-----------------|-----------------|--------|
| **Cortex** | [`astromesh-cortex`](https://github.com/monaccode/astromesh-cortex) | `0.19.0` | Author | Shipped |
| **Leia** | [`astromesh-leia`](https://github.com/monaccode/astromesh-leia) | `0.5.0` | Author | Shipped |
| **Herald** | [`astromesh-herald`](https://github.com/monaccode/astromesh-herald) | `0.7.4` | Reach | Shipped |
| **OS** | [`astromesh-os`](https://github.com/monaccode/astromesh-os) | `0.10.1` | Ship | Shipped |
| **Prisma** | [`astromesh-prisma`](https://github.com/monaccode/astromesh-prisma) | `0.1.0` | Ship | In development |
| **Nexus** | [`astromesh-nexus`](https://github.com/monaccode/astromesh-nexus) | `0.19.0` | Operate | Shipped |
| **Nebula** | [`astromesh-nebula`](https://github.com/monaccode/astromesh-nebula) | `0.1.0` | Models | Preview |

---

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

    adk -->|>=0.40.0| core
    cli -->|>=0.40.0| core
    node -->|>=0.40.0| core
    node -->|>=0.3.0| cli
    core -.optional: extra glyph.->|>=0.1.1| glyph
    orbit -.plugin for.-> cli
```

### 2.1 Detailed dependency matrix

| Consumer package | Declared dependency | Minimum version | Notes |
|------------------|---------------------|-----------------|-------|
| `astromesh-adk` | `astromesh` | `>=0.40.0` | Editable path source in the monorepo (`..`) |
| `astromesh-cli` | `astromesh` | `>=0.40.0` | Editable path source in the monorepo (`..`) |
| `astromesh-node` | `astromesh` | `>=0.40.0` | Editable path source in the monorepo (`..`) |
| `astromesh-node` | `astromesh-cli` | `>=0.3.0` | Editable path source (`../astromesh-cli`) |
| `astromesh` | `astromesh-glyph` | `>=0.1.1` | Optional extra only (`astromesh[glyph]`); editable path source in the monorepo |

### 2.2 Plugin wiring

- `astromesh-cli` exposes the `astromeshctl.plugins` entry point.
- `astromesh-node` registers `node = astromesh_node.cli.plugin:register`.
- `astromesh-orbit` registers `orbit = astromesh_orbit.cli:register`.

This means `astromesh-node` and `astromesh-orbit` extend the same CLI binary (`astromeshctl`) when they are installed alongside `astromesh-cli`.

---

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

---

## 4. Branches and release flow

**`main` is the branch.** `origin/HEAD` points at it, every release tag since `v0.46.0` was
cut on it, and the documentation site publishes from it.

`develop` still exists and is **not used**: it sits behind `main` with nothing of its own.
It was the integration branch until the repository moved. The docs workflow kept watching
it, so publishing meant back-merging `main` into `develop` by hand — and when nobody
remembered, the site stayed on the 2026-08-28 build for eleven days and three releases while
`main` moved on. The workflow now triggers on `main`.

### 4.1 Releases v0.46.0 → v0.50.0

| Version | What landed |
|---------|-------------|
| `0.46.0` | `praxis_alcaldia` — the municipal-revenue vertical joins the integration catalog. |
| `0.46.1` / `0.46.2` | `mi_cuenta` also returns the day's rate; the runtime stops re-prefixing a `session_id` Nexus already namespaced. |
| `0.47.0` | An integration handler can know who is writing. |
| `0.48.0` | ReAct groups one response's tool calls into a single assistant message; `llm.complete` carries `cached_tokens`. |
| `0.49.0` | `praxis.obtener_record` — an agent can follow a relation instead of duplicating a record. |
| `0.50.0` | Price rows for `kimi-k2.7-code`, `kimi-k2.7-code-highspeed` and `kimi-k3`. |

### 4.2 Release flow

1. Update `CHANGELOG.md` under the new version's heading.
2. Bump `astromesh` in `pyproject.toml` (**two** places: `project.version` and
   `[tool.commitizen] version`) and `astromesh/__init__.py`.
3. Re-lock all three `uv.lock` files — root, `astromesh-cli/`, `astromesh-node/`.
4. Push `main`, then the tag `vX.Y.Z`.

The tag fires two independent publications, Docker Hub and PyPI, and one can fail while the
other succeeds. Check both: `v0.50.0` published its image and failed on PyPI.

## 5. Keeping this document current

When a package version changes:

1. Update its version in the package's own `pyproject.toml` / `package.json` / `Cargo.toml` and its `__init__.py`.
2. Update `docs-site/src/data/ecosystem.ts` (the source of truth for the site map and release ledger).
3. Update this file (`docs/ECOSYSTEM_DEPENDENCIES.md`).
4. Update `docs-site/src/content/docs/getting-started/ecosystem.md` if the prose description of the component changed.

When a new dependency is added between monorepo packages, update **Section 2** of this file and the corresponding prose in the docs-site ecosystem page.
