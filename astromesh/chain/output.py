"""Salida estructurada de un agente: `spec.output_schema` -> `result["data"]`.

Ningún provider del repo soporta `response_format` ni `json_schema` nativo, así
que la forma se pide por prompt y se parsea de la respuesta. `answer` nunca se
toca: `data` se agrega al lado, así que quien hoy lee `answer` no se entera.
"""

from __future__ import annotations

import json
import re
from typing import Any

from astromesh.chain.validate import validate
from astromesh.core.schema import normalize_tool_parameters

# ```json ... ``` o ``` ... ```; no-greedy y multilínea.
_FENCED = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def normalize_output_schema(raw: dict | None) -> dict | None:
    """Acepta la misma taquigrafía YAML que los `parameters` de las tools."""
    return normalize_tool_parameters(raw)


def extract_data(answer: str) -> Any | None:
    """Saca el objeto JSON de una respuesta en prosa. None si no hay o no parsea."""
    if not answer:
        return None

    # El último bloque gana: si el modelo mostró un borrador y después lo
    # corrigió, la corrección es la que vale.
    for bloque in reversed(_FENCED.findall(answer)):
        try:
            return json.loads(bloque)
        except json.JSONDecodeError:
            continue

    try:
        return json.loads(answer.strip())
    except json.JSONDecodeError:
        return None


def build_data(answer: str, schema: dict | None) -> tuple[Any | None, str | None]:
    """Devuelve (data, data_error). Sin schema, ambos None y no se hace nada.

    Un fallo de validación NO levanta excepción: deja data en None y describe el
    problema en data_error. Cortar la corrida del agente porque el modelo escribió
    mal un JSON sería peor que devolver la prosa, que casi siempre sigue sirviendo.
    """
    if not schema:
        return None, None

    data = extract_data(answer)
    if data is None:
        return None, "no se encontró un objeto JSON válido en la respuesta"

    errores = validate(data, schema)
    if errores:
        return None, "; ".join(errores)

    return data, None


def schema_prompt_block(schema: dict) -> str:
    """Instrucción que se anexa al system prompt para pedir la salida estructurada."""
    return (
        "\n\n## Salida estructurada (obligatorio)\n"
        "Respondé normalmente en prosa y, al final, agregá un bloque de código "
        "etiquetado `json` con un objeto que cumpla exactamente este JSON Schema:\n\n"
        "```json\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "El bloque debe ser el último de tu respuesta y contener sólo el objeto JSON."
    )
