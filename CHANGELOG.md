# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.14.0] - 2026-03-10

### Added

- **VS Code Extension** (`vscode-extension/`) — official extension wrapping `astromeshctl` CLI with zero business logic in the extension
  - **YAML IntelliSense** — JSON Schemas for `*.agent.yaml` and `*.workflow.yaml` with auto-completion, validation, and hover docs (requires Red Hat YAML extension)
  - **Run Agent** — play button on `.agent.yaml` files, extracts agent name from YAML, prompts for query, shows response in Output panel
  - **Run Workflow** — play button on `.workflow.yaml` files with `--workflow` flag passthrough
  - **Workflow Visualizer** — webview DAG panel with color-coded step types (agent=green, tool=yellow, switch=purple), connectors, and goto labels
  - **Traces Panel** — TreeDataProvider sidebar with expandable span trees, auto-refresh (configurable interval), and manual refresh command
  - **Metrics Dashboard** — webview panel with counters grid and histograms table, auto-refresh every 10s, VS Code theme integration
  - **Copilot Chat** — interactive chat panel wrapping `astromesh ask` with user/assistant message bubbles and loading states
  - **Diagnostics** — command wrapping `astromesh doctor` with check-by-check output and health status notification
  - **Status Bar** — daemon status indicator showing agent count, version, mode; click to run diagnostics
  - **CLI Wrapper** (`src/cli.ts`) — `AstromeshCli` class with `exec`, `execJson`, `buildArgs`, `parseJsonOutput` for spawning CLI commands
  - Extension settings: `astromesh.cliPath`, `astromesh.daemonUrl`, `astromesh.traces.autoRefresh`, `astromesh.traces.refreshInterval`
  - 6 extension unit tests (CLI wrapper + traces logic)
- **Developer Tools Guide** (`docs-site/src/content/docs/getting-started/developer-tools.md`) — step-by-step workflow from scaffold to production: Define → Run → Debug → Optimize → Deploy
- **VS Code Extension Reference** (`docs-site/src/content/docs/reference/os/vscode-extension.md`) — full feature reference with installation, settings, and usage
- **Developer Tools doc** (`docs/DEVELOPER_TOOLS.md`) — CLI command table, Copilot, VS Code Extension features, Dashboard overview
- **README Developer Experience section** — toolkit table (CLI, Copilot, VS Code, Dashboard) with 5-command workflow example
- **README Roadmap update** — 10 completed items including VS Code extension, 5 remaining items
- docs-site sidebar entries for Developer Tools and VS Code Extension (42 pages total)

### Changed

- **README Tool System section** — updated to reflect 18 built-in tools, 3 MCP servers, agent tools, webhooks, RAG
- **README Observability section** — expanded with CLI commands, dashboard URL, OTel export, VS Code integration

## [0.13.0] - 2026-03-10

### Added

- **Workflow Engine** — `WorkflowSpec`, `StepSpec`, `StepResult`, `RetryConfig` dataclasses for YAML-defined multi-step workflows (`astromesh/v1 Workflow`)
- **Workflow Loader** — reads `*.workflow.yaml` from `config/workflows/`, validates schema, registers workflows at bootstrap
- **Step Executor** — handles 3 step types: agent (via `runtime.run()`), tool (via `tool_registry.execute()`), switch (Jinja2 conditional with `goto`)
- **Retry & Timeout** — per-step retry with fixed/exponential backoff via `asyncio.sleep`, per-step and workflow-level timeouts via `asyncio.wait_for`
- **Error Handling** — `on_error` field per step (goto another step or `"fail"` to abort); workflow-level `timeout_seconds`
- **Workflow API** — `POST /v1/workflows/{name}/run`, `GET /v1/workflows`, `GET /v1/workflows/{name}` with `set_workflow_engine()` injection pattern
- **Built-in Dashboard** — single-page HTML at `GET /v1/dashboard/` with auto-refreshing (10s) panels for counters, histograms, traces, and workflows; dark theme matching Astromesh branding
- **CLI Workflow Execution** — `astromeshctl run --workflow` now calls `POST /v1/workflows/{name}/run` (replaces Sub-project 4 stub)
- **Example Workflow** — `config/workflows/example.workflow.yaml` (lead qualification pipeline with research → qualify → decide → send-email/log-and-skip)
- 59 new tests for workflow models, loader, executor, engine, API, dashboard, and CLI wiring

### Changed

- **`astromesh/api/main.py`** — mounts `workflows.router` and `dashboard.router` at `/v1`
- **`cli/commands/run.py`** — replaces "not yet implemented" stub with actual workflow API call
- **`cli/templates/workflow.yaml.j2`** — updated with full workflow schema including triggers, steps, retry, and observability config

## [0.12.0] - 2026-03-10

### Added

- **Built-in Tool Framework** — `BuiltinTool` ABC, `ToolResult`/`ToolContext` dataclasses, and `ToolLoader` with auto-discovery for registering tools via `type: builtin` in agent YAML
- **17 Built-in Tools** across 7 categories:
  - **Utilities** — `datetime_now` (timezone-aware), `json_transform` (Jinja2 templates), `cache_store` (key-value sharing between tool calls)
  - **HTTP** — `http_request` (GET/POST/PUT/DELETE/PATCH with localhost blocking), `graphql_query`
  - **Web** — `web_search` (Tavily provider), `web_scrape` (HTML-to-text), `wikipedia` (article summaries)
  - **Files** — `read_file`, `write_file` (both with configurable `allowed_paths` restrictions)
  - **Database** — `sql_query` (SQLite, `read_only: true` by default, blocks INSERT/UPDATE/DELETE/DROP)
  - **Communication** — `send_webhook`, `send_slack` (via webhook), `send_email` (async SMTP via `asyncio.to_thread`)
  - **AI** — `text_summarize` (delegates to agent's model via `model_fn`, skips short text)
  - **RAG** — `rag_query`, `rag_ingest` (wraps existing RAG pipeline)
- **`GET /v1/tools/builtin`** — API endpoint listing all available builtin tools with metadata (name, description, parameters)
- **TracingContext** — lightweight span-based tracing with `start_span()`/`finish_span()`, nested spans, and `to_dict()` serialization
- **Runtime tracing** — `Agent.run()` automatically creates spans for `memory_build`, `prompt_render`, `llm.complete`, `tool.call`, `orchestration`, `memory_persist`; trace attached to result as `result["trace"]`
- **StructuredLogger** — JSON-to-stdout logger with `info()`/`warning()`/`error()`/`debug()` methods
- **Trace collectors** — `StdoutCollector` (JSON to stream), `InternalCollector` (in-memory deque with index), `OTLPCollector` (bridges to existing `TelemetryManager` for OpenTelemetry export)
- **`GET /v1/traces/`** — list traces with optional `?agent=` filter and `?limit=` pagination
- **`GET /v1/traces/{trace_id}`** — retrieve individual trace by ID (404 on miss)
- **`GET /v1/metrics/`** — in-memory counters and histograms (count, sum, avg, min, max)
- **`POST /v1/metrics/reset`** — clear all metrics
- **Ecosystem design spec** (`docs/superpowers/specs/2026-03-10-astromesh-ecosystem-design.md`) — 5 sub-project architecture for tools, observability, multi-agent, CLI/copilot, and VS Code extension
- 93 new tests for all tools, tracing, collectors, APIs, and registry
- **CLI Scaffolding Commands** — `astromeshctl new agent|workflow|tool` generates YAML/Python from Jinja2 templates with interactive prompts and `--force` overwrite support
- **CLI Execution Commands** — `astromeshctl run <agent> "query"` executes agents via REST API; `astromeshctl dev` starts hot-reload dev server with `uvicorn --reload`
- **CLI Observability Commands** — `astromeshctl traces <agent>` lists recent traces; `astromeshctl trace <id>` shows span tree; `astromeshctl metrics` and `astromeshctl cost` show aggregated metrics
- **CLI Tools Commands** — `astromeshctl tools list` shows available builtin tools; `astromeshctl tools test <name> '{args}'` tests tools in isolation
- **CLI Validation** — `astromeshctl validate` checks all `*.agent.yaml` and `*.workflow.yaml` files for schema compliance
- **Copilot Agent** — `astromeshctl ask "question"` runs an astromesh-copilot agent locally with sandboxed filesystem access and `--context` file support; agent YAML at `config/agents/astromesh-copilot.agent.yaml`
- **Agent-as-Tool** — new `type: agent` tool type allows agents to invoke other agents as tools; registered via `register_agent_tool()` with full ToolResult integration
- **Context Transforms** — Jinja2-based data reshaping between agent-to-agent calls via `context_transform` field in tool YAML; uses `_DotDict` for dot-notation access
- **Nested Agent Tracing** — agent-in-agent calls share trace tree via `parent_trace_id` propagation; child agents create spans under parent's trace
- **Circular Reference Detection** — DFS cycle detection at bootstrap prevents infinite agent-as-tool reference loops
- **Multi-agent Composition docs** — new docs-site page covering agent-as-tool, context transforms, and supervisor/swarm integration
- 68 new tests for CLI commands, agent-as-tool, context transforms, supervisor/swarm agent integration
- 33 CLI tests + 35 multi-agent tests

### Changed

- **License** — consolidated into single `LICENSE` file (Apache 2.0), removed `LICENSE.md`
- **NOTICE.md** — updated repo URL, added managed runtime and enterprise support to commercial offerings
- **Repo rename** — all references to `astromech-platform` replaced with `astromesh` across docs, configs, CI, Helm chart, Dockerfile, packaging, and docs-site (29 files, 78 occurrences)
- **README CI badge** — CI badge now tracks `main` branch instead of `develop`
- **Docs site visual redesign** — replaced emoji icons with SVG Lucide icons across all landing page components for consistent cross-platform rendering
- **PipelineDiagram** — redesigned with gradient icon circles, numbered steps, dashed SVG connectors, glow effects, and staggered animations; each step is now a clickable link to its relevant docs page; responsive flex layout (no horizontal scroll)
- **FeatureCards** — per-card accent colors with tinted SVG icon backgrounds, refined expand/collapse chevron
- **DeploymentTabs** — dark chrome tab bar with per-mode SVG icons, unified glass-morphism surface
- **AgentExample** — macOS-style window chrome (traffic light dots), uppercase response label
- **Custom CSS** — replaced Inter font with DM Sans + JetBrains Mono; added custom design tokens (`--am-glow`, `--am-surface`, `--am-border`) for cohesive aerospace aesthetic
- **Color palette rebrand** — accent palette shifted from blue (`#3b82f6`) to logo-derived cyan (`#00d4ff`); updated all CSS variables, component fallback values, and gradient endpoints (`#06b6d4`) across `custom.css`, `PipelineDiagram`, `FeatureCards`, `DeploymentTabs`, and `AgentExample`
- **`astromesh/runtime/engine.py`** — `_build_agent()` now resolves `type: builtin` tools via `ToolLoader`; `Agent.run()` wrapped with `TracingContext` for automatic span collection
- **`astromesh/api/main.py`** — mounts `traces` and `metrics` routers at `/v1`
- **`astromesh/observability/collector.py`** — refactored with `Collector` ABC; added `OTLPCollector` bridging to OpenTelemetry
- **`astromesh/core/tools.py`** — added `ToolType.AGENT` enum, `agent_config`/`context_transform` fields to `ToolDefinition`, `register_agent_tool()` and `set_runtime()` methods, Jinja2 context transform execution in AGENT branch
- **`astromesh/orchestration/supervisor.py`** — delegates to workers via `tool_fn` instead of direct `model_fn` calls, enabling agent-as-tool delegation
- **`astromesh/orchestration/swarm.py`** — handoffs now use `tool_fn` to invoke agent tools, supporting `type: agent` handoff targets
- **`astromesh/runtime/engine.py`** — wires `type: agent` tools in `_build_agent()`, passes runtime reference to ToolRegistry, adds `_detect_circular_refs()` DFS at bootstrap, `parent_trace_id` propagation
- **`astromesh/observability/tracing.py`** — `start_span()` now accepts optional `parent_span_id` parameter for explicit parent override
- **`cli/main.py`** — registered 8 new command groups (new, run, dev, traces, metrics, tools, validate, ask)
- **`cli/client.py`** — added `api_post_with_timeout()` and `api_get_params()` helper methods
- **`cli/output.py`** — added Rich formatters: `print_trace_list()`, `print_trace_tree()`, `print_metrics_table()`, `print_cost_table()`, `print_tool_list()`

### Added (docs-site)

- **Dark mode lock** — theme toggle removed via Starlight `ThemeSelect` component override; dark mode is now permanent with CSS fallback for any light-theme tokens
- **Astromesh logo** in docs-site landing page hero with blue glow drop-shadow and entrance animation
- "Read full pipeline documentation" CTA button below pipeline diagram linking to `/architecture/agent-pipeline/`
- **README badges** — CI, Release, Docs (workflow status), Version, License, Python version
- **README navigation links** — Documentation site, Quick Start, Releases centered below badges
- Docs site link as primary documentation entry point in README
- Additional doc references in README: Maia guide, Dev quickstart, Installation

### Changed (docs-site)

- **README** — clone URL updated from `your-org` to `monaccode`

### Fixed

- "Get Started" hero button now correctly links to `/astromesh/getting-started/what-is-astromesh/` (was missing `/astromesh` base path)
- Docs CI workflow updated to Node 22 for Astro 5.x compatibility
- Removed broken GitHub raw logo image from landing page
- WhatsApp integration docs formatting fix
- Deployment options table in "What is Astromesh?" now uses "View guide →" link text instead of repeating the deployment name

## [0.11.0] - 2026-03-09

### Added

- **Docker Hub pre-built image** — `monaccode/astromesh:latest` with smart entrypoint that generates config from environment variables (`docker/entrypoint.sh`)
- Entrypoint supports `ASTROMESH_ROLE`, `ASTROMESH_MESH_ENABLED`, `ASTROMESH_NODE_NAME`, `ASTROMESH_SEEDS`, `ASTROMESH_PORT` env vars for zero-config deployment
- `ASTROMESH_AUTO_CONFIG=false` opt-out for users mounting their own `runtime.yaml`
- **4 Docker Compose recipes** (`recipes/`) — pre-built image, no source checkout needed:
  - `single-node.yml` — single full node with Ollama
  - `mesh-3node.yml` — gateway + worker + inference with Maia gossip discovery
  - `mesh-gpu.yml` — mesh with NVIDIA GPU acceleration for Ollama
  - `dev-full.yml` — full stack with Prometheus, Grafana, and OpenTelemetry Collector
- **Docker Hub CI** — `build-docker` job in `.github/workflows/release.yml` pushes `monaccode/astromesh:<version>` and `monaccode/astromesh:latest` on release tags
- **Maia Developer Guide** (`docs/MAIA_GUIDE.md`) — hands-on guide with recipes reference, environment variables, config generation, profiles, scaling, troubleshooting
- **Documentation site** (`docs-site/`) — Starlight (Astro) static site with 37 pages:
  - Interactive landing page with animated pipeline diagram, expandable feature cards, deployment tabs with copy-to-clipboard, and agent YAML split-pane example
  - Getting Started (4 pages): What is Astromesh, Installation, Quick Start, Your First Agent
  - Architecture (4 pages): Overview, Four-Layer Design, Agent Execution Pipeline, K8s Architecture
  - Configuration (6 pages): Init Wizard, Agent YAML Schema, Providers, Runtime Config, Profiles, Channels
  - Deployment (7 pages): Standalone, Astromesh OS, Docker Single, Docker Maia, Docker Maia+GPU, Helm/K8s, ArgoCD/GitOps
  - Advanced (4 pages): Rust Extensions, WhatsApp Integration, Observability, Maia Internals
  - Reference (11 pages): Runtime Engine, Model Router, Tool Registry, Memory Manager, Daemon, CLI, Gossip Protocol, Scheduling, Env Vars, API Endpoints, CLI Commands
- **Docs CI** — `.github/workflows/docs.yml` auto-deploys to GitHub Pages on push to `develop`
- 4 interactive Astro components: `PipelineDiagram`, `FeatureCards`, `DeploymentTabs`, `AgentExample`

### Changed

- `Dockerfile` — added entrypoint script, ENV defaults, changed ENTRYPOINT from `astromeshd` to `/usr/local/bin/entrypoint.sh`
- `docs/ASTROMESH_MAIA.md` — added pointer to MAIA_GUIDE.md developer guide
- `docs/DEV_QUICKSTART.md` — added reference to `recipes/` for pre-built image users
- `.gitignore` — added `docs-site/node_modules/`, `docs-site/dist/`, `docs-site/.astro/`

## [0.10.0] - 2026-03-09

### Added

- **`astromeshctl init` wizard** — interactive setup command that guides developers from zero to a running node: role selection, provider configuration, mesh setup, config file generation, and validation (`cli/commands/init.py`)
- Wizard supports `--non-interactive` mode for CI/scripting (defaults: role=full, provider=ollama)
- Wizard supports `--dev` flag to force local `./config/` mode even as root
- Provider auto-detection: checks Ollama connectivity, prompts API keys for OpenAI/Anthropic, writes `.env` file
- Mesh configuration step for non-full roles: node name, seed URLs, gossip parameters
- Config validation step reusing `astromeshctl config validate` logic
- Sample agents automatically copied to `{config_dir}/agents/` during init
- **One-liner install script** (`packaging/get-astromesh.sh`) — `curl | bash` installer with OS detection, APT repo setup, Python version check, and Docker fallback for non-Debian systems
- **Makefile** with developer targets: `dev-single`, `dev-mesh`, `dev-stop`, `dev-logs`, `test`, `test-cov`, `lint`, `fmt`, `build-deb`, `build-rust`
- **Developer Quick-Start guide** (`docs/DEV_QUICKSTART.md`) — prerequisites, single-node setup, Docker mesh, first agent, Makefile reference, troubleshooting
- Tests for init wizard: profile copy, provider generation (ollama/openai/anthropic), `.env` writing, idempotency, non-interactive mode, validation, dev mode, agents directory (10 new tests, 342 total)

### Changed

- `packaging/systemd/astromeshd.service` — added `EnvironmentFile=-/etc/astromesh/.env` for API key injection
- `packaging/scripts/postinstall.sh` — added hint to run `astromeshctl init` after package install
- `cli/main.py` — registered `init` command

### Fixed

- Version assertions in `test_cli.py` and `test_daemon_integration.py` updated from hardcoded `0.7.0` to match current version

## [0.9.0] - 2026-03-09

### Added

- **APT package distribution** — users can install Astromesh via `apt install astromesh` from a GitHub Pages-hosted APT repository
- `nfpm.yaml` — package definition for nfpm: self-contained Python venv at `/opt/astromesh/venv/`, symlinks to `/usr/bin/`, config files as conffiles (preserved on upgrade)
- Maintainer scripts (`packaging/scripts/`):
  - `preinstall.sh` — idempotent `astromesh` system user/group creation
  - `postinstall.sh` — runtime dirs, permissions, systemd enable (no auto-start)
  - `preremove.sh` — stop and disable service
  - `postremove.sh` — cleanup on purge (data, logs, user), daemon-reload always
- `packaging/build-deb.sh` — build orchestration: extracts version from pyproject.toml, creates venv with `[cli,daemon]` extras, strips `__pycache__`, runs nfpm
- `.github/workflows/release.yml` — CI/CD pipeline triggered on `v*` tags:
  - `build-deb` job: builds `.deb` package
  - `publish-apt-repo` job: updates GitHub Pages APT repository with signed metadata (GPG)
  - `release-assets` job: uploads `.deb` to GitHub Releases
- `build-deb-test` job in CI workflow — verifies `.deb` builds correctly on every PR
- `docs/INSTALLATION.md` — user-facing guide: APT repo setup, configuration, service management, upgrading, uninstalling

### Changed

- `packaging/systemd/astromeshd.service` — `ExecStart` updated from `/opt/astromesh/bin/astromeshd` to `/opt/astromesh/venv/bin/astromeshd`

## [0.8.0] - 2026-03-09

### Added

- **Astromesh Mesh** — gossip-based distributed multi-node agent execution
- **MeshManager** (`astromesh/mesh/manager.py`) — HTTP gossip protocol with periodic heartbeats, failure detection (alive → suspect → dead), and seed-based cluster join/leave
- **LeaderElector** (`astromesh/mesh/leader.py`) — bully algorithm leader election (highest node ID wins), automatic re-election on leader failure
- **Scheduler** (`astromesh/mesh/scheduler.py`) — two-level scheduling: least-loaded agent placement across worker nodes, least-connections request routing
- **NodeState/ClusterState** (`astromesh/mesh/state.py`) — mesh data models with serialization, gossip merge (keep latest heartbeat), and alive node filtering
- **MeshConfig** (`astromesh/mesh/config.py`) — configuration for mesh networking: seeds, heartbeat/gossip intervals, failure/dead timeouts, gossip fanout
- **Mesh API endpoints** (`astromesh/api/routes/mesh.py`) — `POST /v1/mesh/join`, `/leave`, `/heartbeat`, `/gossip`, `/election`, `GET /v1/mesh/state`
- **PeerClient.from_mesh()** — bridges mesh discovery into existing peer forwarding infrastructure; dynamic peers from cluster state replace static config
- `astromeshctl mesh status` — mesh cluster summary (nodes, leader, alive/suspect/dead counts)
- `astromeshctl mesh nodes` — Rich table with all nodes: name, URL, services, agents, load, status, leader flag
- `astromeshctl mesh leave` — graceful mesh departure
- Mesh-enabled config profiles: `mesh-gateway.yaml`, `mesh-worker.yaml`, `mesh-inference.yaml` (`config/profiles/`)
- Docker Compose gossip mesh for local development (`docker/docker-compose.gossip.yml`)
- Background gossip and heartbeat loops in daemon with graceful cleanup on shutdown
- `GET /v1/system/status` now includes `mesh` section (node_id, leader, cluster_size, status)
- `psutil` optional dependency for CPU/memory load metrics (`[mesh]` extra)
- Mesh design and implementation plan documents (`docs/plans/2026-03-09-astromesh-mesh-*.md`)
- Tests for all mesh components: state, config, manager, leader, scheduler, API, PeerClient bridge, daemon wiring, and 3-node integration (78 new tests, 332 total)

### Changed

- `daemon/astromeshd.py` parses `spec.mesh` from runtime.yaml, creates MeshManager/LeaderElector when enabled, starts gossip/heartbeat background loops
- `PeerClient` extended with `from_mesh()` classmethod for dynamic peer discovery
- `cli/main.py` registers `mesh` command group
- `cli/client.py` adds `api_post()` helper

## [0.7.0] - 2026-03-09

### Added

- **ServiceManager** (`astromesh/runtime/services.py`) — controls which subsystems (api, agents, inference, memory, tools, channels, rag, observability) are active on each node
- **PeerClient** (`astromesh/runtime/peers.py`) — HTTP client for inter-node communication with round-robin load balancing, health checks, and request forwarding
- Config profiles for common node roles: `full.yaml`, `gateway.yaml`, `worker.yaml`, `inference.yaml` (`config/profiles/`)
- Conditional bootstrap in AgentRuntime — only initializes subsystems enabled by ServiceManager
- `spec.services` and `spec.peers` configuration sections in `runtime.yaml`
- `astromeshctl peers list` command — display peer nodes with services and connectivity status
- `astromeshctl services` command — display enabled/disabled services on the current node
- Universal multi-stage Dockerfile for all node roles (`Dockerfile`)
- Docker Compose mesh configuration for multi-node local development: gateway + worker + inference nodes (`docker/docker-compose.mesh.yml`)
- `/v1/system/status` now includes `services` (enabled map) and `peers` (list with health)
- `/v1/system/doctor` now checks peer connectivity in addition to local health
- Phase 2 design and implementation plan documents (`docs/plans/2026-03-09-astromesh-os-phase2-*.md`)
- Tests for ServiceManager, PeerClient, conditional bootstrap, mesh integration, CLI commands, and API extensions (7 new test files, 254 total tests passing)

### Changed

- `AgentRuntime` accepts optional `service_manager` and `peer_client` parameters (backward compatible — all services enabled when omitted)
- `daemon/astromeshd.py` parses `spec.services` and `spec.peers` from runtime.yaml, wires into runtime
- `cli/main.py` registers `peers` and `services` command groups

## [0.6.0] - 2026-03-09

### Added

- `astromeshd` daemon — single-process async runtime daemon with systemd integration (`daemon/astromeshd.py`)
- Auto-detection of config directory: `/etc/astromesh/` (system mode) vs `./config/` (dev mode)
- PID file management and graceful shutdown via SIGTERM/SIGHUP signal handling
- systemd notify support via `sdnotify` for `Type=notify` service readiness
- `astromeshctl` CLI management tool built with Typer + Rich (`cli/`)
- CLI `status` command — daemon uptime, version, mode, loaded agents count
- CLI `doctor` command — system health checks with per-provider diagnostics
- CLI `agents list` command — display loaded agents in Rich table
- CLI `providers list` command — display configured model providers
- CLI `config validate` command — offline YAML validation without starting daemon
- All CLI commands support `--json` flag for machine-readable output
- `GET /v1/system/status` API endpoint — version, uptime, mode, PID, agents count
- `GET /v1/system/doctor` API endpoint — runtime and provider health checks
- systemd unit file with security hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` (`packaging/systemd/astromeshd.service`)
- Installation script for Linux system deployment: creates `astromesh` user, filesystem layout, permissions (`packaging/install.sh`)
- Filesystem layout convention: `/etc/astromesh/` (config), `/var/lib/astromesh/` (state), `/var/log/astromesh/` (logs), `/opt/astromesh/` (binaries)
- `cli` and `daemon` optional dependency groups in `pyproject.toml`
- `astromeshd` and `astromeshctl` console script entry points
- Design documents for Astromesh OS phases 1-4 (`docs/plans/2026-03-09-astromesh-os-*.md`)
- Tests for daemon, CLI, system API, and integration (4 new test files)

### Changed

- Registered system routes in FastAPI app (`astromesh/api/main.py`)

## [0.5.0] - 2026-03-09

### Added

- Production-grade Helm chart for Kubernetes deployment (`deploy/helm/astromesh/`)
- Helm chart core: Deployment, Service, Ingress, HPA, ConfigMaps, Secrets, ServiceAccount
- Bitnami PostgreSQL and Redis as hybrid subchart dependencies (disableable for external services)
- Ollama as optional subchart for local LLM inference
- vLLM deployment and service templates with GPU scheduling and configurable model/args
- HuggingFace TEI (Text Embeddings Inference) parametrized templates supporting N instances (embeddings, reranker)
- HuggingFace token authentication (`secret-hf-token.yaml`) for gated model downloads
- kube-prometheus-stack and OpenTelemetry Collector as optional observability subcharts
- Auto-wiring of OTel collector endpoint when subchart is enabled (`astromesh.otel.endpoint` helper)
- External Secrets Operator integration with provider-agnostic `SecretStore` and `ExternalSecret` templates
- ArgoCD `ApplicationSet` for automated multi-environment GitOps deployment (`deploy/gitops/argocd/`)
- Custom Resource Definitions for future Kubernetes Operator (`deploy/helm/astromesh/crds/`):
  - `agents.astromesh.io` — Agent lifecycle management
  - `providers.astromesh.io` — LLM provider configuration
  - `channels.astromesh.io` — Channel integration management
  - `ragpipelines.astromesh.io` — RAG pipeline configuration
- Environment-specific values profiles: `values-dev.yaml`, `values-staging.yaml`, `values-prod.yaml`
- Comprehensive Kubernetes deployment guide (`docs/KUBERNETES_DEPLOYMENT.md`)
- Design documents for all 6 implementation phases (`docs/plans/2026-03-09-*.md`)

### Changed

- Updated `.gitignore` with Helm subchart tarball exclusion (`deploy/helm/astromesh/charts/*.tgz`)

## [0.4.0] - 2026-03-08

### Added

- Rust native extensions (`astromesh._native`) via PyO3 for CPU-bound hot paths (5-50x speedup)
- `native/src/chunking.rs` — Fixed, Recursive, Sentence chunkers with zero-copy UTF-8 slicing + cosine similarity + semantic grouping
- `native/src/guardrails.rs` — `RustPiiRedactor` with pre-compiled regex (email, phone, SSN, CC) + `RustTopicFilter` using Aho-Corasick single-pass automaton
- `native/src/tokens.rs` — `RustTokenBudget` for fast token budget selection with `split_whitespace` fallback
- `native/src/ratelimit.rs` — `RustRateLimiter` with `VecDeque` sliding window (O(1) cleanup vs O(n) in Python)
- `native/src/routing.rs` — `rust_ema_update`, `rust_detect_vision`, `rust_rank_candidates` helpers for model routing
- `native/src/cost_tracker.rs` — `RustCostIndex` with indexed cost/usage queries and `group_by` aggregation
- `native/src/json_parser.rs` — `rust_json_loads` using serde_json for fast JSON → Python object conversion
- Automatic fallback to pure Python when Rust extensions are not compiled (`try/except ImportError`)
- `ASTROMESH_FORCE_PYTHON=1` env var to disable native extensions at runtime
- Parametrized test fixture (`use_native`) for testing both native and Python backends
- Correctness tests for all native modules (`tests/test_native_*.py`)
- Benchmark suite (`tests/benchmarks/`) comparing native vs Python for chunking, guardrails, tokens, rate limiting, routing, cost tracking, and JSON parsing
- `pytest-benchmark>=4.0` dev dependency
- `[tool.maturin]` configuration in `pyproject.toml` for building native extensions
- Native extensions documentation (`docs/NATIVE_ESTENSIONS_RUST.md`)
- `LICENSE.md` — MIT license
- `SECURITY.md` — security policy and vulnerability reporting guidelines
- `CODE_OF_CONDUCT.md` — contributor code of conduct
- `CONTRIBUTING.md` — contribution guidelines
- `GOVERNANCE.md` — project governance model
- `NOTICE.md` — third-party notices
- Project logo (`assets/astromesh-logo.png`)

### Changed

- `astromesh/rag/chunking/{fixed,recursive,sentence,semantic}.py` — delegate to Rust when available
- `astromesh/core/guardrails.py` — delegate PII redaction and topic filtering to Rust when available
- `astromesh/memory/strategies/token_budget.py` — delegate to `RustTokenBudget` when available
- `astromesh/core/tools.py` — delegate rate limiting to `RustRateLimiter` when available
- `astromesh/core/model_router.py` — delegate vision detection and EMA updates to Rust when available
- `astromesh/observability/cost_tracker.py` — mirror records to `RustCostIndex` for indexed queries
- `astromesh/orchestration/patterns.py` — use `rust_json_loads` for JSON parsing in orchestration loops
- Updated `README.md` with Rust Native Extensions section
- Updated `CLAUDE.md` with `maturin develop` and `cargo test` commands
- Updated `.gitignore` with Rust build artifacts (`target/`, `*.so`, `*.pyd`, `*.dylib`)
- Updated `README.md` with project logo

## [0.3.0] - 2026-03-07

### Added

- Base channel abstraction (`ChannelAdapter`, `ChannelMessage`, `MediaAttachment`) for multi-channel support
- Multimedia message handling: images, audio, video, and documents from WhatsApp
- Media-to-LLM content builder (`build_multimodal_query`) with OpenAI vision format output
- Vision auto-detection in `ModelRouter` — automatically routes multimodal queries to vision-capable providers
- Ollama provider multimodal support — converts OpenAI image format to Ollama's native `images` field
- `WhatsAppClient.download_media()` for fetching media via Meta Graph API
- Channel base tests (`tests/test_channels.py`)

### Changed

- `WhatsAppClient` now extends `ChannelAdapter` abstract base class
- Agent pipeline (`AgentRuntime`, orchestration patterns) accepts `str | list[dict]` queries
- `ModelRouter.route()` auto-detects vision requirements from message content
- WhatsApp webhook route uses `ChannelMessage` and `build_multimodal_query` for media processing
- Memory persistence extracts text from multimodal queries for storage, keeps full content in metadata
- WhatsApp assistant agent uses `capability_match` routing with `llava:7b` as primary vision model

## [0.2.0] - 2026-03-06

### Added

- WhatsApp channel integration via Meta Business Cloud API
- WhatsApp webhook handler (GET verification + POST incoming messages)
- WhatsAppClient service with signature validation and message sending
- Channel configuration support (`config/channels.yaml`)
- Sample WhatsApp agent (`whatsapp-assistant.agent.yaml`) optimized for conversational messaging
- WhatsApp integration guide (`docs/whatsapp-integration.md`)
- Integration tests for WhatsApp webhook (20 tests)
- Design document for WhatsApp channel architecture

### Changed

- Updated architecture docs with Channel Adapters layer
- Updated configuration guide with channel configuration section
- Updated README with WhatsApp integration feature

## [0.1.0] - 2026-03-06

### Added

- Integration tests for full agent run with tools
- Docker stack and sample agent configs
- Guardrails engine, full API routes, WebSocket streaming
- Observability — OpenTelemetry tracing, Prometheus metrics, cost tracker
- ML model registry with ONNX/PyTorch serving and training pipelines
- MCP client/server and wire into ToolRegistry
- 5 orchestration patterns wired into AgentRuntime
- RAG pipeline with chunking, embeddings, vector stores, and reranking
- Memory backends (Redis, SQLite, PG, pgvector, ChromaDB, Qdrant, FAISS) and strategies
- Agent Runtime Engine with YAML config loading
- ReAct pattern and MemoryManager with 3 memory types
- ToolRegistry and PromptEngine (Jinja2)
- Phase 0 — Model Router, 6 providers, FastAPI skeleton
- ProviderProtocol, CompletionResponse, RoutingStrategy
- Project scaffolding with uv + pyproject.toml

[Unreleased]: https://github.com/monaccode/astromesh/compare/v0.14.0...HEAD
[0.14.0]: https://github.com/monaccode/astromesh/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/monaccode/astromesh/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/monaccode/astromesh/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/monaccode/astromesh/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/monaccode/astromesh-platform/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/monaccode/astromesh-platform/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/monaccode/astromesh-platform/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/monaccode/astromesh-platform/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/monaccode/astromesh-platform/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/monaccode/astromesh-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/monaccode/astromesh-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/monaccode/astromesh-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/monaccode/astromesh-platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/monaccode/astromesh-platform/releases/tag/v0.1.0
