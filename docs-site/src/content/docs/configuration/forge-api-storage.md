---
title: Forge, API & on-disk agents
description: Persist agents created from Forge or the REST API, and configure where agent templates are loaded from.
---

When you run the Astromesh HTTP API (`astromesh.api.main:app`) or **Forge** against that API, two filesystem-related behaviors matter: **where agent YAML lives** (including definitions created from the UI) and **where Forge templates (`*.template.yaml`) are discovered**.

## Config directory

All agent files and most template paths are anchored to your [runtime configuration directory](/astromesh/configuration/runtime-config/). Set it explicitly with:

```bash
export ASTROMESH_CONFIG_DIR=/path/to/config
```

Typical layout:

```
config/
├── runtime.yaml
├── agents/
│   ├── my-agent.agent.yaml
│   └── ...
└── templates/
    ├── my-template.template.yaml
    └── ...
```

Relative `ASTROMESH_CONFIG_DIR` values (for example `config`) are resolved against the **process current working directory** when the API starts. Run Uvicorn from the project root, or use an absolute path in production.

## Agent persistence (Forge / `POST /v1/agents`)

By default, when you **create**, **update**, or **deploy** an agent through the API, the runtime writes the full agent spec to:

```
${ASTROMESH_CONFIG_DIR}/agents/<name>.agent.yaml
```

Deleting an agent via **`DELETE /v1/agents/{name}`** removes that file (when persistence is enabled).

This means agents you define in Forge survive an API restart, as long as:

- `ASTROMESH_CONFIG_DIR` points at the same directory, and
- persistence is not disabled (see below).

On startup, the runtime loads every `*.agent.yaml` under `agents/`. If a file cannot be built into a runnable agent (for example incomplete YAML), the definition is still kept as a **draft** in memory so you can fix it from Forge instead of disappearing silently.

### Disable writing agent files

Automated tests and some ephemeral environments set:

| Value | Behavior |
|-------|----------|
| `ASTROMESH_PERSIST_AGENTS=0`, `false`, or `no` | No YAML files are written or deleted for API-driven create/update/delete. Agents exist only in memory until the process exits. |

Example:

```bash
ASTROMESH_PERSIST_AGENTS=0 uv run python -m uvicorn astromesh.api.main:app --host 127.0.0.1 --port 8000
```

### Agent names and filenames

The API persists to `<metadata.name>.agent.yaml`. Names must be safe for a single path segment (no `/`, `\`, or `..`).

## Agent template discovery (`GET /v1/templates`)

Forge loads the template gallery from the API. Template files must be named `*.template.yaml` and use the `AgentTemplate` schema (see [Agent Templates](/astromesh/forge/templates/)).

### Default: merged discovery

Unless a single directory is pinned programmatically (for example in tests), the API **merges** templates from every distinct directory below, in order. If the same `metadata.name` appears in more than one place, **the later directory wins** (override).

1. **Bundled templates** next to the installed `astromesh` package (`…/config/templates` in a source checkout).
2. **`${ASTROMESH_CONFIG_DIR}/templates`** (only if that directory exists).
3. **`./config/templates`** relative to the process **current working directory**.
4. **`ASTROMESH_TEMPLATES_DIR`**, if set to an existing directory.

Duplicate paths are only scanned once.

### Extra template root only

To add templates without changing the rest of the config tree:

```bash
export ASTROMESH_TEMPLATES_DIR=/opt/astromesh/extra-templates
```

Files there override earlier roots when template names collide.

### Empty `templates/` folder under `ASTROMESH_CONFIG_DIR`

If you create `${ASTROMESH_CONFIG_DIR}/templates` but add no `*.template.yaml` files yet, the API **does not** treat that empty folder as the only source. Merged discovery still applies, so built-in or bundled templates remain visible in Forge.

When using **astromeshd**, a template directory is registered only if it contains at least one `*.template.yaml` file, so an empty folder does not hide merged templates.

### Exclusive directory (advanced)

If the Python API sets a single templates directory via `set_templates_dir()` (used in tests), **only** that directory is read—no merge. Operators normally rely on environment variables and the default merge behavior above.

## Related environment variables

See the [Environment variables](/astromesh/reference/env-vars/) reference for a compact table including `ASTROMESH_CONFIG_DIR`, `ASTROMESH_PERSIST_AGENTS`, and `ASTROMESH_TEMPLATES_DIR`.

## See also

- [Runtime configuration](/astromesh/configuration/runtime-config/) — `ASTROMESH_CONFIG_DIR` and multi-environment layouts
- [Agent YAML schema](/astromesh/configuration/agent-yaml/) — file format for `agents/*.agent.yaml`
- [Agent Templates (Forge)](/astromesh/forge/templates/) — template file structure and catalog
