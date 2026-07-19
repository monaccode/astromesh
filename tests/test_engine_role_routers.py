"""Tests for source-aware candidate building and per-role routers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from astromesh.core.memory import MemoryManager
from astromesh.core.model_router import ModelRouter
from astromesh.core.prompt_engine import PromptEngine
from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.patterns import ReActPattern
from astromesh.providers.base import CompletionResponse
from astromesh.providers.litellm_provider import LiteLLMProvider
from astromesh.providers.ollama_provider import OllamaProvider
from astromesh.providers.openai_compat import OpenAICompatProvider
from astromesh.runtime.engine import Agent, AgentRuntime, build_candidate_provider


def test_builds_ollama_from_source():
    prov = build_candidate_provider({"source": "ollama", "model": "llama3.1:8b"})
    assert isinstance(prov, OllamaProvider)


def test_builds_litellm_from_source(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider(
        {
            "source": "litellm",
            "model": "anthropic/claude-opus-4-8",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
    )
    assert isinstance(prov, LiteLLMProvider)


def test_infers_litellm_from_prefixed_model(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
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


@pytest.mark.parametrize(
    "source,model",
    [
        ("ollama", "llama3.1:8b"),
        ("openai_compat", "gpt-4o-mini"),
        ("openai", "gpt-4o-mini"),
        ("azure_openai", "gpt-4o-mini"),
        ("litellm", "anthropic/claude-opus-4-8"),
    ],
)
def test_timeout_propagates_from_block(monkeypatch, source, model):
    """Every source must honour an explicit `timeout` from the model block.

    Regression: the openai_compat branch dropped the key, so the provider fell
    back to its 120s default no matter what the agent declared.
    """
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider({"source": source, "model": model, "timeout": 600})
    assert prov is not None
    assert prov.timeout == 600.0


@pytest.mark.parametrize(
    "source,model",
    [
        ("openai_compat", "gpt-4o-mini"),
        ("litellm", "anthropic/claude-opus-4-8"),
    ],
)
def test_parameters_propagate_from_block(monkeypatch, source, model):
    """`parameters` must reach the provider, not just `timeout`.

    Regression: the openai_compat branch dropped this key too, so per-model
    temperature/max_tokens declared in the agent YAML were a silent no-op.
    """
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider(
        {"source": source, "model": model, "parameters": {"temperature": 0.25}}
    )
    assert prov is not None
    assert prov.parameters == {"temperature": 0.25}


@pytest.mark.parametrize(
    "source,model",
    [
        ("openai_compat", "gpt-4o-mini"),
        ("litellm", "anthropic/claude-opus-4-8"),
    ],
)
def test_parameters_default_to_empty_when_absent(monkeypatch, source, model):
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider({"source": source, "model": model})
    assert prov is not None
    assert prov.parameters == {}


@pytest.mark.parametrize(
    "source,model",
    [
        ("ollama", "llama3.1:8b"),
        ("openai_compat", "gpt-4o-mini"),
        ("litellm", "anthropic/claude-opus-4-8"),
    ],
)
def test_timeout_defaults_to_120_when_absent(monkeypatch, source, model):
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider({"source": source, "model": model})
    assert prov is not None
    assert prov.timeout == 120.0


def test_litellm_missing_dependency_skips_candidate(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    def boom():
        raise ImportError("litellm not installed")

    monkeypatch.setattr(_llm, "_import_litellm", boom)
    assert (
        build_candidate_provider({"source": "litellm", "model": "anthropic/claude-opus-4-8"})
        is None
    )


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


def test_emptied_role_is_omitted_and_falls_back(monkeypatch):
    from astromesh.providers import litellm_provider as _llm

    def boom():
        raise ImportError("litellm not installed")

    monkeypatch.setattr(_llm, "_import_litellm", boom)
    rt = _runtime()
    spec = {
        "default": {"candidates": [{"source": "ollama", "model": "llama3.1:8b"}]},
        "roles": {
            "planner": {"candidates": [{"source": "litellm", "model": "anthropic/claude-opus-4-8"}]}
        },
    }
    routers = rt._build_role_routers(spec)
    assert "planner" not in routers  # emptied role omitted -> model_fn falls back to 'default'
    assert "default" in routers


def _make_router_returning(tag):
    router = ModelRouter({"strategy": "cost_optimized"})
    resp = CompletionResponse(
        content=tag, model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0
    )
    router.route = AsyncMock(return_value=resp)
    return router


def _agent_with(routers, role_map=None):
    return Agent(
        name="t",
        version="0.1.0",
        namespace="default",
        description="",
        routers=routers,
        memory=MemoryManager(agent_id="t", config={}),
        tools=ToolRegistry(),
        pattern=ReActPattern(),
        system_prompt="sys",
        prompt_engine=PromptEngine(),
        guardrails={},
        permissions={},
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

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        r = await model_fn([{"role": "user", "content": query}], tools, role="reasoner")
        return {"answer": r.content, "steps": []}

    monkeypatch.setattr(pmod.ReActPattern, "execute", execute)
    out = await agent.run("hi", session_id="s")
    assert out["answer"] == "P"  # reasoner -> planner via role_map


def test_demo_agent_builds_role_routers(monkeypatch):
    import yaml
    from pathlib import Path

    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())  # pretend litellm is installed
    cfg = yaml.safe_load(Path("config/agents/role-router-demo.agent.yaml").read_text())
    rt = _runtime()
    routers = rt._build_role_routers(cfg["spec"]["model"])
    assert set(routers.keys()) == {"default", "planner", "worker"}
