# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development

```bash
uv sync                              # Install base dependencies
uv sync --extra all                  # Install all optional backends
uv run uvicorn astromesh.api.main:app --reload  # Run API server (port 8000)
```

The API app runs an ASGI **lifespan** that bootstraps `AgentRuntime` and wires route modules (same idea as `astromeshd`). Use `ASTROMESH_CONFIG_DIR` to point at a config tree; set `ASTROMESH_SKIP_RUNTIME=1` to skip bootstrap (tests).

**Logging:** `astromesh.logging_config.setup_logging()` runs on API import. Default `ASTROMESH_LOG_LEVEL=DEBUG` (detailed). Quieter: `INFO` or `WARNING`. Third-party noise capped with `ASTROMESH_LOG_THIRDPARTY_LEVEL` (default `WARNING`). Disable setup: `ASTROMESH_LOG_CONFIGURE=0`. Uvicorn access/error log level is still controlled by `uvicorn --log-level`.

Python 3.12+ required. Package manager is `uv`, build system is `hatchling`.

### Rust Native Extensions (optional)

```bash
pip install maturin
maturin develop --release            # Build Rust extensions into astromesh._native
cargo test                           # Run Rust unit tests
cargo check                          # Verify Rust compiles
```

Rust extensions provide 5-50x speedup for CPU-bound paths. Without them, Python fallback is used automatically. Set `ASTROMESH_FORCE_PYTHON=1` to disable native extensions at runtime.

## Tests

```bash
uv run pytest -v                          # All tests
uv run pytest tests/test_whatsapp.py      # Single file
uv run pytest tests/test_api.py -k "test_health"  # Single test
uv run pytest --cov=astromesh             # With coverage
```

Pytest runs with `asyncio_mode = "auto"` — async test functions work without decorators. Use `respx` for mocking HTTP calls. `httpx.ASGITransport` does not run lifespan by default; shared `client` in `tests/conftest.py` wraps the app with `asgi-lifespan` so the runtime is initialized like production.

## Linting

```bash
uv run ruff check astromesh/ tests/       # Lint
uv run ruff format astromesh/ tests/      # Format
```

Line length: 100. Target: Python 3.12.

## Docker

```bash
cd docker && docker compose up -d         # Full stack (API + Ollama + Postgres + Redis + monitoring)
```

## Architecture

4-layer design where everything flows through the Agent Runtime:

```
API Layer (FastAPI REST + WebSocket)
    → Runtime Engine (AgentRuntime loads YAML → Agent instances)
        → Core Services (ModelRouter, MemoryManager, ToolRegistry, PromptEngine, GuardrailsEngine)
            → Infrastructure (Providers, Memory Backends, Orchestration Patterns, Channels, RAG, MCP)
```

**Agent execution pipeline:** Query → input guardrails → build memory context → render Jinja2 prompt → orchestration pattern (ReAct/PlanAndExecute/etc.) → model router → tool calls → output guardrails → persist memory → response.

### Key abstractions

- **ProviderProtocol** (`astromesh/providers/base.py`): Runtime-checkable Protocol that all LLM providers implement. Methods: `complete()`, `stream()`, `health_check()`, `supports_tools()`, `estimated_cost()`.
- **AgentRuntime** (`astromesh/runtime/engine.py`): Bootstraps agents from `config/agents/*.agent.yaml`, wires up all services. Call `runtime.run(agent_name, query, session_id)`.
- **ModelRouter** (`astromesh/core/model_router.py`): Routes to providers using strategies (cost_optimized, latency_optimized, quality_first, round_robin). Has circuit breaker (3 failures → 60s cooldown).
- **ToolRegistry** (`astromesh/core/tools.py`): Registers tools as internal (Python), MCP, webhook, or RAG. Handles permissions, rate limiting, and schema generation for LLM function calling.
- **OrchestrationPattern** (`astromesh/orchestration/patterns.py`): Abstract base for ReAct, PlanAndExecute, ParallelFanOut, Pipeline, Supervisor, Swarm.
- **MemoryManager** (`astromesh/core/memory.py`): Manages 3 memory types — conversational (chat history), semantic (vector embeddings), episodic (event logs). Strategies: sliding_window, summary, token_budget.

### Agent YAML schema

Agents are defined in `config/agents/*.agent.yaml` with schema `apiVersion: astromesh/v1, kind: Agent`. Spec sections: `identity`, `model` (primary + fallback + routing), `prompts` (Jinja2 system prompt), `orchestration` (pattern + iterations + timeout), `tools`, `memory`, `guardrails`, `permissions`.

### API routes

Routes inject runtime via `set_runtime()` called during bootstrap. Pattern: each route module exposes a `router` (APIRouter) and a `set_runtime(runtime)` function.

- `/v1/agents/{name}/run` — Execute agent (POST)
- `/v1/ws/agent/{name}` — WebSocket streaming
- `/v1/channels/whatsapp/webhook` — WhatsApp webhook (GET verify + POST messages)
- `/v1/memory/`, `/v1/tools/`, `/v1/rag/` — Supporting endpoints

### Channels

Channel adapters live in `astromesh/channels/`. Config in `config/channels.yaml` with env var references (`${VAR_NAME}`). WhatsApp uses background tasks for agent execution to respond to Meta within 5s.

## Conventions

- Conventional commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:`
- Versioning: semver with `v` prefix tags (v0.1.0, v0.2.0)
- Main branch: `develop`
- All async: providers, tools, memory backends, and route handlers are async
- Config from env vars for secrets, YAML files for structure

## Changelog Rule

**MANDATORY:** Before creating any commit with type `feat:`, `fix:`, or `refactor:`, you MUST update `CHANGELOG.md` first using the `/changelog-automation` skill. Add the change under the `## [Unreleased]` section in the appropriate subsection (Added, Changed, Fixed). If the `[Unreleased]` section doesn't exist, create it below the header. Follow the [Keep a Changelog](https://keepachangelog.com/) format. Group entries under `### Added (Backend)`, `### Added (Astromesh Forge)`, `### Changed`, `### Fixed`, etc. as appropriate. Never commit a `feat`/`fix`/`refactor` change without its changelog entry in the same commit or an immediately preceding commit.

## Release Checklist

When creating a release, bump ALL version files in sync:
- `pyproject.toml` → `version`
- `astromesh/__init__.py` → `__version__`
- `astromesh-forge/package.json` → `version`
