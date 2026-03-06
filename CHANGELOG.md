# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
