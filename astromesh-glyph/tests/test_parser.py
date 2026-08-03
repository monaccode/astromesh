import pytest
from hypothesis import given
from hypothesis import strategies as st

from astromesh_glyph.errors import GlyphSyntaxError
from astromesh_glyph.syntax import nodes as n
from astromesh_glyph.syntax.parser import parse


def test_assignment_of_a_call_with_kwargs():
    program = parse('v = search(make="Toyota", year=2019)\n')
    (stmt,) = program.body
    assert isinstance(stmt, n.Assign)
    assert stmt.target == "v"
    assert isinstance(stmt.value, n.Call)
    assert stmt.value.func == "search"
    assert stmt.value.args == []
    assert stmt.value.kwargs["make"].value == "Toyota"
    assert stmt.value.kwargs["year"].value == 2019


def test_positional_and_keyword_arguments_together():
    program = parse("x = top(3, by=rating)\n")
    call = program.body[0].value
    assert [a.value for a in call.args] == [3]
    assert isinstance(call.kwargs["by"], n.Name)


def test_dotted_capability_name():
    program = parse("x = agent.email_composer(lead)\n")
    assert program.body[0].value.func == "agent.email_composer"


def test_pipe_collects_stages_in_a_single_node():
    program = parse('oem = v | where(kind == "oem") | top(3, by=rating)\n')
    pipe = program.body[0].value
    assert isinstance(pipe, n.Pipe)
    assert isinstance(pipe.left, n.Name)
    assert [s.func for s in pipe.stages] == ["where", "top"]


def test_comparison_inside_a_stage_argument():
    program = parse("x = v | where(score > 0.75)\n")
    pred = program.body[0].value.stages[0].args[0]
    assert isinstance(pred, n.BinOp)
    assert pred.op == ">"
    assert pred.right.value == 0.75


def test_multiple_stage_arguments_stay_separate():
    program = parse('x = v | where(kind == "oem", stock > 0)\n')
    assert len(program.body[0].value.stages[0].args) == 2


def test_if_else_with_blocks():
    program = parse("if a.empty:\n    b = f()\nelse:\n    c = g()\n")
    (stmt,) = program.body
    assert isinstance(stmt, n.If)
    assert isinstance(stmt.test, n.Attribute)
    assert stmt.test.attr == "empty"
    assert len(stmt.body) == 1
    assert len(stmt.orelse) == 1


def test_if_without_else_has_empty_orelse():
    program = parse("if a:\n    b = f()\n")
    assert program.body[0].orelse == []


def test_dict_shorthand_infers_the_key_from_the_name():
    program = parse("return {oem, alt}\n")
    items = program.body[0].value.items
    assert [k for k, _ in items] == ["oem", "alt"]
    assert all(isinstance(v, n.Name) for _, v in items)


def test_dict_with_explicit_keys():
    program = parse("return {name: full_name, tier: 2}\n")
    items = dict(program.body[0].value.items)
    assert isinstance(items["name"], n.Name)
    assert items["tier"].value == 2


def test_list_literal():
    program = parse("x = [1, 2, 3]\n")
    assert [e.value for e in program.body[0].value.items] == [1, 2, 3]


def test_booleans_and_null_are_literals():
    program = parse("x = [true, false, null]\n")
    assert [e.value for e in program.body[0].value.items] == [True, False, None]


def test_bare_call_is_an_expression_statement():
    program = parse('crm.tag(lead, "cold")\n')
    assert isinstance(program.body[0], n.ExprStmt)


def test_return_without_value():
    program = parse("return\n")
    assert program.body[0].value is None


def test_and_binds_tighter_than_or():
    program = parse("x = v | where(a or b and c)\n")
    top = program.body[0].value.stages[0].args[0]
    assert top.op == "or"
    assert top.right.op == "and"


def test_unexpected_token_raises_with_position():
    with pytest.raises(GlyphSyntaxError) as exc:
        parse("x = = 1\n")
    assert exc.value.line == 1


def test_missing_colon_after_if_is_rejected():
    with pytest.raises(GlyphSyntaxError, match="`:`"):
        parse("if a\n    b = 1\n")


_IDENTIFIERS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=8).filter(
    lambda s: s not in {"if", "else", "return", "and", "or", "true", "false", "null"}
)


@given(
    target=_IDENTIFIERS,
    func=_IDENTIFIERS,
    key=_IDENTIFIERS,
    value=st.integers(min_value=-1000, max_value=1000),
)
def test_roundtrip_of_a_generated_assignment(target, func, key, value):
    """Todo programa generado desde la gramática parsea al AST esperado.

    Es la garantía que sostiene el resto: si el parser acepta algo distinto de lo
    que la gramática del prompt le enseña al modelo, cada programa válido que el
    modelo escriba puede fallar y no vamos a saber por qué.
    """
    program = parse(f"{target} = {func}({key}={value})\n")
    (stmt,) = program.body
    assert stmt.target == target
    assert stmt.value.func == func
    assert stmt.value.kwargs[key].value == value
