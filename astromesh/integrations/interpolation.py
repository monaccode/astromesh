"""Sustitución de `{param}` en requests de integración.

Deliberadamente NO usa Jinja2. Los valores que entran acá los escribe un
modelo; un motor de plantillas con acceso a atributos y llamadas sería una
superficie de ejecución. Esto sustituye texto y nada más.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_LONE_PLACEHOLDER = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class InterpolationError(Exception):
    """Placeholder sin argumento, o valor que no puede ir en esa posición."""


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _reject_traversal(raw: str, param: str) -> None:
    """Rechaza `..` en cualquier codificación razonable.

    Se decodifica dos veces porque un proxy o un cliente puede decodificar
    una capa antes de que el valor llegue al servidor destino: `%252e%252e`
    llega como `%2e%2e` y se convierte en `..` recién del otro lado.
    """
    candidates = {raw, unquote(raw), unquote(unquote(raw))}
    for candidate in candidates:
        if ".." in candidate:
            raise InterpolationError(
                f"el parámetro '{param}' contiene '..' — no puede escapar del path"
            )


def interpolate(template: str, args: dict, *, position: str, allow_slash: bool = False) -> str:
    """Sustituye `{param}` en `template` con los valores de `args`.

    position: "path" (encodea, prohíbe `/` salvo allow_slash, siempre prohíbe `..`),
              "query" (encodea todo, incluida la barra),
              "raw" (no encodea; para bodies y headers).
    """

    def _replace(match: re.Match) -> str:
        param = match.group(1)
        if param not in args:
            raise InterpolationError(f"falta el argumento '{param}'")
        value = _stringify(args[param])
        if position == "path":
            _reject_traversal(value, param)
            if "/" in value and not allow_slash:
                raise InterpolationError(
                    f"el parámetro '{param}' contiene una barra y la acción no la permite"
                )
            safe = "/" if allow_slash else ""
            return quote(value, safe=safe)
        if position == "query":
            return quote(value, safe="")
        return value

    return _PLACEHOLDER.sub(_replace, template)


def interpolate_structure(value: Any, args: dict, *, allow_slash_params: set[str]) -> Any:
    """Interpola recursivamente dicts, listas y strings de un body o unas headers.

    Un string que es exactamente un placeholder conserva el tipo del
    argumento: `{"limit": "{limit}"}` con limit=25 produce `{"limit": 25}`,
    no `{"limit": "25"}`. Una API que valida tipos rechaza lo segundo.
    """
    if isinstance(value, dict):
        return {
            k: interpolate_structure(v, args, allow_slash_params=allow_slash_params)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            interpolate_structure(v, args, allow_slash_params=allow_slash_params) for v in value
        ]
    if isinstance(value, str):
        lone = _LONE_PLACEHOLDER.match(value)
        if lone:
            param = lone.group(1)
            if param not in args:
                raise InterpolationError(f"falta el argumento '{param}'")
            return args[param]
        return interpolate(value, args, position="raw")
    return value
