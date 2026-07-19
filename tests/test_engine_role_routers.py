"""Tests for source-aware candidate building and per-role routers."""

from __future__ import annotations

import logging
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


# ---------------------------------------------------------------------------
# Declared-but-dropped keys — the failure family behind the timeout/parameters
# bugs: a key the schema accepts, the wiring ignores, and nobody is told about.
# ---------------------------------------------------------------------------


def test_warns_when_a_declared_key_is_not_consumed(monkeypatch, caplog):
    """`endpoint` means nothing to litellm (it routes by model prefix), so
    declaring one must say so rather than disappear."""
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    with caplog.at_level(logging.WARNING):
        build_candidate_provider(
            {
                "source": "litellm",
                "model": "anthropic/claude-opus-4-8",
                "endpoint": "https://example.invalid/v1",
            }
        )
    assert "endpoint" in caplog.text
    assert "litellm" in caplog.text


def test_warns_for_key_unused_by_this_source_only(caplog):
    """`timeout` is honoured by three sources but not by centinela; the warning
    is per-source, not global."""
    with caplog.at_level(logging.WARNING):
        build_candidate_provider(
            {"source": "centinela", "model": "c", "endpoint": "https://x", "timeout": 300}
        )
    assert "timeout" in caplog.text


def test_no_warning_for_a_fully_consumed_block(caplog):
    with caplog.at_level(logging.WARNING):
        build_candidate_provider(
            {
                "source": "openai_compat",
                "model": "gpt-4o-mini",
                "endpoint": "https://api.openai.com/v1",
                "api_key": "sk-x",
                "timeout": 600,
                "parameters": {"temperature": 0.2},
            }
        )
    assert caplog.text == ""


def test_no_warning_for_none_valued_keys_from_provider_ref(monkeypatch, caplog):
    """resolve_block() injects endpoint/contract/... as None for every source.
    Warning on those would fire on every providerRef block and train people to
    ignore the warning entirely."""
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    with caplog.at_level(logging.WARNING):
        build_candidate_provider(
            {
                "source": "litellm",
                "model": "anthropic/claude-opus-4-8",
                "endpoint": None,
                "endpoint_name": None,
                "contract": None,
            }
        )
    assert caplog.text == ""


@pytest.mark.parametrize(
    "source,model",
    [
        ("ollama", "llama3.1:8b"),
        ("openai_compat", "gpt-4o-mini"),
        ("litellm", "anthropic/claude-opus-4-8"),
    ],
)
def test_top_level_temperature_shorthand_folds_into_parameters(monkeypatch, source, model):
    """The schema calls `temperature` a "top-level shorthand for
    parameters.temperature"; it was never read by anything."""
    from astromesh.providers import litellm_provider as _llm

    monkeypatch.setattr(_llm, "_import_litellm", lambda: object())
    prov = build_candidate_provider(
        {"source": source, "model": model, "temperature": 0.4, "max_tokens": 256}
    )
    assert prov.parameters == {"temperature": 0.4, "max_tokens": 256}


def test_explicit_parameters_win_over_shorthand():
    prov = build_candidate_provider(
        {
            "source": "openai_compat",
            "model": "gpt-4o-mini",
            "temperature": 0.4,
            "parameters": {"temperature": 0.9},
        }
    )
    assert prov.parameters["temperature"] == 0.9


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
        ("ollama", "llama3.1:8b"),
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
        ("ollama", "llama3.1:8b"),
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
