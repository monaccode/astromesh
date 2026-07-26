"""Cómo una credencial se pone en el cable.

El core no negocia OAuth, no refresca tokens y no conoce client_secret:
eso es de Nexus. Acá sólo se toma material ya resuelto y se lo convierte
en headers o parámetros de query.
"""

from __future__ import annotations

import base64

from astromesh.integrations.manifest import AuthSpec


class CredentialMissing(Exception):
    """La conexión no trae el material que el manifest declara necesitar."""


def apply_auth(auth: AuthSpec, material: dict) -> tuple[dict, dict]:
    """Devuelve (headers, query_params) para firmar el request."""
    if auth.scheme == "none":
        return {}, {}

    value = (material or {}).get(auth.credential)
    if not value:
        raise CredentialMissing(
            f"la conexión no trae '{auth.credential}' (requerido por scheme '{auth.scheme}')"
        )

    if auth.scheme == "bearer":
        return {"Authorization": f"Bearer {value}"}, {}
    if auth.scheme == "header":
        return {auth.header_name: str(value)}, {}
    if auth.scheme == "query":
        return {}, {auth.param_name: str(value)}
    if auth.scheme == "basic":
        if not isinstance(value, dict):
            raise CredentialMissing(
                f"'{auth.credential}' para scheme 'basic' debe ser un mapping "
                "con 'username' y 'password'"
            )
        username = value.get("username")
        password = value.get("password")
        if not username or not password:
            raise CredentialMissing(
                f"'{auth.credential}' para scheme 'basic' necesita 'username' y 'password'"
            )
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}, {}

    raise CredentialMissing(f"scheme desconocido: {auth.scheme}")
