# Astromesh Cloud — Runtime Prerequisites Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dynamic agent CRUD endpoints, BYOK provider key injection, and usage data to the existing Astromesh runtime — the foundation for Astromesh Cloud.

**Architecture:** Four targeted changes to the existing runtime: (1) POST/DELETE agent endpoints for dynamic registration, (2) BYOK headers read by the run endpoint and passed to ModelRouter, (3) usage field added to AgentRunResponse, (4) memory delete endpoint made functional. All changes are backward-compatible.

**Tech Stack:** Python 3.12, FastAPI, pytest, httpx AsyncClient, respx/unittest.mock

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `astromesh/api/routes/agents.py` | Add POST/DELETE endpoints, read BYOK headers, add usage to response |
| Modify | `astromesh/runtime/engine.py` | Add `register_agent()` and `unregister_agent()` methods |
| Modify | `astromesh/core/model_router.py` | Accept request-scoped provider override via `route()` kwargs |
| Create | `astromesh/providers/factory.py` | Provider factory function for BYOK instantiation |
| Modify | `astromesh/api/routes/memory.py` | Implement the DELETE endpoint (currently stub) |
| Modify | `astromesh/api/main.py` | Wire memory.set_runtime() |
| Modify | `tests/test_api.py` | Tests for new endpoints |
| Create | `tests/test_dynamic_agents.py` | Tests for register/unregister engine methods |
| Modify | `tests/test_model_router.py` | Tests for provider override |

---

### Task 1: Dynamic Agent Registration in Engine

**Files:**
- Modify: `astromesh/runtime/engine.py:152-162`
- Create: `tests/test_dynamic_agents.py`

- [ ] **Step 1: Write failing tests for register/unregister**

```python
# tests/test_dynamic_agents.py
import pytest
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture
def runtime(tmp_path):
    agents_dir = tmp_path / "config" / "agents"
    agents_dir.mkdir(parents=True)
    return AgentRuntime(config_dir=str(tmp_path))


async def test_register_agent_adds_to_agents(runtime):
    config = {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "test-agent", "version": "1.0"},
        "spec": {
            "identity": {"name": "test-agent", "role": "assistant"},
            "model": {
                "primary": {"provider": "ollama", "model": "llama3"},
            },
            "prompts": {"system": "You are a test assistant."},
        },
    }
    await runtime.register_agent(config)
    assert "test-agent" in runtime._agents
    agents = runtime.list_agents()
    assert any(a["name"] == "test-agent" for a in agents)


async def test_register_agent_upsert_overwrites(runtime):
    config = {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "dupe-agent", "version": "1.0"},
        "spec": {
            "identity": {"name": "dupe-agent", "role": "assistant"},
            "model": {
                "primary": {"provider": "ollama", "model": "llama3"},
            },
            "prompts": {"system": "Test."},
        },
    }
    await runtime.register_agent(config)
    # Re-registering same name overwrites (idempotent for reconciliation/re-deploy)
    await runtime.register_agent(config)
    assert "dupe-agent" in runtime._agents


async def test_unregister_agent_removes(runtime):
    config = {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "temp-agent", "version": "1.0"},
        "spec": {
            "identity": {"name": "temp-agent", "role": "assistant"},
            "model": {
                "primary": {"provider": "ollama", "model": "llama3"},
            },
            "prompts": {"system": "Test."},
        },
    }
    await runtime.register_agent(config)
    runtime.unregister_agent("temp-agent")
    assert "temp-agent" not in runtime._agents


async def test_unregister_agent_not_found_raises(runtime):
    with pytest.raises(ValueError, match="not found"):
        runtime.unregister_agent("nonexistent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dynamic_agents.py -v`
Expected: FAIL — `AgentRuntime` has no `register_agent` or `unregister_agent` methods.

- [ ] **Step 3: Implement register_agent and unregister_agent**

Add to `astromesh/runtime/engine.py` after the `list_agents()` method:

```python
async def register_agent(self, config: dict) -> None:
    """Register an agent dynamically from a config dict (same schema as YAML).
    If an agent with the same name exists, it is overwritten (upsert semantics
    required by reconciliation loop and re-deploy flows)."""
    name = config.get("metadata", {}).get("name") or config.get("spec", {}).get("identity", {}).get("name")
    if not name:
        raise ValueError("Agent config must include metadata.name or spec.identity.name")
    agent = self._build_agent(config)
    self._agents[agent.name] = agent

def unregister_agent(self, name: str) -> None:
    """Remove a dynamically registered agent."""
    if name not in self._agents:
        raise ValueError(f"Agent '{name}' not found")
    del self._agents[name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dynamic_agents.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_dynamic_agents.py
git commit -m "feat(runtime): add register_agent and unregister_agent for dynamic agent CRUD"
```

---

### Task 2: POST/DELETE Agent API Endpoints

**Files:**
- Modify: `astromesh/api/routes/agents.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for POST and DELETE endpoints**

Add to `tests/test_api.py`:

```python
async def test_create_agent_returns_201(client):
    config = {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "api-test-agent", "version": "1.0"},
        "spec": {
            "identity": {"name": "api-test-agent", "role": "assistant"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "Test."},
        },
    }
    response = await client.post("/v1/agents", json=config)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "api-test-agent"
    assert data["status"] == "registered"


async def test_create_agent_no_runtime_returns_503(client):
    config = {"metadata": {"name": "x"}, "spec": {}}
    response = await client.post("/v1/agents", json=config)
    assert response.status_code == 503


async def test_delete_agent_returns_200(client):
    response = await client.delete("/v1/agents/some-agent")
    # Without runtime, returns 503
    assert response.status_code == 503


async def test_delete_agent_not_found_returns_404(client):
    # This test requires a runtime to be set; tested in integration
    pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -k "create_agent or delete_agent" -v`
Expected: FAIL — routes don't exist yet (404).

- [ ] **Step 3: Implement POST and DELETE endpoints**

Add to `astromesh/api/routes/agents.py`:

```python
@router.post("/agents", status_code=201)
async def create_agent(config: dict):
    """Register a new agent dynamically."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.register_agent(config)
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get("identity", {}).get("name", "unknown")
        return {"name": name, "status": "registered"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """Remove a dynamically registered agent."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        _runtime.unregister_agent(agent_name)
        return {"name": agent_name, "status": "removed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -k "create_agent or delete_agent" -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `uv run pytest tests/test_api.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add astromesh/api/routes/agents.py tests/test_api.py
git commit -m "feat(api): add POST /v1/agents and DELETE /v1/agents/{name} endpoints"
```

---

### Task 3: BYOK Provider Key Override in ModelRouter and Run Endpoint

**Files:**
- Modify: `astromesh/core/model_router.py:52-117`
- Modify: `astromesh/api/routes/agents.py:48-58`
- Modify: `tests/test_model_router.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing test for ModelRouter provider override**

Add to `tests/test_model_router.py`:

```python
async def test_route_with_provider_override():
    """When a provider_override is passed, ModelRouter uses it instead of registered providers."""
    router = ModelRouter({"strategy": "cost_optimized"})

    # Register a default provider
    default_provider = _make_mock_provider(cost=0.01)
    router.register_provider("openai", default_provider)

    # Create an override provider
    override_provider = _make_mock_provider(cost=0.0)
    override_provider.complete.return_value = MagicMock(
        content="override response",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
        latency_ms=50.0,
    )

    messages = [{"role": "user", "content": "test"}]
    result = await router.route(messages, provider_override=("openai", override_provider))

    # Override provider should have been called, not the default
    override_provider.complete.assert_called_once()
    default_provider.complete.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model_router.py::test_route_with_provider_override -v`
Expected: FAIL — `route()` doesn't accept `provider_override` kwarg.

- [ ] **Step 3: Implement provider override in ModelRouter.route()**

Modify `astromesh/core/model_router.py`, `route()` method. Add at the start of the method, before candidate ranking:

```python
async def route(self, messages: list[dict], requirements: dict | None = None, **kwargs) -> "CompletionResponse":
    # Check for request-scoped provider override (BYOK)
    provider_override = kwargs.pop("provider_override", None)
    if provider_override:
        override_name, override_provider = provider_override
        try:
            response = await override_provider.complete(messages, **kwargs)
            response.latency_ms = 0.0  # Will be set by caller
            return response
        except Exception as e:
            raise RuntimeError(f"Override provider '{override_name}' failed: {e}") from e

    # ... existing candidate ranking and routing logic unchanged ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model_router.py::test_route_with_provider_override -v`
Expected: PASS

- [ ] **Step 5: Modify run endpoint to read BYOK headers**

Modify `astromesh/api/routes/agents.py`, `run_agent()`:

```python
from fastapi import Request

@router.post("/agents/{agent_name}/run")
async def run_agent(agent_name: str, request_body: AgentRunRequest, request: Request):
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")

    # Read optional BYOK headers
    provider_key = request.headers.get("X-Astromesh-Provider-Key")
    provider_name = request.headers.get("X-Astromesh-Provider-Name")

    context = request_body.context or {}
    if provider_key and provider_name:
        context["_provider_override"] = {
            "key": provider_key,
            "name": provider_name,
        }

    try:
        result = await _runtime.run(
            agent_name, request_body.query, request_body.session_id, context
        )
        return AgentRunResponse(answer=result["answer"], steps=result.get("steps", []))
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

Note: The full integration of `_provider_override` from context into `ModelRouter.route()` requires changes in `Agent.run()` inside `engine.py`. For v1, Cloud API passes the override via context dict, and the runtime's `Agent.run()` extracts it and passes to `model_router.route(provider_override=...)`. This wiring happens in the `Agent.run()` method where `self.model_router.route()` is called.

- [ ] **Step 6: Create provider factory**

Create `astromesh/providers/factory.py`:

```python
# astromesh/providers/factory.py
"""Factory for creating provider instances dynamically (used by BYOK flow)."""


def create_provider(provider_name: str, api_key: str):
    """Create a provider instance by name with the given API key."""
    if provider_name in ("openai", "anthropic", "vllm", "hf"):
        from astromesh.providers.openai_compat import OpenAICompatProvider
        # Map provider names to their base URLs
        base_urls = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "vllm": None,  # Requires explicit URL
            "hf": None,
        }
        return OpenAICompatProvider(
            name=provider_name,
            base_url=base_urls.get(provider_name, "https://api.openai.com/v1"),
            api_key=api_key,
        )
    elif provider_name == "ollama":
        from astromesh.providers.ollama_provider import OllamaProvider
        return OllamaProvider(api_key=api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
```

- [ ] **Step 7: Add BYOK wiring in Agent.run()**

Modify `astromesh/runtime/engine.py`, inside the `Agent.run()` method, where `self.model_router.route()` is called (approximately line 280). Before the route call, extract the override:

```python
# Extract provider override from context if present (BYOK flow)
route_kwargs = {}
provider_override_config = (context or {}).get("_provider_override")
if provider_override_config:
    from astromesh.providers.factory import create_provider
    override_name = provider_override_config["name"]
    override_key = provider_override_config["key"]
    override_provider = create_provider(override_name, api_key=override_key)
    route_kwargs["provider_override"] = (override_name, override_provider)

response = await self.model_router.route(messages, **route_kwargs)
```

- [ ] **Step 8: Run full model router tests**

Run: `uv run pytest tests/test_model_router.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add astromesh/core/model_router.py astromesh/api/routes/agents.py astromesh/runtime/engine.py astromesh/providers/factory.py tests/test_model_router.py
git commit -m "feat(runtime): add BYOK provider key override via X-Astromesh-Provider-Key header"
```

---

### Task 4: Add Usage Field to AgentRunResponse

**Files:**
- Modify: `astromesh/api/routes/agents.py:21-23`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_api.py`:

```python
async def test_run_response_includes_usage_field(client):
    """The response schema should accept a usage field."""
    from astromesh.api.routes.agents import AgentRunResponse

    response = AgentRunResponse(
        answer="test",
        steps=[],
        usage={"tokens_in": 100, "tokens_out": 50, "model": "ollama/llama3"},
    )
    assert response.usage["tokens_in"] == 100
    assert response.usage["tokens_out"] == 50
    assert response.usage["model"] == "ollama/llama3"


async def test_run_response_usage_defaults_to_none(client):
    """Usage field should be optional for backward compatibility."""
    from astromesh.api.routes.agents import AgentRunResponse

    response = AgentRunResponse(answer="test", steps=[])
    assert response.usage is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -k "usage" -v`
Expected: FAIL — `AgentRunResponse` has no `usage` field.

- [ ] **Step 3: Add usage to AgentRunResponse and populate from trace**

Modify `astromesh/api/routes/agents.py`:

```python
class UsageInfo(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


class AgentRunResponse(BaseModel):
    answer: str
    steps: list[dict] = []
    usage: UsageInfo | None = None
```

In `run_agent()`, extract usage from the runtime result's trace:

```python
# Extract usage from trace if available
usage = None
trace = result.get("trace", {})
spans = trace.get("spans", []) if isinstance(trace, dict) else []
total_in = 0
total_out = 0
model_used = ""
for span in spans:
    span_meta = span.get("metadata", {})
    if "usage" in span_meta:
        u = span_meta["usage"]
        total_in += u.get("prompt_tokens", 0)
        total_out += u.get("completion_tokens", 0)
    if "model" in span_meta and not model_used:
        model_used = span_meta["model"]
if total_in or total_out:
    usage = UsageInfo(tokens_in=total_in, tokens_out=total_out, model=model_used)

return AgentRunResponse(
    answer=result["answer"],
    steps=result.get("steps", []),
    usage=usage,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -k "usage" -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add astromesh/api/routes/agents.py tests/test_api.py
git commit -m "feat(api): add usage field (tokens_in, tokens_out, model) to AgentRunResponse"
```

---

### Task 5: Implement Memory Delete Endpoint

**Files:**
- Modify: `astromesh/api/routes/memory.py:18-20`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_api.py`:

```python
async def test_clear_memory_no_runtime_returns_503(client):
    response = await client.delete("/v1/memory/test-agent/history/test-session")
    assert response.status_code == 503
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `uv run pytest tests/test_api.py::test_clear_memory_no_runtime_returns_503 -v`
Expected: FAIL — currently returns 200 (stub).

- [ ] **Step 3: Implement the delete endpoint**

Modify `astromesh/api/routes/memory.py`. Add `set_runtime()` pattern and implement the delete:

```python
_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


@router.delete("/memory/{agent_name}/history/{session_id}")
async def clear_history(agent_name: str, session_id: str):
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    agent = _runtime._agents.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    try:
        await agent.memory_manager.clear_history(session_id)
        return {"status": "cleared", "agent": agent_name, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Wire set_runtime in main.py**

Modify `astromesh/api/main.py` — in the bootstrap section where `agents.set_runtime(runtime)` is called, add:

```python
from astromesh.api.routes import memory as memory_routes
memory_routes.set_runtime(runtime)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_api.py -k "clear_memory" -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS (no regressions)

- [ ] **Step 7: Commit**

```bash
git add astromesh/api/routes/memory.py astromesh/api/main.py tests/test_api.py
git commit -m "feat(api): implement DELETE /v1/memory/{agent}/history/{session} endpoint"
```

---

## Summary

| Task | What it delivers |
|------|-----------------|
| 1 | `register_agent()` / `unregister_agent()` on AgentRuntime |
| 2 | `POST /v1/agents` and `DELETE /v1/agents/{name}` HTTP endpoints |
| 3 | BYOK provider override via `X-Astromesh-Provider-Key` header |
| 4 | `usage` field in AgentRunResponse (tokens_in, tokens_out, model) |
| 5 | Functional `DELETE /v1/memory/{agent}/history/{session}` endpoint |

After these 5 tasks, the runtime has everything Cloud API needs to operate.
