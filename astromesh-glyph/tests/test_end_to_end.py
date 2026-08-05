"""El camino completo: texto del modelo -> parse -> compile -> execute."""

from astromesh_glyph import build_system_block, compile_program, execute, extract_program, parse
from astromesh_glyph.capabilities import CapabilitySpec

CAPS = [
    CapabilitySpec(
        name="search_parts",
        description="Busca repuestos",
        parameters={
            "type": "object",
            "properties": {"make": {"type": "string"}, "part": {"type": "string"}},
            "required": ["make"],
        },
    ),
    CapabilitySpec(
        name="check_restock",
        description="Consulta reposición",
        parameters={"type": "object", "properties": {"sku": {"type": "string"}}},
    ),
]

PARTS = [
    {"sku": "A", "kind": "oem", "price": 30, "rating": 5, "stock": 4},
    {"sku": "B", "kind": "aftermarket", "price": 10, "rating": 3, "stock": 0},
    {"sku": "C", "kind": "aftermarket", "price": 20, "rating": 4, "stock": 7},
]


class Provider:
    def list_capabilities(self):
        return CAPS

    async def invoke(self, name, args):
        if name == "search_parts":
            return PARTS
        if name == "check_restock":
            return {"eta_days": 5}
        raise AssertionError(name)


MODEL_OUTPUT = """Voy a buscar y comparar:

```glyph
v = search_parts(make="Toyota", part="pastillas")
oem = v | where(kind == "oem") | top(3, by=rating)
alt = v | where(kind == "aftermarket", stock > 0) | top(3, by=price)
return {oem, alt}
```
"""


async def test_the_spec_example_runs_end_to_end():
    program = parse(extract_program(MODEL_OUTPUT))
    graph = compile_program(program, CAPS)
    result = await execute(graph, Provider())

    assert [r["sku"] for r in result.value["oem"]] == ["A"]
    assert [r["sku"] for r in result.value["alt"]] == ["C"]
    # Una sola llamada a la capacidad, reutilizada por las dos ramas del pipe.
    assert len(result.calls) == 1


async def test_a_conditional_branch_runs_against_real_data():
    source = (
        'v = search_parts(make="Toyota")\n'
        'oem = v | where(kind == "inexistente")\n'
        "if oem.empty:\n"
        "    eta = check_restock(sku=v.first.sku)\n"
        "return {eta}\n"
    )
    graph = compile_program(parse(source), CAPS)
    result = await execute(graph, Provider())
    assert result.value["eta"] == {"eta_days": 5}


def test_the_system_block_advertises_every_capability():
    block = build_system_block(CAPS)
    assert "search_parts" in block
    assert "check_restock" in block
