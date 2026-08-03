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


class CountingModel:
    """Envuelve un `model_fn` y acumula el uso de tokens de toda la corrida."""

    def __init__(self, provider_fn: Callable) -> None:
        self._provider_fn = provider_fn
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    async def __call__(self, messages, tools, role=None) -> Any:
        self.calls += 1
        response = await self._provider_fn(messages, tools, role=role)
        usage = getattr(response, "usage", None) or {}
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        return response


async def run_scenario(scenario: Scenario, pattern: Any, model: CountingModel) -> RunMetrics:
    tool_calls = 0

    async def tool_fn(name: str, args: dict) -> Any:
        nonlocal tool_calls
        tool_calls += 1
        return await scenario.tool_impl[name](args)

    started = time.monotonic()
    result = await pattern.execute(
        query=scenario.query,
        context={},
        model_fn=model,
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
    )
