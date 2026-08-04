import pytest

from astromesh_glyph.errors import GlyphCompileError
from astromesh_glyph.runtime.stages import apply_stage
from astromesh_glyph.runtime.values import wrap
from astromesh_glyph.syntax import nodes as n
from astromesh_glyph.syntax.parser import parse

ITEMS = [
    {"sku": "A", "kind": "oem", "price": 30, "rating": 5, "stock": 2},
    {"sku": "B", "kind": "aftermarket", "price": 10, "rating": 3, "stock": 0},
    {"sku": "C", "kind": "aftermarket", "price": 20, "rating": 4, "stock": 7},
]


def _stage(source):
    """Extrae la primera etapa de `x = v | <source>`."""
    return parse(f"x = v | {source}\n").body[0].value.stages[0]


async def _eval_in_scope(node, scope):
    """Evaluador mínimo, suficiente para las etapas: nombres, literales y BinOp."""
    match node:
        case n.Literal(value=value):
            return value
        case n.Name(id=name):
            return scope[name]
        case n.BinOp(op=op, left=left, right=right):
            a = await _eval_in_scope(left, scope)
            b = await _eval_in_scope(right, scope)
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
            return {k: await _eval_in_scope(v, scope) for k, v in items}
    raise AssertionError(node)


async def _apply(source, items=ITEMS):
    return await apply_stage(_stage(source), wrap(items), _eval_in_scope)


async def test_where_keeps_matching_items():
    result = await _apply('where(kind == "oem")')
    assert [r.sku for r in result.items] == ["A"]


async def test_where_combines_multiple_arguments_with_and():
    result = await _apply('where(kind == "aftermarket", stock > 0)')
    assert [r.sku for r in result.items] == ["C"]


async def test_top_truncates():
    assert (await _apply("top(2)")).count == 2


async def test_top_sorts_descending_by_the_given_field():
    result = await _apply("top(2, by=rating)")
    assert [r.sku for r in result.items] == ["A", "C"]


async def test_top_with_asc_sorts_ascending():
    result = await _apply("top(2, by=price, asc=true)")
    assert [r.sku for r in result.items] == ["B", "C"]


async def test_map_projects_the_given_shape():
    result = await _apply("map({sku, precio: price})")
    assert result.first.precio == 30
    assert "kind" not in result.first


async def test_top_without_a_positional_count_is_rejected():
    with pytest.raises(GlyphCompileError, match="top"):
        await _apply("top(by=rating)")


async def test_where_without_predicates_is_rejected():
    with pytest.raises(GlyphCompileError, match="where"):
        await _apply("where()")


async def test_a_stage_on_a_non_collection_is_rejected():
    with pytest.raises(GlyphCompileError, match="colección"):
        await apply_stage(_stage("top(1)"), wrap(7), _eval_in_scope)


async def test_map_can_invoke_a_capability_once_per_item():
    """El patrón que los modelos escriben apenas hay una colección."""
    llamadas = []

    async def evaluador(node, scope):
        if isinstance(node, n.DictLit):
            return {k: await evaluador(v, scope) for k, v in node.items}
        if isinstance(node, n.Call):
            llamadas.append(scope["sku"])
            return {"covered": scope["sku"] != "B"}
        return await _eval_in_scope(node, scope)

    stage = _stage("map({g: garantia(sku=sku)})")
    result = await apply_stage(stage, wrap(ITEMS), evaluador)

    assert llamadas == ["A", "B", "C"]
    assert [r.g["covered"] for r in result.items] == [True, False, True]
