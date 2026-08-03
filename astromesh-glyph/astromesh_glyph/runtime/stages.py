"""Las tres etapas builtin del pipe: where, top, map.

Sus argumentos llegan **sin evaluar**: `where(kind == "oem")` evalúa la
comparación una vez por elemento, con los campos del elemento en scope. Por eso
recibe `eval_in_scope` en vez de valores ya calculados.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from astromesh_glyph.errors import GlyphCompileError
from astromesh_glyph.runtime.values import Collection, Record, wrap
from astromesh_glyph.syntax import nodes as n

EvalInScope = Callable[[n.Node, dict[str, Any]], Any]


def apply_stage(stage: n.Call, value: Any, eval_in_scope: EvalInScope) -> Collection:
    if not isinstance(value, Collection):
        raise GlyphCompileError(
            f"`{stage.func}` sólo se aplica a una colección, y recibió {type(value).__name__}",
            stage.line,
        )
    handlers = {"where": _where, "top": _top, "map": _map}
    return handlers[stage.func](stage, value, eval_in_scope)


def _scope_of(item: Any) -> dict[str, Any]:
    return dict(item) if isinstance(item, Record) else {}


def _where(stage: n.Call, value: Collection, eval_in_scope: EvalInScope) -> Collection:
    if not stage.args:
        raise GlyphCompileError("`where` necesita al menos una condición", stage.line)
    kept = [
        item
        for item in value.items
        if all(eval_in_scope(pred, _scope_of(item)) for pred in stage.args)
    ]
    return Collection(kept)


def _top(stage: n.Call, value: Collection, eval_in_scope: EvalInScope) -> Collection:
    if len(stage.args) != 1:
        raise GlyphCompileError("`top` necesita exactamente un número: top(3)", stage.line)
    limit = eval_in_scope(stage.args[0], {})
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise GlyphCompileError("el argumento de `top` tiene que ser un entero >= 0", stage.line)

    items = list(value.items)
    by = stage.kwargs.get("by")
    if by is not None:
        if not isinstance(by, n.Name):
            raise GlyphCompileError("`by` tiene que ser el nombre de un campo", stage.line)
        ascending = bool(eval_in_scope(stage.kwargs["asc"], {})) if "asc" in stage.kwargs else False
        items.sort(key=lambda item: _scope_of(item).get(by.id), reverse=not ascending)
    return Collection(items[:limit])


def _map(stage: n.Call, value: Collection, eval_in_scope: EvalInScope) -> Collection:
    if len(stage.args) != 1 or not isinstance(stage.args[0], n.DictLit):
        raise GlyphCompileError("`map` necesita una forma: map({campo, otro: origen})", stage.line)
    shape = stage.args[0]
    return Collection([wrap(eval_in_scope(shape, _scope_of(item))) for item in value.items])
