"""La única frontera entre Glyph y su host.

Dos métodos. Glyph no sabe qué es una tool, un agente ni un modelo: sabe que hay
capacidades con nombre, schema y una forma de invocarlas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class CapabilitySpec:
    """Una capacidad invocable desde un programa Glyph.

    `parameters` es un JSON Schema de tipo object, el mismo formato que usa el
    function-calling de OpenAI. `is_semantic` marca las capacidades que invocan un
    modelo — el host las contabiliza aparte porque cada una es un round-trip.

    `returns` describe la **forma de lo que devuelve**, en una línea legible:
    `"lista de {sku, kind, price}"`. Sin esto el modelo tiene que inventar los
    nombres de campo, y en un lenguaje donde el pipe filtra por campo eso no da
    error: da colecciones vacías en silencio. Es prosa y no un JSON Schema a
    propósito — se paga en cada turno y una línea cuesta una fracción.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    is_semantic: bool = False
    returns: str = ""


@runtime_checkable
class CapabilityProvider(Protocol):
    def list_capabilities(self) -> list[CapabilitySpec]: ...

    async def invoke(self, name: str, args: dict[str, Any]) -> Any: ...
