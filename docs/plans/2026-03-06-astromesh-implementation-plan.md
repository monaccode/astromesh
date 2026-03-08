# Astromesh Agent Runtime — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Astromesh Agent Runtime Platform — a multi-model, multi-pattern AI agent runtime with declarative YAML config, pluggable memory, MCP/tool extensibility, RAG pipelines, ML model registry, and full observability.

**Architecture:** Literal implementation of the NEXUS Agent Runtime Spec v1.0, renamed to Astromesh. Four-layer architecture: Agent Layer (YAML configs → Lifecycle Manager), Core Services (Model Router, Memory Manager, Tool Registry), Provider/Storage/Extension Layer, and Infrastructure Layer. All modules are decoupled, configurable, and async.

**Tech Stack:** Python 3.12+, uv, FastAPI, httpx, Pydantic, PyYAML, Jinja2, redis (aioredis), asyncpg, SQLite (aiosqlite), chromadb, qdrant-client, faiss-cpu, sentence-transformers, onnxruntime, opentelemetry, prometheus-client, Docker.

---

## Phase 0: Foundation

### Task 1: Project scaffolding — pyproject.toml + uv

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `CLAUDE.md`
- Create: `astromesh/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "astromesh"
version = "0.1.0"
description = "Astromesh Agent Runtime Platform — multi-model, multi-pattern AI agent runtime"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
    "pydantic>=2.9.0",
    "pyyaml>=6.0",
    "jinja2>=3.1.0",
]

[project.optional-dependencies]
redis = ["redis[hiredis]>=5.0.0"]
postgres = ["asyncpg>=0.30.0"]
sqlite = ["aiosqlite>=0.20.0"]
chromadb = ["chromadb>=0.5.0"]
qdrant = ["qdrant-client>=1.11.0"]
faiss = ["faiss-cpu>=1.8.0"]
embeddings = ["sentence-transformers>=3.0.0"]
onnx = ["onnxruntime>=1.19.0"]
ml = ["torch>=2.0.0"]
observability = [
    "opentelemetry-api>=1.27.0",
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-exporter-otlp>=1.27.0",
    "prometheus-client>=0.21.0",
]
mcp = ["mcp>=1.0.0"]
all = [
    "astromesh[redis,postgres,sqlite,chromadb,qdrant,faiss,embeddings,onnx,observability,mcp]",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0",
    "respx>=0.21.0",
    "ruff>=0.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

**Step 2: Create .gitignore**

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
env/
.env
*.db
*.sqlite3
models/*.pt
models/*.onnx
models/*.bin
.mypy_cache/
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
*.log
.uv/
uv.lock
```

**Step 3: Create CLAUDE.md**

```markdown
# Astromesh Agent Runtime Platform

## Project
Multi-model, multi-pattern AI agent runtime with declarative YAML configuration.

## Tech Stack
- Python 3.12+, uv for package management
- FastAPI for API layer
- httpx for async HTTP
- Pydantic for validation
- PyYAML + Jinja2 for config

## Commands
- Install: `uv sync --all-extras`
- Test: `uv run pytest -v`
- Lint: `uv run ruff check .`
- Run: `uv run uvicorn astromesh.api.main:app --reload`

## Conventions
- All IO is async (async/await)
- Protocols (typing.Protocol) for interfaces, not ABC where possible
- Dataclasses for data, Pydantic for API models
- Imports: stdlib → third-party → local (ruff handles this)
- All references to "nexus" should be "astromesh"
- Config apiVersion: astromesh/v1
```

**Step 4: Create astromesh/__init__.py**

```python
"""Astromesh Agent Runtime Platform."""

__version__ = "0.1.0"
```

**Step 5: Initialize uv project and install deps**

Run: `cd D:/monaccode/astromesh-platform && uv sync --all-extras --dev`
Expected: Dependencies installed, `.venv` created

**Step 6: Commit**

```bash
git add pyproject.toml .gitignore CLAUDE.md astromesh/__init__.py
git commit -m "feat: project scaffolding with uv + pyproject.toml"
```

---

### Task 2: Data models — CompletionResponse + ProviderProtocol

**Files:**
- Create: `astromesh/core/__init__.py`
- Create: `astromesh/providers/__init__.py`
- Create: `astromesh/providers/base.py`
- Create: `tests/__init__.py`
- Create: `tests/test_model_router.py`

**Step 1: Write the failing test**

```python
# tests/test_model_router.py
import pytest
from astromesh.providers.base import (
    CompletionResponse,
    ProviderHealth,
    RoutingStrategy,
)


def test_completion_response_defaults():
    resp = CompletionResponse(
        content="Hello",
        model="llama3",
        provider="ollama",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        latency_ms=100.0,
        cost=0.001,
    )
    assert resp.content == "Hello"
    assert resp.tool_calls == []
    assert resp.metadata == {}


def test_provider_health_defaults():
    h = ProviderHealth()
    assert h.is_healthy is True
    assert h.consecutive_failures == 0
    assert h.circuit_open is False


def test_routing_strategy_values():
    assert RoutingStrategy.COST_OPTIMIZED == "cost_optimized"
    assert RoutingStrategy.LATENCY_OPTIMIZED == "latency_optimized"
    assert RoutingStrategy.QUALITY_FIRST == "quality_first"
    assert RoutingStrategy.ROUND_ROBIN == "round_robin"
    assert RoutingStrategy.CAPABILITY_MATCH == "capability_match"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model_router.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write the implementation**

```python
# astromesh/providers/base.py
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Protocol


class RoutingStrategy(str, Enum):
    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_FIRST = "quality_first"
    ROUND_ROBIN = "round_robin"
    CAPABILITY_MATCH = "capability_match"


@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    usage: dict  # {input_tokens, output_tokens, total_tokens}
    latency_ms: float
    cost: float
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class CompletionChunk:
    content: str
    model: str
    provider: str
    done: bool = False
    usage: dict | None = None


@dataclass
class ProviderHealth:
    is_healthy: bool = True
    last_check: float = 0.0
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    circuit_open: bool = False
    circuit_open_until: float = 0.0


class ProviderProtocol(Protocol):
    """Contract every provider must implement."""

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse: ...

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[CompletionChunk]: ...

    async def health_check(self) -> bool: ...

    def supports_tools(self) -> bool: ...

    def supports_vision(self) -> bool: ...

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float: ...
```

Also create the `__init__.py` files:

```python
# astromesh/core/__init__.py
# astromesh/providers/__init__.py
# tests/__init__.py
```

(all empty)

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model_router.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add astromesh/core/ astromesh/providers/ tests/
git commit -m "feat: add ProviderProtocol, CompletionResponse, RoutingStrategy"
```

---

### Task 3: Model Router — core routing engine

**Files:**
- Create: `astromesh/core/model_router.py`
- Modify: `tests/test_model_router.py` (add router tests)

**Step 1: Write the failing tests**

Append to `tests/test_model_router.py`:

```python
from unittest.mock import AsyncMock
from astromesh.core.model_router import ModelRouter


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        content="test response",
        model="test-model",
        provider="test",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        latency_ms=0,
        cost=0.001,
    )
    provider.health_check.return_value = True
    provider.supports_tools.return_value = True
    provider.supports_vision.return_value = False
    provider.estimated_cost.return_value = 0.001
    return provider


@pytest.fixture
def router():
    return ModelRouter({"strategy": "cost_optimized"})


async def test_router_registers_provider(router, mock_provider):
    router.register_provider("test", mock_provider)
    assert "test" in router._providers


async def test_router_routes_to_provider(router, mock_provider):
    router.register_provider("test", mock_provider)
    result = await router.route([{"role": "user", "content": "hello"}])
    assert result.content == "test response"
    assert result.latency_ms > 0


async def test_router_fallback_on_failure(router, mock_provider):
    failing = AsyncMock()
    failing.complete.side_effect = RuntimeError("provider down")
    failing.estimated_cost.return_value = 0.0001

    router.register_provider("failing", failing)
    router.register_provider("backup", mock_provider)

    mock_provider.estimated_cost.return_value = 0.01

    result = await router.route([{"role": "user", "content": "hello"}])
    assert result.content == "test response"


async def test_router_circuit_breaker(router):
    failing = AsyncMock()
    failing.complete.side_effect = RuntimeError("down")
    failing.estimated_cost.return_value = 0.001
    router.register_provider("bad", failing)

    for _ in range(3):
        try:
            await router.route([{"role": "user", "content": "hi"}])
        except RuntimeError:
            pass

    assert router._health["bad"].circuit_open is True


async def test_router_all_exhausted_raises(router):
    failing = AsyncMock()
    failing.complete.side_effect = RuntimeError("down")
    failing.estimated_cost.return_value = 0.001
    router.register_provider("only", failing)

    with pytest.raises(RuntimeError, match="All providers exhausted"):
        # Need 3 failures to trip circuit + 1 more to see it closed
        for _ in range(5):
            await router.route([{"role": "user", "content": "hi"}])
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model_router.py -v -k "router"`
Expected: FAIL — ImportError

**Step 3: Write the implementation**

```python
# astromesh/core/model_router.py
import time

from astromesh.providers.base import (
    CompletionResponse,
    ProviderHealth,
    ProviderProtocol,
    RoutingStrategy,
)


class ModelRouter:
    """Routes requests to the optimal provider based on strategy, health checks, and circuit breakers."""

    def __init__(self, config: dict):
        self._providers: dict[str, ProviderProtocol] = {}
        self._health: dict[str, ProviderHealth] = {}
        self._strategy = RoutingStrategy(config.get("strategy", "cost_optimized"))
        self._config = config
        self._request_count = 0

    def register_provider(self, name: str, provider: ProviderProtocol):
        self._providers[name] = provider
        self._health[name] = ProviderHealth()

    async def route(
        self,
        messages: list[dict],
        requirements: dict | None = None,
        **kwargs,
    ) -> CompletionResponse:
        candidates = self._rank_candidates(requirements or {})
        if not candidates:
            raise RuntimeError("No providers available")

        last_error = None
        for candidate_name in candidates:
            provider = self._providers[candidate_name]
            health = self._health[candidate_name]

            if health.circuit_open and time.time() < health.circuit_open_until:
                continue

            try:
                start = time.monotonic()
                response = await provider.complete(messages, **kwargs)
                latency = (time.monotonic() - start) * 1000

                health.is_healthy = True
                health.consecutive_failures = 0
                health.avg_latency_ms = (health.avg_latency_ms * 0.8) + (latency * 0.2)
                health.circuit_open = False

                response.latency_ms = latency
                return response

            except Exception as e:
                last_error = e
                health.consecutive_failures += 1

                if health.consecutive_failures >= 3:
                    health.circuit_open = True
                    health.circuit_open_until = time.time() + 60
                    health.is_healthy = False

        raise RuntimeError(f"All providers exhausted. Last error: {last_error}")

    def _rank_candidates(self, requirements: dict) -> list[str]:
        available = [
            name
            for name, h in self._health.items()
            if not (h.circuit_open and time.time() < h.circuit_open_until)
        ]

        if not available:
            return list(self._health.keys())

        if self._strategy == RoutingStrategy.COST_OPTIMIZED:
            return sorted(available, key=lambda n: self._providers[n].estimated_cost(500, 500))

        elif self._strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            return sorted(available, key=lambda n: self._health[n].avg_latency_ms)

        elif self._strategy == RoutingStrategy.ROUND_ROBIN:
            self._request_count += 1
            idx = self._request_count % len(available)
            return available[idx:] + available[:idx]

        elif self._strategy == RoutingStrategy.CAPABILITY_MATCH:
            needs_tools = requirements.get("tools", False)
            needs_vision = requirements.get("vision", False)
            scored = []
            for name in available:
                p = self._providers[name]
                if needs_tools and not p.supports_tools():
                    continue
                if needs_vision and not p.supports_vision():
                    continue
                scored.append(name)
            return scored or available

        return available
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_model_router.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add astromesh/core/model_router.py tests/test_model_router.py
git commit -m "feat: add ModelRouter with strategy-based routing and circuit breaker"
```

---

### Task 4: Ollama Provider adapter

**Files:**
- Create: `astromesh/providers/ollama_provider.py`
- Create: `tests/test_providers.py`

**Step 1: Write the failing test**

```python
# tests/test_providers.py
import pytest
import httpx
import respx
from astromesh.providers.ollama_provider import OllamaProvider


@pytest.fixture
def ollama_config():
    return {
        "endpoint": "http://ollama:11434",
        "model": "llama3.1:8b",
        "parameters": {"temperature": 0.7},
    }


@respx.mock
async def test_ollama_complete(ollama_config):
    respx.post("http://ollama:11434/api/chat").mock(
        return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": "Hello!"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        })
    )
    provider = OllamaProvider(ollama_config)
    result = await provider.complete([{"role": "user", "content": "hi"}])
    assert result.content == "Hello!"
    assert result.provider == "ollama"
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 5


@respx.mock
async def test_ollama_health_check_healthy(ollama_config):
    respx.get("http://ollama:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    provider = OllamaProvider(ollama_config)
    assert await provider.health_check() is True


@respx.mock
async def test_ollama_health_check_unhealthy(ollama_config):
    respx.get("http://ollama:11434/api/tags").mock(side_effect=httpx.ConnectError("down"))
    provider = OllamaProvider(ollama_config)
    assert await provider.health_check() is False


def test_ollama_supports_tools(ollama_config):
    provider = OllamaProvider(ollama_config)
    assert provider.supports_tools() is True


def test_ollama_supports_vision(ollama_config):
    provider = OllamaProvider(ollama_config)
    assert provider.supports_vision() is False

    vision_config = {**ollama_config, "model": "llava:7b"}
    vision_provider = OllamaProvider(vision_config)
    assert vision_provider.supports_vision() is True


def test_ollama_estimated_cost(ollama_config):
    provider = OllamaProvider(ollama_config)
    cost = provider.estimated_cost(1000, 500)
    assert cost > 0
    assert isinstance(cost, float)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_providers.py -v`
Expected: FAIL — ImportError

**Step 3: Write the implementation**

```python
# astromesh/providers/ollama_provider.py
import httpx

from astromesh.providers.base import CompletionChunk, CompletionResponse


class OllamaProvider:
    """Adapter for Ollama (local models)."""

    def __init__(self, config: dict):
        self._endpoint = config["endpoint"]
        self._model = config["model"]
        self._params = config.get("parameters", {})
        self._client = httpx.AsyncClient(timeout=120.0)
        self._cost_per_1k_tokens = config.get("cost_per_1k_tokens", 0.0001)

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            **self._params,
        }

        if "tools" in kwargs:
            payload["tools"] = self._convert_tools(kwargs["tools"])

        resp = await self._client.post(f"{self._endpoint}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        usage = {
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        }

        return CompletionResponse(
            content=data["message"]["content"],
            model=self._model,
            provider="ollama",
            usage=usage,
            latency_ms=0,
            cost=usage["total_tokens"] / 1000 * self._cost_per_1k_tokens,
            tool_calls=data["message"].get("tool_calls", []),
        )

    async def stream(self, messages: list[dict], **kwargs):
        import json as json_mod

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            **self._params,
        }
        async with self._client.stream(
            "POST", f"{self._endpoint}/api/chat", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    chunk = json_mod.loads(line)
                    yield CompletionChunk(
                        content=chunk.get("message", {}).get("content", ""),
                        model=self._model,
                        provider="ollama",
                        done=chunk.get("done", False),
                    )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._endpoint}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return "llava" in self._model or "vision" in self._model

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) / 1000 * self._cost_per_1k_tokens

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters", {}),
                },
            }
            for t in tools
        ]
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_providers.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add astromesh/providers/ollama_provider.py tests/test_providers.py
git commit -m "feat: add Ollama provider adapter"
```

---

### Task 5: OpenAI-compatible Provider adapter

**Files:**
- Create: `astromesh/providers/openai_compat.py`
- Modify: `tests/test_providers.py` (add OpenAI compat tests)

**Step 1: Write the failing test**

Append to `tests/test_providers.py`:

```python
from astromesh.providers.openai_compat import OpenAICompatProvider


@pytest.fixture
def openai_config():
    return {
        "endpoint": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key": "test-key",
        "parameters": {"temperature": 0.5},
    }


@respx.mock
async def test_openai_compat_complete(openai_config):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Hi there!"}}],
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
        })
    )
    provider = OpenAICompatProvider(openai_config)
    result = await provider.complete([{"role": "user", "content": "hello"}])
    assert result.content == "Hi there!"
    assert result.provider == "openai_compat"
    assert result.usage["total_tokens"] == 11


def test_openai_compat_supports_tools(openai_config):
    provider = OpenAICompatProvider(openai_config)
    assert provider.supports_tools() is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_providers.py -v -k "openai"`
Expected: FAIL — ImportError

**Step 3: Write the implementation**

```python
# astromesh/providers/openai_compat.py
import os

import httpx

from astromesh.providers.base import CompletionChunk, CompletionResponse


class OpenAICompatProvider:
    """Adapter for any OpenAI-compatible API (OpenAI, Azure, Groq, etc.)."""

    # Pricing per 1K tokens for known models (input, output)
    PRICING = {
        "gpt-4o": (0.0025, 0.01),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4-turbo": (0.01, 0.03),
    }

    def __init__(self, config: dict):
        self._endpoint = config["endpoint"].rstrip("/")
        self._model = config["model"]
        self._params = config.get("parameters", {})
        api_key = config.get("api_key") or os.environ.get(
            config.get("api_key_env", "OPENAI_API_KEY"), ""
        )
        self._client = httpx.AsyncClient(
            timeout=120.0,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._cost_per_1k_input, self._cost_per_1k_output = self.PRICING.get(
            self._model, (0.001, 0.002)
        )

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        payload = {
            "model": self._model,
            "messages": messages,
            **self._params,
        }
        if "tools" in kwargs:
            payload["tools"] = kwargs["tools"]

        resp = await self._client.post(
            f"{self._endpoint}/chat/completions", json=payload
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        usage_data = data.get("usage", {})

        usage = {
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        cost = (
            usage["input_tokens"] / 1000 * self._cost_per_1k_input
            + usage["output_tokens"] / 1000 * self._cost_per_1k_output
        )

        return CompletionResponse(
            content=message.get("content", ""),
            model=data.get("model", self._model),
            provider="openai_compat",
            usage=usage,
            latency_ms=0,
            cost=cost,
            tool_calls=message.get("tool_calls", []),
        )

    async def stream(self, messages: list[dict], **kwargs):
        import json as json_mod

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            **self._params,
        }
        async with self._client.stream(
            "POST", f"{self._endpoint}/chat/completions", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json_mod.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    yield CompletionChunk(
                        content=delta.get("content", ""),
                        model=self._model,
                        provider="openai_compat",
                        done=chunk["choices"][0].get("finish_reason") is not None,
                    )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._endpoint}/models")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return "vision" in self._model or "gpt-4o" in self._model

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1000 * self._cost_per_1k_input
            + output_tokens / 1000 * self._cost_per_1k_output
        )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_providers.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add astromesh/providers/openai_compat.py tests/test_providers.py
git commit -m "feat: add OpenAI-compatible provider adapter"
```

---

### Task 6: vLLM Provider adapter

**Files:**
- Create: `astromesh/providers/vllm_provider.py`
- Modify: `tests/test_providers.py`

**Step 1: Write the failing test**

Append to `tests/test_providers.py`:

```python
from astromesh.providers.vllm_provider import VLLMProvider


@pytest.fixture
def vllm_config():
    return {
        "endpoint": "http://vllm:8000",
        "model": "mistral-7b-instruct",
        "parameters": {"temperature": 0.3},
    }


@respx.mock
async def test_vllm_complete(vllm_config):
    respx.post("http://vllm:8000/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "vLLM response"}}],
            "model": "mistral-7b-instruct",
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        })
    )
    provider = VLLMProvider(vllm_config)
    result = await provider.complete([{"role": "user", "content": "test"}])
    assert result.content == "vLLM response"
    assert result.provider == "vllm"
```

**Step 2: Run test → FAIL. Step 3: Implement**

```python
# astromesh/providers/vllm_provider.py
import httpx

from astromesh.providers.base import CompletionChunk, CompletionResponse


class VLLMProvider:
    """Adapter for vLLM (OpenAI-compatible API, GPU-optimized)."""

    def __init__(self, config: dict):
        self._endpoint = config["endpoint"].rstrip("/")
        self._model = config["model"]
        self._params = config.get("parameters", {})
        self._client = httpx.AsyncClient(timeout=120.0)
        self._cost_per_1k_tokens = config.get("cost_per_1k_tokens", 0.0001)

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        payload = {"model": self._model, "messages": messages, **self._params}
        if "tools" in kwargs:
            payload["tools"] = kwargs["tools"]

        resp = await self._client.post(f"{self._endpoint}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        usage_data = data.get("usage", {})
        usage = {
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        return CompletionResponse(
            content=choice["message"].get("content", ""),
            model=data.get("model", self._model),
            provider="vllm",
            usage=usage,
            latency_ms=0,
            cost=usage["total_tokens"] / 1000 * self._cost_per_1k_tokens,
            tool_calls=choice["message"].get("tool_calls", []),
        )

    async def stream(self, messages: list[dict], **kwargs):
        import json as json_mod

        payload = {"model": self._model, "messages": messages, "stream": True, **self._params}
        async with self._client.stream(
            "POST", f"{self._endpoint}/v1/chat/completions", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json_mod.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    yield CompletionChunk(
                        content=delta.get("content", ""),
                        model=self._model,
                        provider="vllm",
                        done=chunk["choices"][0].get("finish_reason") is not None,
                    )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._endpoint}/v1/models")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) / 1000 * self._cost_per_1k_tokens
```

**Step 4: Run tests, Step 5: Commit**

```bash
git add astromesh/providers/vllm_provider.py tests/test_providers.py
git commit -m "feat: add vLLM provider adapter"
```

---

### Task 7: llama.cpp, HF TGI, and ONNX Provider adapters

**Files:**
- Create: `astromesh/providers/llamacpp_provider.py`
- Create: `astromesh/providers/hf_tgi_provider.py`
- Create: `astromesh/providers/onnx_provider.py`
- Modify: `tests/test_providers.py`

**Step 1: Write failing tests for all three**

Append to `tests/test_providers.py`:

```python
from astromesh.providers.llamacpp_provider import LlamaCppProvider
from astromesh.providers.hf_tgi_provider import HFTGIProvider
from astromesh.providers.onnx_provider import ONNXProvider


@respx.mock
async def test_llamacpp_complete():
    respx.post("http://llamacpp:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "llama.cpp!"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        })
    )
    provider = LlamaCppProvider({"endpoint": "http://llamacpp:8080", "model": "local"})
    result = await provider.complete([{"role": "user", "content": "hi"}])
    assert result.content == "llama.cpp!"
    assert result.provider == "llamacpp"


@respx.mock
async def test_hf_tgi_complete():
    respx.post("http://tgi:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "TGI response"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        })
    )
    provider = HFTGIProvider({"endpoint": "http://tgi:8080", "model": "mistral"})
    result = await provider.complete([{"role": "user", "content": "test"}])
    assert result.content == "TGI response"
    assert result.provider == "hf_tgi"


def test_onnx_provider_init():
    provider = ONNXProvider({"model_path": "/models/test", "model": "custom-cls"})
    assert provider.supports_tools() is False
    assert provider.supports_vision() is False
```

**Step 2: Run tests → FAIL. Step 3: Implement all three.**

```python
# astromesh/providers/llamacpp_provider.py
import httpx
from astromesh.providers.base import CompletionChunk, CompletionResponse


class LlamaCppProvider:
    """Adapter for llama.cpp server (OpenAI-compatible API)."""

    def __init__(self, config: dict):
        self._endpoint = config["endpoint"].rstrip("/")
        self._model = config.get("model", "local")
        self._params = config.get("parameters", {})
        self._client = httpx.AsyncClient(timeout=120.0)
        self._cost_per_1k_tokens = config.get("cost_per_1k_tokens", 0.00005)

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        payload = {"model": self._model, "messages": messages, **self._params}
        resp = await self._client.post(f"{self._endpoint}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        usage_data = data.get("usage", {})
        usage = {
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }
        return CompletionResponse(
            content=choice["message"].get("content", ""),
            model=self._model,
            provider="llamacpp",
            usage=usage,
            latency_ms=0,
            cost=usage["total_tokens"] / 1000 * self._cost_per_1k_tokens,
            tool_calls=choice["message"].get("tool_calls", []),
        )

    async def stream(self, messages: list[dict], **kwargs):
        import json as json_mod
        payload = {"model": self._model, "messages": messages, "stream": True, **self._params}
        async with self._client.stream(
            "POST", f"{self._endpoint}/v1/chat/completions", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json_mod.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    yield CompletionChunk(
                        content=delta.get("content", ""),
                        model=self._model,
                        provider="llamacpp",
                        done=chunk["choices"][0].get("finish_reason") is not None,
                    )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._endpoint}/health")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) / 1000 * self._cost_per_1k_tokens
```

```python
# astromesh/providers/hf_tgi_provider.py
import httpx
from astromesh.providers.base import CompletionChunk, CompletionResponse


class HFTGIProvider:
    """Adapter for HuggingFace Text Generation Inference."""

    def __init__(self, config: dict):
        self._endpoint = config["endpoint"].rstrip("/")
        self._model = config.get("model", "")
        self._params = config.get("parameters", {})
        self._client = httpx.AsyncClient(timeout=120.0)
        self._cost_per_1k_tokens = config.get("cost_per_1k_tokens", 0.0001)

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        payload = {"model": self._model, "messages": messages, **self._params}
        resp = await self._client.post(f"{self._endpoint}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        usage_data = data.get("usage", {})
        usage = {
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }
        return CompletionResponse(
            content=choice["message"].get("content", ""),
            model=self._model,
            provider="hf_tgi",
            usage=usage,
            latency_ms=0,
            cost=usage["total_tokens"] / 1000 * self._cost_per_1k_tokens,
            tool_calls=choice["message"].get("tool_calls", []),
        )

    async def stream(self, messages: list[dict], **kwargs):
        import json as json_mod
        payload = {"model": self._model, "messages": messages, "stream": True, **self._params}
        async with self._client.stream(
            "POST", f"{self._endpoint}/v1/chat/completions", json=payload
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json_mod.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    yield CompletionChunk(
                        content=delta.get("content", ""),
                        model=self._model,
                        provider="hf_tgi",
                        done=chunk["choices"][0].get("finish_reason") is not None,
                    )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._endpoint}/health")
            return resp.status_code == 200
        except Exception:
            return False

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) / 1000 * self._cost_per_1k_tokens
```

```python
# astromesh/providers/onnx_provider.py
from astromesh.providers.base import CompletionResponse


class ONNXProvider:
    """Adapter for ONNX Runtime custom models (classifiers, embedders, etc.)."""

    def __init__(self, config: dict):
        self._model_path = config.get("model_path", "")
        self._model = config.get("model", "custom")
        self._device = config.get("device", "cpu")
        self._session = None

    async def complete(self, messages: list[dict], **kwargs) -> CompletionResponse:
        if self._session is None:
            self._load_model()

        text = messages[-1].get("content", "") if messages else ""
        result = self._session.run(None, {"input": [text]})

        return CompletionResponse(
            content=str(result),
            model=self._model,
            provider="onnx",
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            latency_ms=0,
            cost=0.0,
        )

    async def stream(self, messages: list[dict], **kwargs):
        result = await self.complete(messages, **kwargs)
        from astromesh.providers.base import CompletionChunk
        yield CompletionChunk(content=result.content, model=self._model, provider="onnx", done=True)

    async def health_check(self) -> bool:
        return self._session is not None or self._model_path != ""

    def supports_tools(self) -> bool:
        return False

    def supports_vision(self) -> bool:
        return False

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0

    def _load_model(self):
        try:
            import onnxruntime as ort
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self._device == "cuda" else ["CPUExecutionProvider"]
            self._session = ort.InferenceSession(f"{self._model_path}/model.onnx", providers=providers)
        except ImportError:
            raise RuntimeError("onnxruntime not installed. Install with: pip install onnxruntime")
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/providers/ tests/test_providers.py
git commit -m "feat: add llama.cpp, HF TGI, and ONNX provider adapters"
```

---

### Task 8: FastAPI skeleton with health endpoint

**Files:**
- Create: `astromesh/api/__init__.py`
- Create: `astromesh/api/main.py`
- Create: `astromesh/api/routes/__init__.py`
- Create: `astromesh/api/routes/agents.py`
- Create: `tests/test_api.py`

**Step 1: Write the failing test**

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from astromesh.api.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_list_agents_empty(client):
    resp = await client.get("/v1/agents")
    assert resp.status_code == 200
    assert resp.json()["agents"] == []
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/api/main.py
from fastapi import FastAPI

from astromesh import __version__
from astromesh.api.routes import agents

app = FastAPI(title="Astromesh Agent Runtime API", version=__version__)

app.include_router(agents.router, prefix="/v1")


@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": __version__}
```

```python
# astromesh/api/routes/agents.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/agents")
async def list_agents():
    return {"agents": []}
```

```python
# astromesh/api/__init__.py
# astromesh/api/routes/__init__.py
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/api/ tests/test_api.py
git commit -m "feat: add FastAPI skeleton with health and agents list endpoints"
```

---

## Phase 1: Core Agent

### Task 9: Tool Registry

**Files:**
- Create: `astromesh/core/tools.py`
- Create: `tests/test_tools.py`

**Step 1: Write the failing test**

```python
# tests/test_tools.py
import pytest
from astromesh.core.tools import ToolDefinition, ToolRegistry, ToolType


@pytest.fixture
def registry():
    return ToolRegistry()


def test_register_internal_tool(registry):
    async def my_handler(**kwargs):
        return {"result": kwargs.get("x", 0) * 2}

    registry.register_internal(
        name="double",
        handler=my_handler,
        description="Doubles a number",
        parameters={"x": {"type": "number"}},
    )
    assert "double" in registry._tools


async def test_execute_internal_tool(registry):
    async def my_handler(**kwargs):
        return {"result": kwargs["x"] * 2}

    registry.register_internal(
        name="double",
        handler=my_handler,
        description="Doubles a number",
        parameters={"x": {"type": "number"}},
    )
    result = await registry.execute("double", {"x": 5})
    assert result == {"result": 10}


async def test_execute_missing_tool(registry):
    result = await registry.execute("nonexistent", {})
    assert "error" in result


def test_get_tool_schemas(registry):
    async def noop(**kwargs):
        return {}

    registry.register_internal("t1", noop, "Tool 1", {"a": {"type": "string"}})
    registry.register_internal("t2", noop, "Tool 2", {"b": {"type": "number"}})

    schemas = registry.get_tool_schemas()
    assert len(schemas) == 2
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "t1"


def test_get_tool_schemas_filtered(registry):
    async def noop(**kwargs):
        return {}

    registry.register(ToolDefinition(
        name="admin_tool", description="Admin", tool_type=ToolType.INTERNAL,
        parameters={}, handler=noop, permissions=["admin"],
    ))
    registry.register(ToolDefinition(
        name="user_tool", description="User", tool_type=ToolType.INTERNAL,
        parameters={}, handler=noop, permissions=["user"],
    ))

    schemas = registry.get_tool_schemas(agent_permissions=["user"])
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "user_tool"
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/core/tools.py
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ToolType(str, Enum):
    INTERNAL = "internal"
    MCP_STDIO = "mcp_stdio"
    MCP_SSE = "mcp_sse"
    MCP_HTTP = "mcp_http"
    WEBHOOK = "webhook"
    RAG = "rag"


@dataclass
class ToolDefinition:
    name: str
    description: str
    tool_type: ToolType
    parameters: dict
    handler: Callable | None = None
    mcp_config: dict = field(default_factory=dict)
    requires_approval: bool = False
    timeout_seconds: int = 30
    rate_limit: dict | None = None
    permissions: list[str] = field(default_factory=list)


class ToolRegistry:
    """Central registry for tools — internal, MCP, webhooks, RAG."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._mcp_clients: dict[str, Any] = {}
        self._call_counts: dict[str, list[float]] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def register_internal(
        self,
        name: str,
        handler: Callable,
        description: str,
        parameters: dict,
        **kwargs,
    ):
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            tool_type=ToolType.INTERNAL,
            parameters=parameters,
            handler=handler,
            **kwargs,
        )

    async def execute(
        self, tool_name: str, arguments: dict, context: dict | None = None
    ) -> dict:
        tool = self._tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}

        if tool.rate_limit and not self._check_rate_limit(tool_name, tool.rate_limit):
            return {"error": f"Rate limit exceeded for '{tool_name}'"}

        if tool.tool_type == ToolType.INTERNAL and tool.handler:
            return await tool.handler(**arguments)

        elif tool.tool_type.value.startswith("mcp_"):
            server_name = tool.mcp_config["server"]
            client = self._mcp_clients.get(server_name)
            if not client:
                return {"error": f"MCP server '{server_name}' not connected"}
            result = await client.call_tool(tool.mcp_config["tool_name"], arguments)
            return result

        return {"error": f"Unsupported tool type: {tool.tool_type}"}

    def get_tool_schemas(self, agent_permissions: list[str] | None = None) -> list[dict]:
        schemas = []
        for name, tool in self._tools.items():
            if agent_permissions and tool.permissions:
                if not any(p in agent_permissions for p in tool.permissions):
                    continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    def _check_rate_limit(self, tool_name: str, rate_limit: dict) -> bool:
        now = time.time()
        window = rate_limit.get("window_seconds", 60)
        max_calls = rate_limit.get("max_calls", 10)

        if tool_name not in self._call_counts:
            self._call_counts[tool_name] = []

        self._call_counts[tool_name] = [
            t for t in self._call_counts[tool_name] if now - t < window
        ]

        if len(self._call_counts[tool_name]) >= max_calls:
            return False

        self._call_counts[tool_name].append(now)
        return True
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/core/tools.py tests/test_tools.py
git commit -m "feat: add ToolRegistry with internal tools, permissions, rate limiting"
```

---

### Task 10: Prompt Engine (Jinja2 templating)

**Files:**
- Create: `astromesh/core/prompt_engine.py`
- Create: `tests/test_prompt_engine.py`

**Step 1: Write the failing test**

```python
# tests/test_prompt_engine.py
from astromesh.core.prompt_engine import PromptEngine


def test_render_simple_template():
    engine = PromptEngine()
    result = engine.render("Hello {{ name }}!", {"name": "Astromesh"})
    assert result == "Hello Astromesh!"


def test_render_with_missing_var():
    engine = PromptEngine()
    result = engine.render("Hello {{ name }}!", {})
    assert result == "Hello !"


def test_render_multiline():
    engine = PromptEngine()
    template = """You are {{ role }}.
Your task: {{ task }}
Rules: {{ rules }}"""
    result = engine.render(template, {"role": "assistant", "task": "help", "rules": "be kind"})
    assert "You are assistant." in result
    assert "Your task: help" in result


def test_register_and_render_template():
    engine = PromptEngine()
    engine.register_template("greeting", "Hello {{ name }}, welcome to {{ place }}!")
    result = engine.render_template("greeting", {"name": "User", "place": "Astromesh"})
    assert result == "Hello User, welcome to Astromesh!"


def test_render_nonexistent_template():
    engine = PromptEngine()
    result = engine.render_template("missing", {})
    assert result == ""
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/core/prompt_engine.py
from jinja2 import Environment, BaseLoader, Undefined


class SilentUndefined(Undefined):
    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


class PromptEngine:
    """Jinja2-based template rendering for agent prompts."""

    def __init__(self):
        self._env = Environment(loader=BaseLoader(), undefined=SilentUndefined)
        self._templates: dict[str, str] = {}

    def render(self, template_str: str, variables: dict) -> str:
        template = self._env.from_string(template_str)
        return template.render(**variables)

    def register_template(self, name: str, template_str: str):
        self._templates[name] = template_str

    def render_template(self, name: str, variables: dict) -> str:
        template_str = self._templates.get(name)
        if not template_str:
            return ""
        return self.render(template_str, variables)
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/core/prompt_engine.py tests/test_prompt_engine.py
git commit -m "feat: add PromptEngine with Jinja2 templating"
```

---

### Task 11: ReAct orchestration pattern

**Files:**
- Create: `astromesh/orchestration/__init__.py`
- Create: `astromesh/orchestration/patterns.py`
- Create: `tests/test_patterns.py`

**Step 1: Write the failing test**

```python
# tests/test_patterns.py
import pytest
from unittest.mock import AsyncMock
from astromesh.orchestration.patterns import ReActPattern, AgentStep
from astromesh.providers.base import CompletionResponse


def make_response(content, tool_calls=None):
    return CompletionResponse(
        content=content, model="test", provider="test",
        usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        latency_ms=0, cost=0, tool_calls=tool_calls or [],
    )


async def test_react_direct_answer():
    model_fn = AsyncMock(return_value=make_response("The answer is 42."))
    tool_fn = AsyncMock()

    pattern = ReActPattern()
    result = await pattern.execute(
        query="What is the answer?",
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[],
    )
    assert result["answer"] == "The answer is 42."
    assert len(result["steps"]) == 1


async def test_react_with_tool_call():
    call1 = make_response("Let me search.", tool_calls=[
        {"id": "tc1", "name": "search", "arguments": {"q": "test"}}
    ])
    call2 = make_response("Based on the search, the answer is 42.")

    model_fn = AsyncMock(side_effect=[call1, call2])
    tool_fn = AsyncMock(return_value={"result": "found it"})

    pattern = ReActPattern()
    result = await pattern.execute(
        query="Search for answer",
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[{"name": "search", "description": "Search", "parameters": {}}],
    )
    assert result["answer"] == "Based on the search, the answer is 42."
    assert len(result["steps"]) == 2
    tool_fn.assert_called_once_with("search", {"q": "test"})


async def test_react_max_iterations():
    tool_call = [{"id": "tc1", "name": "loop", "arguments": {}}]
    model_fn = AsyncMock(return_value=make_response("thinking...", tool_calls=tool_call))
    tool_fn = AsyncMock(return_value={"result": "ok"})

    pattern = ReActPattern()
    result = await pattern.execute(
        query="loop forever",
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[],
        max_iterations=3,
    )
    assert result["answer"] == "Max iterations reached"
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/orchestration/patterns.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AgentStep:
    thought: str | None = None
    action: str | None = None
    action_input: dict | None = None
    observation: str | None = None
    result: str | None = None


class OrchestrationPattern(ABC):
    """Base for all orchestration patterns."""

    @abstractmethod
    async def execute(
        self,
        query: str,
        context: dict,
        model_fn,
        tool_fn,
        tools: list[dict],
        max_iterations: int = 10,
    ) -> dict: ...


class ReActPattern(OrchestrationPattern):
    """Thought -> Action -> Observation loop."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        messages = [{"role": "user", "content": query}]
        steps: list[AgentStep] = []

        for _ in range(max_iterations):
            response = await model_fn(messages, tools)

            if response.tool_calls:
                for tc in response.tool_calls:
                    observation = await tool_fn(tc["name"], tc["arguments"])
                    steps.append(AgentStep(
                        thought=response.content,
                        action=tc["name"],
                        action_input=tc["arguments"],
                        observation=str(observation),
                    ))
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [tc],
                    })
                    messages.append({
                        "role": "tool",
                        "content": str(observation),
                        "tool_call_id": tc["id"],
                    })
            else:
                steps.append(AgentStep(result=response.content))
                return {"answer": response.content, "steps": steps}

        return {"answer": "Max iterations reached", "steps": steps}
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/orchestration/ tests/test_patterns.py
git commit -m "feat: add ReAct orchestration pattern"
```

---

### Task 12: Memory data models + MemoryManager

**Files:**
- Create: `astromesh/core/memory.py`
- Create: `astromesh/memory/__init__.py`
- Create: `tests/test_memory.py`

**Step 1: Write the failing test**

```python
# tests/test_memory.py
import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from astromesh.core.memory import (
    ConversationTurn, SemanticMemory, EpisodicMemory,
    ConversationBackend, SemanticBackend, EpisodicBackend,
    MemoryManager,
)


def test_conversation_turn():
    turn = ConversationTurn(role="user", content="hello", timestamp=datetime.now())
    assert turn.role == "user"
    assert turn.token_count == 0


def test_semantic_memory():
    mem = SemanticMemory(content="fact", embedding=[0.1, 0.2], metadata={})
    assert mem.similarity == 0.0


def test_episodic_memory():
    ep = EpisodicMemory(
        event_type="task_completed", summary="Did X", context={},
        outcome={}, timestamp=datetime.now(),
    )
    assert ep.importance_score == 0.5


async def test_memory_manager_build_context():
    conv = AsyncMock(spec=ConversationBackend)
    conv.get_history.return_value = [
        ConversationTurn(role="user", content="hi", timestamp=datetime.now(), token_count=5),
        ConversationTurn(role="assistant", content="hey", timestamp=datetime.now(), token_count=5),
    ]
    conv.get_summary.return_value = None

    mgr = MemoryManager(
        agent_id="test-agent",
        config={"conversational": {"strategy": "sliding_window"}},
        conversation=conv,
    )
    ctx = await mgr.build_context("session1", "hello")
    assert len(ctx["conversation"]) == 2
    assert ctx["semantic"] == []
    assert ctx["episodic"] == []


async def test_memory_manager_persist_turn():
    conv = AsyncMock(spec=ConversationBackend)
    conv.get_history.return_value = []

    mgr = MemoryManager(
        agent_id="test",
        config={"conversational": {"max_turns": 50}},
        conversation=conv,
    )
    turn = ConversationTurn(role="user", content="hi", timestamp=datetime.now())
    await mgr.persist_turn("session1", turn)
    conv.save_turn.assert_called_once()
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/core/memory.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


@dataclass
class SemanticMemory:
    content: str
    embedding: list[float]
    metadata: dict
    similarity: float = 0.0
    source: str = ""


@dataclass
class EpisodicMemory:
    event_type: str
    summary: str
    context: dict
    outcome: dict
    timestamp: datetime
    importance_score: float = 0.5


class ConversationBackend(ABC):
    @abstractmethod
    async def save_turn(self, session_id: str, turn: ConversationTurn): ...
    @abstractmethod
    async def get_history(self, session_id: str, limit: int = 50) -> list[ConversationTurn]: ...
    @abstractmethod
    async def clear(self, session_id: str): ...
    @abstractmethod
    async def get_summary(self, session_id: str) -> str | None: ...
    @abstractmethod
    async def save_summary(self, session_id: str, summary: str): ...


class SemanticBackend(ABC):
    @abstractmethod
    async def store(self, agent_id: str, content: str, embedding: list[float], metadata: dict): ...
    @abstractmethod
    async def search(self, agent_id: str, query_embedding: list[float], top_k: int = 10, threshold: float = 0.7) -> list[SemanticMemory]: ...
    @abstractmethod
    async def delete(self, agent_id: str, memory_id: str): ...


class EpisodicBackend(ABC):
    @abstractmethod
    async def record(self, agent_id: str, episode: EpisodicMemory): ...
    @abstractmethod
    async def recall(self, agent_id: str, event_type: str | None = None, since: datetime | None = None, limit: int = 20) -> list[EpisodicMemory]: ...


class MemoryManager:
    """Orchestrates the three memory types for an agent."""

    def __init__(
        self,
        agent_id: str,
        config: dict,
        conversation: ConversationBackend | None = None,
        semantic: SemanticBackend | None = None,
        episodic: EpisodicBackend | None = None,
        embedding_fn=None,
        summarize_fn=None,
    ):
        self.agent_id = agent_id
        self.config = config
        self._conversation = conversation
        self._semantic = semantic
        self._episodic = episodic
        self._embed = embedding_fn
        self._summarize = summarize_fn

    async def build_context(self, session_id: str, current_query: str, max_tokens: int = 4096) -> dict:
        context: dict = {"conversation": [], "semantic": [], "episodic": []}
        token_budget = max_tokens

        if self._conversation:
            strategy = self.config.get("conversational", {}).get("strategy", "sliding_window")

            if strategy == "sliding_window":
                turns = await self._conversation.get_history(session_id)
                context["conversation"] = turns
                token_budget -= sum(t.token_count for t in turns)

            elif strategy == "summary":
                summary = await self._conversation.get_summary(session_id)
                recent = await self._conversation.get_history(session_id, limit=5)
                context["conversation_summary"] = summary
                context["conversation"] = recent

            elif strategy == "token_budget":
                turns = await self._conversation.get_history(session_id)
                selected = []
                used = 0
                for turn in reversed(turns):
                    if used + turn.token_count > token_budget * 0.5:
                        break
                    selected.insert(0, turn)
                    used += turn.token_count
                context["conversation"] = selected
                token_budget -= used

        if self._semantic and self._embed:
            query_emb = await self._embed(current_query)
            threshold = self.config.get("semantic", {}).get("similarity_threshold", 0.75)
            max_results = self.config.get("semantic", {}).get("max_results", 10)
            memories = await self._semantic.search(self.agent_id, query_emb, top_k=max_results, threshold=threshold)
            context["semantic"] = memories

        if self._episodic:
            episodes = await self._episodic.recall(self.agent_id, limit=5)
            context["episodic"] = episodes

        return context

    async def persist_turn(self, session_id: str, turn: ConversationTurn):
        if self._conversation:
            await self._conversation.save_turn(session_id, turn)

            history = await self._conversation.get_history(session_id)
            max_turns = self.config.get("conversational", {}).get("max_turns", 50)

            if len(history) > max_turns and self._summarize:
                old_turns = history[:-10]
                summary = await self._summarize(old_turns)
                await self._conversation.save_summary(session_id, summary)

        if self._semantic and self._embed and turn.role == "assistant":
            if turn.token_count > 50:
                emb = await self._embed(turn.content)
                await self._semantic.store(
                    self.agent_id, turn.content, emb,
                    {"session_id": session_id, "timestamp": turn.timestamp.isoformat()},
                )
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/core/memory.py astromesh/memory/ tests/test_memory.py
git commit -m "feat: add MemoryManager with conversation, semantic, episodic types"
```

---

### Task 13: Agent Runtime Engine (YAML loader + Agent class)

**Files:**
- Create: `astromesh/runtime/__init__.py`
- Create: `astromesh/runtime/engine.py`
- Create: `config/agents/` (directory)
- Create: `config/runtime.yaml`
- Create: `tests/test_engine.py`

**Step 1: Write the failing test**

```python
# tests/test_engine.py
import pytest
import os
import tempfile
from pathlib import Path
from astromesh.runtime.engine import AgentRuntime, Agent


@pytest.fixture
def config_dir(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    agent_yaml = agents_dir / "test-agent.agent.yaml"
    agent_yaml.write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "0.1.0"
  namespace: test
spec:
  identity:
    display_name: "Test Agent"
    description: "A test agent"
  model:
    primary:
      provider: ollama
      model: "llama3:8b"
      endpoint: "http://ollama:11434"
      parameters:
        temperature: 0.5
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 5
""")
    return str(tmp_path)


async def test_runtime_loads_agents(config_dir):
    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()
    assert "test-agent" in runtime._agents


async def test_runtime_agent_properties(config_dir):
    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()
    agent = runtime._agents["test-agent"]
    assert agent.name == "test-agent"
    assert agent.version == "0.1.0"
    assert agent.namespace == "test"
    assert agent.description == "A test agent"


async def test_runtime_missing_agent(config_dir):
    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()
    with pytest.raises(ValueError, match="not found"):
        await runtime.run("nonexistent", "hello", "session1")
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/runtime/engine.py
from pathlib import Path

import yaml

from astromesh.core.memory import MemoryManager
from astromesh.core.model_router import ModelRouter
from astromesh.core.prompt_engine import PromptEngine
from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.patterns import ReActPattern


class AgentRuntime:
    """Main runtime. Loads agents from config and executes them."""

    def __init__(self, config_dir: str = "./config"):
        self._config_dir = Path(config_dir)
        self._agents: dict[str, "Agent"] = {}
        self._prompt_engine = PromptEngine()

    async def bootstrap(self):
        agents_dir = self._config_dir / "agents"
        if not agents_dir.exists():
            return

        agent_files = list(agents_dir.glob("*.agent.yaml"))
        for f in agent_files:
            config = yaml.safe_load(f.read_text())
            agent = self._build_agent(config)
            self._agents[agent.name] = agent

    def _build_agent(self, config: dict) -> "Agent":
        spec = config["spec"]
        metadata = config["metadata"]

        router = ModelRouter(
            spec.get("model", {}).get("routing", {"strategy": "cost_optimized"})
        )

        memory = MemoryManager(
            agent_id=metadata["name"],
            config=spec.get("memory", {}),
        )

        tools = ToolRegistry()

        pattern_name = spec.get("orchestration", {}).get("pattern", "react")
        pattern_map = {
            "react": ReActPattern,
        }
        pattern_cls = pattern_map.get(pattern_name, ReActPattern)
        pattern = pattern_cls()

        prompts = spec.get("prompts", {})
        system_prompt = prompts.get("system", "")

        for name, tmpl in prompts.get("templates", {}).items():
            self._prompt_engine.register_template(name, tmpl)

        return Agent(
            name=metadata["name"],
            version=metadata.get("version", "0.1.0"),
            namespace=metadata.get("namespace", "default"),
            description=spec.get("identity", {}).get("description", ""),
            router=router,
            memory=memory,
            tools=tools,
            pattern=pattern,
            system_prompt=system_prompt,
            prompt_engine=self._prompt_engine,
            guardrails=spec.get("guardrails", {}),
            permissions=spec.get("permissions", {}),
            orchestration_config=spec.get("orchestration", {}),
        )

    async def run(
        self, agent_name: str, query: str, session_id: str, context: dict | None = None
    ) -> dict:
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(query, session_id, context)

    def list_agents(self) -> list[dict]:
        return [
            {"name": a.name, "version": a.version, "namespace": a.namespace}
            for a in self._agents.values()
        ]


class Agent:
    """Configured agent instance ready to execute."""

    def __init__(
        self, name, version, namespace, description,
        router, memory, tools, pattern, system_prompt,
        prompt_engine, guardrails, permissions, orchestration_config,
    ):
        self.name = name
        self.version = version
        self.namespace = namespace
        self.description = description
        self._router = router
        self._memory = memory
        self._tools = tools
        self._pattern = pattern
        self._system_prompt = system_prompt
        self._prompt_engine = prompt_engine
        self._guardrails = guardrails
        self._permissions = permissions
        self._orchestration_config = orchestration_config

    async def run(self, query: str, session_id: str, context: dict | None = None) -> dict:
        from datetime import datetime
        from astromesh.core.memory import ConversationTurn

        memory_context = await self._memory.build_context(session_id, query, max_tokens=4096)

        rendered_prompt = self._prompt_engine.render(self._system_prompt, {
            **(context or {}),
            "memory": memory_context,
        })

        tool_schemas = self._tools.get_tool_schemas(
            self._permissions.get("allowed_actions")
        )

        max_iterations = self._orchestration_config.get("max_iterations", 10)

        async def model_fn(messages, tools):
            full_messages = [{"role": "system", "content": rendered_prompt}] + messages
            return await self._router.route(full_messages, tools=tools)

        async def tool_fn(name, args):
            return await self._tools.execute(name, args, {"agent": self.name, "session": session_id})

        result = await self._pattern.execute(
            query=query,
            context=memory_context,
            model_fn=model_fn,
            tool_fn=tool_fn,
            tools=tool_schemas,
            max_iterations=max_iterations,
        )

        await self._memory.persist_turn(session_id, ConversationTurn(
            role="user", content=query, timestamp=datetime.utcnow(),
        ))
        await self._memory.persist_turn(session_id, ConversationTurn(
            role="assistant", content=result.get("answer", ""), timestamp=datetime.utcnow(),
        ))

        return result
```

Also create `config/runtime.yaml`:

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default

spec:
  api:
    host: "0.0.0.0"
    port: 8000
  defaults:
    orchestration:
      pattern: react
      max_iterations: 10
      timeout_seconds: 120
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/runtime/ config/ tests/test_engine.py
git commit -m "feat: add AgentRuntime engine with YAML config loading"
```

---

## Phase 2: Memory & RAG

### Task 14: Redis conversational memory backend

**Files:**
- Create: `astromesh/memory/backends/__init__.py`
- Create: `astromesh/memory/backends/redis_conv.py`
- Create: `tests/test_memory_backends.py`

**Step 1: Write test (with mock Redis)**

```python
# tests/test_memory_backends.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from astromesh.core.memory import ConversationTurn


async def test_redis_conv_save_and_get():
    with patch("astromesh.memory.backends.redis_conv.aioredis") as mock_redis_mod:
        mock_redis = AsyncMock()
        mock_redis_mod.from_url.return_value = mock_redis
        mock_redis.lrange.return_value = []

        from astromesh.memory.backends.redis_conv import RedisConversationBackend
        backend = RedisConversationBackend("redis://localhost:6379")

        turn = ConversationTurn(role="user", content="hi", timestamp=datetime.now())
        await backend.save_turn("s1", turn)
        mock_redis.rpush.assert_called_once()
        mock_redis.expire.assert_called_once()


async def test_redis_conv_clear():
    with patch("astromesh.memory.backends.redis_conv.aioredis") as mock_redis_mod:
        mock_redis = AsyncMock()
        mock_redis_mod.from_url.return_value = mock_redis

        from astromesh.memory.backends.redis_conv import RedisConversationBackend
        backend = RedisConversationBackend("redis://localhost:6379")

        await backend.clear("s1")
        mock_redis.delete.assert_called_once_with("conv:s1")
```

**Step 2: Run → FAIL. Step 3: Implement.**

```python
# astromesh/memory/backends/redis_conv.py
import json
from datetime import datetime

import redis.asyncio as aioredis

from astromesh.core.memory import ConversationBackend, ConversationTurn


class RedisConversationBackend(ConversationBackend):
    """Redis-backed conversational memory with TTL and sliding window."""

    def __init__(self, redis_url: str, ttl: int = 3600):
        self._redis = aioredis.from_url(redis_url)
        self._ttl = ttl

    async def save_turn(self, session_id: str, turn: ConversationTurn):
        key = f"conv:{session_id}"
        turn_data = json.dumps({
            "role": turn.role,
            "content": turn.content,
            "timestamp": turn.timestamp.isoformat(),
            "metadata": turn.metadata,
            "token_count": turn.token_count,
        })
        await self._redis.rpush(key, turn_data)
        await self._redis.expire(key, self._ttl)

    async def get_history(self, session_id: str, limit: int = 50) -> list[ConversationTurn]:
        key = f"conv:{session_id}"
        raw = await self._redis.lrange(key, -limit, -1)
        turns = []
        for r in raw:
            data = json.loads(r)
            turns.append(ConversationTurn(
                role=data["role"],
                content=data["content"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                metadata=data.get("metadata", {}),
                token_count=data.get("token_count", 0),
            ))
        return turns

    async def clear(self, session_id: str):
        await self._redis.delete(f"conv:{session_id}")

    async def get_summary(self, session_id: str) -> str | None:
        result = await self._redis.get(f"conv_summary:{session_id}")
        return result.decode() if result else None

    async def save_summary(self, session_id: str, summary: str):
        await self._redis.set(f"conv_summary:{session_id}", summary, ex=self._ttl * 2)
```

**Step 4: Run tests. Step 5: Commit.**

```bash
git add astromesh/memory/ tests/test_memory_backends.py
git commit -m "feat: add Redis conversational memory backend"
```

---

### Task 15: SQLite conversational memory backend

**Files:**
- Create: `astromesh/memory/backends/sqlite_conv.py`
- Modify: `tests/test_memory_backends.py`

_(Similar pattern: test with real SQLite in-memory, implement with aiosqlite.)_

**Commit:** `"feat: add SQLite conversational memory backend"`

---

### Task 16: PostgreSQL conversational memory backend

**Files:**
- Create: `astromesh/memory/backends/pg_conv.py`
- Modify: `tests/test_memory_backends.py`

_(Mock asyncpg, implement save/get/clear/summary.)_

**Commit:** `"feat: add PostgreSQL conversational memory backend"`

---

### Task 17: pgvector semantic memory backend

**Files:**
- Create: `astromesh/memory/backends/pgvector_sem.py`
- Modify: `tests/test_memory_backends.py`

**Commit:** `"feat: add pgvector semantic memory backend"`

---

### Task 18: ChromaDB semantic memory backend

**Files:**
- Create: `astromesh/memory/backends/chroma_sem.py`

**Commit:** `"feat: add ChromaDB semantic memory backend"`

---

### Task 19: Qdrant semantic memory backend

**Files:**
- Create: `astromesh/memory/backends/qdrant_sem.py`

**Commit:** `"feat: add Qdrant semantic memory backend"`

---

### Task 20: FAISS semantic memory backend

**Files:**
- Create: `astromesh/memory/backends/faiss_sem.py`

**Commit:** `"feat: add FAISS semantic memory backend"`

---

### Task 21: PostgreSQL episodic memory backend

**Files:**
- Create: `astromesh/memory/backends/pg_episodic.py`

**Commit:** `"feat: add PostgreSQL episodic memory backend"`

---

### Task 22: Memory strategies (sliding_window, summary, token_budget)

**Files:**
- Create: `astromesh/memory/strategies/__init__.py`
- Create: `astromesh/memory/strategies/sliding_window.py`
- Create: `astromesh/memory/strategies/summary.py`
- Create: `astromesh/memory/strategies/token_budget.py`

**Commit:** `"feat: add memory window strategies"`

---

### Task 23: RAG pipeline — chunking strategies

**Files:**
- Create: `astromesh/rag/__init__.py`
- Create: `astromesh/rag/chunking/__init__.py`
- Create: `astromesh/rag/chunking/fixed.py`
- Create: `astromesh/rag/chunking/recursive.py`
- Create: `astromesh/rag/chunking/semantic.py`
- Create: `astromesh/rag/chunking/sentence.py`
- Create: `tests/test_rag.py`

**Step 1: Write the failing test**

```python
# tests/test_rag.py
from astromesh.rag.chunking.fixed import FixedChunker
from astromesh.rag.chunking.recursive import RecursiveChunker
from astromesh.rag.chunking.sentence import SentenceChunker


def test_fixed_chunker():
    chunker = FixedChunker(chunk_size=50, overlap=10)
    text = "A" * 120
    chunks = chunker.chunk(text, {"source": "test"})
    assert len(chunks) >= 2
    assert all("content" in c for c in chunks)


def test_sentence_chunker():
    chunker = SentenceChunker(chunk_size=100, overlap=0)
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    chunks = chunker.chunk(text, {})
    assert len(chunks) >= 1
    assert all("content" in c for c in chunks)
```

**Step 2: Run → FAIL. Step 3: Implement chunkers.**

Each chunker has a `chunk(document: str, metadata: dict) -> list[dict]` method. Fixed splits by char count, Recursive splits by separators (\n\n, \n, ., space), Semantic uses embedding similarity (stub), Sentence splits at sentence boundaries.

**Commit:** `"feat: add RAG chunking strategies"`

---

### Task 24: RAG pipeline — embedding providers

**Files:**
- Create: `astromesh/rag/embeddings/__init__.py`
- Create: `astromesh/rag/embeddings/hf.py`
- Create: `astromesh/rag/embeddings/st.py`
- Create: `astromesh/rag/embeddings/ollama.py`

**Commit:** `"feat: add RAG embedding providers (HF, SentenceTransformers, Ollama)"`

---

### Task 25: RAG pipeline — vector stores

**Files:**
- Create: `astromesh/rag/stores/__init__.py`
- Create: `astromesh/rag/stores/pgvector.py`
- Create: `astromesh/rag/stores/chroma.py`
- Create: `astromesh/rag/stores/qdrant.py`
- Create: `astromesh/rag/stores/faiss_store.py`

**Commit:** `"feat: add RAG vector stores (pgvector, ChromaDB, Qdrant, FAISS)"`

---

### Task 26: RAG pipeline — reranking + pipeline orchestrator

**Files:**
- Create: `astromesh/rag/reranking/__init__.py`
- Create: `astromesh/rag/reranking/cross_encoder.py`
- Create: `astromesh/rag/reranking/cohere.py`
- Create: `astromesh/rag/pipeline.py`

**Commit:** `"feat: add RAG reranking + pipeline orchestrator"`

---

## Phase 3: Multi-Pattern Orchestration

### Task 27: Plan & Execute pattern

**Files:**
- Modify: `astromesh/orchestration/patterns.py`
- Modify: `tests/test_patterns.py`

**Step 1: Write the failing test**

```python
async def test_plan_execute_pattern():
    from astromesh.orchestration.patterns import PlanAndExecutePattern

    plan_response = make_response('{"steps": [{"step": 1, "description": "Search", "tool": null, "depends_on": []}]}')
    step_response = make_response("Step 1 result")
    final_response = make_response("Final synthesized answer")

    model_fn = AsyncMock(side_effect=[plan_response, step_response, final_response])
    tool_fn = AsyncMock()

    pattern = PlanAndExecutePattern()
    result = await pattern.execute("Do research", {}, model_fn, tool_fn, [])
    assert "answer" in result
    assert result["answer"] == "Final synthesized answer"
```

**Step 2: Run → FAIL. Step 3: Add PlanAndExecutePattern to patterns.py.**

**Commit:** `"feat: add Plan & Execute orchestration pattern"`

---

### Task 28: Parallel Fan-Out pattern

**Commit:** `"feat: add Parallel Fan-Out orchestration pattern"`

---

### Task 29: Pipeline pattern

**Commit:** `"feat: add Pipeline orchestration pattern"`

---

### Task 30: Supervisor pattern

**Files:**
- Create: `astromesh/orchestration/supervisor.py`

**Commit:** `"feat: add Supervisor orchestration pattern"`

---

### Task 31: Swarm pattern

**Files:**
- Create: `astromesh/orchestration/swarm.py`

**Commit:** `"feat: add Swarm orchestration pattern"`

---

### Task 32: Wire all patterns into AgentRuntime

**Files:**
- Modify: `astromesh/runtime/engine.py` — add all patterns to pattern_map

**Commit:** `"feat: wire all 6 orchestration patterns into AgentRuntime"`

---

## Phase 4: MCP Integration

### Task 33: MCP client — stdio, SSE, streamable HTTP

**Files:**
- Create: `astromesh/mcp/__init__.py`
- Create: `astromesh/mcp/client.py`
- Create: `tests/test_mcp.py`

**Commit:** `"feat: add MCP client with stdio, SSE, and HTTP transports"`

---

### Task 34: MCP server — expose agents as MCP tools

**Files:**
- Create: `astromesh/mcp/server.py`

**Commit:** `"feat: add MCP server to expose Astromesh agents as tools"`

---

### Task 35: Wire MCP into ToolRegistry

**Files:**
- Modify: `astromesh/core/tools.py` — add register_mcp_server
- Modify: `astromesh/runtime/engine.py` — load MCP servers from agent config

**Commit:** `"feat: integrate MCP servers into ToolRegistry and agent loading"`

---

## Phase 5: ML Model Registry

### Task 36: Local model registry

**Files:**
- Create: `astromesh/ml/__init__.py`
- Create: `astromesh/ml/model_registry.py`
- Create: `tests/test_ml.py`

**Commit:** `"feat: add local ML model registry"`

---

### Task 37: ONNX and PyTorch serving

**Files:**
- Create: `astromesh/ml/serving/__init__.py`
- Create: `astromesh/ml/serving/onnx_runtime.py`
- Create: `astromesh/ml/serving/torch_serve.py`

**Commit:** `"feat: add ONNX and PyTorch model serving"`

---

### Task 38: Training pipeline config

**Files:**
- Create: `astromesh/ml/training/__init__.py`
- Create: `astromesh/ml/training/classifier.py`
- Create: `astromesh/ml/training/embeddings.py`

**Commit:** `"feat: add ML training pipeline (classifier + embeddings)"`

---

## Phase 6: Observability

### Task 39: OpenTelemetry setup

**Files:**
- Create: `astromesh/observability/__init__.py`
- Create: `astromesh/observability/telemetry.py`

**Commit:** `"feat: add OpenTelemetry tracing setup"`

---

### Task 40: Prometheus metrics

**Files:**
- Create: `astromesh/observability/metrics.py`

**Commit:** `"feat: add Prometheus metrics for agent runs"`

---

### Task 41: Cost tracker

**Files:**
- Create: `astromesh/observability/cost_tracker.py`

**Commit:** `"feat: add cost tracker per agent/session/model"`

---

## Phase 7: Hardening

### Task 42: Guardrails engine

**Files:**
- Create: `astromesh/core/guardrails.py`
- Create: `tests/test_guardrails.py`

**Step 1: Write test**

```python
# tests/test_guardrails.py
from astromesh.core.guardrails import GuardrailsEngine


async def test_pii_redaction():
    engine = GuardrailsEngine(config={
        "input": [{"type": "pii_detection", "action": "redact"}]
    })
    result = await engine.apply_input("My email is john@example.com")
    assert "john@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


async def test_topic_filter():
    engine = GuardrailsEngine(config={
        "input": [{"type": "topic_filter", "blocked_topics": ["competitor"]}]
    })
    result = await engine.apply_input("Tell me about competitor products")
    assert result is not None  # Returns warning or blocks


async def test_cost_limit():
    engine = GuardrailsEngine(config={
        "output": [{"type": "cost_limit", "max_tokens_per_turn": 100}]
    })
    long_text = "word " * 200
    result = await engine.apply_output(long_text)
    # Should truncate or warn
    assert len(result) <= len(long_text)
```

**Commit:** `"feat: add GuardrailsEngine with PII, topic, cost filters"`

---

### Task 43: Full API routes (agents, memory, tools, RAG)

**Files:**
- Modify: `astromesh/api/routes/agents.py` — full CRUD
- Create: `astromesh/api/routes/memory.py`
- Create: `astromesh/api/routes/tools.py`
- Create: `astromesh/api/routes/rag.py`
- Modify: `astromesh/api/main.py` — register all routers

**Commit:** `"feat: add full API routes for agents, memory, tools, RAG"`

---

### Task 44: WebSocket streaming

**Files:**
- Create: `astromesh/api/ws.py`

**Commit:** `"feat: add WebSocket streaming for agent responses"`

---

### Task 45: Docker files

**Files:**
- Create: `docker/Dockerfile`
- Create: `docker/Dockerfile.gpu`
- Create: `docker/docker-compose.yaml`
- Create: `docker/init.sql`

**Step 1: Write Dockerfile**

```dockerfile
# docker/Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY astromesh/ astromesh/
COPY config/ config/

RUN pip install uv && uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "astromesh.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Write docker-compose.yaml**

Full stack with all services from the design doc: astromesh, ollama, vllm, embeddings, reranker, postgres, redis, otel-collector, prometheus, grafana.

**Step 3: Write init.sql**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS semantic_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS episodic_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    outcome JSONB DEFAULT '{}',
    importance_score FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    token_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name TEXT NOT NULL,
    session_id TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    cost_usd FLOAT DEFAULT 0.0,
    latency_ms FLOAT DEFAULT 0.0,
    pattern TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_semantic_agent ON semantic_memories(agent_id);
CREATE INDEX idx_episodic_agent ON episodic_memories(agent_id);
CREATE INDEX idx_conv_session ON conversation_history(session_id);
CREATE INDEX idx_usage_agent ON usage_records(agent_name);
```

**Commit:** `"feat: add Docker files and docker-compose stack"`

---

### Task 46: Sample agent configs

**Files:**
- Create: `config/agents/sales-qualifier.agent.yaml`
- Create: `config/agents/support-agent.agent.yaml`
- Create: `config/rag/product-knowledge.rag.yaml`
- Create: `config/providers.yaml`

_(These are example configs matching the spec, with `apiVersion: astromesh/v1`)_

**Commit:** `"feat: add sample agent and RAG configs"`

---

### Task 47: Integration test — full agent run

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write test**

```python
# tests/test_integration.py
import pytest
from unittest.mock import AsyncMock, patch
from astromesh.runtime.engine import AgentRuntime
from astromesh.providers.base import CompletionResponse


async def test_full_agent_run(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "echo.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: echo
  version: "0.1.0"
  namespace: test
spec:
  identity:
    display_name: Echo Agent
    description: Echoes back
  model:
    primary:
      provider: ollama
      model: test
      endpoint: http://localhost:11434
  prompts:
    system: "Echo the user's message."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    mock_response = CompletionResponse(
        content="Echo: hello",
        model="test",
        provider="ollama",
        usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        latency_ms=10,
        cost=0.0,
    )

    agent = runtime._agents["echo"]
    agent._router.register_provider("test", AsyncMock(
        complete=AsyncMock(return_value=mock_response),
        estimated_cost=lambda *a: 0.0,
    ))

    result = await runtime.run("echo", "hello", "test-session")
    assert result["answer"] == "Echo: hello"
```

**Commit:** `"test: add integration test for full agent run"`

---

### Task 48: Final lint + test pass

**Step 1: Run ruff**

Run: `uv run ruff check . --fix`

**Step 2: Run full test suite**

Run: `uv run pytest -v --tb=short`

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "chore: lint fixes and final test pass"
```

---

## Summary

| Phase | Tasks | Key Files |
|-------|-------|-----------|
| 0: Foundation | 1-8 | pyproject.toml, 6 providers, ModelRouter, FastAPI |
| 1: Core Agent | 9-13 | ToolRegistry, PromptEngine, ReAct, MemoryManager, AgentRuntime |
| 2: Memory & RAG | 14-26 | 8 memory backends, 3 strategies, chunking, embeddings, stores, reranking, pipeline |
| 3: Multi-Pattern | 27-32 | Plan&Execute, Parallel, Pipeline, Supervisor, Swarm |
| 4: MCP | 33-35 | MCP client (3 transports), server, integration |
| 5: ML | 36-38 | Model registry, ONNX/PyTorch serving, training |
| 6: Observability | 39-41 | OTel, Prometheus, cost tracker |
| 7: Hardening | 42-48 | Guardrails, full API, WebSocket, Docker, sample configs, integration test |

**Total: 48 tasks across 8 phases.**
