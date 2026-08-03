"""Lo que la ejecución produce, y lo que sobrevive a un fallo.

`PartialState.to_prompt()` es la interfaz de reparación con el modelo: su texto
determina si el segundo intento repite un efecto ya aplicado o no.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallRecord:
    capability: str
    args: dict[str, Any]
    ok: bool
    result: Any = None
    error: str | None = None


@dataclass
class ExecutionResult:
    value: Any
    bindings: dict[str, Any]
    calls: list[CallRecord] = field(default_factory=list)


@dataclass
class PartialState:
    bindings: dict[str, Any]
    executed: list[str]
    failed_node: str
    error: str
    calls: list[CallRecord] = field(default_factory=list)

    def to_prompt(self) -> str:
        applied = [c for c in self.calls if c.ok]
        lines = [
            "El programa anterior falló a mitad de la ejecución.",
            "",
            f"Error: {self.error}",
            "",
        ]
        if applied:
            lines.append("Estas llamadas YA se ejecutaron y sus efectos ya ocurrieron —")
            lines.append("no las repitas en el programa nuevo:")
            lines.extend(f"  - {c.capability}({_render(c.args)})" for c in applied)
            lines.append("")
        if self.bindings:
            lines.append("Variables que quedaron ligadas, con su valor:")
            lines.extend(f"  {name} = {_render(value)}" for name, value in self.bindings.items())
            lines.append("")
        lines.append("Escribí un programa nuevo que continúe desde acá.")
        return "\n".join(lines)


def _render(value: Any, limit: int = 500) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}… (truncado)"
