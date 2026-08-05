"""Corre un escenario contra un patrón y devuelve sus métricas.

Mide cinco cosas y no una: tokens es el objetivo, pero un patrón que ahorra tokens
y responde mal no sirve, y uno que ahorra tokens sin bajar latencia deja la mitad
de la ganancia sobre la mesa.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bench.glyph.fixtures import Scenario


@dataclass
class RunMetrics:
    scenario: str
    pattern: str
    input_tokens: int
    output_tokens: int
    model_calls: int
    tool_calls: int
    wall_ms: float
    correct: bool
    invalid_programs: int
    # Tokens de entrada servidos desde el caché de prefijo del proveedor. Van
    # DENTRO de input_tokens, no aparte: sin esta columna, una optimización de
    # prompt se evalúa contando a precio pleno tokens que el proveedor cobró con
    # descuento — que es como se sobreestimó el multiplicador de RAG.
    cached_tokens: int = 0
    # Lo que el proveedor cobra de verdad. Es LA métrica: los tokens de salida
    # cuestan ~4x los de entrada, así que un patrón que baja la entrada y sube la
    # salida —que es exactamente lo que hace Glyph— parece barato contando tokens
    # totales y sale caro en la factura. Queda en 0.0 si el modelo no tiene
    # entrada en PRICING; ahí la fila no se emite en vez de mentir con un cero.
    cost: float = 0.0
    # Estimación por caracteres/4: no hay tokenizer en el repo y agregarlo por una
    # fila de reporte no se justifica. El dato duro es `input_tokens`, que sale del
    # `usage` del proveedor; esto existe para hacer visible el mecanismo.
    knowledge_tokens_resent: int = 0


class CountingModel:
    """Envuelve un `model_fn` y acumula el uso de tokens de toda la corrida."""

    def __init__(self, provider_fn: Callable) -> None:
        self._provider_fn = provider_fn
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.cost = 0.0
        self.calls = 0

    async def __call__(self, messages, tools, role=None) -> Any:
        self.calls += 1
        response = await self._provider_fn(messages, tools, role=role)
        usage = getattr(response, "usage", None) or {}
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.cached_tokens += usage.get("cache_read_input_tokens", 0)
        self.cost += getattr(response, "cost", 0.0) or 0.0
        return response


async def run_scenario(scenario: Scenario, pattern: Any, model: CountingModel) -> RunMetrics:
    tool_calls = 0

    async def tool_fn(name: str, args: dict) -> Any:
        nonlocal tool_calls
        tool_calls += 1
        return await scenario.tool_impl[name](args)

    # Producción antepone `rendered_prompt` —que lleva los chunks de RAG— como
    # system en cada llamada (astromesh/runtime/engine.py:906). Reproducirlo es lo
    # que hace medible el multiplicador.
    #
    # El envoltorio va ENTRE el patrón y CountingModel, no adentro: así el
    # proveedor recibe el system y su `usage` lo cobra. Al revés, los tokens del
    # knowledge no aparecerían en el conteo y la medición daría cero.
    model_fn: Any = model
    if scenario.knowledge:
        system = {"role": "system", "content": scenario.knowledge}

        async def with_knowledge(messages, tools, role=None):
            return await model([system, *messages], tools, role=role)

        model_fn = with_knowledge

    started = time.monotonic()
    result = await pattern.execute(
        query=scenario.query,
        context={},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=scenario.tools,
        max_iterations=8,
    )
    wall_ms = (time.monotonic() - started) * 1000

    glyph_info = result.get("glyph", {})
    return RunMetrics(
        scenario=scenario.name,
        pattern="glyph" if glyph_info else "react",
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        model_calls=model.calls,
        tool_calls=tool_calls,
        wall_ms=wall_ms,
        correct=scenario.expected(result.get("answer") or ""),
        invalid_programs=glyph_info.get("repairs", 0),
        cached_tokens=model.cached_tokens,
        cost=model.cost,
        knowledge_tokens_resent=len(scenario.knowledge) // 4 * model.calls,
    )
