"""`spec.knowledge.bundle` en el engine: tools registradas y `bundle_index` en el template."""

import logging
from pathlib import Path

import pytest

from astromesh.knowledge.okf import Bundle
from astromesh.knowledge.tools import TOOL_NAMES
from astromesh.runtime.engine import Agent, AgentRuntime

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "okf"


def _config(knowledge, tools=None):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "kb-agent", "version": "1.0.0"},
        "spec": {
            "model": {"primary": {"provider": "ollama", "model": "llama3.1:8b"}},
            "orchestration": {"pattern": "react"},
            "knowledge": knowledge,
            "tools": tools or [],
        },
    }


def _names(agent):
    return {s["function"]["name"] for s in agent._tools.get_tool_schemas()}


def test_relative_bundle_resolves_against_config_dir():
    agent = AgentRuntime(config_dir=str(FIX.parent))._build_agent(_config({"bundle": "okf"}))
    assert set(TOOL_NAMES) <= _names(agent)


def test_absolute_bundle_path():
    agent = AgentRuntime(config_dir="./config")._build_agent(_config({"bundle": str(FIX)}))
    assert set(TOOL_NAMES) <= _names(agent)


def test_missing_bundle_warns_and_registers_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        agent = AgentRuntime(config_dir=str(FIX.parent))._build_agent(_config({"bundle": "nope"}))
    assert not set(TOOL_NAMES) & _names(agent)
    assert "knowledge.bundle" in caplog.text


def test_declared_tool_with_a_kb_name_collides():
    with pytest.raises(ValueError, match="kb_read"):
        AgentRuntime(config_dir=str(FIX.parent))._build_agent(
            _config({"bundle": "okf"}, tools=[{"name": "kb_read", "type": "agent", "agent": "x"}])
        )


def test_bundle_and_pipeline_coexist():
    agent = AgentRuntime(config_dir=str(FIX.parent))._build_agent(
        _config({"bundle": "okf", "pipeline": "unknown-pipeline"})
    )
    assert set(TOOL_NAMES) <= _names(agent)


class _RecordingPromptEngine:
    def __init__(self):
        self.context = None

    def render(self, template, context):
        self.context = context
        return "SYSTEM"


class _StubPattern:
    async def execute(self, *a, **k):
        return {"answer": "ok"}


class _StubMemory:
    async def build_context(self, *a, **k):
        return {}

    def fit_history(self, context, budget):
        return {"turns_kept": 0, "turns_dropped": 0, "tokens": 0, "summary_used": False}

    async def persist_turn(self, *a, **k):
        return None


class _StubTools:
    def get_tool_schemas(self, *a, **k):
        return []


def _runner(bundle):
    pe = _RecordingPromptEngine()
    runner = Agent(
        name="a1",
        version="1",
        namespace="default",
        description="",
        routers={"default": None},
        memory=_StubMemory(),
        tools=_StubTools(),
        pattern=_StubPattern(),
        system_prompt="hola",
        prompt_engine=pe,
        guardrails={},
        orchestration_config={},
        bundle=bundle,
    )
    return runner, pe


async def test_bundle_index_reaches_the_template():
    runner, pe = _runner(Bundle(FIX))
    await runner.run("hola", session_id="s1")
    assert pe.context["bundle_index"].startswith("# Subdirectories")


async def test_no_bundle_gives_empty_bundle_index():
    runner, pe = _runner(None)
    await runner.run("hola", session_id="s1")
    assert pe.context["bundle_index"] == ""


async def test_bundle_that_disappears_does_not_break_the_run(tmp_path):
    root = tmp_path / "gone"
    root.mkdir()
    bundle = Bundle(root)
    root.rmdir()
    runner, pe = _runner(bundle)
    await runner.run("hola", session_id="s1")
    assert pe.context["bundle_index"] == ""
