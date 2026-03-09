# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/monaccode/astromesh-platform/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/monaccode/astromesh-platform/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/monaccode/astromesh-platform/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/monaccode/astromesh-platform/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/monaccode/astromesh-platform/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/monaccode/astromesh-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/monaccode/astromesh-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/monaccode/astromesh-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/monaccode/astromesh-platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/monaccode/astromesh-platform/releases/tag/v0.1.0
