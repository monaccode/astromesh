"""Corrida completa del benchmark y su reporte.

El reporte no aprueba ni rechaza: publica los números. La decisión de avanzar a la
fase 2 la toma una persona con los datos delante — un umbral automático elegido de
antemano decide con menos información que la que el benchmark produce.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from astromesh.orchestration.patterns import ReActPattern
from bench.glyph.fixtures import SCENARIOS
from bench.glyph.harness import CountingModel, RunMetrics, run_scenario


async def run_all(model_factory: Callable[[], CountingModel]) -> list[RunMetrics]:
    from astromesh.orchestration.glyph_pattern import GlyphPattern

    # Secuencial a propósito: dos corridas en paralelo contra el mismo proveedor
    # se contaminan la latencia, que es una de las métricas que se están midiendo.
    return [
        await run_scenario(scenario, pattern, model_factory())
        for scenario in SCENARIOS
        for pattern in (ReActPattern(), GlyphPattern())
    ]


def render_report(metrics: list[RunMetrics]) -> str:
    by_scenario: dict[str, dict[str, RunMetrics]] = {}
    for m in metrics:
        by_scenario.setdefault(m.scenario, {})[m.pattern] = m

    lines = ["# Benchmark Glyph vs ReAct", ""]
    for scenario, runs in by_scenario.items():
        lines.append(f"## {scenario}")
        lines.append("")
        react, glyph = runs.get("react"), runs.get("glyph")
        if react is None or glyph is None:
            measured = ", ".join(sorted(runs))
            lines.extend([f"Resultado incompleto: sólo se midió `{measured}`.", ""])
            continue

        lines.extend(
            [
                "| Métrica | ReAct | Glyph | Δ |",
                "|---|---:|---:|---:|",
                _row("Tokens de entrada", react.input_tokens, glyph.input_tokens),
                _row("Tokens de salida", react.output_tokens, glyph.output_tokens),
                _row("Tokens totales", _total(react), _total(glyph)),
                _row("Llamadas al modelo", react.model_calls, glyph.model_calls),
                _row("Llamadas a tools", react.tool_calls, glyph.tool_calls),
                _row("Latencia (ms)", round(react.wall_ms), round(glyph.wall_ms)),
                f"| Respuesta correcta | {_mark(react.correct)} | {_mark(glyph.correct)} | |",
                f"| Programas inválidos | — | {glyph.invalid_programs} | |",
                "",
            ]
        )
        if react.correct and not glyph.correct:
            lines.extend(["**REGRESIÓN**: Glyph responde mal donde ReAct responde bien.", ""])

    lines.extend(
        [
            "---",
            "",
            "No hay umbral automático de aprobación: estos números se leen y se decide.",
            "La tasa de programas inválidos es la que valida o refuta la apuesta de que",
            "una sintaxis familiar se escribe bien sin entrenamiento previo.",
        ]
    )
    return "\n".join(lines)


def _total(m: RunMetrics) -> int:
    return m.input_tokens + m.output_tokens


def _row(label: str, react_value: float, glyph_value: float) -> str:
    delta = f"{(glyph_value - react_value) / react_value * 100:+.0f}%" if react_value else "—"
    return f"| {label} | {react_value} | {glyph_value} | {delta} |"


def _mark(ok: bool) -> str:
    return "sí" if ok else "**no**"


if __name__ == "__main__":

    async def _main() -> None:
        from astromesh.runtime.engine import AgentRuntime

        runtime = AgentRuntime()
        await runtime.bootstrap()
        agent = runtime.get_agent("autolink-parts")

        async def provider_fn(messages, tools, role=None):
            return await agent._routers["default"].route(messages, tools=tools)

        metrics = await run_all(lambda: CountingModel(provider_fn))
        print(render_report(metrics))

    asyncio.run(_main())
