"""Asserts deterministas de un caso. Puros: no saben del runtime."""

from __future__ import annotations

import re


def chequear(asercion: dict, respuesta: str, tools_llamadas: list[str]) -> str | None:
    """None si el assert pasa; si no, el motivo para el reporte."""
    ((clave, valor),) = asercion.items()
    if clave == "contains":
        return None if valor.lower() in respuesta.lower() else f"no contiene {valor!r}"
    if clave == "not_contains":
        return f"contiene {valor!r}" if valor.lower() in respuesta.lower() else None
    if clave == "regex":
        return None if re.search(valor, respuesta) else f"no coincide con /{valor}/"
    if clave == "equals":
        return None if respuesta.strip() == valor else f"no es igual a {valor!r}"
    if clave == "tool_called":
        return None if valor in tools_llamadas else f"no llamó a la tool {valor!r}"
    if clave == "tool_not_called":
        return f"llamó a la tool {valor!r}" if valor in tools_llamadas else None
    raise ValueError(f"assert desconocido {clave!r}")  # formato.py ya lo rechaza al cargar
