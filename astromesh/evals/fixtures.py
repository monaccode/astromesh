"""Fixtures de tools por caso.

El runner envuelve una vez el `execute` del `ToolRegistry` de cada agente. Las fixtures
del caso viajan en un ContextVar, así que un sub-agente llamado como tool —que corre en
el mismo contexto— también queda stubeado. El recorte de 0.66 (`presentar`) y el gate de
confirmación (en `tool_fn`) siguen aplicando: ocurren antes y después de `execute`.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from astromesh.evals.memoria import MemoriaDeEval


@dataclass
class EstadoCaso:
    fixtures: dict
    bloquear: bool
    llamadas: list[str] = field(default_factory=list)


_CASO: ContextVar[EstadoCaso | None] = ContextVar("astromesh_eval_caso", default=None)


def instalar(registry) -> None:
    if getattr(registry, "_eval_fixtures", False):
        return
    original = registry.execute

    async def execute(tool_name, arguments, context=None):
        estado = _CASO.get()
        if estado is None:
            return await original(tool_name, arguments, context)
        estado.llamadas.append(tool_name)
        if tool_name in estado.fixtures:
            valor = copy.deepcopy(estado.fixtures[tool_name])
            return valor if isinstance(valor, dict) else {"result": valor}
        if estado.bloquear:
            return {"error": f"tool sin fixture en el eval: {tool_name}"}
        return await original(tool_name, arguments, context)

    registry.execute = execute
    registry._eval_fixtures = True


@contextmanager
def caso(fixtures: dict, bloquear: bool) -> Iterator[EstadoCaso]:
    estado = EstadoCaso(fixtures=dict(fixtures), bloquear=bloquear)
    token = _CASO.set(estado)
    try:
        yield estado
    finally:
        _CASO.reset(token)


def preparar(runtime) -> None:
    """Fixtures en todos los agentes y memoria aislada en los que declaran conversacional."""
    for agente in runtime._agents.values():
        instalar(agente._tools)
        memoria = getattr(agente, "_memory", None)
        if memoria is not None and "conversational" in (memoria.config or {}):
            memoria._conversation = MemoriaDeEval()
