"""Juez LLM de los casos con `rubric`. Nunca levanta: un veredicto inválido es `error`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_SISTEMA = (
    "Sos un evaluador estricto. Juzgás si la respuesta de un agente cumple una rúbrica. "
    'Respondé SÓLO con JSON: {"score": <número entre 0 y 1>, "reason": "<una oración>"}.'
)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


@dataclass(frozen=True)
class Veredicto:
    score: float | None
    reason: str
    tokens: int
    error: str | None


def _prompt(rubrica: str, turnos: list[str], respuesta: str) -> str:
    usuario = "\n".join(f"- {t}" for t in turnos)
    return (
        f"RÚBRICA:\n{rubrica}\n\nMENSAJES DEL USUARIO:\n{usuario}\n\n"
        f"RESPUESTA DEL AGENTE:\n{respuesta}"
    )


async def juzgar(provider, rubrica: str, turnos: list[str], respuesta: str) -> Veredicto:
    mensajes = [
        {"role": "system", "content": _SISTEMA},
        {"role": "user", "content": _prompt(rubrica, turnos, respuesta)},
    ]
    try:
        r = await provider.complete(mensajes)
    except Exception as exc:  # noqa: BLE001  (el juez caído deja el caso en error, no corta)
        return Veredicto(None, "", 0, f"el juez falló: {type(exc).__name__}: {exc}")
    usage = r.usage or {}
    tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
    texto = (r.content or "").strip()
    m = _FENCE.match(texto)
    if m:
        texto = m.group(1)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return Veredicto(None, "", tokens, f"el juez no devolvió JSON: {texto[:200]!r}")
    score = datos.get("score") if isinstance(datos, dict) else None
    if not isinstance(score, int | float) or isinstance(score, bool) or not 0 <= score <= 1:
        return Veredicto(None, "", tokens, f"score inválido del juez: {score!r}")
    return Veredicto(float(score), str(datos.get("reason", "")), tokens, None)
