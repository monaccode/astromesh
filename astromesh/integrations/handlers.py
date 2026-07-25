"""Resolución del escape `handler: python:modulo:funcion`.

Se resuelve al cargar el catálogo, no en la primera llamada: un handler
mal referenciado tiene que romper el arranque de esa integración, no una
corrida en producción seis semanas después.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable


class HandlerError(Exception):
    """Referencia de handler que no resuelve a algo invocable."""


def load_handler(ref: str) -> Callable:
    if not isinstance(ref, str) or not ref.startswith("python:"):
        raise HandlerError(f"referencia de handler inválida: {ref!r} — debe empezar con 'python:'")
    body = ref[len("python:") :]
    if body.count(":") != 1:
        raise HandlerError(
            f"referencia de handler inválida: {ref!r} — formato 'python:modulo:funcion'"
        )
    module_name, symbol = body.split(":")
    if not module_name or not symbol:
        raise HandlerError(f"referencia de handler inválida: {ref!r}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise HandlerError(f"no se pudo importar el módulo '{module_name}': {exc}") from exc
    if not hasattr(module, symbol):
        raise HandlerError(f"el símbolo '{symbol}' no existe en '{module_name}'")
    fn = getattr(module, symbol)
    if not callable(fn):
        raise HandlerError(f"'{module_name}:{symbol}' no es invocable")
    return fn
