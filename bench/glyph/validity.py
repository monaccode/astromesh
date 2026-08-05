"""Tasa de programas válidos al primer intento.

Es la métrica que decide si Glyph le sirve a un modelo, y la más barata de las
dos: sólo hace la llamada de escritura — sin ejecutar tools, sin narración. Un
modelo se evalúa en un par de minutos y por centavos.

Importa más que los tokens porque los domina: cada programa inválido cuesta una
llamada entera de reparación, con su razonamiento. Un modelo con 40% de validez
paga ~2 llamadas extra por corrida y no hay ahorro que sobreviva a eso.

    BENCH_MODEL=kimi-k2.7-code-highspeed \
    BENCH_ENDPOINT=https://api.moonshot.ai/v1 \
    BENCH_API_KEY_ENV=MOONSHOT_API_KEY \
    N=6 uv run python -m bench.glyph.validity
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from astromesh_glyph import build_system_block, compile_program, extract_program, parse

from bench.glyph.fixtures import SCENARIOS, Scenario


@dataclass
class ValidityResult:
    scenario: str
    samples: int
    valid: int
    errors: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.valid / self.samples if self.samples else 0.0


async def sample_once(
    scenario: Scenario, model_fn: Callable, catalog: list, block: str
) -> str | None:
    """Devuelve None si el programa compila, o el mensaje de error si no."""
    messages = [
        {"role": "user", "content": block},
        {"role": "user", "content": scenario.query},
    ]
    response = await model_fn(messages, [], role="reasoner")
    try:
        compile_program(parse(extract_program(response.content or "")), catalog)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cuenta como inválido
        return f"{type(exc).__name__}: {exc}"
    return None


async def measure(model_fn: Callable, samples: int = 6) -> list[ValidityResult]:
    from astromesh.orchestration.glyph_pattern import PatternCapabilities

    results = []
    for scenario in SCENARIOS:
        caps = PatternCapabilities(tools=scenario.tools, tool_fn=None, model_fn=model_fn)
        catalog = caps.list_capabilities()
        block = build_system_block(catalog)
        outcomes = await asyncio.gather(
            *(sample_once(scenario, model_fn, catalog, block) for _ in range(samples))
        )
        results.append(
            ValidityResult(
                scenario=scenario.name,
                samples=samples,
                valid=sum(1 for o in outcomes if o is None),
                errors=[o for o in outcomes if o is not None],
            )
        )
    return results


def render_report(results: list[ValidityResult]) -> str:
    lines = ["# Tasa de programas válidos al primer intento", ""]
    for result in results:
        lines.append(f"## {result.scenario} — {result.valid}/{result.samples}")
        lines.append("")
        # Los errores se agrupan porque un mismo fallo repetido N veces es una
        # señal muy distinta de N fallos distintos: el primero se arregla.
        for message, count in Counter(result.errors).most_common():
            lines.append(f"- **{count}x** {message}")
        if result.errors:
            lines.append("")

    total = sum(r.samples for r in results)
    valid = sum(r.valid for r in results)
    pct = round(100 * valid / total) if total else 0
    lines.extend(["---", "", f"**Global: {valid}/{total} = {pct}%**", ""])
    if pct >= 80:
        lines.append("Apto: las reparaciones son raras y no se comen el ahorro.")
    elif pct >= 50:
        lines.append("Al límite: cada corrida paga reparaciones seguido. Revisá los errores")
        lines.append("repetidos de arriba — si uno domina, suele arreglarse en la gramática.")
    else:
        lines.append("No apto: el modelo no escribe Glyph de forma confiable y la reparación")
        lines.append("cuesta más que cualquier ahorro. Probá un modelo mejor en código.")
    return "\n".join(lines)


if __name__ == "__main__":

    async def _main() -> None:
        from bench.glyph.harness import CountingModel
        from bench.glyph.run import build_provider_fn

        model = CountingModel(build_provider_fn())
        results = await measure(model, samples=int(os.environ.get("N", "6")))
        print(render_report(results))

    asyncio.run(_main())
