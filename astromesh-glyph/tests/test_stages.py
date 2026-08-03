import pytest

from astromesh_glyph.errors import GlyphCompileError
from astromesh_glyph.runtime.stages import apply_stage
from astromesh_glyph.runtime.values import wrap
from astromesh_glyph.syntax.parser import parse

ITEMS = [
    {"sku": "A", "kind": "oem", "price": 30, "rating": 5, "stock": 2},
    {"sku": "B", "kind": "aftermarket", "price": 10, "rating": 3, "stock": 0},
    {"sku": "C", "kind": "aftermarket", "price": 20, "rating": 4, "stock": 7},
]


def _stage(source):
    """Extrae la primera etapa de `x = v | <source>`."""
    return parse(f"x = v | {source}\n").body[0].value.stages[0]


def _eval_in_scope(node, scope):
    """Evaluador mínimo, suficiente para las etapas: nombres, literales y BinOp."""
    from astromesh_glyph.syntax import nodes as n

    match node:
        case n.Literal(value=value):
            return value
        case n.Name(id=name):
            return scope[name]
        case n.BinOp(op=op, left=left, right=right):
            a = _eval_in_scope(left, scope)
            b = _eval_in_scope(right, scope)
            return {
                "==": lambda: a == b,
                "!=": lambda: a != b,
                ">": lambda: a > b,
                "<": lambda: a < b,
                ">=": lambda: a >= b,
                "<=": lambda: a <= b,
                "and": lambda: bool(a and b),
                "or": lambda: bool(a or b),
            }[op]()
        case n.DictLit(items=items):
            return {k: _eval_in_scope(v, scope) for k, v in items}
    raise AssertionError(node)


def _apply(source, items=ITEMS):
    return apply_stage(_stage(source), wrap(items), _eval_in_scope)


def test_where_keeps_matching_items():
    assert [r.sku for r in _apply('where(kind == "oem")').items] == ["A"]


def test_where_combines_multiple_arguments_with_and():
    result = _apply('where(kind == "aftermarket", stock > 0)')
    assert [r.sku for r in result.items] == ["C"]


def test_top_truncates():
    assert _apply("top(2)").count == 2


def test_top_sorts_descending_by_the_given_field():
    assert [r.sku for r in _apply("top(2, by=rating)").items] == ["A", "C"]


def test_top_with_asc_sorts_ascending():
    assert [r.sku for r in _apply("top(2, by=price, asc=true)").items] == ["B", "C"]


def test_map_projects_the_given_shape():
    result = _apply("map({sku, precio: price})")
    assert result.first.precio == 30
    assert "kind" not in result.first


def test_top_without_a_positional_count_is_rejected():
    with pytest.raises(GlyphCompileError, match="top"):
        _apply("top(by=rating)")


def test_where_without_predicates_is_rejected():
    with pytest.raises(GlyphCompileError, match="where"):
        _apply("where()")


def test_a_stage_on_a_non_collection_is_rejected():
    with pytest.raises(GlyphCompileError, match="colección"):
        apply_stage(_stage("top(1)"), wrap(7), _eval_in_scope)
