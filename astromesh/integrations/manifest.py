"""Modelos y carga del manifest de integraciones.

pydantic v2, no jsonschema: jsonschema vive en el grupo dev y este código
tiene que importar en un runtime instalado sin extras.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from astromesh.core.schema import InvalidToolParameters, normalize_tool_parameters

AUTH_SCHEMES = ("bearer", "header", "query", "basic", "none")


class ManifestError(Exception):
    """Manifest inválido. Lleva el mensaje ya legible para el log."""


class AuthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: Literal["bearer", "header", "query", "basic", "none"] = "none"
    credential: str = "access_token"
    header_name: str | None = None
    param_name: str | None = None

    @model_validator(mode="after")
    def _needs_name(self):
        if self.scheme == "header" and not self.header_name:
            raise ValueError("scheme 'header' requiere 'header_name'")
        if self.scheme == "query" and not self.param_name:
            raise ValueError("scheme 'query' requiere 'param_name'")
        return self


class RequestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    query: dict = Field(default_factory=dict)
    headers: dict = Field(default_factory=dict)
    body: dict | str | None = None


class ResponseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    select: str | None = None


class PaginationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: Literal["cursor", "offset"]
    cursor_param: str = "cursor"
    cursor_path: str | None = None
    limit_param: str | None = None
    offset_param: str | None = None

    @model_validator(mode="after")
    def _needs_fields(self):
        if self.style == "cursor" and not self.cursor_path:
            raise ValueError("pagination 'cursor' requiere 'cursor_path'")
        if self.style == "offset" and not self.offset_param:
            raise ValueError("pagination 'offset' requiere 'offset_param'")
        return self


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = 30
    headers: dict = Field(default_factory=dict)
    rate_limit: dict | None = None


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict = Field(default_factory=dict)
    request: RequestSpec | None = None
    handler: str | None = None
    response: ResponseSpec | None = None
    pagination: PaginationSpec | None = None
    writes: bool = False
    rate_limit: dict | None = None
    timeout_seconds: int | None = None
    allow_slash: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def _description_not_empty(cls, v: str) -> str:
        # Es lo único que el modelo lee para decidir si llamar la acción.
        if not v.strip():
            raise ValueError("description no puede estar vacía")
        return v

    @model_validator(mode="after")
    def _exactly_one_mode(self):
        if self.request is not None and self.handler is not None:
            raise ValueError(f"acción '{self.name}': declara 'request' y 'handler' a la vez")
        if self.request is None and self.handler is None:
            raise ValueError(f"acción '{self.name}': necesita 'request' o 'handler'")
        return self

    def tool_parameters(self) -> dict:
        """Esquema JSON que ve el modelo: taquigrafía normalizada + cursor."""
        shorthand = {}
        required: list[str] = []
        for name, spec in (self.parameters or {}).items():
            entry = dict(spec) if isinstance(spec, dict) else {"type": "string"}
            if entry.pop("required", False):
                required.append(name)
            shorthand[name] = entry
        schema = normalize_tool_parameters(shorthand) or {"type": "object", "properties": {}}
        if self.pagination is not None:
            schema["properties"]["cursor"] = {
                "type": "string",
                "description": "Cursor de la página siguiente, devuelto en metadata.next_cursor",
            }
        if required:
            schema["required"] = required
        return schema


class IntegrationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    version: str = "0.1.0"
    description: str = ""
    base_url: str | None = None
    auth: AuthSpec = Field(default_factory=AuthSpec)
    defaults: Defaults = Field(default_factory=Defaults)
    actions: list[ActionSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_action_names(self):
        seen = set()
        for action in self.actions:
            if action.name in seen:
                raise ValueError(f"acción duplicada: '{action.name}'")
            seen.add(action.name)
        return self

    def action(self, name: str) -> ActionSpec | None:
        for action in self.actions:
            if action.name == name:
                return action
        return None


def load_manifest(path: Path) -> IntegrationManifest:
    """Lee y valida un integration.yaml. Levanta ManifestError con causa legible."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path}: YAML inválido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: el manifest debe ser un mapping")
    if raw.get("kind") != "Integration":
        raise ManifestError(f"{path}: kind debe ser 'Integration', es {raw.get('kind')!r}")
    metadata = raw.get("metadata") or {}
    spec = raw.get("spec") or {}
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise ManifestError(f"{path}: 'metadata' y 'spec' deben ser mappings")
    payload = {
        "slug": metadata.get("name"),
        "version": metadata.get("version", "0.1.0"),
        "description": metadata.get("description", ""),
        **spec,
    }
    try:
        return IntegrationManifest(**payload)
    except (ValidationError, InvalidToolParameters) as exc:
        raise ManifestError(f"{path}: {exc}") from exc
