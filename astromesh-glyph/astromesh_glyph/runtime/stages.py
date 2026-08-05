"""Las tres etapas builtin del pipe: where, top, map.

Sus argumentos llegan **sin evaluar**: `where(kind == "oem")` evalúa la
comparación una vez por elemento, con los campos del elemento en scope. Por eso
recibe `eval_in_scope` en vez de valores ya calculados.

`eval_in_scope` es async porque una etapa puede invocar capacidades:
`map({g: garantia(sku=sku)})` la llama una vez por elemento. Es el patrón que los
modelos escriben apenas hay una colección, y sin él no había forma de expresarlo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from astromesh_glyph.errors import GlyphCompileError
from astromesh_glyph.runtime.values import Collection, Record, wrap
from astromesh_glyph.syntax import nodes as n

EvalInScope = Callable[[n.Node, dict[str, Any]], Awaitable[Any]]


async def apply_stage(stage: n.Call, value: Any, eval_in_scope: EvalInScope) -> Collection:
    if not isinstance(value, Collection):
        raise GlyphCompileError(
            f"`{stage.func}` sólo se aplica a una colección, y recibió {type(value).__name__}",
            stage.line,
        )
    handlers = {"where": _where, "top": _top, "map": _map}
    return await handlers[stage.func](stage, value, eval_in_scope)


def _scope_of(item: Any) -> dict[str, Any]:
    return dict(item) if isinstance(item, Record) else {}


async def _where(stage: n.Call, value: Collection, eval_in_scope: EvalInScope) -> Collection:
    if not stage.args:
        raise GlyphCompileError("`where` necesita al menos una condición", stage.line)

    # Un predicado no invoca capacidades en la práctica, pero se evalúa igual con
    # el mismo camino async para no tener dos evaluadores que puedan divergir.
    verdicts = await asyncio.gather(
        *(_all_true(item, stage.args, eval_in_scope) for item in value.items)
    )
    return Collection([item for item, keep in zip(value.items, verdicts, strict=True) if keep])


async def _all_true(item: Any, preds: list[n.Node], eval_in_scope: EvalInScope) -> bool:
    scope = _scope_of(item)
    for pred in preds:
        if not await eval_in_scope(pred, scope):
            return False
    return True


async def _top(stage: n.Call, value: Collection, eval_in_scope: EvalInScope) -> Collection:
    if len(stage.args) != 1:
        raise GlyphCompileError("`top` necesita exactamente un número: top(3)", stage.line)
    limit = await eval_in_scope(stage.args[0], {})
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise GlyphCompileError("el argumento de `top` tiene que ser un entero >= 0", stage.line)

    items = list(value.items)
    by = stage.kwargs.get("by")
    if by is not None:
        if not isinstance(by, n.Name):
            raise GlyphCompileError("`by` tiene que ser el nombre de un campo", stage.line)
        ascending = (
            bool(await eval_in_scope(stage.kwargs["asc"], {})) if "asc" in stage.kwargs else False
        )
        items.sort(key=lambda item: _scope_of(item).get(by.id), reverse=not ascending)
    return Collection(items[:limit])


async def _map(stage: n.Call, value: Collection, eval_in_scope: EvalInScope) -> Collection:
    if len(stage.args) != 1 or not isinstance(stage.args[0], n.DictLit):
        raise GlyphCompileError("`map` necesita una forma: map({campo, otro: origen})", stage.line)
    shape = stage.args[0]

    # Concurrente: si la forma invoca una capacidad, esto son N llamadas en
    # paralelo. El tope real lo pone el semáforo del evaluador, no esta línea.
    projected = await asyncio.gather(
        *(eval_in_scope(shape, _scope_of(item)) for item in value.items)
    )
    return Collection([wrap(item) for item in projected])
