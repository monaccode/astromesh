from astromesh.orchestration.glyph_pattern import GlyphPattern
from astromesh.orchestration.patterns import ReActPattern, with_turn_context

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

PROGRAM = '```glyph\nv = search_parts(make="Toyota")\nreturn v\n```'


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None
        self.usage = {"input_tokens": 10, "output_tokens": 5}


class ScriptedModel:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    async def __call__(self, messages, tools, role=None):
        self.calls.append(messages)
        return FakeResponse(self._responses.pop(0))


async def _tool_fn(name, args):
    return [{"sku": "A"}]


def test_with_turn_context_string():
    assert with_turn_context("hola", "DOCS: x") == "DOCS: x\n\nhola"


def test_with_turn_context_multimodal():
    parts = [{"type": "text", "text": "mirá"}, {"type": "image_url", "image_url": {}}]
    assert with_turn_context(parts, "DOCS: x") == [{"type": "text", "text": "DOCS: x"}, *parts]


def test_with_turn_context_vacio_deja_la_query():
    assert with_turn_context("hola", None) == "hola"
    assert with_turn_context("hola", "") == "hola"
    parts = [{"type": "text", "text": "mirá"}]
    assert with_turn_context(parts, None) is parts


def test_los_patrones_declaran_que_consumen_el_contexto():
    assert ReActPattern.consumes_turn_context is True
    assert GlyphPattern.consumes_turn_context is True


async def test_react_antepone_el_contexto_al_ultimo_mensaje():
    model = ScriptedModel("listo")
    history = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}]
    await ReActPattern().execute(
        query="q",
        context={"_history_messages": history, "_turn_context": "DOCS: x"},
        model_fn=model,
        tool_fn=None,
        tools=[],
    )
    assert model.calls[0] == [*history, {"role": "user", "content": "DOCS: x\n\nq"}]


async def test_react_sin_contexto_no_cambia():
    model = ScriptedModel("listo")
    await ReActPattern().execute(query="q", context={}, model_fn=model, tool_fn=None, tools=[])
    assert model.calls[0] == [{"role": "user", "content": "q"}]


async def test_glyph_lleva_el_contexto_en_la_query_y_en_la_narracion():
    sin = ScriptedModel(PROGRAM, "ok")
    await GlyphPattern().execute(
        query="necesito pastillas", context={}, model_fn=sin, tool_fn=_tool_fn, tools=TOOLS
    )
    con = ScriptedModel(PROGRAM, "ok")
    await GlyphPattern().execute(
        query="necesito pastillas",
        context={"_turn_context": "DOCS: x"},
        model_fn=con,
        tool_fn=_tool_fn,
        tools=TOOLS,
    )
    generacion = con.calls[0]
    # La gramática queda antes y sin tocar; sólo cambia el último mensaje.
    assert generacion[:-1] == sin.calls[0][:-1]
    assert generacion[-1] == {"role": "user", "content": "DOCS: x\n\nnecesito pastillas"}
    narracion = con.calls[1]
    assert narracion[0] == {"role": "user", "content": "DOCS: x\n\nnecesito pastillas"}


async def test_glyph_el_programa_ve_la_query_original():
    vistos = []

    async def tool_fn(name, args):
        vistos.append(args)
        return [{"sku": "A"}]

    async def explota(messages, tools, role=None):
        raise AssertionError("un programa fijo sin narración no llama al modelo")

    await GlyphPattern(program="v = search_parts(make=query)\nreturn v\n", narrate=False).execute(
        query=[{"type": "text", "text": "pastillas"}, {"type": "image_url", "image_url": {}}],
        context={"_caller_context": {}, "_turn_context": "DOCS: x"},
        model_fn=explota,
        tool_fn=tool_fn,
        tools=TOOLS,
    )
    assert vistos == [{"make": "pastillas"}]
