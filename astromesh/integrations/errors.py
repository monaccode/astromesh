"""Clasificación de fallos de integración.

El `error_kind` es parte del contrato: Nexus lo consume para decidir si
refrescar un token, hacer backoff o devolver el error al usuario.
"""

from __future__ import annotations

CREDENTIAL_INVALID = "credential_invalid"
CREDENTIAL_MISSING = "credential_missing"
RATE_LIMITED = "rate_limited"
RATE_LIMITED_LOCAL = "rate_limited_local"
UPSTREAM_ERROR = "upstream_error"
BAD_REQUEST = "bad_request"


def classify_status(status_code: int) -> str:
    if status_code in (401, 403):
        return CREDENTIAL_INVALID
    if status_code == 429:
        return RATE_LIMITED
    if status_code == 408 or status_code >= 500:
        return UPSTREAM_ERROR
    if status_code >= 400:
        return BAD_REQUEST
    return ""


def classify_exception(exc: Exception) -> str:
    """Todo lo que no sea una respuesta HTTP es upstream y reintentable.

    Incluye los bugs de un handler Python: un handler roto degrada esa
    llamada, no la corrida.
    """
    return UPSTREAM_ERROR


def retry_after_seconds(headers) -> float | None:
    """Lee Retry-After en segundos. La forma con fecha HTTP se ignora."""
    for key, value in dict(headers or {}).items():
        if key.lower() == "retry-after":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None
