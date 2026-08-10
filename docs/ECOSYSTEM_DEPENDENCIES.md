# Astromesh Ecosystem — Components, Relations, and Dependencies

This document tracks the **components that make up the Astromesh ecosystem**, how they relate to each other, and the **dependency graph between the packages in this monorepo**. It is meant to be kept in sync with:

- The high-level [Ecosystem page](https://monaccode.github.io/astromesh/getting-started/ecosystem/) on the documentation site.
- The technical [Ecosystem Components & Dependencies](https://monaccode.github.io/astromesh/architecture/ecosystem-dependencies/) page on the documentation site.

> **Versioning rule:** This is a monorepo of independently versioned packages. A release of the core runtime does **not** bump any other package unless that package itself changed. Each package carries its own changelog and its own tag.

---

## 1. Component registry

### 1.1 Packages inside this monorepo

These directories ship from this repository on their own tags and versions.

| Component | Package | Directory | `main` version | `develop` version | Version source | Min Python |
|-----------|---------|-----------|----------------|-------------------|----------------|------------|
| **Core Runtime** | `astromesh` | `astromesh/` | `0.40.0` | `0.40.0` | `astromesh/__init__.py` | 3.12 |
| **Glyph** | `astromesh-glyph` | `astromesh-glyph/` | `0.1.0` | `0.1.0` | `astromesh_glyph/__init__.py` | 3.12 |
| **ADK** | `astromesh-adk` | `astromesh-adk/` | `0.2.0` | `0.2.0` | `astromesh_adk/__init__.py` | 3.12 |
| **CLI** | `astromesh-cli` | `astromesh-cli/` | `0.2.0` | `0.2.0` | `astromesh_cli/__init__.py` | 3.12 |
| **Node** | `astromesh-node` | `astromesh-node/` | `0.1.1` | `0.1.1` | `src/astromesh_node/__init__.py` | 3.12 |
| **Orbit** | `astromesh-orbit` | `astromesh-orbit/` | `0.4.0` | `0.4.0` | `astromesh_orbit/__init__.py` | 3.12 |
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

## 4. `main` vs `develop` status

Last merge from `develop` to `main`: **v0.40.0** (`23c1a4c`).
Current state: `develop` is ahead of `main` with documentation-only changes; no monorepo package versions have changed since the last merge.

### 4.1 Versions in `main`

All monorepo packages currently on `main`:

| Package | Version in `main` |
|---------|-------------------|
| `astromesh` | `0.40.0` |
| `astromesh-glyph` | `0.1.0` |
| `astromesh-adk` | `0.2.0` |
| `astromesh-cli` | `0.2.0` |
| `astromesh-node` | `0.1.1` |
| `astromesh-orbit` | `0.4.0` |
| `astromesh-forge` | `0.24.0` |

### 4.2 What is in `develop` but not yet in `main`

These changes are documentation/site updates and do not require a version bump of any runtime package:

- **Documentation site**: ecosystem star-map on the homepage, Glyph and Herald sections, release ledger, status board, Prisma page.
- **README.md**: ecosystem table rewritten by layer, layer badge, updated orchestration pattern count.
- **CHANGELOG.md**: `[Unreleased]` section documenting the docs-site changes.
- **AGENTS.md**: guidance file for AI coding agents.
- **`.claude/settings.local.json`**: local Claude command history.

### 4.3 What needs to be taken to `main`

A merge of the current `develop` branch into `main` would carry the documentation and site updates. No package releases are blocked because no code changed since `v0.40.0`.

If a new runtime release is desired, the normal release flow applies:

1. Update `CHANGELOG.md` under `[Unreleased]` (already done).
2. Run `cz bump` on `develop` to bump `astromesh` to the next version.
3. Re-lock `uv.lock` files for packages that reference the core as an editable path (`astromesh-node`, `astromesh-cli`, root).
4. Merge `develop` into `main` and tag `vX.Y.Z`.

---

## 5. Keeping this document current

When a package version changes:

1. Update its version in the package's own `pyproject.toml` / `package.json` / `Cargo.toml` and its `__init__.py`.
2. Update `docs-site/src/data/ecosystem.ts` (the source of truth for the site map and release ledger).
3. Update this file (`docs/ECOSYSTEM_DEPENDENCIES.md`).
4. Update `docs-site/src/content/docs/getting-started/ecosystem.md` if the prose description of the component changed.

When a new dependency is added between monorepo packages, update **Section 2** of this file and the corresponding prose in the docs-site ecosystem page.
