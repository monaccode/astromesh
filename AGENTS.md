# Astromesh — Agent Guidance

This file is written for AI coding agents. It assumes no prior knowledge of the project. For Claude-specific guidance (changelog rule, release checklist), also see [`CLAUDE.md`](CLAUDE.md).

---

## 1. Project Overview

Astromesh is an open-source **Agent Runtime Platform** for building, orchestrating, and running AI agents. It is designed as "Kubernetes for AI Agents": you define agents declaratively in YAML and the runtime handles model routing, tool execution, memory, RAG, guardrails, observability, and multi-agent patterns.

This repository is a **monorepo** of independently versioned packages. The core runtime lives in `astromesh/`. The other top-level directories are optional components, developer tools, deployment assets, and documentation.

Key facts:

- **Language:** Python 3.12+ for the runtime and most tools; TypeScript/React for the visual builder; Rust for optional native extensions.
- **Package manager:** [`uv`](https://docs.astral.sh/uv/). All Python projects use `uv` and keep their `uv.lock` files under version control.
- **Build backend:** `hatchling` for Python packages; `maturin` for the Rust extension.
- **License:** Apache-2.0.

---

## 2. Repository Layout

| Path | What it is | Current version |
|------|------------|-----------------|
| `astromesh/` | Core runtime (PyPI package `astromesh`) | `0.40.0` |
| `astromesh-adk/` | Agent Development Kit — Python SDK (`astromesh-adk`) | `0.2.0` |
| `astromesh-cli/` | `astromeshctl` command-line tool (`astromesh-cli`) | `0.2.0` |
| `astromesh-node/` | Cross-platform installer/daemon (`astromesh-node`) | `0.1.1` |
| `astromesh-orbit/` | Cloud-native deployment tool (`astromesh-orbit`) | `0.4.0` |
| `astromesh-glyph/` | Action language for LLM agents (`astromesh-glyph`) | `0.1.0` |
| `astromesh-forge/` | Visual agent builder (React/Vite/TypeScript) | `0.24.0` |
| `vscode-extension/` | Official VS Code extension | `0.1.0` |
| `docs-site/` | Documentation site (Astro + Starlight) | `0.1.0` |
| `native/` | Optional Rust native extension (`astromesh-native`) | `0.1.0` |
| `config/` | Default YAML configuration tree |
| `tests/` | Core runtime test suite |
| `docker/` | Dockerfiles and Compose stacks |
| `recipes/` | Ready-made Compose recipes for single-node and mesh deployments |
| `deploy/` | Helm chart and ArgoCD GitOps manifests |

> **Note:** `astromesh-cloud` (the managed SaaS platform) is maintained in a separate repository; it is **not** present in this monorepo even though it is documented in `README.md`.

### Core runtime modules (`astromesh/`)

- `api/` — FastAPI app, REST routes, and WebSocket endpoint.
- `runtime/` — `AgentRuntime` bootstrap and agent lifecycle (`engine.py`).
- `core/` — `ModelRouter`, `MemoryManager`, `ToolRegistry`, `PromptEngine`, `GuardrailsEngine`.
- `providers/` — LLM provider adapters (Ollama, OpenAI-compatible, vLLM, llama.cpp, HF TGI, ONNX, LiteLLM, Centinela).
- `orchestration/` — Reasoning patterns: ReAct, Plan & Execute, Parallel Fan-Out, Pipeline, Supervisor, Swarm, Glyph.
- `memory/` — Conversational, semantic, and episodic memory backends and strategies.
- `rag/` — Document chunking, embeddings, vector stores, reranking, and query pipeline.
- `tools/` — Built-in tool implementations.
- `mcp/` — Model Context Protocol client and server.
- `channels/` — Messaging channel adapters (WhatsApp, webhook dispatcher).
- `integrations/` — External service integration catalog (WhatsApp, Instagram, Facebook, Gmail, Google Drive/Sheets, TikTok, generic HTTP).
- `mesh/` — Distributed agent networking / gossip mesh.
- `observability/` — OpenTelemetry tracing, Prometheus metrics, cost tracking, logging.
- `workflow/` — YAML workflow engine with durable runs and approvals.
- `chain/` — Agent chain compiler and output schema handling.
- `ml/` — Model registry, ONNX/PyTorch serving, training stubs.
- `centinela/` — Model endpoint promotion/reconciliation tooling.

---

## 3. Technology Stack

### Core runtime

- **Web framework:** FastAPI + Uvicorn
- **Validation / serialization:** Pydantic V2
- **HTTP client:** httpx
- **Templating:** Jinja2
- **Configuration:** YAML via PyYAML
- **Async:** Python `asyncio` throughout

### Optional backends (installed via extras)

- Memory: Redis (`redis`), PostgreSQL (`asyncpg`), SQLite (`aiosqlite`)
- Vector stores: ChromaDB, Qdrant, FAISS
- Embeddings: `sentence-transformers`
- Inference: ONNX Runtime, PyTorch
- Observability: OpenTelemetry, Prometheus client
- Protocols: MCP, LiteLLM
- Glyph: `astromesh-glyph` (editable path source)

### Frontend / tooling

- **Forge:** Vite + React 19 + TypeScript 5.9 + Tailwind CSS + Zustand + React Flow + dnd-kit + Vitest
- **Docs site:** Astro + Starlight + Mermaid
- **VS Code extension:** TypeScript + esbuild + Mocha
- **Rust extension:** PyO3 + `regex` + `aho-corasick` + `serde`

---

## 4. Build and Development Commands

All commands assume you are using `uv` and are run from the project root unless noted.

### Install dependencies

```bash
uv sync                         # base runtime only
uv sync --extra all             # all optional Python backends + glyph
uv sync --group dev             # include dev/test tools
uv sync --extra redis --extra postgres --extra observability
```

### Run the API server

```bash
uv run uvicorn astromesh.api.main:app --reload
# or
make dev-single                 # uv run astromeshd --config ./config --log-level debug
```

The API listens on port `8000` by default. Override the config tree with:

```bash
ASTROMESH_CONFIG_DIR=./config/dev uv run uvicorn astromesh.api.main:app --reload
```

### Docker stacks

```bash
# Full 10-service development stack (API + Ollama + vLLM + Postgres + Redis + monitoring)
cd docker && docker compose up -d

# 3-node gossip mesh from source
make dev-mesh
make dev-logs
make dev-stop

# Pre-built image recipes (no source checkout needed)
docker compose -f recipes/single-node.yml up -d
docker compose -f recipes/mesh-3node.yml up -d
```

### Rust native extension (optional)

```bash
pip install maturin
maturin develop --release
# or
make build-rust
```

Without the extension the runtime falls back to pure Python automatically. Force the fallback with `ASTROMESH_FORCE_PYTHON=1`.

### Frontend tooling

```bash
cd astromesh-forge
npm ci
npm run dev                     # VITE_ASTROMESH_URL=http://localhost:8000

# Embed Forge into the API
npm run build
cp -r dist/ ../astromesh/static/forge/
```

### Documentation site

```bash
cd docs-site
npm ci
npm run dev
npm run build
```

---

## 5. Configuration Conventions

All configuration is YAML with the header:

```yaml
apiVersion: astromesh/v1
kind: <ResourceKind>
metadata:
  name: <unique-name>
```

Supported kinds:

- `Agent` — agent definitions in `config/agents/*.agent.yaml`
- `ProviderConfig` — LLM provider registry in `config/providers.yaml`
- `RAGPipeline` — RAG configs in `config/rag/*.rag.yaml`
- `RuntimeConfig` — global runtime settings in `config/runtime.yaml`

Important files:

- `config/runtime.yaml` — API host/port and default orchestration settings.
- `config/providers.yaml` — Provider endpoints, models, routing strategy, circuit breaker.
- `config/channels.yaml` — WhatsApp / messaging channel credentials via `${ENV_VAR}`.
- `config/connections.yaml` — Integration credentials for self-hosted deployments. **This file is `.gitignore`d.** Copy from `config/connections.yaml.example`.
- `config/agents/` — Agent YAML files.
- `config/rag/` — RAG pipeline YAML files.
- `config/workflows/` — Workflow YAML files.

Secrets must **always** be referenced by environment variable name, never hardcoded. Example:

```yaml
api_key_env: OPENAI_API_KEY
```

The default config directory is resolved in this order:

1. `ASTROMESH_CONFIG_DIR` environment variable
2. `./config` from the current working directory
3. Bundled config inside the installed wheel (`astromesh/_bundled/config`)
4. Source config next to the package directory

---

## 6. Runtime Architecture

Astromesh follows a 4-layer architecture:

```
API Layer (FastAPI REST + WebSocket)
    → Runtime Engine (AgentRuntime loads YAML → Agent instances)
        → Core Services (ModelRouter, MemoryManager, ToolRegistry, PromptEngine, GuardrailsEngine)
            → Infrastructure (Providers, Memory Backends, Orchestration Patterns, Channels, RAG, MCP, Mesh)
```

### Key abstractions

- **`AgentRuntime`** (`astromesh/runtime/engine.py`) — Scans `config/agents/*.agent.yaml`, builds fully wired `Agent` instances, and runs them.
- **`Agent`** — Executes the pipeline: input guardrails → memory context → Jinja2 prompt render → orchestration pattern → model router → tool execution → output guardrails → memory persistence.
- **`ProviderProtocol`** (`astromesh/providers/base.py`) — Runtime-checkable protocol implemented by every LLM provider. Methods include `complete()`, `stream()`, `health_check()`, `supports_tools()`, `estimated_cost()`.
- **`ModelRouter`** (`astromesh/core/model_router.py`) — Routes requests across providers using strategies (`cost_optimized`, `latency_optimized`, `quality_first`, `round_robin`, `capability_match`) with circuit-breaker fallback (3 failures → 60s cooldown).
- **`ToolRegistry`** (`astromesh/core/tools.py`) — Registers internal, MCP, webhook, RAG, agent-as-tool, and integration tools. Handles permissions, rate limiting, and function-call schemas.
- **`MemoryManager`** (`astromesh/core/memory.py`) — Manages conversational, semantic, and episodic memory with pluggable backends and strategies (`sliding_window`, `summary`, `token_budget`).

### API route wiring

Each route module in `astromesh/api/routes/` exposes:

- a FastAPI `router`
- a `set_runtime(runtime)` function

The API lifespan calls `set_runtime()` on every route module and stores the runtime in a **module-level singleton**. This is intentional and documented; the `PLW0603` ruff rule is disabled globally because of it. Do not refactor these globals without redesigning the API wiring.

The lifespan also bootstraps the `WorkflowEngine`. A broken workflow config is logged but does **not** prevent the API from starting.

In tests, you can skip runtime bootstrap with:

```python
# or set the env var before importing the app
os.environ["ASTROMESH_SKIP_RUNTIME"] = "1"
```

---

## 7. Code Style and Conventions

### Linting and formatting

- **Tool:** ruff (lint + format)
- **Line length:** 100
- **Target Python version:** 3.12

```bash
uv run ruff check astromesh/ tests/
uv run ruff format astromesh/ tests/
```

The ruff rule set is **explicitly declared** in each `pyproject.toml` under `[tool.ruff.lint] select`. Notable intentional overrides:

- `PLW0603` is ignored because module-level `global runtime` variables are the chosen route-wiring pattern.
- `N818` is ignored because renaming public exceptions like `CredentialMissing` would break the integration spec.

Tests have additional per-file ignores (`tests/**` in `tool.ruff.lint.per-file-ignores`).

### Pre-commit

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

The hooks mirror CI: `ruff check --fix` and `ruff format` on `astromesh/` and `tests/`.

### Commits and branching

- Default branch: `develop`
- Conventional Commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:`, `refactor:`
- Branch naming: `feature/<name>`, `fix/<name>`

### Changelog rule

**Mandatory:** Before any commit of type `feat:`, `fix:`, or `refactor:`, update `CHANGELOG.md` first. Add the entry under `## [Unreleased]` in the appropriate subsection (Added, Changed, Fixed, etc.) following [Keep a Changelog](https://keepachangelog.com/). For Claude Code users, use the `/changelog-automation` skill. See `CLAUDE.md` for the full rule.

### Language note

Documentation and this file are in English. Code comments are mostly English but some Spanish comments appear in config and source files (especially around lockfile policy and integration error handling). Do not "fix" Spanish comments; match the surrounding style when editing.

---

## 8. Testing Instructions

### Core runtime

```bash
uv run pytest -v
uv run pytest --cov=astromesh -v
uv run pytest tests/test_api.py -k test_health -v
```

Test markers:

- `benchmark` — performance tests; deselect with `-m "not benchmark"`
- `orbit_gcp` — provisions real GCP resources; always deselect in local/CI with `-m "not orbit_gcp"`

The shared `client` fixture in `tests/conftest.py` wraps the FastAPI app with `asgi-lifespan` so the lifespan runs, and uses `httpx.AsyncClient` with `ASGITransport`. Use `respx` for mocking HTTP calls. `asyncio_mode = "auto"` is set in `pyproject.toml`, so async test functions do not need decorators.

### Sub-packages

Each Python sub-package has its own `pyproject.toml` and `uv.lock`. Run tests inside the package directory:

```bash
cd astromesh-node
uv sync --locked --extra test
uv run pytest -v

cd astromesh-cli
uv sync --locked --extra test
uv run pytest -v

cd astromesh-orbit
uv sync --locked --extra dev
uv run pytest -v -m "not orbit_gcp"

cd astromesh-glyph
uv sync --locked --extra dev
uv run pytest -v
```

### Forge

```bash
cd astromesh-forge
npm ci
npm test
npm run build
```

### Rust

```bash
cargo test
cargo check
```

---

## 9. Deployment Processes

### Docker / Compose

- `docker/Dockerfile` — production CPU image; installs with `uv sync --frozen --no-dev --extra glyph`
- `docker/Dockerfile.gpu` — CUDA 12.1 image
- `docker/docker-compose.yaml` — full development stack
- `docker/docker-compose.gossip.yml` — 3-node mesh built from source (`make dev-mesh`)
- `docker/docker-compose.mesh.yml` — additional mesh variant
- `recipes/*.yml` — user-facing recipes that use the prebuilt `monaccode/astromesh:latest` image

### Kubernetes

- `deploy/helm/astromesh/` — Helm chart with CRDs for `Agent`, `Channel`, `Provider`, and `RAGPipeline`
- Value files: `values.yaml`, `values-dev.yaml`, `values-staging.yaml`, `values-prod.yaml`
- `deploy/gitops/argocd/applicationset.yaml` — ArgoCD ApplicationSet for GitOps deployments

### Cloud deployment (Orbit)

Orbit generates Terraform from Jinja2 templates using a provider plugin architecture.

```bash
cd astromesh-orbit
uv sync --locked --extra gcp
astromeshctl orbit init --provider gcp --preset starter
astromeshctl orbit plan
astromeshctl orbit apply
```

- GCP is the first supported provider. AWS and Azure providers are stubs on the roadmap.
- `astromeshctl orbit eject` produces standalone Terraform files.
- Mark real-GCP tests with `orbit_gcp` and skip them by default.

### System packages (Node)

`astromesh-node` builds cross-platform system packages:

```bash
make build-deb          # runs packaging/build-deb.sh
```

Produces `.deb` (Debian/Ubuntu), `.rpm` (RHEL/Fedora), `.tar.gz` (macOS), and `.zip` (Windows). Installs:

- `/etc/astromesh/` — configuration
- `/opt/astromesh/venv/` — Python environment
- `/var/lib/astromesh/` — runtime data
- `/var/log/astromesh/` — logs

Install service management: systemd on Linux, launchd on macOS, Windows Service on Windows.

### Release automation

GitHub Actions in `.github/workflows/`:

- `ci.yml` — lint, format, tests for core, node, CLI, orbit, glyph, Forge, and Docker image build/boot check
- `release.yml` — triggered on `vX.Y.Z` tags; creates GitHub release and pushes Docker image `fulfarodev/astromesh`
- `release-pypi.yml`, `release-adk.yml`, `release-cli.yml`, `release-node.yml`, `release-orbit.yml`, `release-glyph.yml` — per-package PyPI/npm releases
- `docs.yml` — builds and publishes the docs site
- `bench-glyph.yml` — Glyph benchmarks
- `centinela-*.yml` — model endpoint sync/promotion jobs

---

## 10. Releasing and Versioning

This is a **monorepo of independently versioned packages**. Do not bump a sub-package just because the core changed.

### Core runtime (`astromesh`)

Version must stay in sync in:

- `pyproject.toml` (`[project] version` and `[tool.commitizen] version`)
- `astromesh/__init__.py` (`__version__`)

Use Commitizen:

```bash
cz bump
```

This updates both version files and the changelog. Then move `[Unreleased]` entries into a `## [vX.Y.Z] - YYYY-MM-DD` section, commit, and tag `vX.Y.Z`.

Because `uv.lock` is versioned and several packages reference the core as an editable path source, you must also re-lock after a core version bump:

```bash
uv lock                         # root
uv lock -C astromesh-node
uv lock -C astromesh-cli
```

`astromesh-orbit` does **not** reference the core, so its lock does not need updating for a core release.

### Sub-packages

Each Python sub-package keeps its `pyproject.toml` version and its package `__init__.py` `__version__` in sync manually (nothing automates this except the core):

- `astromesh-adk` → `astromesh_adk/__init__.py`
- `astromesh-orbit` → `astromesh_orbit/__init__.py`
- `astromesh-node` → `src/astromesh_node/__init__.py`
- `astromesh-cli` → `astromesh_cli/__init__.py`
- `astromesh-forge` → `package.json` only

Each release is its own commit and tag. See `CLAUDE.md` for the full release checklist.

---

## 11. Security Considerations

- **Secrets:** API keys, tokens, and passwords must be referenced by environment variable name (`api_key_env`, `${VAR}`) or placed in `config/connections.yaml` (which is `.gitignore`d). Never commit secrets.
- **Guardrails:** Configure per-agent guardrails for PII redaction, topic filtering, content filtering, max input length, and cost limits. See `astromesh/core/guardrails.py`.
- **Integrations:** Integration actions never raise on failure; they return a structured `error_kind` (`credential_missing`, `credential_invalid`, `rate_limited`, `upstream_error`, `bad_request`). The runtime does not store or refresh OAuth credentials — that is Nexus's responsibility.
- **Channels:** WhatsApp webhook signatures are validated with `app_secret`. Outgoing messages are rate-limited.
- **Production hardening:** Enable TLS, restrict network access to runtime infrastructure, and monitor logs/telemetry.
- **Vulnerability reporting:** Do not open public issues. Email `security@astromesh.ai`. See `SECURITY.md`.

---

## 12. Useful References

- `README.md` — project overview and quick start
- `CLAUDE.md` — Claude-specific guidance, changelog rule, release checklist
- `CONTRIBUTING.md` — contribution workflow and conventions
- `SECURITY.md` — security policy and reporting
- `docs/TECH_OVERVIEW.md` — detailed feature overview
- `docs/GENERAL_ARCHITECTURE.md` — architecture deep dive
- `docs/CONFIGURATION_GUIDE.md` — YAML configuration reference
- `docs/DEV_QUICKSTART.md` — local development and mesh setup
- `docs/INSTALLATION.md` — Debian package installation
- `docs/ADK_QUICKSTART.md` and `docs/ADK_PENDING.md` — ADK usage and roadmap
- `docs/ORBIT_OVERVIEW.md`, `docs/ORBIT_QUICKSTART.md`, `docs/ORBIT_CONFIGURATION.md` — Orbit docs
- `docs/GLYPH_GUIDE.md` — Glyph action language guide
