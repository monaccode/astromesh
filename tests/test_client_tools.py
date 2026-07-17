"""Client tools: the runtime announces them to the model and does not execute them."""

from __future__ import annotations

import json
import logging
import pathlib
from unittest.mock import AsyncMock, MagicMock

import yaml

from astromesh.core.tools import ToolRegistry, ToolType
from astromesh.runtime.engine import Agent, AgentRuntime


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


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


def _agent_files():
    return sorted((REPO_ROOT / "config" / "agents").glob("*.agent.yaml"))


def test_no_shipped_agent_declares_a_tool_type_the_loader_drops():
    """A shipped example that lies about its tools teaches the lie."""
    supported = {"builtin", "agent", "client"}
    offenders = []
    for path in _agent_files():
        spec = yaml.safe_load(path.read_text())
        for tool in (spec.get("spec") or {}).get("tools", []) or []:
            tool_type = tool.get("type", "internal")
            if tool_type not in supported:
                offenders.append(f"{path.name}:{tool.get('name')} -> {tool_type}")
    assert offenders == []


def test_the_configuration_guide_lists_the_types_that_actually_load():
    guide = (REPO_ROOT / "docs" / "CONFIGURATION_GUIDE.md").read_text()
    assert "builtin | agent | client" in guide
    assert "# internal | mcp | webhook | rag" not in guide


def _template_files():
    return sorted((REPO_ROOT / "config" / "templates").glob("*.template.yaml"))


def _template_tools(path: "pathlib.Path") -> list:
    """Templates nest the real agent spec under template.agent_config.spec.tools,
    not spec.tools directly — a different shape than config/agents/*.agent.yaml."""
    spec = yaml.safe_load(path.read_text())
    agent_config = (spec.get("template") or {}).get("agent_config") or {}
    return (agent_config.get("spec") or {}).get("tools", []) or []


def test_no_shipped_template_declares_type_internal():
    """The templates guard the original test missed: it only globbed config/agents/,
    so these — bundled into the wheel and served at /v1/templates, a wider-copied
    surface than the example agents — rotted unnoticed with the same 'internal'
    lie Task 4 fixed for config/agents/.

    Scoped to 'internal' specifically (not 'any type the loader drops'): a few
    templates also declare 'type: rag' under tools, which the loader equally
    drops today (RAG is wired through spec.knowledge, not spec.tools) — a
    real, separate, pre-existing bug outside this fix's scope. Widening this
    assertion to catch it too would require deciding what those tools should
    become, which nothing in this change directs.
    """
    offenders = []
    for path in _template_files():
        for tool in _template_tools(path):
            tool_type = tool.get("type", "internal")
            if tool_type == "internal":
                offenders.append(f"{path.name}:{tool.get('name')} -> {tool_type}")
    assert offenders == []


def test_agent_yaml_doc_does_not_teach_type_internal():
    doc = (
        REPO_ROOT / "docs-site" / "src" / "content" / "docs" / "configuration" / "agent-yaml.md"
    ).read_text()
    assert "type: internal" not in doc
    assert "builtin | agent | client" in doc
    assert "`internal` (Python function)" not in doc


def test_first_agent_doc_does_not_teach_type_internal():
    doc = (
        REPO_ROOT / "docs-site" / "src" / "content" / "docs" / "getting-started" / "first-agent.md"
    ).read_text()
    assert "type: internal" not in doc


def test_vscode_schema_tool_type_enum_matches_what_the_loader_supports():
    schema = json.loads(
        (REPO_ROOT / "vscode-extension" / "schemas" / "agent.schema.json").read_text()
    )
    tool_type_enum = schema["properties"]["spec"]["properties"]["tools"]["items"]["properties"][
        "type"
    ]["enum"]
    assert set(tool_type_enum) == {"builtin", "agent", "client"}


def _tool_schema(agent, tool_name: str) -> dict:
    return next(
        s["function"] for s in agent._tools.get_tool_schemas() if s["function"]["name"] == tool_name
    )


def test_yaml_shorthand_parameters_reach_the_model_as_valid_json_schema():
    """The bug: {param: {type, description}} shorthand passed through raw is not JSON Schema."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec(
            [
                {
                    "name": "lookup_company",
                    "type": "client",
                    "description": "Look up company information",
                    "parameters": {
                        "company_name": {
                            "type": "string",
                            "description": "Company name to look up",
                        }
                    },
                }
            ]
        )
    )
    schema = _tool_schema(agent, "lookup_company")["parameters"]
    assert schema["type"] == "object"
    assert schema["properties"] == {
        "company_name": {"type": "string", "description": "Company name to look up"}
    }


def test_already_valid_json_schema_parameters_pass_through_unchanged():
    """Idempotent: a YAML author who already writes real JSON Schema must not be rewritten."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec(
            [{"name": "show_thing", "type": "client", "description": "d", "parameters": PARAMS}]
        )
    )
    schema = _tool_schema(agent, "show_thing")["parameters"]
    assert schema == PARAMS


def test_absent_parameters_still_get_the_client_tool_default():
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec([{"name": "ping", "type": "client", "description": "d"}])
    )
    schema = _tool_schema(agent, "ping")["parameters"]
    assert schema == {"type": "object", "properties": {}}


def test_a_list_typed_parameters_block_warns_and_skips_only_that_tool(caplog):
    """YAML can write `parameters: [a, b]` — a list has no .get() and used to raise."""
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        agent = runtime._build_agent(
            _agent_spec(
                [
                    {
                        "name": "broken",
                        "type": "client",
                        "description": "d",
                        "parameters": ["a", "b"],
                    },
                    {"name": "fine", "type": "client", "description": "d"},
                ]
            )
        )
    assert "broken" in caplog.text
    assert "test-agent" in caplog.text
    names = [s["function"]["name"] for s in agent._tools.get_tool_schemas()]
    assert "broken" not in names
    assert "fine" in names


def test_a_string_typed_parameters_block_warns_and_skips_only_that_tool(caplog):
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        agent = runtime._build_agent(
            _agent_spec(
                [
                    {"name": "broken", "type": "client", "description": "d", "parameters": "oops"},
                    {"name": "fine", "type": "client", "description": "d"},
                ]
            )
        )
    assert "broken" in caplog.text
    names = [s["function"]["name"] for s in agent._tools.get_tool_schemas()]
    assert "broken" not in names
    assert "fine" in names


def test_an_int_typed_parameters_block_warns_and_skips_only_that_tool(caplog):
    with caplog.at_level(logging.WARNING):
        runtime = AgentRuntime(config_dir="/nonexistent")
        agent = runtime._build_agent(
            _agent_spec(
                [
                    {"name": "broken", "type": "client", "description": "d", "parameters": 7},
                    {"name": "fine", "type": "client", "description": "d"},
                ]
            )
        )
    assert "broken" in caplog.text
    names = [s["function"]["name"] for s in agent._tools.get_tool_schemas()]
    assert "broken" not in names
    assert "fine" in names


def test_a_bare_type_object_schema_does_not_get_a_phantom_type_property():
    """{type: object} with no `properties` key is already-valid JSON Schema for a
    no-arg tool. The old check required `properties` to be present before treating
    a mapping as already-schema, so this fell through to the shorthand-wrapping
    branch and became {"type": "object", "properties": {"type": "object"}} — a
    phantom parameter literally named "type"."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    agent = runtime._build_agent(
        _agent_spec(
            [
                {
                    "name": "no_args",
                    "type": "client",
                    "description": "d",
                    "parameters": {"type": "object"},
                }
            ]
        )
    )
    schema = _tool_schema(agent, "no_args")["parameters"]
    assert schema == {"type": "object", "properties": {}}


def test_shipped_client_tools_emit_valid_json_schema():
    """This is the test that would have caught it: the real shipped YAMLs, not a hand-written fixture."""
    runtime = AgentRuntime(config_dir="/nonexistent")
    for path, tool_names in [
        (REPO_ROOT / "config" / "agents" / "sales-qualifier.agent.yaml", ["lookup_company"]),
        (
            REPO_ROOT / "config" / "agents" / "autolink-parts.agent.yaml",
            ["search_parts", "get_quote"],
        ),
    ]:
        config = yaml.safe_load(path.read_text())
        agent = runtime._build_agent(config)
        for tool_name in tool_names:
            schema = _tool_schema(agent, tool_name)["parameters"]
            assert schema.get("type") == "object", f"{path.name}:{tool_name} -> {schema}"
            assert "properties" in schema, f"{path.name}:{tool_name} -> {schema}"
            for param_name, param_schema in schema["properties"].items():
                assert "type" in param_schema, (
                    f"{path.name}:{tool_name}.{param_name} -> {param_schema}"
                )
