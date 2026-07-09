# Model Roles per Architecture + LiteLLM Sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each orchestration pattern pick a per-role model, and let assistants declare models from many sources (LiteLLM cloud + native adapters), while keeping every existing agent working unchanged.

**Architecture:** One `ModelRouter` per role (`dict[str, ModelRouter]` on the `Agent`). The pattern's `model_fn` gains an optional `role` argument that selects the router; an undefined role falls back to `default`. A new `LiteLLMProvider` implements `ProviderProtocol` for 100+ cloud models. The legacy `primary/fallback/extra` schema is normalized into a `default` role at load time, so no YAML migration is needed.

**Tech Stack:** Python 3.12, FastAPI runtime, `litellm` (new optional dependency), pytest + respx, uv.

## Global Constraints

- Python 3.12; line length 100; `uv run ruff check` / `ruff format` must pass.
- All provider/router/pattern code is `async`.
- `litellm` is an **optional** dependency — importing it must be lazy; the runtime must work when it is not installed.
- Backward compatibility is mandatory: the 6 agents in `config/agents/*.agent.yaml` must load and run unchanged.
- Conventional commits. `feat:`/`fix:`/`refactor:` commits require a `CHANGELOG.md` entry under `## [Unreleased]` in the same commit (project changelog rule).
- Provider adapters implement `ProviderProtocol` (`astromesh/providers/base.py`): `complete`, `stream`, `health_check`, `supports_tools`, `supports_vision`, `estimated_cost`.
- Public docs site is updated **last**, only after the feature ships and tests are green (present tense, no "planned" pages).

---

### Task 1: `LiteLLMProvider` + optional dependency

**Files:**
- Create: `astromesh/providers/litellm_provider.py`
- Modify: `pyproject.toml` (add `litellm` optional extra)
- Test: `tests/test_litellm_provider.py`

**Interfaces:**
- Consumes: `CompletionResponse`, `CompletionChunk` from `astromesh/providers/base.py`; `_normalize_tool_calls` from `astromesh/providers/openai_compat.py`.
- Produces: `LiteLLMProvider(config: dict)` implementing `ProviderProtocol`. `complete(messages, **kwargs) -> CompletionResponse`. Model string carries a LiteLLM prefix (`anthropic/claude-opus-4-8`). `provider` label = prefix before `/`, else `"litellm"`.

- [ ] **Step 1: Add the optional dependency**

In `pyproject.toml`, under `[project.optional-dependencies]`, add:

```toml
litellm = ["litellm>=1.50.0"]
```

And add `litellm` to the `all` extra list:

```toml
all = [
    "astromesh[redis,postgres,sqlite,chromadb,qdrant,faiss,embeddings,onnx,observability,mcp,mesh,litellm]",
]
```

- [ ] **Step 2: Write the failing test**

`tests/test_litellm_provider.py`:

```python
"""Tests for the LiteLLM-backed provider adapter (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from astromesh.providers.base import CompletionResponse
from astromesh.providers.litellm_provider import LiteLLMProvider, _litellm_provider_label


def _fake_model_response() -> SimpleNamespace:
    """Mimics litellm.ModelResponse.model_dump() shape (OpenAI-compatible)."""
    return SimpleNamespace(
        model_dump=lambda: {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello from Claude!",
                        "tool_calls": [
                            {
                                "id": "tc_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": '{"q": "x"}'},
                            }
                        ],
                        "reasoning_content": "thinking...",
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "cache_read_input_tokens": 4},
        }
    )


def test_provider_label():
    assert _litellm_provider_label("anthropic/claude-opus-4-8") == "anthropic"
    assert _litellm_provider_label("gpt-4o") == "litellm"


async def test_complete_maps_response(monkeypatch):
    import astromesh.providers.litellm_provider as mod

    async def fake_acompletion(**kwargs):
        assert kwargs["model"] == "anthropic/claude-opus-4-8"
        return _fake_model_response()

    fake_litellm = SimpleNamespace(
        acompletion=fake_acompletion,
        completion_cost=lambda **_: 0.0031,
    )
    monkeypatch.setattr(mod, "_import_litellm", lambda: fake_litellm)

    provider = LiteLLMProvider(config={"model": "anthropic/claude-opus-4-8"})
    resp = await provider.complete([{"role": "user", "content": "hi"}])

    assert isinstance(resp, CompletionResponse)
    assert resp.content == "Hello from Claude!"
    assert resp.provider == "anthropic"
    assert resp.usage["input_tokens"] == 12
    assert resp.usage["output_tokens"] == 7
    assert resp.usage["cache_read_input_tokens"] == 4
    assert resp.cost == 0.0031
    assert resp.tool_calls == [{"id": "tc_1", "name": "lookup", "arguments": {"q": "x"}}]
    assert resp.reasoning_content == "thinking..."


def test_missing_dependency_raises_on_use(monkeypatch):
    import astromesh.providers.litellm_provider as mod

    def boom():
        raise ImportError("litellm not installed")

    monkeypatch.setattr(mod, "_import_litellm", boom)
    provider = LiteLLMProvider(config={"model": "anthropic/claude-opus-4-8"})
    with pytest.raises(ImportError):
        provider._litellm()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_litellm_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'astromesh.providers.litellm_provider'`

- [ ] **Step 4: Write the implementation**

`astromesh/providers/litellm_provider.py`:

```python
"""LiteLLM-backed provider adapter: unified access to 100+ cloud LLM providers.

`litellm` is an optional dependency; the import is lazy so the runtime works
without it. Requesting a `source: litellm` candidate without the package
installed surfaces an ImportError, which the engine catches and turns into a
skipped candidate (see runtime.engine).
"""

from __future__ import annotations

import os
import time
from typing import Any, AsyncIterator

from .base import CompletionChunk, CompletionResponse
from .openai_compat import _normalize_tool_calls


def _import_litellm():
    """Import litellm lazily. Isolated for monkeypatching in tests."""
    import litellm  # noqa: PLC0415

    return litellm


def _litellm_provider_label(model: str) -> str:
    """Derive the provider label from a LiteLLM model string (prefix before '/')."""
    return model.split("/", 1)[0] if "/" in (model or "") else "litellm"


class LiteLLMProvider:
    """Provider adapter that routes completions through LiteLLM."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.model: str = config.get("model", "gpt-4o")
        self.timeout: float = float(config.get("timeout", 120.0))
        self.parameters: dict = config.get("parameters", {}) or {}

        api_key = config.get("api_key")
        env_var = config.get("api_key_env")
        if not api_key and env_var:
            api_key = os.environ.get(env_var, "")
        self.api_key: str | None = api_key or None

    def _litellm(self):
        return _import_litellm()

    async def complete(self, messages: list[dict], **kwargs: Any) -> CompletionResponse:
        litellm = self._litellm()
        model = kwargs.pop("model", self.model)
        params = {**self.parameters, **kwargs}
        if self.api_key:
            params.setdefault("api_key", self.api_key)

        start = time.perf_counter()
        resp = await litellm.acompletion(
            model=model, messages=messages, timeout=self.timeout, **params
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        data = resp if isinstance(resp, dict) else resp.model_dump()
        message = data["choices"][0].get("message", {})
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cached = usage.get("cache_read_input_tokens", 0)

        try:
            cost = float(litellm.completion_cost(completion_response=resp))
        except Exception:  # noqa: BLE001 — pricing is best-effort
            cost = 0.0

        return CompletionResponse(
            content=message.get("content", "") or "",
            model=model,
            provider=_litellm_provider_label(model),
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cached,
            },
            latency_ms=latency_ms,
            cost=cost,
            tool_calls=_normalize_tool_calls(message.get("tool_calls")),
            reasoning_content=message.get("reasoning_content"),
        )

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[CompletionChunk]:
        litellm = self._litellm()
        model = kwargs.pop("model", self.model)
        params = {**self.parameters, **kwargs}
        if self.api_key:
            params.setdefault("api_key", self.api_key)
        response = await litellm.acompletion(
            model=model, messages=messages, stream=True, timeout=self.timeout, **params
        )
        async for chunk in response:
            data = chunk if isinstance(chunk, dict) else chunk.model_dump()
            delta = data["choices"][0].get("delta", {})
            yield CompletionChunk(
                content=delta.get("content", "") or "",
                model=model,
                provider=_litellm_provider_label(model),
                done=False,
            )
        yield CompletionChunk(content="", model=model, provider=_litellm_provider_label(model), done=True)

    async def health_check(self) -> bool:
        try:
            self._litellm()
            return True
        except Exception:  # noqa: BLE001
            return False

    def supports_tools(self) -> bool:
        try:
            return bool(self._litellm().supports_function_calling(self.model))
        except Exception:  # noqa: BLE001
            return True

    def supports_vision(self) -> bool:
        try:
            return bool(self._litellm().supports_vision(self.model))
        except Exception:  # noqa: BLE001
            return False

    def estimated_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        try:
            litellm = self._litellm()
            prompt, completion = litellm.cost_per_token(
                model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens
            )
            return float(prompt) + float(completion)
        except Exception:  # noqa: BLE001
            return 0.0
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_litellm_provider.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check astromesh/providers/litellm_provider.py tests/test_litellm_provider.py
uv run ruff format astromesh/providers/litellm_provider.py tests/test_litellm_provider.py
git add astromesh/providers/litellm_provider.py tests/test_litellm_provider.py pyproject.toml
git commit -m "feat(providers): LiteLLMProvider for multi-source cloud models (optional dep)"
```

Note: this commit is `feat:` — add the CHANGELOG entry in Task 6, or add a one-line entry here under `### Added (Backend)`. If committing now, add to `CHANGELOG.md` first: `- LiteLLM-backed provider for 100+ cloud models (optional \`litellm\` extra).`

---

### Task 2: Source-aware candidate builder in the engine

**Files:**
- Modify: `astromesh/runtime/engine.py:157-237` (`_register_model_providers` → refactor to a candidate builder)
- Test: `tests/test_engine_role_routers.py` (new)

**Interfaces:**
- Consumes: `OllamaProvider`, `OpenAICompatProvider`, `LiteLLMProvider`.
- Produces: module-level function `build_candidate_provider(block: dict) -> object | None` in `astromesh/runtime/engine.py`. `block` keys: `source` (or legacy `provider`), `model`, `endpoint?`, `api_key_env?`, `api_key?`, `parameters?`, `timeout?`. Returns a provider instance or `None` for unknown/failed source. Source inference: missing `source` and `"/" in model` → `litellm`; else `openai_compat`.

- [ ] **Step 1: Write the failing test**

`tests/test_engine_role_routers.py`:

```python
"""Tests for source-aware candidate building and per-role routers."""

from __future__ import annotations

from astromesh.providers.litellm_provider import LiteLLMProvider
from astromesh.providers.ollama_provider import OllamaProvider
from astromesh.providers.openai_compat import OpenAICompatProvider
from astromesh.runtime.engine import build_candidate_provider


def test_builds_ollama_from_source():
    prov = build_candidate_provider({"source": "ollama", "model": "llama3.1:8b"})
    assert isinstance(prov, OllamaProvider)


def test_builds_litellm_from_source():
    prov = build_candidate_provider(
        {"source": "litellm", "model": "anthropic/claude-opus-4-8", "api_key_env": "ANTHROPIC_API_KEY"}
    )
    assert isinstance(prov, LiteLLMProvider)


def test_infers_litellm_from_prefixed_model():
    prov = build_candidate_provider({"model": "gemini/gemini-2.0-pro"})
    assert isinstance(prov, LiteLLMProvider)


def test_infers_openai_compat_without_prefix():
    prov = build_candidate_provider({"model": "gpt-4o-mini"})
    assert isinstance(prov, OpenAICompatProvider)


def test_legacy_provider_key_maps_to_source():
    prov = build_candidate_provider({"provider": "ollama", "model": "llama3"})
    assert isinstance(prov, OllamaProvider)


def test_unknown_source_returns_none():
    assert build_candidate_provider({"source": "does-not-exist", "model": "x"}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_role_routers.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_candidate_provider'`

- [ ] **Step 3: Add `build_candidate_provider` to `engine.py`**

Add this module-level function near the top of `astromesh/runtime/engine.py` (after the imports, before `AgentRuntime`):

```python
def build_candidate_provider(block: dict):
    """Build a provider instance from a candidate/legacy block.

    Accepts `source` (new) or `provider` (legacy) to select the adapter. When
    neither is set, infers `litellm` for prefixed models (contain '/') and
    `openai_compat` otherwise. Returns None for unknown sources.
    """
    from astromesh.providers.litellm_provider import LiteLLMProvider
    from astromesh.providers.ollama_provider import OllamaProvider
    from astromesh.providers.openai_compat import OpenAICompatProvider

    source = (block.get("source") or block.get("provider") or "").strip().lower()
    model = block.get("model", "")
    if not source:
        source = "litellm" if "/" in model else "openai_compat"

    if source == "ollama":
        base = (block.get("endpoint") or "http://localhost:11434").rstrip("/")
        return OllamaProvider(
            config={
                "base_url": base,
                "model": model or "llama3",
                "timeout": float(block.get("timeout", 120)),
            }
        )
    if source in ("openai_compat", "openai", "azure_openai"):
        base = (block.get("endpoint") or "https://api.openai.com/v1").rstrip("/")
        return OpenAICompatProvider(
            config={
                "base_url": base,
                "model": model or "gpt-4o-mini",
                "api_key_env": block.get("api_key_env", "OPENAI_API_KEY"),
                "api_key": block.get("api_key"),
            }
        )
    if source == "litellm":
        return LiteLLMProvider(
            config={
                "model": model or "gpt-4o",
                "api_key": block.get("api_key"),
                "api_key_env": block.get("api_key_env"),
                "parameters": block.get("parameters"),
                "timeout": float(block.get("timeout", 120)),
            }
        )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_engine_role_routers.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_role_routers.py
git commit -m "feat(runtime): source-aware candidate provider builder"
```

---

### Task 3: Normalize schema → per-role `ModelRouter` dict

> **MERGED WITH TASK 4** (per pre-flight review): implement Task 3 and Task 4 as one atomic change with a **single** final commit. SKIP Task 3 Step 4 (the premature `_build_agent` rewire) and Task 3 Step 6 (the intermediate commit); do the `_build_agent` rewire together with the `Agent(routers=...)` signature change and delete `_register_model_providers` in the same change, then run the full regression and commit once. This keeps every task's suite green.

**Files:**
- Modify: `astromesh/runtime/engine.py` (replace `_register_model_providers` usage in `_build_agent`; add `_normalize_model_spec` + `_build_role_routers`)
- Test: `tests/test_engine_role_routers.py` (append)

**Interfaces:**
- Consumes: `build_candidate_provider` (Task 2), `ModelRouter`.
- Produces:
  - `AgentRuntime._normalize_model_spec(model_spec: dict) -> dict[str, dict]` → maps role name → `{"candidates": [block, ...], "strategy": str}`. Always contains a `"default"` key. Legacy `primary`/`fallback`/`extra.{name}`/`routing.strategy` collapse into `default`.
  - `AgentRuntime._build_role_routers(model_spec: dict) -> dict[str, ModelRouter]` → one router per role, each with its candidates registered under slot names `cand0`, `cand1`, …

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_role_routers.py`:

```python
from astromesh.core.model_router import ModelRouter
from astromesh.runtime.engine import AgentRuntime


def _runtime():
    return AgentRuntime(config_dir="./config")


def test_legacy_schema_normalizes_to_default_role():
    rt = _runtime()
    legacy = {
        "primary": {"provider": "ollama", "model": "llama3.1:8b"},
        "fallback": {"provider": "openai", "model": "gpt-4o-mini"},
        "routing": {"strategy": "latency_optimized"},
    }
    roles = rt._normalize_model_spec(legacy)
    assert set(roles.keys()) == {"default"}
    assert roles["default"]["strategy"] == "latency_optimized"
    assert len(roles["default"]["candidates"]) == 2
    assert roles["default"]["candidates"][0]["model"] == "llama3.1:8b"


def test_new_schema_parses_default_and_roles():
    rt = _runtime()
    spec = {
        "default": {"candidates": [{"source": "ollama", "model": "llama3.1:8b"}]},
        "roles": {
            "planner": {
                "candidates": [{"source": "litellm", "model": "anthropic/claude-opus-4-8"}],
                "strategy": "quality_first",
            }
        },
    }
    roles = rt._normalize_model_spec(spec)
    assert set(roles.keys()) == {"default", "planner"}
    assert roles["planner"]["strategy"] == "quality_first"


def test_build_role_routers_returns_router_per_role():
    rt = _runtime()
    spec = {
        "default": {"candidates": [{"source": "ollama", "model": "llama3.1:8b"}]},
        "roles": {"planner": {"candidates": [{"source": "ollama", "model": "llama3.1:70b"}]}},
    }
    routers = rt._build_role_routers(spec)
    assert set(routers.keys()) == {"default", "planner"}
    assert isinstance(routers["default"], ModelRouter)
    assert isinstance(routers["planner"], ModelRouter)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine_role_routers.py -k "normalize or role_routers or new_schema or legacy" -v`
Expected: FAIL with `AttributeError: 'AgentRuntime' object has no attribute '_normalize_model_spec'`

- [ ] **Step 3: Implement normalization + router building**

Add these methods to `AgentRuntime` in `astromesh/runtime/engine.py`:

```python
    def _normalize_model_spec(self, model_spec: dict) -> dict[str, dict]:
        """Normalize legacy and new model schemas into {role: {candidates, strategy}}.

        Always returns a 'default' role. Legacy primary/fallback/extra/routing
        collapse into 'default'; the new schema uses model.default + model.roles.
        """
        roles: dict[str, dict] = {}

        # New schema
        if "default" in model_spec or "roles" in model_spec:
            default_block = model_spec.get("default") or {}
            roles["default"] = {
                "candidates": list(default_block.get("candidates", [])),
                "strategy": default_block.get("strategy", "cost_optimized"),
            }
            for name, block in (model_spec.get("roles") or {}).items():
                if name == "default":
                    continue
                roles[str(name)] = {
                    "candidates": list((block or {}).get("candidates", [])),
                    "strategy": (block or {}).get("strategy", "cost_optimized"),
                }
            return roles

        # Legacy schema → single 'default' role
        candidates: list[dict] = []
        for slot in ("primary", "fallback"):
            block = model_spec.get(slot)
            if isinstance(block, dict) and (block.get("provider") or block.get("source")):
                candidates.append(block)
        extras = model_spec.get("extra")
        if isinstance(extras, dict):
            for block in extras.values():
                if isinstance(block, dict) and (block.get("provider") or block.get("source")):
                    candidates.append(block)
        strategy = (model_spec.get("routing") or {}).get("strategy", "cost_optimized")
        roles["default"] = {"candidates": candidates, "strategy": strategy}
        return roles

    def _build_role_routers(self, model_spec: dict) -> dict[str, "ModelRouter"]:
        """Build one ModelRouter per role from the normalized spec."""
        roles = self._normalize_model_spec(model_spec)
        routers: dict[str, ModelRouter] = {}
        for role_name, cfg in roles.items():
            router = ModelRouter({"strategy": cfg.get("strategy", "cost_optimized")})
            registered = 0
            for i, block in enumerate(cfg.get("candidates", [])):
                try:
                    prov = build_candidate_provider(block)
                except Exception:
                    logger.exception("role %s candidate %d failed to build", role_name, i)
                    continue
                if prov is None:
                    logger.warning(
                        "role %s candidate %d: unknown source %r; skipping",
                        role_name, i, block.get("source") or block.get("provider"),
                    )
                    continue
                router.register_provider(f"cand{i}", prov)
                registered += 1
            if registered == 0:
                logger.warning("role %s registered 0 providers", role_name)
            routers[role_name] = router
        if "default" not in routers:
            routers["default"] = ModelRouter({"strategy": "cost_optimized"})
        return routers
```

- [ ] **Step 4: Wire `_build_agent` to use role routers**

In `astromesh/runtime/engine.py`, in `_build_agent`, replace:

```python
        router = ModelRouter(model_spec.get("routing", {"strategy": "cost_optimized"}))
        self._register_model_providers(router, model_spec)
```

with:

```python
        routers = self._build_role_routers(model_spec)
```

Then change the `Agent(...)` construction to pass `routers=routers` instead of `router=router` (the `Agent` signature change lands in Task 4; for now pass `routers=routers`). Leave the old `_register_model_providers` method in place (unused) until Task 4's tests pass, then delete it in Task 4 Step 6.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine_role_routers.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_role_routers.py
git commit -m "feat(runtime): normalize model schema into per-role ModelRouter dict"
```

---

### Task 4: `Agent` resolves model by role

**Files:**
- Modify: `astromesh/runtime/engine.py` (`Agent.__init__`, `Agent.run` `model_fn`; delete dead `_register_model_providers`)
- Test: `tests/test_engine_role_routers.py` (append)

**Interfaces:**
- Consumes: `routers: dict[str, ModelRouter]` (Task 3), `orchestration_config` (may contain `role_map: dict[str,str]`).
- Produces: `Agent(..., routers=<dict>, ...)` (replaces `router=`). `model_fn(messages, tools, role=None)` resolves `role_map[role]` → `routers[...]` → `routers["default"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_role_routers.py`:

```python
from unittest.mock import AsyncMock

from astromesh.core.memory import MemoryManager
from astromesh.core.prompt_engine import PromptEngine
from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.patterns import ReActPattern
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import Agent


def _make_router_returning(tag):
    router = ModelRouter({"strategy": "cost_optimized"})
    resp = CompletionResponse(
        content=tag, model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0
    )
    router.route = AsyncMock(return_value=resp)
    return router


def _agent_with(routers, role_map=None):
    return Agent(
        name="t", version="0.1.0", namespace="default", description="",
        routers=routers, memory=MemoryManager(agent_id="t", config={}),
        tools=ToolRegistry(), pattern=ReActPattern(), system_prompt="sys",
        prompt_engine=PromptEngine(), guardrails={}, permissions={},
        orchestration_config={"role_map": role_map or {}},
    )


async def test_model_fn_routes_by_role():
    routers = {"default": _make_router_returning("D"), "planner": _make_router_returning("P")}
    agent = _agent_with(routers)
    out = await agent.run("hi", session_id="s")
    # ReAct requests role=None -> default; assert default router was used
    routers["default"].route.assert_awaited()
    routers["planner"].route.assert_not_awaited()
    assert out["answer"] == "D"


async def test_role_map_remaps_role(monkeypatch):
    routers = {"default": _make_router_returning("D"), "planner": _make_router_returning("P")}
    agent = _agent_with(routers, role_map={"reasoner": "planner"})
    # patch ReAct to request the 'reasoner' role
    from astromesh.orchestration import patterns as pmod
    orig = pmod.ReActPattern.execute

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        r = await model_fn([{"role": "user", "content": query}], tools, role="reasoner")
        return {"answer": r.content, "steps": []}

    monkeypatch.setattr(pmod.ReActPattern, "execute", execute)
    out = await agent.run("hi", session_id="s")
    assert out["answer"] == "P"  # reasoner -> planner via role_map
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_role_routers.py -k "model_fn or role_map" -v`
Expected: FAIL — `Agent.__init__` has no `routers` parameter (currently `router`).

- [ ] **Step 3: Update `Agent.__init__`**

In `astromesh/runtime/engine.py`, change `Agent.__init__` signature `router` → `routers` and store role_map:

```python
    def __init__(
        self,
        name,
        version,
        namespace,
        description,
        routers,
        memory,
        tools,
        pattern,
        system_prompt,
        prompt_engine,
        guardrails,
        permissions,
        orchestration_config,
    ):
        self.name = name
        self.version = version
        self.namespace = namespace
        self.description = description
        self._routers = routers
        self._role_map = (orchestration_config or {}).get("role_map", {}) or {}
        self._memory = memory
        self._tools = tools
        self._pattern = pattern
        self._system_prompt = system_prompt
        self._prompt_engine = prompt_engine
        self._guardrails = guardrails
        self._permissions = permissions
        self._orchestration_config = orchestration_config
```

- [ ] **Step 4: Update `model_fn` in `Agent.run`**

Change the `model_fn` signature and router selection. Replace:

```python
            async def model_fn(messages, tools):
                llm_span = tracing.start_span("llm.complete", parent_span_id=root_span.span_id)
                full_messages = [{"role": "system", "content": rendered_prompt}] + messages
                try:
                    response = await self._router.route(full_messages, tools=tools, **route_kwargs)
```

with:

```python
            async def model_fn(messages, tools, role=None):
                llm_span = tracing.start_span("llm.complete", parent_span_id=root_span.span_id)
                full_messages = [{"role": "system", "content": rendered_prompt}] + messages
                resolved_role = self._role_map.get(role, role) if role else "default"
                router = self._routers.get(resolved_role) or self._routers["default"]
                llm_span.set_attribute("role", role or "default")
                llm_span.set_attribute("resolved_role", resolved_role or "default")
                try:
                    response = await router.route(full_messages, tools=tools, **route_kwargs)
```

- [ ] **Step 5: Update `_build_agent`'s `Agent(...)` call**

In `_build_agent`, the `Agent(...)` construction must pass `routers=routers` (from Task 3) — confirm the keyword is `routers=routers`, not `router=router`. Remove any lingering `router=` keyword.

- [ ] **Step 6: Delete dead code**

Delete the now-unused `_register_model_providers` method from `AgentRuntime` (the whole method, lines ~157–237 in the original file).

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine_role_routers.py tests/test_engine.py -v`
Expected: PASS (role tests + existing engine tests still green — legacy agents build via the `default` role)

- [ ] **Step 8: Full regression + commit**

```bash
uv run pytest -q
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_engine_role_routers.py
git commit -m "feat(runtime): Agent resolves per-role model via model_fn(role=...)"
```

---

### Task 5: Patterns pass role vocabulary

**Files:**
- Modify: `astromesh/orchestration/patterns.py` (ReAct, PlanAndExecute, ParallelFanOut, Pipeline), `astromesh/orchestration/supervisor.py`, `astromesh/orchestration/swarm.py`
- Test: `tests/test_patterns_roles.py` (new)

**Interfaces:**
- Consumes: `model_fn(messages, tools, role=None)` (Task 4).
- Produces: each pattern passes a `role=` kwarg at its decision points per the vocabulary table. All existing `model_fn(messages, tools)` calls become `model_fn(messages, tools, role="<name>")`. `role` is keyword — existing pattern tests using `AsyncMock` remain valid.

Vocabulary: ReAct→`reasoner`; PlanAndExecute→`planner`(plan)/`worker`(exec)/`synthesizer`(final); ParallelFanOut→`planner`(decompose)/`worker`(subtask)/`synthesizer`(aggregate); Pipeline→`stage:<name>` per stage; Supervisor→`supervisor`; Swarm→`reasoner`.

- [ ] **Step 1: Write the failing test**

`tests/test_patterns_roles.py`:

```python
"""Assert each pattern requests the correct role at each decision point."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from astromesh.orchestration.patterns import (
    ParallelFanOutPattern,
    PipelinePattern,
    PlanAndExecutePattern,
    ReActPattern,
)


@dataclass
class Resp:
    content: str
    tool_calls: list | None = None
    reasoning_content: str | None = None


def _roles_used(model_fn_mock):
    return [c.kwargs.get("role") for c in model_fn_mock.await_args_list]


async def test_react_uses_reasoner():
    model_fn = AsyncMock(return_value=Resp("done"))
    await ReActPattern().execute("q", {}, model_fn, AsyncMock(), [])
    assert _roles_used(model_fn) == ["reasoner"]


async def test_plan_and_execute_role_sequence():
    model_fn = AsyncMock(
        side_effect=[
            Resp('{"steps": [{"step": 1, "description": "do", "tool": null}]}'),
            Resp("step done"),
            Resp("final"),
        ]
    )
    await PlanAndExecutePattern().execute("q", {}, model_fn, AsyncMock(), [])
    assert _roles_used(model_fn) == ["planner", "worker", "synthesizer"]


async def test_parallel_fan_out_role_sequence():
    model_fn = AsyncMock(
        side_effect=[Resp('["a", "b"]'), Resp("ra"), Resp("rb"), Resp("agg")]
    )
    await ParallelFanOutPattern().execute("q", {}, model_fn, AsyncMock(), [])
    roles = _roles_used(model_fn)
    assert roles[0] == "planner"
    assert roles[1] == "worker" and roles[2] == "worker"
    assert roles[-1] == "synthesizer"


async def test_pipeline_uses_stage_roles():
    model_fn = AsyncMock(side_effect=[Resp("a"), Resp("b"), Resp("c")])
    await PipelinePattern(stages=["analyze", "process", "synthesize"]).execute(
        "q", {}, model_fn, AsyncMock(), []
    )
    assert _roles_used(model_fn) == ["stage:analyze", "stage:process", "stage:synthesize"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_patterns_roles.py -v`
Expected: FAIL (roles come back as `[None, ...]` because patterns don't pass `role=` yet)

- [ ] **Step 3: Update ReAct**

In `astromesh/orchestration/patterns.py`, `ReActPattern.execute`, change:

```python
            response = await model_fn(messages, tools)
```
to:
```python
            response = await model_fn(messages, tools, role="reasoner")
```

- [ ] **Step 4: Update PlanAndExecute**

In `PlanAndExecutePattern.execute`:
- Plan call: `await model_fn([{"role": "user", "content": plan_prompt}], tools, role="planner")`
- Step exec call: `await model_fn([{"role": "user", "content": step_query}], tools, role="worker")`
- Synthesis call: `await model_fn([{"role": "user", "content": synthesis_prompt}], [], role="synthesizer")`

- [ ] **Step 5: Update ParallelFanOut**

In `ParallelFanOutPattern.execute`:
- Decompose call: `... role="planner"`
- Inside `run_subtask`: `resp = await model_fn([{"role": "user", "content": subtask}], tools, role="worker")`
- Aggregate call: `... role="synthesizer"`

- [ ] **Step 6: Update Pipeline**

In `PipelinePattern.execute`, the per-stage call:

```python
            response = await model_fn([{"role": "user", "content": prompt}], tools, role=f"stage:{stage}")
```

- [ ] **Step 7: Update Supervisor and Swarm**

In `astromesh/orchestration/supervisor.py`, `SupervisorPattern.execute`, the model call:

```python
            response = await model_fn(
                [{"role": "user", "content": supervisor_prompt}], tools, role="supervisor"
            )
```

In `astromesh/orchestration/swarm.py`, add `role="reasoner"` to each `model_fn(...)` call (read the file first; apply to every reasoning call — Swarm may have multiple).

- [ ] **Step 8: Run role + existing pattern tests**

Run: `uv run pytest tests/test_patterns_roles.py tests/test_patterns.py -v`
Expected: PASS (new role tests + existing pattern tests unchanged — `AsyncMock` accepts the extra kwarg)

- [ ] **Step 9: Full regression + commit**

```bash
uv run pytest -q
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/orchestration/ tests/test_patterns_roles.py
git commit -m "feat(orchestration): patterns request per-role models (reasoner/planner/worker/...)"
```

---

### Task 6: Example agent + CHANGELOG

**Files:**
- Create: `config/agents/role-router-demo.agent.yaml`
- Modify: `CHANGELOG.md`
- Test: `tests/test_engine.py` (append a build-smoke test) OR reuse existing config-loading test

**Interfaces:**
- Consumes: the full feature (Tasks 1–5).
- Produces: a loadable example agent proving `default` + `roles` + mixed sources parse and build.

- [ ] **Step 1: Write the example agent YAML**

`config/agents/role-router-demo.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: role-router-demo
  version: "0.1.0"
  namespace: demo

spec:
  identity:
    display_name: "Role Router Demo"
    description: "Demonstrates per-role models across sources"

  model:
    default:
      candidates:
        - {source: ollama, model: "llama3.1:8b", endpoint: "http://localhost:11434"}
      strategy: cost_optimized
    roles:
      planner:
        candidates:
          - {source: litellm, model: "anthropic/claude-opus-4-8", api_key_env: ANTHROPIC_API_KEY}
        strategy: quality_first
      worker:
        candidates:
          - {source: ollama, model: "llama3.1:8b"}
        strategy: cost_optimized

  prompts:
    system: |
      You are a demo agent. Plan with the strong model, execute with the cheap one.

  orchestration:
    pattern: plan_and_execute
    max_iterations: 6
```

- [ ] **Step 2: Write the build-smoke test**

Append to `tests/test_engine_role_routers.py`:

```python
def test_demo_agent_builds_role_routers():
    import yaml
    from pathlib import Path

    cfg = yaml.safe_load(Path("config/agents/role-router-demo.agent.yaml").read_text())
    rt = _runtime()
    routers = rt._build_role_routers(cfg["spec"]["model"])
    assert set(routers.keys()) == {"default", "planner", "worker"}
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/test_engine_role_routers.py::test_demo_agent_builds_role_routers -v`
Expected: PASS

- [ ] **Step 4: Update CHANGELOG**

In `CHANGELOG.md`, under `## [Unreleased]` → `### Added (Backend)` (create the section if missing):

```markdown
### Added (Backend)
- **Per-role models per architecture:** agents can declare `spec.model.default` and
  `spec.model.roles.<name>` (candidates + strategy). Orchestration patterns request a
  role at each decision point (ReAct→`reasoner`; PlanAndExecute→`planner`/`worker`/
  `synthesizer`; ParallelFanOut→`planner`/`worker`/`synthesizer`; Pipeline→`stage:<name>`;
  Supervisor→`supervisor`; Swarm→`reasoner`). Undefined roles fall back to `default`.
  Optional `orchestration.role_map` remaps roles.
- **LiteLLM provider source:** `source: litellm` gives access to 100+ cloud models
  (Anthropic, Gemini, Bedrock, Groq, Mistral, Azure…) via the optional `litellm` extra.
- Legacy `model.primary`/`fallback`/`extra`/`routing` still work unchanged (normalized
  into the `default` role).
```

- [ ] **Step 5: Commit**

```bash
git add config/agents/role-router-demo.agent.yaml tests/test_engine_role_routers.py CHANGELOG.md
git commit -m "feat(config): role-router demo agent + changelog for per-role models"
```

---

### Task 7: Public docs site (LAST — only after Tasks 1–6 ship green)

**Files:**
- Modify: `docs-site/src/content/docs/configuration/providers.md`
- Modify: `docs-site/src/content/docs/configuration/agent-yaml.md`
- Modify: `docs-site/src/content/docs/reference/core/model-router.md`

**Interfaces:**
- Consumes: shipped, tested behavior from Tasks 1–5.
- Produces: present-tense documentation (no "planned"/"coming soon" language).

- [ ] **Step 1: Verify the feature is green**

Run: `uv run pytest -q`
Expected: full suite PASS. Do not proceed if red.

- [ ] **Step 2: Document per-role schema in `agent-yaml.md`**

Add a "Per-role models" section to `docs-site/src/content/docs/configuration/agent-yaml.md` showing `spec.model.default` + `spec.model.roles.<name>` with the `{source, model, endpoint?, api_key_env?, strategy?}` candidate shape, plus the role vocabulary table (ReAct/PlanAndExecute/ParallelFanOut/Pipeline/Supervisor/Swarm) and `orchestration.role_map`. State that legacy `primary/fallback/extra` still works (normalized to `default`). Use the `role-router-demo.agent.yaml` as the worked example.

- [ ] **Step 3: Document `source: litellm` in `providers.md`**

Add a "LiteLLM source (cloud multi-provider)" subsection to `docs-site/src/content/docs/configuration/providers.md`: install with `uv sync --extra litellm` (or `--extra all`), the model-prefix convention (`anthropic/…`, `gemini/…`, `groq/…`), auth via `api_key_env`, and that a missing `litellm` install skips the candidate with a warning (other candidates in the role still register).

- [ ] **Step 4: Document per-role routing in `model-router.md`**

In `docs-site/src/content/docs/reference/core/model-router.md`, add a "Per-role routers" note: one `ModelRouter` per role, isolated circuit breakers, `model_fn(messages, tools, role=...)` selection, fallback to `default`.

- [ ] **Step 5: Build the docs site to verify no broken MDX**

Run: `cd docs-site && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add docs-site/src/content/docs/configuration/providers.md \
        docs-site/src/content/docs/configuration/agent-yaml.md \
        docs-site/src/content/docs/reference/core/model-router.md
git commit -m "docs(site): document per-role models and LiteLLM source"
```

---

## Self-Review

**Spec coverage:**
- Per-role `ModelRouter` dict (Option A) → Tasks 3, 4. ✓
- `model_fn(role=...)` + role_map resolution → Task 4. ✓
- YAML schema `default`/`roles`/candidate block → Tasks 3, 6. ✓
- Backward-compat normalization (primary/fallback/extra/routing → default) → Task 3 (+ explicit test). ✓
- Pattern → role vocabulary (all 6 patterns) → Task 5. ✓
- `LiteLLMProvider` + optional dep + skip-on-missing → Tasks 1, 2. ✓
- Cost/usage/reasoning passthrough → Task 1. ✓
- Observability `role` span attribute → Task 4 Step 4. ✓
- Testing (provider, normalization, resolution, per-pattern) → Tasks 1, 3, 4, 5. ✓
- Rollout order incl. docs last → Task ordering + Task 7. ✓

**Placeholder scan:** No TBD/TODO. Swarm's calls are handled by "read the file first, apply to every call" because `swarm.py` was not read at plan time — this is an explicit, bounded instruction, not a placeholder.

**Type consistency:** `build_candidate_provider` (module fn), `_normalize_model_spec`/`_build_role_routers` (AgentRuntime methods), `Agent(routers=...)`, `model_fn(messages, tools, role=None)`, resolution `role_map[role] → routers[...] → routers["default"]` — consistent across Tasks 2–5. `Agent` param renamed `router`→`routers` everywhere it is constructed (Task 3 Step 4, Task 4 Steps 3/5).

## Execution Handoff

Two execution options — see below.
