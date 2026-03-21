import pytest
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture
def config_dir(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-agent.agent.yaml").write_text("""
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
    assert "primary" in agent._router._providers


async def test_runtime_missing_agent(config_dir):
    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()
    with pytest.raises(ValueError, match="not found"):
        await runtime.run("nonexistent", "hello", "s1")


async def test_runtime_list_agents(config_dir):
    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()
    agents = runtime.list_agents()
    assert len(agents) == 1
    assert agents[0]["name"] == "test-agent"
