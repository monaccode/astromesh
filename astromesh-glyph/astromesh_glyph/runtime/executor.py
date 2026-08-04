"""Ejecuta un PlanGraph en olas topológicas.

Cada ola toma todos los nodos listos y los corre concurrentes. Es la ganancia de
latencia que un loop ReAct no puede tener: ReAct pide una acción por vuelta, así
que dos tools independientes siempre esperan una a la otra.

Si un nodo falla, la ola en vuelo se deja terminar antes de cortar. Cancelar
tareas que ya llamaron a una capacidad dejaría efectos aplicados que el estado
parcial no podría reportar con certeza, y ese estado es lo único que el modelo
tiene para no repetirlos.
"""

from __future__ import annotations

import asyncio
from typing import Any

from astromesh_glyph.capabilities import CapabilityProvider
from astromesh_glyph.errors import GlyphExecutionError
from astromesh_glyph.plan.graph import PlanGraph, PlanNode
from astromesh_glyph.runtime.evaluator import DEFAULT_MAX_FANOUT, RETURNED, Evaluator
from astromesh_glyph.runtime.state import CallRecord, ExecutionResult, PartialState
from astromesh_glyph.runtime.values import unwrap, wrap


async def execute(
    graph: PlanGraph,
    provider: CapabilityProvider,
    *,
    node_timeout: float | None = None,
    max_fanout: int = DEFAULT_MAX_FANOUT,
    initial_env: dict[str, Any] | None = None,
) -> ExecutionResult:
    # Los valores del host se envuelven igual que lo que devuelve una capacidad,
    # para que `context.campo` funcione sobre un dict inyectado como funciona
    # sobre un resultado.
    env: dict[str, Any] = {k: wrap(v) for k, v in (initial_env or {}).items()}
    calls: list[CallRecord] = []
    evaluator = Evaluator(provider, calls, max_fanout=max_fanout)
    executed: list[str] = []
    pending = list(graph.nodes)
    returned: Any = None
    has_returned = False

    while pending and not has_returned:
        ready = [node for node in pending if node.depends_on <= env.keys()]
        if not ready:
            missing = sorted({d for node in pending for d in node.depends_on} - env.keys())
            raise GlyphExecutionError(
                f"el plan quedó bloqueado esperando: {', '.join(missing)}",
                capability="<plan>",
                args={},
                partial=PartialState(
                    bindings=_snapshot(env),
                    executed=executed,
                    failed_node=pending[0].id,
                    error="dependencias irresolubles",
                    calls=calls,
                ),
            )

        # Cada nodo corre sobre su propio entorno para que dos nodos de la misma
        # ola no se pisen; se fusionan al terminar, que es seguro porque el
        # compilador prohíbe reasignar.
        scopes = [dict(env) for _ in ready]
        outcomes = await asyncio.gather(
            *(
                _run_node(evaluator, node, scope, node_timeout)
                for node, scope in zip(ready, scopes, strict=True)
            ),
            return_exceptions=True,
        )

        failure: tuple[PlanNode, BaseException] | None = None
        for node, scope, outcome in zip(ready, scopes, outcomes, strict=True):
            pending.remove(node)
            if isinstance(outcome, BaseException):
                if failure is None:
                    failure = (node, outcome)
                continue
            executed.append(node.id)
            # Lo que una rama no ejecutada no ligó queda en null. Sin esto, un
            # `return {eta}` con `eta` ligada sólo dentro de un `if` esperaría
            # para siempre a una variable que nunca va a existir.
            for name in node.produces:
                scope.setdefault(name, None)
            env.update(scope)
            kind, value = outcome
            if kind is RETURNED and not has_returned:
                returned, has_returned = value, True

        if failure is not None:
            node, exc = failure
            capability = _last_failed_capability(calls)
            raise GlyphExecutionError(
                str(exc),
                capability=capability,
                args=_last_failed_args(calls),
                partial=PartialState(
                    bindings=_snapshot(env),
                    executed=executed,
                    failed_node=node.id,
                    error=f"{capability}: {exc}",
                    calls=calls,
                ),
            ) from exc

    return ExecutionResult(value=returned, bindings=_snapshot(env), calls=calls)


async def _run_node(
    evaluator: Evaluator, node: PlanNode, scope: dict[str, Any], limit: float | None
) -> tuple[object, Any]:
    if limit is None:
        return await evaluator.run_statement(node.stmt, scope)
    try:
        async with asyncio.timeout(limit):
            return await evaluator.run_statement(node.stmt, scope)
    except TimeoutError as exc:
        # Se convierte a RuntimeError para que el executor lo trate como
        # cualquier otro fallo de nodo y arme el estado parcial igual.
        raise RuntimeError(f"tiempo agotado tras {limit}s") from exc


def _snapshot(env: dict[str, Any]) -> dict[str, Any]:
    return {name: unwrap(value) for name, value in env.items()}


def _last_failed_capability(calls: list[CallRecord]) -> str:
    failed = [c for c in calls if not c.ok]
    return failed[-1].capability if failed else "<plan>"


def _last_failed_args(calls: list[CallRecord]) -> dict[str, Any]:
    failed = [c for c in calls if not c.ok]
    return failed[-1].args if failed else {}
