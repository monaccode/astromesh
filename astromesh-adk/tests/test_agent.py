import pytest
from astromesh_adk.agent import agent, Agent, AgentWrapper
from astromesh_adk.tools import tool


@tool(description="Add numbers")
async def add(a: int, b: int) -> int:
    return a + b


# --- Decorator tests ---

@agent(name="simple", model="ollama/llama3", description="Simple agent")
async def simple_agent(ctx):
    """You are a simple assistant."""
    return None


@agent(
    name="configured",
    model="openai/gpt-4o",
    fallback_model="ollama/llama3",
    tools=[add],
    pattern="react",
    max_iterations=5,
    memory="sqlite",
    routing="cost_optimized",
    guardrails={"input": ["pii_detection"], "output": []},
)
async def configured_agent(ctx):
    """You are a configured agent."""
    return None


def test_agent_decorator_creates_wrapper():
    assert isinstance(simple_agent, AgentWrapper)


def test_agent_wrapper_name():
    assert simple_agent.name == "simple"
    assert configured_agent.name == "configured"


def test_agent_wrapper_model():
    assert simple_agent.model == "ollama/llama3"
    assert configured_agent.model == "openai/gpt-4o"


def test_agent_wrapper_description():
    assert simple_agent.description == "Simple agent"


def test_agent_wrapper_system_prompt():
    assert simple_agent.system_prompt == "You are a simple assistant."


def test_agent_wrapper_tools():
    assert len(configured_agent.tools) == 1


def test_agent_wrapper_pattern():
    assert simple_agent.pattern == "react"  # default
    assert configured_agent.pattern == "react"


def test_agent_wrapper_fallback():
    assert configured_agent.fallback_model == "ollama/llama3"
    assert simple_agent.fallback_model is None


def test_agent_wrapper_memory():
    assert configured_agent.memory_config is not None
    assert configured_agent.memory_config["conversational"]["backend"] == "sqlite"


def test_agent_wrapper_guardrails():
    assert len(configured_agent.guardrails_config["input"]) == 1


def test_agent_wrapper_has_run():
    assert hasattr(simple_agent, "run")
    assert callable(simple_agent.run)


def test_agent_wrapper_has_stream():
    assert hasattr(simple_agent, "stream")
    assert callable(simple_agent.stream)


def test_agent_wrapper_has_as_tool():
    assert hasattr(simple_agent, "as_tool")
    assert callable(simple_agent.as_tool)


def test_agent_as_tool():
    tool_def = simple_agent.as_tool()
    assert tool_def.tool_name == "simple"


# --- Class-based agent tests ---

class MyAgent(Agent):
    name = "custom"
    model = "ollama/llama3"
    description = "Custom agent"
    tools = [add]
    pattern = "plan_and_execute"

    def system_prompt_fn(self, ctx):
        return f"You help {ctx.user_id}"


def test_class_agent_attributes():
    a = MyAgent()
    assert a.name == "custom"
    assert a.model == "ollama/llama3"
    assert a.pattern == "plan_and_execute"
    assert len(a.tools) == 1


def test_class_agent_has_run():
    a = MyAgent()
    assert hasattr(a, "run")
    assert callable(a.run)


def test_class_agent_has_stream():
    a = MyAgent()
    assert hasattr(a, "stream")


def test_class_agent_has_as_tool():
    a = MyAgent()
    tool_def = a.as_tool()
    assert tool_def.tool_name == "custom"
