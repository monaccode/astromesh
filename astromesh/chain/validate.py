"""Validador mínimo de JSON Schema para `spec.output_schema`.

Deliberadamente no usa `jsonschema`: esa librería es dependencia de dev
únicamente, y subirla a las deps base obligaría a re-lockear tres proyectos uv
y agregaría una dependencia al arranque de la imagen de astromesh-os (que se
construye con pip, no con uv). El subconjunto de abajo cubre lo que un
`output_schema` de agente usa de verdad.

Soporta: type (object, string, integer, number, boolean, array, null),
properties, required, enum, items.

Ignora, a propósito y sin avisar: allOf, anyOf, oneOf, not, $ref,
patternProperties, additionalProperties, format, minimum, maximum, minLength,
maxLength, pattern, minItems, maxItems, uniqueItems.

Ignorar en vez de rechazar es deliberado: un output_schema con `oneOf` sigue
validando las partes que este módulo entiende, en lugar de tumbar el agente
entero por una keyword que no conocemos.
"""

from __future__ import annotations

from typing import Any

# `boolean` se chequea antes que `integer` a propósito: en Python
# `isinstance(True, int)` es True, y un `{"type": "integer"}` que acepte `true`
# sería un agujero silencioso en las condiciones de una cadena.
_CHECKS = {
    "null": lambda v: v is None,
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def validate(data: Any, schema: dict | None) -> list[str]:
    """Valida `data` contra `schema`. Devuelve los errores; lista vacía = válido."""
    if not schema:
        return []
    return _validate(data, schema, path="")


def _validate(value: Any, schema: dict, path: str) -> list[str]:
    errors: list[str] = []
    label = path or "(raíz)"

    expected = schema.get("type")
    if expected:
        check = _CHECKS.get(expected)
        # Un `type` que no conocemos no se valida: mismo criterio que el resto de
        # las keywords fuera del subconjunto.
        if check is not None and not check(value):
            return [f"{label}: se esperaba {expected}, llegó {type(value).__name__}"]

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append(f"{label}: {value!r} no está en enum {enum}")

    if expected == "object" or (expected is None and isinstance(value, dict)):
        errors.extend(_validate_object(value, schema, path))
    elif expected == "array" or (expected is None and isinstance(value, list)):
        errors.extend(_validate_array(value, schema, path))

    return errors


def _validate_object(value: Any, schema: dict, path: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    errors: list[str] = []
    prefix = f"{path}." if path else ""

    errors.extend(
        f"{prefix}{name}: campo requerido faltante"
        for name in schema.get("required", [])
        if name not in value
    )

    for name, subschema in (schema.get("properties") or {}).items():
        if name in value and isinstance(subschema, dict):
            errors.extend(_validate(value[name], subschema, f"{prefix}{name}"))

    return errors


def _validate_array(value: Any, schema: dict, path: str) -> list[str]:
    if not isinstance(value, list):
        return []
    items = schema.get("items")
    if not isinstance(items, dict):
        return []
    errors: list[str] = []
    label = path or "(raíz)"
    for i, item in enumerate(value):
        errors.extend(_validate(item, items, f"{label}[{i}]"))
    return errors
