"""El ejemplo de config/ construye y su bundle es conformante."""

from pathlib import Path

import yaml

from astromesh.knowledge.okf import Bundle
from astromesh.knowledge.tools import TOOL_NAMES
from astromesh.runtime.engine import AgentRuntime


def test_demo_agent_builds_with_the_bundle_tools():
    cfg = yaml.safe_load(Path("config/agents/okf-demo.agent.yaml").read_text())
    agent = AgentRuntime(config_dir="./config")._build_agent(cfg)
    names = {s["function"]["name"] for s in agent._tools.get_tool_schemas()}
    assert set(TOOL_NAMES) <= names


def test_demo_bundle_has_no_invalid_concepts():
    result = Bundle(Path("config/knowledge/okf-demo")).find(include_deprecated=True)
    assert result["skipped_invalid"] == 0
    assert len(result["results"]) == 3
