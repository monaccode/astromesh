import pytest

from astromesh_glyph.capabilities import CapabilitySpec
from astromesh_glyph.errors import GlyphCompileError
from astromesh_glyph.plan.compiler import compile_program
from astromesh_glyph.syntax.parser import parse

CAPS = [
    CapabilitySpec(
        name="search",
        description="busca repuestos",
        parameters={
            "type": "object",
            "properties": {"make": {"type": "string"}, "year": {"type": "integer"}},
            "required": ["make"],
        },
    ),
    CapabilitySpec(
        name="restock",
        description="consulta reposición",
        parameters={"type": "object", "properties": {"sku": {"type": "string"}}},
    ),
    CapabilitySpec(name="ask", description="pregunta al modelo", parameters={}, is_semantic=True),
]


def _compile(source):
    return compile_program(parse(source), CAPS)


def test_independent_statements_do_not_depend_on_each_other():
    graph = _compile('a = search(make="T")\nb = search(make="H")\n')
    assert [node.depends_on for node in graph.nodes] == [frozenset(), frozenset()]


def test_a_statement_depends_on_the_variables_it_reads():
    graph = _compile('v = search(make="T")\nx = v | top(1)\n')
    assert graph.nodes[1].depends_on == frozenset({"v"})


def test_produces_records_the_assigned_name():
    graph = _compile('v = search(make="T")\n')
    assert graph.nodes[0].produces == frozenset({"v"})


def test_a_bare_call_produces_nothing():
    graph = _compile('restock(sku="a")\n')
    assert graph.nodes[0].produces == frozenset()


def test_an_if_declares_everything_its_branches_may_write():
    """Aunque la rama no corra: si no, los nodos que leen `r` esperan para siempre."""
    graph = _compile(
        'v = search(make="T")\n'
        "if v.empty:\n"
        '    r = restock(sku="a")\n'
        "else:\n"
        '    s = restock(sku="b")\n'
    )
    assert graph.nodes[1].produces == frozenset({"r", "s"})


def test_the_same_name_may_be_bound_in_both_branches():
    """No es reasignar: corre una rama sola. Es el patrón más natural que hay."""
    graph = _compile(
        'v = search(make="T")\n'
        "if v.empty:\n"
        '    r = restock(sku="a")\n'
        "else:\n"
        '    r = restock(sku="b")\n'
        "return {r}\n"
    )
    assert graph.nodes[1].produces == frozenset({"r"})
    assert graph.nodes[2].depends_on == frozenset({"r"})


def test_reassignment_inside_a_single_branch_is_still_rejected():
    with pytest.raises(GlyphCompileError, match="ya está ligada"):
        _compile(
            'v = search(make="T")\n'
            "if v.empty:\n"
            '    r = restock(sku="a")\n'
            '    r = restock(sku="b")\n'
        )


def test_a_branch_cannot_rebind_a_name_from_an_outer_statement():
    with pytest.raises(GlyphCompileError, match="ya está ligada"):
        _compile('v = search(make="T")\nif v.empty:\n    v = search(make="H")\n')


def test_if_depends_on_the_variables_of_its_test_and_its_body():
    graph = _compile('v = search(make="T")\nif v.empty:\n    r = restock(sku="a")\n')
    assert graph.nodes[1].depends_on == frozenset({"v"})


def test_names_bound_inside_an_if_are_visible_afterwards():
    graph = _compile('v = search(make="T")\nif v.empty:\n    r = restock(sku="a")\nreturn {r}\n')
    assert graph.nodes[2].depends_on == frozenset({"r"})


def test_unknown_capability_is_rejected_with_the_line():
    with pytest.raises(GlyphCompileError, match="no existe") as exc:
        _compile('a = search(make="T")\nb = inventar(x=1)\n')
    assert exc.value.line == 2


def test_unknown_keyword_argument_is_rejected():
    with pytest.raises(GlyphCompileError, match="no acepta el argumento `color`"):
        _compile('a = search(make="T", color="rojo")\n')


def test_missing_required_argument_is_rejected():
    with pytest.raises(GlyphCompileError, match="requiere `make`"):
        _compile("a = search(year=2019)\n")


def test_positional_arguments_to_a_capability_are_rejected():
    with pytest.raises(GlyphCompileError, match="por nombre"):
        _compile('a = search("Toyota")\n')


def test_undefined_variable_is_rejected():
    with pytest.raises(GlyphCompileError, match="no está definida"):
        _compile("a = search(make=marca)\n")


def test_reassignment_is_rejected():
    with pytest.raises(GlyphCompileError, match="ya está ligada"):
        _compile('a = search(make="T")\na = search(make="H")\n')


def test_unknown_pipe_stage_is_rejected():
    with pytest.raises(GlyphCompileError, match="etapa"):
        _compile('a = search(make="T")\nb = a | ordenar(1)\n')


def test_builtin_stages_are_not_looked_up_as_capabilities():
    graph = _compile('a = search(make="T")\nb = a | where(kind == "oem") | top(3, by=rating)\n')
    assert graph.nodes[1].depends_on == frozenset({"a"})


def test_dependents_lists_the_nodes_that_read_a_node_output():
    graph = _compile('v = search(make="T")\nx = v | top(1)\n')
    assert graph.dependents(graph.nodes[0].id) == (graph.nodes[1].id,)
