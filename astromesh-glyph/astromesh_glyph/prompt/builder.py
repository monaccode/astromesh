"""Arma el bloque de sistema y extrae el programa de la respuesta del modelo."""

from __future__ import annotations

import re
from collections.abc import Sequence

from astromesh_glyph.capabilities import CapabilitySpec
from astromesh_glyph.prompt.grammar import GRAMMAR

_FENCE = re.compile(r"```(?:glyph)?\s*\n(.*?)```", re.DOTALL)


def build_system_block(capabilities: Sequence[CapabilitySpec]) -> str:
    lines = [GRAMMAR, "", "Capacidades disponibles:", ""]
    for cap in sorted(capabilities, key=lambda c: c.name):
        suffix = (
            " — cuesta una llamada al modelo, usala sólo si hace falta" if cap.is_semantic else ""
        )
        lines.append(f"- {cap.name}: {cap.description}{suffix}")
        lines.extend(f"    {param}" for param in _render_parameters(cap))
    return "\n".join(lines)


def _render_parameters(cap: CapabilitySpec) -> list[str]:
    properties = cap.parameters.get("properties", {})
    required = set(cap.parameters.get("required", []))
    rendered = []
    for name, schema in properties.items():
        type_ = schema.get("type", "any")
        mark = " (requerido)" if name in required else ""
        rendered.append(f"{name}: {type_}{mark}")
    return rendered


def extract_program(text: str) -> str:
    """Saca el programa de la respuesta del modelo.

    Se acepta texto suelto además del bloque cercado: pedir el fence y castigar su
    ausencia con un round-trip de reparación sería cobrar por un error cosmético.
    """
    match = _FENCE.search(text)
    return (match.group(1) if match else text).strip()
