"""Jerarquía de errores de Glyph.

Cada error de compilación o ejecución termina volviendo al LLM como texto de
reparación, así que los mensajes son interfaz pública: cambiarlos cambia la tasa
de reparación exitosa.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astromesh_glyph.runtime.state import PartialState


class GlyphError(Exception):
    """Raíz de todos los errores de Glyph."""


class GlyphSyntaxError(GlyphError):
    """El texto no es un programa Glyph válido."""

    def __init__(self, message: str, line: int, column: int) -> None:
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"línea {line}, columna {column}: {message}")


class GlyphCompileError(GlyphError):
    """El programa parsea pero no puede planificarse."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.message = message
        self.line = line
        super().__init__(f"línea {line}: {message}" if line is not None else message)


class GlyphExecutionError(GlyphError):
    """Una capacidad falló a mitad de la ejecución del plan."""

    def __init__(
        self,
        message: str,
        capability: str,
        args: dict[str, Any],
        partial: PartialState,
    ) -> None:
        self.message = message
        self.capability = capability
        self.args = args
        self.partial = partial
        super().__init__(f"{capability}: {message}")
