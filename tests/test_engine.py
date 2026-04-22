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


@pytest.fixture
def multi_provider_config_dir(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "multi-agent.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: multi-agent
  version: "0.1.0"
  namespace: test
spec:
  identity:
    display_name: "Multi Provider Agent"
    description: "Agent with primary + fallback + extra providers"
  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://localhost:11434"
    fallback:
      provider: openai_compat
      model: "gpt-4o-mini"
      endpoint: "https://api.openai.com/v1"
      api_key_env: OPENAI_API_KEY
    extra:
      cloud_claude:
        provider: openai_compat
        model: "claude-haiku-4-5"
        endpoint: "https://api.anthropic.com/v1"
        api_key_env: ANTHROPIC_API_KEY
      azure_primary:
        provider: azure_openai
        model: "gpt-4o"
        endpoint: "https://example.openai.azure.com"
        api_key_env: AZURE_OPENAI_KEY
      primary:
        provider: ollama
        model: "should-be-skipped"
    routing:
      strategy: cost_optimized
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 5
""")
    return str(tmp_path)


async def test_runtime_registers_extra_providers(multi_provider_config_dir):
    runtime = AgentRuntime(config_dir=multi_provider_config_dir)
    await runtime.bootstrap()
    agent = runtime._agents["multi-agent"]
    providers = agent._router._providers
    # primary + fallback + two valid extras; the `primary` key inside extra is rejected
    assert set(providers.keys()) == {"primary", "fallback", "cloud_claude", "azure_primary"}


async def test_runtime_extra_with_no_primary(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "extra-only.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: extra-only
  version: "0.1.0"
spec:
  identity:
    display_name: "Extra Only Agent"
  model:
    extra:
      local_ollama:
        provider: ollama
        model: "llama3.1:8b"
        endpoint: "http://localhost:11434"
    routing:
      strategy: cost_optimized
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 5
""")
    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()
    agent = runtime._agents["extra-only"]
    assert list(agent._router._providers.keys()) == ["local_ollama"]
