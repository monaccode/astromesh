import pytest
from unittest.mock import AsyncMock, MagicMock
from astromesh.runtime.engine import AgentRuntime
from astromesh.providers.base import CompletionResponse


async def test_full_agent_run(tmp_path):
    """End-to-end test: load agent from YAML, register mock provider, run query."""
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
    description: Echoes back the user message
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "Echo the user's message back."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert "echo" in runtime._agents
    agent = runtime._agents["echo"]

    mock_response = CompletionResponse(
        content="Echo: hello world",
        model="test-model",
        provider="ollama",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        latency_ms=50,
        cost=0.001,
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(return_value=mock_response)
    mock_provider.estimated_cost = MagicMock(return_value=0.001)
    mock_provider.supports_tools = MagicMock(return_value=True)
    mock_provider.supports_vision = MagicMock(return_value=False)

    agent._router._providers.clear()
    agent._router._health.clear()
    agent._router.register_provider("test", mock_provider)

    result = await runtime.run("echo", "hello world", "test-session-1")
    assert result["answer"] == "Echo: hello world"
    assert "steps" in result


async def test_full_agent_run_with_tool(tmp_path):
    """End-to-end test: agent uses a tool during execution."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "tool-agent.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: tool-agent
  version: "0.1.0"
  namespace: test
spec:
  identity:
    display_name: Tool Agent
    description: An agent that uses tools
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a helpful assistant with tools."
  orchestration:
    pattern: react
    max_iterations: 5
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    agent = runtime._agents["tool-agent"]

    # Register a tool
    async def calculator(**kwargs):
        return {"result": kwargs.get("a", 0) + kwargs.get("b", 0)}

    agent._tools.register_internal("add", calculator, "Add two numbers",
        {"a": {"type": "number"}, "b": {"type": "number"}})

    # First call: model returns tool call. Second call: model returns final answer.
    tool_call_response = CompletionResponse(
        content="Let me calculate that.",
        model="test", provider="ollama",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        latency_ms=50, cost=0.001,
        tool_calls=[{"id": "tc1", "name": "add", "arguments": {"a": 3, "b": 4}}],
    )
    final_response = CompletionResponse(
        content="The result is 7.",
        model="test", provider="ollama",
        usage={"input_tokens": 15, "output_tokens": 5, "total_tokens": 20},
        latency_ms=40, cost=0.001,
    )

    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(side_effect=[tool_call_response, final_response])
    mock_provider.estimated_cost = MagicMock(return_value=0.001)
    mock_provider.supports_tools = MagicMock(return_value=True)
    mock_provider.supports_vision = MagicMock(return_value=False)

    agent._router._providers.clear()
    agent._router._health.clear()
    agent._router.register_provider("test", mock_provider)

    result = await runtime.run("tool-agent", "What is 3 + 4?", "test-session-2")
    assert result["answer"] == "The result is 7."
    assert len(result["steps"]) == 2


async def test_multiple_agents(tmp_path):
    """Test loading multiple agents from config directory."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    for name in ["agent-a", "agent-b", "agent-c"]:
        (agents_dir / f"{name}.agent.yaml").write_text(f"""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: {name}
  version: "1.0.0"
  namespace: test
spec:
  identity:
    display_name: "{name}"
    description: "Test agent {name}"
  model:
    primary:
      provider: ollama
      model: test
      endpoint: http://localhost:11434
  prompts:
    system: "You are {name}."
  orchestration:
    pattern: react
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    agents_list = runtime.list_agents()
    assert len(agents_list) == 3
    names = {a["name"] for a in agents_list}
    assert names == {"agent-a", "agent-b", "agent-c"}


async def test_runtime_missing_agent_raises(tmp_path):
    """Test that running a nonexistent agent raises ValueError."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    with pytest.raises(ValueError, match="not found"):
        await runtime.run("nonexistent", "hello", "session")
