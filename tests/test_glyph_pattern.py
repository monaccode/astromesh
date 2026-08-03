import pytest

from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.glyph_pattern import PatternCapabilities

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_parts",
            "description": "Busca repuestos",
            "parameters": {
                "type": "object",
                "properties": {"make": {"type": "string"}},
                "required": ["make"],
            },
        },
    }
]


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None
        self.usage = {"input_tokens": 10, "output_tokens": 5}


def _make(tool_fn=None, model_fn=None):
    async def _default_tool_fn(name, args):
        return [{"sku": "A"}]

    async def _default_model_fn(messages, tools, role=None):
        return FakeResponse("resumen")

    return PatternCapabilities(
        tools=TOOLS,
        tool_fn=tool_fn or _default_tool_fn,
        model_fn=model_fn or _default_model_fn,
    )


def test_tool_schemas_become_capability_specs():
    caps = {c.name: c for c in _make().list_capabilities()}
    assert caps["search_parts"].description == "Busca repuestos"
    assert caps["search_parts"].parameters["required"] == ["make"]
    assert caps["search_parts"].is_semantic is False


def test_ask_is_added_as_a_semantic_capability():
    caps = {c.name: c for c in _make().list_capabilities()}
    assert caps["ask"].is_semantic is True
    assert "prompt" in caps["ask"].parameters["properties"]


def test_the_adapter_satisfies_the_glyph_protocol():
    from astromesh_glyph import CapabilityProvider

    assert isinstance(_make(), CapabilityProvider)


async def test_invoke_delegates_to_tool_fn():
    seen = []

    async def tool_fn(name, args):
        seen.append((name, args))
        return [{"sku": "A"}]

    result = await _make(tool_fn=tool_fn).invoke("search_parts", {"make": "T"})
    assert seen == [("search_parts", {"make": "T"})]
    assert result == [{"sku": "A"}]


async def test_invoke_of_ask_calls_the_model_and_counts_the_round_trip():
    caps = _make()
    result = await caps.invoke("ask", {"prompt": "resumí esto", "context": [{"a": 1}]})
    assert result == "resumen"
    assert caps.semantic_calls == 1


async def test_ask_sends_the_context_serialized_in_the_message():
    seen = []

    async def model_fn(messages, tools, role=None):
        seen.append(messages)
        return FakeResponse("ok")

    await _make(model_fn=model_fn).invoke("ask", {"prompt": "p", "context": [{"a": 1}]})
    content = seen[0][0]["content"]
    assert "p" in content
    assert '"a": 1' in content


async def test_ask_without_context_still_works():
    assert await _make().invoke("ask", {"prompt": "hola"}) == "resumen"


async def test_tool_invocations_do_not_count_as_semantic():
    caps = _make()
    await caps.invoke("search_parts", {"make": "T"})
    assert caps.semantic_calls == 0


def test_a_tool_schema_without_parameters_still_becomes_a_capability():
    caps = PatternCapabilities(
        tools=[{"type": "function", "function": {"name": "ping", "description": "d"}}],
        tool_fn=None,
        model_fn=None,
    )
    assert {c.name for c in caps.list_capabilities()} == {"ping", "ask"}


def test_a_tool_without_permission_never_reaches_the_glyph_catalog():
    """Los permisos se aplican antes del adapter, filtrando los schemas."""
    registry = ToolRegistry()
    registry.register_internal(
        "publica", lambda **kw: "ok", "Sin restricción", {"type": "object", "properties": {}}
    )
    registry.register_internal(
        "restringida",
        lambda **kw: "ok",
        "Requiere permiso",
        {"type": "object", "properties": {}},
        permissions=["admin"],
    )

    schemas = registry.get_tool_schemas(agent_permissions=["usuario"])
    caps = PatternCapabilities(tools=schemas, tool_fn=None, model_fn=None)
    names = {c.name for c in caps.list_capabilities()}

    assert "publica" in names
    assert "restringida" not in names


def test_a_program_calling_an_unavailable_capability_fails_at_compile_time():
    """Y falla antes de ejecutar nada: sin efectos, sin round-trip gastado."""
    from astromesh_glyph import GlyphCompileError, compile_program, parse

    caps = _make().list_capabilities()
    with pytest.raises(GlyphCompileError, match="no existe"):
        compile_program(parse("x = restringida()\n"), caps)
