"""Client tools: the runtime announces them to the model and does not execute them."""

from __future__ import annotations

from astromesh.core.tools import ToolRegistry, ToolType


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
