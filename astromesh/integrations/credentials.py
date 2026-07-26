"""Resolución de credenciales de conexión.

El core no guarda, no cifra y no refresca nada. Resuelve en este orden:

1. Bundle de la corrida — lo que inyecta Nexus. Máxima prioridad.
2. `config/connections.yaml` con `${VAR}` — self-hosted sin Nexus.
3. Ausente — quien llame devuelve `credential_missing`; no revienta el run.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class ResolvedConnection:
    """Material de credencial listo para firmar un request."""

    name: str
    material: dict = field(default_factory=dict)
    base_url: str | None = None


def _expand(value):
    """Sustituye `${VAR}` por su valor de entorno. Sin definir → cadena vacía.

    Misma sintaxis que `config/channels.yaml`, para que quien ya configuró
    canales no tenga que aprender otra.
    """
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _split(name: str, raw: dict) -> ResolvedConnection:
    material = dict(raw or {})
    base_url = material.pop("base_url", None) or None
    return ResolvedConnection(name=name, material=material, base_url=base_url)


class CredentialResolver:
    def __init__(self, connections_file: Path | None = None):
        self._file_connections: dict = {}
        if connections_file is not None:
            self._load_file(Path(connections_file))

    def _load_file(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            data = yaml.safe_load(path.read_text()) or {}
            self._file_connections = data.get("connections") or {}
        except (yaml.YAMLError, OSError) as exc:
            logger.error("no se pudo leer %s: %s", path, exc)

    def resolve(self, connection_name: str, bundle: dict | None) -> ResolvedConnection | None:
        material = (bundle or {}).get(connection_name)
        if isinstance(material, dict) and material:
            return _split(connection_name, material)
        from_file = self._file_connections.get(connection_name)
        if isinstance(from_file, dict) and from_file:
            return _split(connection_name, _expand(from_file))
        return None
