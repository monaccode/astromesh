"""Los valores que circulan por un programa Glyph.

Todo lo que devuelve una capacidad es JSON. Se envuelve al entrar para que el
programa pueda escribir `v.first.sku` sin corchetes, y se desenvuelve al salir
para que el host reciba estructuras Python planas.
"""

from __future__ import annotations

from typing import Any


class Record(dict):
    """Dict con acceso por punto."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"el registro no tiene el campo `{name}`; tiene: {', '.join(sorted(self))}"
            ) from None


class Collection:
    """Lista con las tres propiedades que el lenguaje expone sobre colecciones."""

    __slots__ = ("items",)

    def __init__(self, items: list[Any]) -> None:
        self.items = items

    @property
    def empty(self) -> bool:
        return not self.items

    @property
    def first(self) -> Any:
        return self.items[0] if self.items else None

    @property
    def count(self) -> int:
        return len(self.items)

    def __repr__(self) -> str:
        return f"Collection({self.items!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Collection) and self.items == other.items

    def __hash__(self) -> int:
        raise TypeError("Collection no es hashable")


def wrap(value: Any) -> Any:
    if isinstance(value, Collection | Record):
        return value
    if isinstance(value, dict):
        return Record({k: wrap(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return Collection([wrap(v) for v in value])
    return value


def unwrap(value: Any) -> Any:
    if isinstance(value, Collection):
        return [unwrap(v) for v in value.items]
    if isinstance(value, dict):
        return {k: unwrap(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [unwrap(v) for v in value]
    return value
