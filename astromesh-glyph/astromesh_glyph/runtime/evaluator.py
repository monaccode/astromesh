"""Evaluación async de expresiones y sentencias de Glyph.

El evaluador no sabe nada del grafo: ejecuta una sentencia contra un entorno.
El paralelismo lo decide el executor, que llama acá una vez por nodo.
"""

from __future__ import annotations

import operator
from typing import Any

from astromesh_glyph.capabilities import CapabilityProvider
from astromesh_glyph.runtime.stages import apply_stage
from astromesh_glyph.runtime.state import CallRecord
from astromesh_glyph.runtime.values import Record, unwrap, wrap
from astromesh_glyph.syntax import nodes as n

RETURNED = object()
"""Centinela: la sentencia fue un `return` y su valor es el del programa."""

CONTINUE = object()
"""Centinela: la sentencia terminó sin devolver."""

_BINARY = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


class Evaluator:
    def __init__(self, provider: CapabilityProvider, calls: list[CallRecord]) -> None:
        self._provider = provider
        self._calls = calls

    async def run_statement(self, stmt: n.Node, env: dict[str, Any]) -> tuple[object, Any]:
        """Ejecuta una sentencia. Devuelve (RETURNED, valor) o (CONTINUE, None)."""
        match stmt:
            case n.Assign(target=target, value=value):
                env[target] = await self.evaluate(value, env)
                return (CONTINUE, None)
            case n.ExprStmt(value=value):
                await self.evaluate(value, env)
                return (CONTINUE, None)
            case n.Return(value=value):
                result = None if value is None else await self.evaluate(value, env)
                return (RETURNED, unwrap(result))
            case n.If(test=test, body=body, orelse=orelse):
                branch = body if _truthy(await self.evaluate(test, env)) else orelse
                for inner in branch:
                    kind, result = await self.run_statement(inner, env)
                    if kind is RETURNED:
                        return (RETURNED, result)
                return (CONTINUE, None)
        raise TypeError(f"sentencia no ejecutable: {type(stmt).__name__}")

    async def evaluate(self, expr: n.Node | None, env: dict[str, Any]) -> Any:
        match expr:
            case None:
                return None
            case n.Literal(value=value):
                return value
            case n.Name(id=name):
                return env[name]
            case n.Attribute(value=value, attr=attr):
                return getattr(await self.evaluate(value, env), attr)
            case n.ListLit(items=items):
                return wrap([await self.evaluate(item, env) for item in items])
            case n.DictLit(items=items):
                return wrap({key: await self.evaluate(value, env) for key, value in items})
            case n.BinOp() as node:
                return await self._eval_binop(node, env)
            case n.Pipe(left=left, stages=stages):
                value = await self.evaluate(left, env)
                for stage in stages:
                    value = apply_stage(stage, value, self._sync_eval_factory(env))
                return value
            case n.Call() as call:
                return await self._invoke(call, env)
        raise TypeError(f"expresión no evaluable: {type(expr).__name__}")

    async def _eval_binop(self, node: n.BinOp, env: dict[str, Any]) -> Any:
        if node.op == "and":
            left = await self.evaluate(node.left, env)
            return bool(_truthy(left) and _truthy(await self.evaluate(node.right, env)))
        if node.op == "or":
            left = await self.evaluate(node.left, env)
            return bool(_truthy(left) or _truthy(await self.evaluate(node.right, env)))
        left = await self.evaluate(node.left, env)
        right = await self.evaluate(node.right, env)
        return _BINARY[node.op](left, right)

    async def _invoke(self, call: n.Call, env: dict[str, Any]) -> Any:
        args = {key: unwrap(await self.evaluate(value, env)) for key, value in call.kwargs.items()}
        record = CallRecord(capability=call.func, args=args, ok=False)
        self._calls.append(record)
        try:
            raw = await self._provider.invoke(call.func, args)
        except Exception as exc:
            record.error = str(exc)
            raise
        record.ok = True
        record.result = raw
        return wrap(raw)

    def _sync_eval_factory(self, env: dict[str, Any]):
        """Evaluador síncrono para argumentos de etapa.

        Las etapas evalúan sus argumentos una vez por elemento, y esos argumentos
        no pueden llamar capacidades — el compilador ya lo garantiza, porque una
        etapa sólo acepta expresiones sobre los campos del elemento. Por eso acá
        alcanza con una versión sin await.
        """

        def _eval(node: n.Node, scope: dict[str, Any]) -> Any:
            merged = {**env, **scope}
            match node:
                case n.Literal(value=value):
                    return value
                case n.Name(id=name):
                    return merged.get(name)
                case n.Attribute(value=value, attr=attr):
                    return getattr(_eval(value, scope), attr)
                case n.DictLit(items=items):
                    return {key: _eval(value, scope) for key, value in items}
                case n.ListLit(items=items):
                    return [_eval(item, scope) for item in items]
                case n.BinOp(op=op, left=left, right=right):
                    a = _eval(left, scope)
                    if op == "and":
                        return bool(_truthy(a) and _truthy(_eval(right, scope)))
                    if op == "or":
                        return bool(_truthy(a) or _truthy(_eval(right, scope)))
                    return _BINARY[op](a, _eval(right, scope))
            raise TypeError(f"expresión no válida dentro de una etapa: {type(node).__name__}")

        return _eval


def _truthy(value: Any) -> bool:
    if isinstance(value, Record):
        return bool(dict(value))
    return bool(value)
