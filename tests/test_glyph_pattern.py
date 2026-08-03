import pytest

from astromesh.core.tools import ToolRegistry
from astromesh.orchestration.glyph_pattern import GlyphPattern, PatternCapabilities

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


class ScriptedModel:
    """Devuelve respuestas prefijadas, en orden, y registra qué se le mandó."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    async def __call__(self, messages, tools, role=None):
        self.calls.append({"messages": messages, "tools": tools, "role": role})
        return FakeResponse(self._responses.pop(0))


PROGRAM = '```glyph\nv = search_parts(make="Toyota")\nreturn v\n```'


async def _run(model, tool_fn=None, **kwargs):
    async def _default_tool_fn(name, args):
        return [{"sku": "A"}]

    return await GlyphPattern(**kwargs).execute(
        query="necesito pastillas",
        context={},
        model_fn=model,
        tool_fn=tool_fn or _default_tool_fn,
        tools=TOOLS,
        max_iterations=6,
    )


async def test_the_happy_path_uses_exactly_two_model_calls():
    model = ScriptedModel(PROGRAM, "Encontré una opción.")
    result = await _run(model)
    assert result["answer"] == "Encontré una opción."
    assert len(model.calls) == 2


async def test_the_first_call_carries_the_grammar_and_the_catalog():
    model = ScriptedModel(PROGRAM, "listo")
    await _run(model)
    content = model.calls[0]["messages"][-1]["content"]
    assert "```glyph" in content
    assert "search_parts" in content
    assert "necesito pastillas" in content


async def test_the_first_call_offers_no_tools():
    """Si se le ofrecen tools, el modelo emite tool_calls en vez de un programa."""
    model = ScriptedModel(PROGRAM, "listo")
    await _run(model)
    assert model.calls[0]["tools"] == []


async def test_steps_carry_one_entry_per_capability_call():
    model = ScriptedModel(PROGRAM, "listo")
    result = await _run(model)
    tool_steps = [s for s in result["steps"] if s.action]
    assert [s.action for s in tool_steps] == ["search_parts"]
    assert tool_steps[0].action_input == {"make": "Toyota"}


async def test_the_final_step_carries_the_answer():
    model = ScriptedModel(PROGRAM, "listo")
    result = await _run(model)
    assert result["steps"][-1].result == "listo"


async def test_a_syntax_error_triggers_one_repair():
    model = ScriptedModel("```glyph\nv = = 1\n```", PROGRAM, "reparado")
    result = await _run(model)
    assert result["answer"] == "reparado"
    assert len(model.calls) == 3
    assert "línea 1" in model.calls[1]["messages"][-1]["content"]


async def test_a_compile_error_names_the_missing_capability():
    model = ScriptedModel("```glyph\nv = inventada(x=1)\n```", PROGRAM, "reparado")
    await _run(model)
    assert "no existe" in model.calls[1]["messages"][-1]["content"]


async def test_repairs_are_capped_and_the_failure_is_reported():
    bad = "```glyph\nv = = 1\n```"
    model = ScriptedModel(bad, bad, bad)
    result = await _run(model, max_repairs=2)
    assert "no pudo" in result["answer"].lower()
    assert result["glyph"]["repairs"] == 2


async def test_an_execution_failure_sends_the_partial_state_to_the_model():
    async def tool_fn(name, args):
        raise RuntimeError("503 del proveedor")

    model = ScriptedModel(PROGRAM, PROGRAM, "reparado")
    await _run(model, tool_fn=tool_fn)
    repair_prompt = model.calls[1]["messages"][-1]["content"]
    assert "503" in repair_prompt


async def test_the_result_reports_counters_for_the_benchmark():
    model = ScriptedModel(PROGRAM, "listo")
    result = await _run(model)
    assert result["glyph"]["model_calls"] == 2
    assert result["glyph"]["capability_calls"] == 1
    assert result["glyph"]["semantic_calls"] == 0
    assert result["glyph"]["repairs"] == 0
