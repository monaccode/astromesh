"""Corrida completa del benchmark y su reporte.

El reporte no aprueba ni rechaza: publica los números. La decisión de avanzar a la
fase 2 la toma una persona con los datos delante — un umbral automático elegido de
antemano decide con menos información que la que el benchmark produce.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace

from astromesh.orchestration.patterns import ReActPattern
from bench.glyph.fixtures import SCENARIOS
from bench.glyph.harness import CountingModel, RunMetrics, run_scenario


def _variants() -> list[tuple[str, object]]:
    from astromesh.orchestration.glyph_pattern import GlyphPattern

    return [
        ("react", ReActPattern()),
        ("glyph", GlyphPattern()),
        # Sin narración: el patrón devuelve el resultado del programa como JSON en
        # vez de gastar una segunda llamada al modelo en redactarlo. Es la
        # configuración de un agente encadenado, que consume output.data.
        ("glyph-datos", GlyphPattern(narrate=False)),
    ]


async def run_all(model_factory: Callable[[], CountingModel]) -> list[RunMetrics]:
    # Secuencial a propósito: dos corridas en paralelo contra el mismo proveedor
    # se contaminan la latencia, que es una de las métricas que se están midiendo.
    results = []
    for scenario in SCENARIOS:
        for label, pattern in _variants():
            metrics = await run_scenario(scenario, pattern, model_factory())
            results.append(replace(metrics, pattern=label))
    return results


def render_report(metrics: list[RunMetrics]) -> str:
    by_scenario: dict[str, dict[str, RunMetrics]] = {}
    for m in metrics:
        by_scenario.setdefault(m.scenario, {})[m.pattern] = m

    lines = ["# Benchmark Glyph vs ReAct", ""]
    for scenario, runs in by_scenario.items():
        lines.append(f"## {scenario}")
        lines.append("")
        react = runs.get("react")
        others = [(name, m) for name, m in runs.items() if name != "react"]
        if react is None or not others:
            measured = ", ".join(sorted(runs))
            lines.extend([f"Resultado incompleto: sólo se midió `{measured}`.", ""])
            continue

        header = " | ".join(name for name, _ in others)
        lines.extend(
            [
                f"| Métrica | ReAct | {header} |",
                "|---" * (2 + len(others)) + "|",
                _row("Tokens de entrada", react.input_tokens, [m.input_tokens for _, m in others]),
                _row("Tokens de salida", react.output_tokens, [m.output_tokens for _, m in others]),
                _row("Tokens totales", _total(react), [_total(m) for _, m in others]),
                _row("Llamadas al modelo", react.model_calls, [m.model_calls for _, m in others]),
                _row("Llamadas a tools", react.tool_calls, [m.tool_calls for _, m in others]),
                _row("Latencia (ms)", round(react.wall_ms), [round(m.wall_ms) for _, m in others]),
                "| Respuesta correcta | "
                + " | ".join([_mark(react.correct)] + [_mark(m.correct) for _, m in others])
                + " |",
                "| Programas inválidos | — | "
                + " | ".join(str(m.invalid_programs) for _, m in others)
                + " |",
                "",
            ]
        )
        regressions = [name for name, m in others if react.correct and not m.correct]
        if regressions:
            lines.extend(
                [
                    f"**REGRESIÓN** en {', '.join(regressions)}: responde mal donde ReAct acierta.",
                    "",
                ]
            )

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


def _row(label: str, baseline: float, values: list[float]) -> str:
    """Cada columna muestra su valor y su Δ contra ReAct, que es la referencia."""

    def cell(value: float) -> str:
        if not baseline:
            return str(value)
        return f"{value} ({(value - baseline) / baseline * 100:+.0f}%)"

    return f"| {label} | {baseline} | " + " | ".join(cell(v) for v in values) + " |"


def _mark(ok: bool) -> str:
    return "sí" if ok else "**no**"


def build_provider_fn():
    """Arma el `model_fn` del benchmark desde variables de entorno.

    No se toma el router de un agente del repo: `autolink-parts` está cableado a
    ollama en localhost, así que correr el benchmark contra otro proveedor
    obligaría a editar su YAML. Acá el proveedor es del benchmark, no del agente.

    Cualquier endpoint compatible con OpenAI sirve — OpenAI, Groq, Together,
    vLLM, un ollama local con `/v1`:

        BENCH_MODEL=gpt-4o-mini
        BENCH_ENDPOINT=https://api.openai.com/v1
        BENCH_API_KEY_ENV=OPENAI_API_KEY
    """
    import os

    from astromesh.runtime.engine import build_candidate_provider

    model = os.environ.get("BENCH_MODEL")
    if not model:
        raise SystemExit(
            "Falta BENCH_MODEL. Ejemplo:\n"
            "  BENCH_MODEL=gpt-4o-mini BENCH_API_KEY_ENV=OPENAI_API_KEY \\\n"
            "    uv run python -m bench.glyph.run"
        )

    key_env = os.environ.get("BENCH_API_KEY_ENV", "OPENAI_API_KEY")
    if not os.environ.get(key_env):
        raise SystemExit(
            f"La variable {key_env} está vacía; exportá la credencial o cambiá BENCH_API_KEY_ENV."
        )

    # La temperatura no se fija por defecto: sería lo ideal para determinismo, pero
    # hay modelos que rechazan cualquier valor distinto del suyo — kimi-k2.5
    # devuelve 400 con "only 1 is allowed for this model". Se pide con
    # BENCH_TEMPERATURE cuando el modelo la acepte.
    parameters = {}
    if (temperature := os.environ.get("BENCH_TEMPERATURE")) is not None:
        parameters["temperature"] = float(temperature)

    # 600 s por llamada, contra los 120 s de default: un modelo de razonamiento
    # escribiendo un programa entero tarda minutos, y un timeout no se distingue
    # de un fallo del lenguaje en las métricas.
    provider = build_candidate_provider(
        {
            "source": "openai_compat",
            "model": model,
            "endpoint": os.environ.get("BENCH_ENDPOINT", "https://api.openai.com/v1"),
            "api_key_env": key_env,
            "timeout": float(os.environ.get("BENCH_TIMEOUT", "600")),
            "parameters": parameters or None,
        }
    )
    if provider is None:
        raise SystemExit(f"No se pudo construir un proveedor para el modelo {model!r}.")

    async def provider_fn(messages, tools, role=None):
        kwargs = {"tools": tools} if tools else {}
        return await provider.complete(messages, **kwargs)

    return provider_fn


if __name__ == "__main__":

    async def _main() -> None:
        provider_fn = build_provider_fn()
        metrics = await run_all(lambda: CountingModel(provider_fn))
        print(render_report(metrics))

    asyncio.run(_main())
