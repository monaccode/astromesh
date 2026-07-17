"""Client tools: the runtime announces them to the model and does not execute them."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

from astromesh.core.tools import ToolRegistry, ToolType
from astromesh.runtime.engine import Agent, AgentRuntime


PARAMS = {
    "type": "object",
    "properties": {"label": {"type": "string", "description": "What to show"}},
    "required": ["label"],
}


def test_register_client_tool_records_it_as_client():
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="Show a thing", parameters=PARAMS)
    tool = tools._tools["show_thing"]
    assert tool.tool_type == ToolType.CLIENT
    assert tool.handler is None
    assert tool.parameters == PARAMS


def test_a_client_tool_is_offered_to_the_model():
    """If it isn't in the schemas the model never sees it and the feature doesn't exist."""
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="Show a thing", parameters=PARAMS)
    schemas = tools.get_tool_schemas()
    fn = next(s["function"] for s in schemas if s["function"]["name"] == "show_thing")
    assert fn["description"] == "Show a thing"
    assert fn["parameters"] == PARAMS


async def test_executing_a_client_tool_returns_ok_and_runs_nothing():
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="Show a thing", parameters=PARAMS)
    result = await tools.execute("show_thing", {"label": "hola"})
    assert result == {"ok": True}


async def test_a_client_tool_does_not_echo_its_arguments():
    """The model wrote the args; steps.action_input already carries them."""
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="d", parameters=PARAMS)
    result = await tools.execute("show_thing", {"label": "secreto"})
    assert "secreto" not in str(result)


async def test_a_client_tool_does_not_claim_delivery():
    """The runtime signals; it cannot know whether anyone listened."""
    tools = ToolRegistry()
    tools.register_client_tool(name="show_thing", description="d", parameters=PARAMS)
    result = await tools.execute("show_thing", {"label": "hola"})
    assert "delivered" not in result and "sent" not in result


def test_register_client_tool_defaults_its_parameters():
    tools = ToolRegistry()
    tools.register_client_tool(name="ping", description="d")
    assert tools._tools["ping"].parameters["type"] == "object"


async def test_an_unknown_tool_still_reports_not_found():
    """The pre-existing behavior for a name nobody registered."""
    tools = ToolRegistry()
    result = await tools.execute("nope", {})
    assert "error" in result


def _agent_spec(tools: list[dict]) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "test-agent", "version": "1.0.0"},
        "spec": {
            "identity": {"display_name": "Test", "description": "d"},
            "model": {
                "primary": {
                    "provider": "openai_compat",
                    "model": "gpt-4o-mini",
                    "endpoint": "https://example.invalid/v1",
                    "api_key_env": "NOPE_KEY",
                }
            },
            "prompts": {"system": "you are a test agent"},
            "orchestration": {"pattern": "react", "max_iterations": 3},
            "tools": tools,
        },
    }


def test_a_client_tool_declared_in_yaml_is_actually_registered():
    """The bug this whole change exists for: the loader used to discard it silently."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec(
            [
                {
                    "name": "diagram_process",
                    "type": "client",
                    "description": "Draw the process",
                    "parameters": {
                        "type": "object",
                        "properties": {"nodes": {"type": "array"}},
                    },
                }
            ]
        )
    )
    names = [s["function"]["name"] for s in agent._tools.get_tool_schemas()]
    assert "diagram_process" in names


def test_an_unsupported_tool_type_warns_and_names_what_it_dropped(caplog):
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        runtime._build_agent(
            _agent_spec([{"name": "lookup_company", "type": "internal", "description": "d"}])
        )
    assert "lookup_company" in caplog.text
    assert "test-agent" in caplog.text
    assert "internal" in caplog.text


def test_an_unsupported_tool_type_does_not_stop_the_agent_from_loading():
    """Raising would take bootstrap() down for every existing YAML with 'internal'."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec([{"name": "ghost", "type": "internal", "description": "d"}])
    )
    assert agent is not None
    assert "ghost" not in [s["function"]["name"] for s in agent._tools.get_tool_schemas()]


def test_a_tool_with_no_type_at_all_warns(caplog):
    """'internal' is the default, so a tool with no type silently didn't exist."""
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        runtime._build_agent(_agent_spec([{"name": "typeless", "description": "d"}]))
    assert "typeless" in caplog.text


class _FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.model = "fake-model"
        self.provider = "fake"
        self.latency_ms = 1
        self.cost = 0.0
        self.usage = {"input_tokens": 1, "output_tokens": 1}


class _CallsTheClientTool:
    """Stands in for a real pattern: drives the same closures every pattern drives."""

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        from astromesh.orchestration.patterns import AgentStep

        observation = await tool_fn("diagram_process", {"nodes": [{"id": "a"}]})
        return {
            "answer": "listo",
            "steps": [
                AgentStep(
                    action="diagram_process",
                    action_input={"nodes": [{"id": "a"}]},
                    observation=str(observation),
                )
            ],
        }


async def test_a_client_tool_reaches_a_consumer_live_and_in_steps():
    """The two paths of the contract. Neither alone is enough."""
    agent = Agent.__new__(Agent)
    agent.name = "test-agent"
    agent._pattern = _CallsTheClientTool()
    agent._role_map = {}
    agent._orchestration_config = {"pattern": "test"}
    agent._permissions = {}
    agent._guardrails = {}
    agent._rag = None
    agent._knowledge = None
    agent._system_prompt = "you are a test agent"

    router = MagicMock()
    router.route = AsyncMock(return_value=_FakeResponse(content="narrando"))
    agent._routers = {"default": router}

    tools = ToolRegistry()
    tools.register_client_tool(
        name="diagram_process",
        description="Draw the process",
        parameters={"type": "object", "properties": {"nodes": {"type": "array"}}},
    )
    agent._tools = tools

    memory = MagicMock()
    memory.build_context = AsyncMock(return_value=[])
    memory.persist_turn = AsyncMock()
    agent._memory = memory

    prompt = MagicMock()
    prompt.render = MagicMock(return_value="you are a test agent")
    agent._prompt_engine = prompt

    events = []
    result = await agent.run("hola", "s1", on_event=events.append)

    # Path 1: live.
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["name"] == "diagram_process"
    assert call["arguments"] == {"nodes": [{"id": "a"}]}
    assert next(e for e in events if e["type"] == "tool_result")["ok"] is True

    # Path 2: after the fact.
    step = result["steps"][0]
    assert step.action == "diagram_process"
    assert step.action_input == {"nodes": [{"id": "a"}]}
