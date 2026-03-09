# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/monaccode/astromesh-platform/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/monaccode/astromesh-platform/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/monaccode/astromesh-platform/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/monaccode/astromesh-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/monaccode/astromesh-platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/monaccode/astromesh-platform/releases/tag/v0.1.0
