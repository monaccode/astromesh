"""Tests for AgentRuntime with ServiceManager integration."""

import pytest

from astromesh.runtime.engine import AgentRuntime
from astromesh.runtime.services import ServiceManager

AGENT_YAML = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
"""


@pytest.fixture
def agent_config(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text(AGENT_YAML)
    return tmp_path


async def test_bootstrap_with_agents_enabled(agent_config):
    sm = ServiceManager({"agents": True})
    runtime = AgentRuntime(config_dir=str(agent_config), service_manager=sm)
    await runtime.bootstrap()
    assert len(runtime._agents) == 1


async def test_bootstrap_with_agents_disabled(agent_config):
    sm = ServiceManager({"agents": False})
    runtime = AgentRuntime(config_dir=str(agent_config), service_manager=sm)
    await runtime.bootstrap()
    assert len(runtime._agents) == 0


async def test_bootstrap_without_service_manager(agent_config):
    runtime = AgentRuntime(config_dir=str(agent_config))
    await runtime.bootstrap()
    assert len(runtime._agents) == 1


def test_runtime_exposes_service_manager():
    sm = ServiceManager({"agents": True})
    runtime = AgentRuntime(service_manager=sm)
    assert runtime.service_manager is sm


def test_runtime_exposes_peer_client():
    from astromesh.runtime.peers import PeerClient

    pc = PeerClient([])
    runtime = AgentRuntime(peer_client=pc)
    assert runtime.peer_client is pc
