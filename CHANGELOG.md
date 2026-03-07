# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/monaccode/astromech-platform/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/monaccode/astromech-platform/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/monaccode/astromech-platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/monaccode/astromech-platform/releases/tag/v0.1.0
