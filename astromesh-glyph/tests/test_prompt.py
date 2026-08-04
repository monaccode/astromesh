from astromesh_glyph.capabilities import CapabilitySpec
from astromesh_glyph.prompt.builder import build_system_block, extract_program
from astromesh_glyph.prompt.grammar import GRAMMAR

CAPS = [
    CapabilitySpec(
        name="search",
        description="Busca repuestos por vehículo",
        parameters={
            "type": "object",
            "properties": {"make": {"type": "string"}, "year": {"type": "integer"}},
            "required": ["make"],
        },
        returns="lista de {sku, kind, price}",
    ),
    CapabilitySpec(name="ask", description="Consulta al modelo", parameters={}, is_semantic=True),
]


def test_the_block_contains_the_grammar_and_the_catalog():
    block = build_system_block(CAPS)
    assert GRAMMAR in block
    assert "search" in block
    assert "Busca repuestos por vehículo" in block


def test_parameters_are_rendered_with_type_and_requiredness():
    block = build_system_block(CAPS)
    assert "make: string (requerido)" in block
    assert "year: integer" in block


def test_semantic_capabilities_are_marked_as_costly():
    assert "cuesta una llamada al modelo" in build_system_block(CAPS)


def test_the_return_shape_is_published():
    """Sin esto el modelo inventa nombres de campo y el pipe filtra a vacío en silencio."""
    assert "→ devuelve lista de {sku, kind, price}" in build_system_block(CAPS)


def test_a_capability_without_a_declared_shape_renders_no_arrow():
    block = build_system_block([CapabilitySpec(name="ping", description="d", parameters={})])
    assert "→" not in block.split("Capacidades disponibles:")[1]


def test_the_grammar_warns_that_invented_fields_fail_silently():
    assert "filtra a vacío en silencio" in GRAMMAR


def test_the_grammar_block_stays_small():
    """Es el único costo fijo por turno que agrega Glyph; si crece, come el ahorro."""
    assert len(GRAMMAR) < 2400


def test_extract_program_strips_a_fenced_block():
    text = 'Acá va:\n```glyph\nx = search(make="T")\n```\nlisto'
    assert extract_program(text) == 'x = search(make="T")'


def test_extract_program_handles_an_unlabelled_fence():
    assert extract_program("```\nx = 1\n```") == "x = 1"


def test_extract_program_returns_bare_text_untouched():
    assert extract_program("x = 1\n") == "x = 1"
