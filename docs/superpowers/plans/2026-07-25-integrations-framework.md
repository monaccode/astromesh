# Marco de integraciones declarativas — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que agregar una integración nueva a AstroMesh sea un archivo YAML y un PR, sin tocar ningún archivo compartido y sin escribir tests.

**Architecture:** Un catálogo in-tree de manifests YAML (`astromesh/integrations/catalog/<slug>/integration.yaml`) describe base_url, autenticación y acciones de cada servicio. Un ejecutor HTTP genérico convierte cada acción en una tool que el agente llama; las acciones que no caben en un request declaran `handler: python:modulo:funcion`. Las credenciales no viven en el core: llegan por corrida en un bundle `connections` que inyecta Nexus, viajan por el dict de contexto de `tool_fn`, y nunca se persisten.

**Tech Stack:** Python 3.12+, pydantic v2 (validación de manifests), httpx (ejecutor), pyyaml (manifests), pytest + respx (tests), uv (paquetes), ruff (lint).

**Spec:** `docs/superpowers/specs/2026-07-24-integrations-framework-design.md`

## Global Constraints

- **Cero dependencias nuevas de runtime.** `jsonschema` está en `[dependency-groups] dev` (`pyproject.toml:54`), **no** es dependencia base. Validar manifests con él rompería el build de `astromesh-os`, cuyo `build-deb.sh` usa pip (ignora las uv path sources) y cuya compuerta de arranque exige que `astromesh.api.main` importe **sin extras**. Usar **pydantic v2**, que sí es dependencia base (`pyproject.toml:10`). Lo mismo aplica a `httpx`, `pyyaml` y `jinja2`: ya están. No agregar nada más.
- **Nada de Jinja2 en la interpolación de requests.** Los argumentos los escribe un LLM. Sustitución restringida `{param}`, no motor de plantillas.
- **Ningún error de integración levanta excepción.** `tool_fn` re-lanza (`astromesh/runtime/engine.py:905-909`) y eso mata la corrida entera. Todo sale como `ToolResult(success=False, ...)`.
- **Nombres de tool `<slug>_<accion>` con guion bajo.** OpenAI y Anthropic validan contra `^[a-zA-Z0-9_-]{1,64}$`; un punto hace 400 la request entera.
- **Credenciales nunca en `arguments`, memoria, respuesta, spans ni logs.** Los args de tool se persisten en la traza (`engine.py:900`).
- **Retrocompatibilidad total.** `connections` ausente = `{}`. Todo agente y toda llamada existente sigue funcionando sin cambios.
- Line length 100, target py312 (ruff). Todo async. `asyncio_mode = "auto"`: los tests async no llevan decorador.
- Commits convencionales. **Regla de changelog del repo:** ningún commit `feat:`/`fix:`/`refactor:` sin su entrada en `CHANGELOG.md` bajo `## [Unreleased]`. Las tareas que lo requieren lo dicen en su paso de commit.

## Refinamiento sobre el spec

El spec (§3) ubica `schema.py` dentro de `astromesh/integrations/`. **Este plan lo pone en `astromesh/core/schema.py`.** Razón: `engine.py` es capa Runtime e `integrations/` es capa Infrastructure; hacer que el runtime importe un normalizador genérico desde una infraestructura concreta invierte la dependencia. `core/` es la capa que ambos ya consumen. Es el único punto donde el plan se aparta del spec.

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `astromesh/core/schema.py` | **Crear.** `normalize_tool_parameters` (mudado de `engine.py`). Compartido por engine e integrations. |
| `astromesh/integrations/__init__.py` | **Crear.** `IntegrationCatalog`: descubre, valida, cachea. |
| `astromesh/integrations/manifest.py` | **Crear.** Modelos pydantic del manifest + `load_manifest`. |
| `astromesh/integrations/interpolation.py` | **Crear.** Sustitución `{param}` + guardia de traversal. Aislado por ser crítico de seguridad. |
| `astromesh/integrations/auth.py` | **Crear.** Los 5 esquemas → headers/query. |
| `astromesh/integrations/errors.py` | **Crear.** HTTP → `error_kind`. |
| `astromesh/integrations/handlers.py` | **Crear.** Carga del escape `python:modulo:funcion`. |
| `astromesh/integrations/credentials.py` | **Crear.** `CredentialResolver` de 3 capas + `ResolvedConnection`. |
| `astromesh/integrations/executor.py` | **Crear.** `HttpActionExecutor` + `IntegrationContext`. |
| `astromesh/integrations/catalog/*/integration.yaml` | **Crear.** Los manifests. |
| `astromesh/core/tools.py` | **Modificar.** `ToolType.INTEGRATION`, `register_integration_tool`, rama de `execute`. |
| `astromesh/runtime/engine.py` | **Modificar.** Rama `integration` en `_build_agent`; `connections` por `run` → `tool_fn`. |
| `astromesh/api/routes/agents.py` | **Modificar.** `connections` en `AgentRunRequest`. |
| `astromesh/api/routes/integrations.py` | **Crear.** `GET /v1/integrations` y `/{slug}`. |
| `config/connections.yaml.example` | **Crear.** Plantilla self-hosted. |

---

### Task 1: Mudar el normalizador de parámetros a `core/schema.py`

Refactor puro, sin cambio de comportamiento. Habilita que el manifest reuse la misma taquigrafía que el YAML de agentes en vez de tener una segunda copia.

**Files:**
- Create: `astromesh/core/schema.py`
- Modify: `astromesh/runtime/engine.py:70-140` (borrar `_InvalidToolParameters` y `_normalize_tool_parameters`, importar desde `core.schema`)
- Test: `tests/test_core_schema.py`

**Interfaces:**
- Consumes: nada.
- Produces: `normalize_tool_parameters(parameters: dict | None) -> dict | None`, `InvalidToolParameters(Exception)` con atributo `.actual_type: str`. Las tareas 2 y 10 los usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_core_schema.py`:

```python
import pytest

from astromesh.core.schema import InvalidToolParameters, normalize_tool_parameters


def test_none_passes_through():
    assert normalize_tool_parameters(None) is None


def test_shorthand_is_wrapped():
    result = normalize_tool_parameters({"city": {"type": "string", "description": "Ciudad"}})
    assert result == {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "Ciudad"}},
    }


def test_real_json_schema_is_left_alone():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    assert normalize_tool_parameters(schema) == schema


def test_bare_object_gets_empty_properties():
    assert normalize_tool_parameters({"type": "object"}) == {"type": "object", "properties": {}}


def test_normalization_is_idempotent():
    once = normalize_tool_parameters({"city": {"type": "string"}})
    assert normalize_tool_parameters(once) == once


def test_non_mapping_raises_with_type_name():
    with pytest.raises(InvalidToolParameters) as exc:
        normalize_tool_parameters(["a", "b"])
    assert exc.value.actual_type == "list"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_core_schema.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'astromesh.core.schema'`

- [ ] **Step 3: Crear `astromesh/core/schema.py`**

Mover el cuerpo tal cual desde `engine.py`, renombrando sin el guion bajo inicial. **Copiar el docstring completo de `_normalize_tool_parameters` (`engine.py:81-131`) sin recortarlo** — explica por qué existe la función y qué se rompe sin ella; perderlo en la mudanza es perder la razón de ser del código.

```python
"""Normalización de esquemas de parámetros de tools.

Compartido por el loader de agentes (runtime) y por el marco de
integraciones (infrastructure): ambos aceptan la misma taquigrafía YAML.
"""


class InvalidToolParameters(Exception):
    """`parameters` presente pero no es un mapping (lista, string, int, bool).

    Lleva el nombre del tipo ofensor para que quien llame lo nombre en su
    warning.
    """

    def __init__(self, actual_type: str):
        self.actual_type = actual_type
        super().__init__(actual_type)


def normalize_tool_parameters(parameters: dict | None) -> dict | None:
    """<pegar acá el docstring íntegro de engine.py:81-131>"""
    if parameters is None:
        return None
    if not isinstance(parameters, dict):
        raise InvalidToolParameters(type(parameters).__name__)
    if parameters.get("type") == "object":
        normalized = dict(parameters)
        normalized.setdefault("properties", {})
        return normalized
    return {"type": "object", "properties": parameters}
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_core_schema.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Apuntar `engine.py` al módulo nuevo**

En `astromesh/runtime/engine.py`, borrar las clases/funciones `_InvalidToolParameters` (líneas 70-77) y `_normalize_tool_parameters` (líneas 80-140), y agregar el import junto a los demás del bloque superior:

```python
from astromesh.core.schema import InvalidToolParameters, normalize_tool_parameters
```

Actualizar los dos usos dentro de `_build_agent` (alrededor de `engine.py:547-548`):

```python
                try:
                    normalized_parameters = normalize_tool_parameters(tool_def.get("parameters"))
                except InvalidToolParameters as exc:
```

- [ ] **Step 6: Verificar que no quedó ninguna referencia vieja**

Run: `grep -rn "_normalize_tool_parameters\|_InvalidToolParameters" astromesh/ tests/ --include="*.py"`
Expected: sin resultados

- [ ] **Step 7: Correr la suite completa — el refactor no puede mover nada**

Run: `uv run pytest -q`
Expected: PASS, mismo total de tests que antes del cambio (los de `test_client_tools.py` cubren este camino)

- [ ] **Step 8: Lint**

Run: `uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/`
Expected: sin errores

- [ ] **Step 9: Commit**

Requiere entrada de changelog (`refactor:`). Agregar bajo `## [Unreleased]` → `### Changed`:
`- Normalización de parámetros de tools mudada a `astromesh/core/schema.py` para compartirla entre el loader de agentes y el marco de integraciones.`

```bash
git add astromesh/core/schema.py astromesh/runtime/engine.py tests/test_core_schema.py CHANGELOG.md
git commit -m "refactor(core): mover normalize_tool_parameters a core/schema.py"
```

---

### Task 2: Modelos del manifest

**Files:**
- Create: `astromesh/integrations/__init__.py` (vacío por ahora), `astromesh/integrations/manifest.py`
- Test: `tests/test_integration_manifest.py`

**Interfaces:**
- Consumes: `normalize_tool_parameters` de Task 1.
- Produces:
  - `AuthSpec` con `.scheme: str`, `.credential: str`, `.header_name: str | None`, `.param_name: str | None`
  - `RequestSpec` con `.method: str`, `.path: str`, `.query: dict`, `.headers: dict`, `.body: dict | None`
  - `ResponseSpec` con `.select: str | None`
  - `PaginationSpec` con `.style: str`, `.cursor_param: str`, `.cursor_path: str | None`, `.limit_param: str | None`, `.offset_param: str | None`
  - `ActionSpec` con `.name`, `.description`, `.parameters: dict`, `.request: RequestSpec | None`, `.handler: str | None`, `.response`, `.pagination`, `.writes: bool`, `.rate_limit: dict | None`, `.timeout_seconds: int | None`, `.allow_slash: list[str]`, y método `.tool_parameters() -> dict`
  - `IntegrationManifest` con `.slug: str`, `.version: str`, `.description: str`, `.base_url: str | None`, `.auth: AuthSpec`, `.defaults: Defaults`, `.actions: list[ActionSpec]`, y método `.action(name: str) -> ActionSpec | None`
  - `load_manifest(path: Path) -> IntegrationManifest`
  - `ManifestError(Exception)`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_manifest.py`:

```python
from pathlib import Path

import pytest

from astromesh.integrations.manifest import ManifestError, load_manifest

VALID = """
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: demo
  version: 0.1.0
  description: "Integración de prueba"
spec:
  base_url: "https://api.demo.test/v1"
  auth:
    scheme: bearer
    credential: access_token
  defaults:
    timeout_seconds: 20
    headers: {X-Demo: "1"}
  actions:
    - name: list_items
      description: "Lista items"
      parameters:
        owner: {type: string, description: "Dueño", required: true}
        limit: {type: integer, description: "Máximo", default: 25}
      request:
        method: GET
        path: "/{owner}/items"
        query: {limit: "{limit}"}
      response: {select: "data"}
      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}
    - name: create_item
      description: "Crea un item"
      writes: true
      handler: "python:astromesh.integrations.catalog.demo.handlers:create_item"
      parameters:
        title: {type: string, description: "Título", required: true}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "integration.yaml"
    path.write_text(text)
    return path


def test_loads_metadata_and_defaults(tmp_path):
    m = load_manifest(_write(tmp_path, VALID))
    assert m.slug == "demo"
    assert m.version == "0.1.0"
    assert m.base_url == "https://api.demo.test/v1"
    assert m.auth.scheme == "bearer"
    assert m.auth.credential == "access_token"
    assert m.defaults.timeout_seconds == 20
    assert m.defaults.headers == {"X-Demo": "1"}
    assert len(m.actions) == 2


def test_action_lookup(tmp_path):
    m = load_manifest(_write(tmp_path, VALID))
    assert m.action("list_items").description == "Lista items"
    assert m.action("nope") is None


def test_declarative_action_fields(tmp_path):
    action = load_manifest(_write(tmp_path, VALID)).action("list_items")
    assert action.request.method == "GET"
    assert action.request.path == "/{owner}/items"
    assert action.request.query == {"limit": "{limit}"}
    assert action.response.select == "data"
    assert action.pagination.style == "cursor"
    assert action.pagination.cursor_path == "paging.next"
    assert action.handler is None
    assert action.writes is False


def test_handler_action_fields(tmp_path):
    action = load_manifest(_write(tmp_path, VALID)).action("create_item")
    assert action.handler == "python:astromesh.integrations.catalog.demo.handlers:create_item"
    assert action.request is None
    assert action.writes is True


def test_tool_parameters_normalizes_shorthand_and_marks_required(tmp_path):
    params = load_manifest(_write(tmp_path, VALID)).action("list_items").tool_parameters()
    assert params["type"] == "object"
    assert params["required"] == ["owner"]
    assert params["properties"]["owner"] == {"type": "string", "description": "Dueño"}
    assert params["properties"]["limit"]["default"] == 25
    # la paginación cursor agrega un parámetro opcional
    assert "cursor" in params["properties"]
    assert "cursor" not in params["required"]


def test_tool_parameters_omits_cursor_without_pagination(tmp_path):
    params = load_manifest(_write(tmp_path, VALID)).action("create_item").tool_parameters()
    assert "cursor" not in params["properties"]


def test_rejects_action_with_both_request_and_handler(tmp_path):
    bad = VALID.replace(
        '      handler: "python:astromesh.integrations.catalog.demo.handlers:create_item"',
        '      handler: "python:x:y"\n      request: {method: POST, path: "/items"}',
    )
    with pytest.raises(ManifestError, match="request.*handler|handler.*request"):
        load_manifest(_write(tmp_path, bad))


def test_rejects_action_with_neither_request_nor_handler(tmp_path):
    bad = VALID.replace(
        '      handler: "python:astromesh.integrations.catalog.demo.handlers:create_item"\n', ""
    )
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, bad))


def test_rejects_unknown_auth_scheme(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, VALID.replace("scheme: bearer", "scheme: telepathy")))


def test_rejects_wrong_kind(tmp_path):
    with pytest.raises(ManifestError, match="kind"):
        load_manifest(_write(tmp_path, VALID.replace("kind: Integration", "kind: Agent")))


def test_rejects_empty_description(tmp_path):
    bad = VALID.replace('      description: "Lista items"', '      description: ""')
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, bad))


def test_rejects_duplicate_action_names(tmp_path):
    bad = VALID.replace("    - name: create_item", "    - name: list_items")
    with pytest.raises(ManifestError, match="duplicad"):
        load_manifest(_write(tmp_path, bad))
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_manifest.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'astromesh.integrations'`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/__init__.py` vacío (Task 7 lo llena) y `astromesh/integrations/manifest.py`:

```python
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
    body: dict | None = None


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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_manifest.py -v`
Expected: PASS, 12 tests

- [ ] **Step 5: Lint y commit**

Requiere entrada de changelog (`feat:`). Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: modelos y validación del manifest \`integration.yaml\`.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/ tests/test_integration_manifest.py CHANGELOG.md
git commit -m "feat(integrations): modelos y validación del manifest"
```

---

### Task 3: Interpolación y guardia de traversal

Módulo propio porque es la superficie de seguridad del marco: los valores que interpola los escribe un LLM.

**Files:**
- Create: `astromesh/integrations/interpolation.py`
- Test: `tests/test_integration_interpolation.py`

**Interfaces:**
- Consumes: nada.
- Produces: `interpolate(template: str, args: dict, *, position: str, allow_slash: bool = False) -> str`, `interpolate_structure(value, args, *, allow_slash_params: set[str]) -> Any`, `InterpolationError(Exception)`. `position` es `"path"`, `"query"` o `"raw"`. Task 9 los usa.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_interpolation.py`:

```python
import pytest

from astromesh.integrations.interpolation import (
    InterpolationError,
    interpolate,
    interpolate_structure,
)


def test_substitutes_named_placeholder():
    assert interpolate("/{owner}/items", {"owner": "acme"}, position="path") == "/acme/items"


def test_url_encodes_in_path():
    assert interpolate("/{name}", {"name": "a b&c"}, position="path") == "/a%20b%26c"


def test_query_position_encodes_too():
    assert interpolate("{q}", {"q": "hola mundo"}, position="query") == "hola%20mundo"


def test_raw_position_does_not_encode():
    assert interpolate("{q}", {"q": "hola mundo"}, position="raw") == "hola mundo"


def test_non_string_values_are_stringified():
    assert interpolate("{limit}", {"limit": 25}, position="query") == "25"
    assert interpolate("{flag}", {"flag": True}, position="query") == "true"


def test_multiple_placeholders():
    out = interpolate("/{a}/x/{b}", {"a": "1", "b": "2"}, position="path")
    assert out == "/1/x/2"


def test_text_without_placeholders_passes_through():
    assert interpolate("/static/path", {}, position="path") == "/static/path"


def test_missing_argument_raises():
    with pytest.raises(InterpolationError, match="owner"):
        interpolate("/{owner}/items", {}, position="path")


def test_slash_rejected_in_path_by_default():
    with pytest.raises(InterpolationError, match="barra|slash"):
        interpolate("/{owner}/items", {"owner": "a/b"}, position="path")


def test_slash_allowed_when_opted_in():
    out = interpolate("/{repo}/x", {"repo": "a/b"}, position="path", allow_slash=True)
    assert out == "/a/b/x"


def test_traversal_rejected_even_with_allow_slash():
    with pytest.raises(InterpolationError, match="\\.\\."):
        interpolate("/{repo}/x", {"repo": "../../me/accounts"}, position="path", allow_slash=True)


def test_encoded_traversal_rejected():
    with pytest.raises(InterpolationError):
        interpolate("/{p}", {"p": "%2e%2e/secrets"}, position="path")


def test_double_encoded_traversal_rejected():
    with pytest.raises(InterpolationError):
        interpolate("/{p}", {"p": "%252e%252e/secrets"}, position="path")


def test_slash_allowed_freely_in_query():
    assert interpolate("{q}", {"q": "a/b"}, position="query") == "a%2Fb"


def test_interpolate_structure_walks_nested_dicts_and_lists():
    out = interpolate_structure(
        {"a": "{x}", "b": [{"c": "{y}"}], "d": 7},
        {"x": "1", "y": "2"},
        allow_slash_params=set(),
    )
    assert out == {"a": "1", "b": [{"c": "2"}], "d": 7}


def test_interpolate_structure_keeps_whole_value_type_for_lone_placeholder():
    # Un body {"limit": "{limit}"} con limit=25 debe mandar 25, no "25".
    out = interpolate_structure({"limit": "{limit}"}, {"limit": 25}, allow_slash_params=set())
    assert out == {"limit": 25}
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_interpolation.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/interpolation.py`:

```python
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


def interpolate(
    template: str, args: dict, *, position: str, allow_slash: bool = False
) -> str:
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


def interpolate_structure(
    value: Any, args: dict, *, allow_slash_params: set[str]
) -> Any:
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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_interpolation.py -v`
Expected: PASS, 16 tests

- [ ] **Step 5: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: interpolación restringida de \`{param}\` con guardia anti-traversal.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/interpolation.py tests/test_integration_interpolation.py CHANGELOG.md
git commit -m "feat(integrations): interpolación restringida con guardia de traversal"
```

---

### Task 4: Esquemas de autenticación

**Files:**
- Create: `astromesh/integrations/auth.py`
- Test: `tests/test_integration_auth.py`

**Interfaces:**
- Consumes: `AuthSpec` de Task 2.
- Produces: `apply_auth(auth: AuthSpec, material: dict) -> tuple[dict, dict]` devolviendo `(headers, query_params)`; `CredentialMissing(Exception)`. Task 9 lo usa.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_auth.py`:

```python
import base64

import pytest

from astromesh.integrations.auth import CredentialMissing, apply_auth
from astromesh.integrations.manifest import AuthSpec


def test_bearer_sets_authorization_header():
    headers, params = apply_auth(
        AuthSpec(scheme="bearer", credential="access_token"), {"access_token": "T0K3N"}
    )
    assert headers == {"Authorization": "Bearer T0K3N"}
    assert params == {}


def test_header_scheme_uses_configured_name():
    headers, params = apply_auth(
        AuthSpec(scheme="header", credential="api_key", header_name="X-Api-Key"),
        {"api_key": "abc"},
    )
    assert headers == {"X-Api-Key": "abc"}
    assert params == {}


def test_query_scheme_puts_credential_in_params():
    headers, params = apply_auth(
        AuthSpec(scheme="query", credential="api_key", param_name="key"), {"api_key": "abc"}
    )
    assert headers == {}
    assert params == {"key": "abc"}


def test_basic_scheme_encodes_user_and_password():
    headers, _ = apply_auth(
        AuthSpec(scheme="basic", credential="basic"),
        {"basic": {"username": "u", "password": "p"}},
    )
    expected = base64.b64encode(b"u:p").decode()
    assert headers == {"Authorization": f"Basic {expected}"}


def test_none_scheme_adds_nothing():
    assert apply_auth(AuthSpec(scheme="none"), {}) == ({}, {})


def test_missing_credential_raises():
    with pytest.raises(CredentialMissing, match="access_token"):
        apply_auth(AuthSpec(scheme="bearer", credential="access_token"), {})


def test_empty_credential_raises():
    with pytest.raises(CredentialMissing):
        apply_auth(AuthSpec(scheme="bearer", credential="access_token"), {"access_token": ""})


def test_basic_missing_password_raises():
    with pytest.raises(CredentialMissing):
        apply_auth(AuthSpec(scheme="basic", credential="basic"), {"basic": {"username": "u"}})
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_auth.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/auth.py`:

```python
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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_auth.py -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: esquemas de autenticación bearer, header, query, basic y none.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/auth.py tests/test_integration_auth.py CHANGELOG.md
git commit -m "feat(integrations): esquemas de autenticación"
```

---

### Task 5: Clasificación de errores

**Files:**
- Create: `astromesh/integrations/errors.py`
- Test: `tests/test_integration_errors.py`

**Interfaces:**
- Consumes: nada.
- Produces: `classify_status(status_code: int) -> str`, `classify_exception(exc: Exception) -> str`, `retry_after_seconds(headers: dict) -> float | None`, y las constantes `CREDENTIAL_INVALID`, `RATE_LIMITED`, `UPSTREAM_ERROR`, `BAD_REQUEST`, `CREDENTIAL_MISSING`, `RATE_LIMITED_LOCAL`. Tasks 9 y 10 las usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_errors.py`:

```python
import httpx

from astromesh.integrations import errors


def test_401_and_403_are_credential_invalid():
    assert errors.classify_status(401) == errors.CREDENTIAL_INVALID
    assert errors.classify_status(403) == errors.CREDENTIAL_INVALID


def test_429_is_rate_limited():
    assert errors.classify_status(429) == errors.RATE_LIMITED


def test_408_and_5xx_are_upstream():
    assert errors.classify_status(408) == errors.UPSTREAM_ERROR
    assert errors.classify_status(500) == errors.UPSTREAM_ERROR
    assert errors.classify_status(503) == errors.UPSTREAM_ERROR


def test_other_4xx_is_bad_request():
    assert errors.classify_status(400) == errors.BAD_REQUEST
    assert errors.classify_status(404) == errors.BAD_REQUEST
    assert errors.classify_status(422) == errors.BAD_REQUEST


def test_timeout_and_network_are_upstream():
    assert errors.classify_exception(httpx.ConnectTimeout("t")) == errors.UPSTREAM_ERROR
    assert errors.classify_exception(httpx.ConnectError("c")) == errors.UPSTREAM_ERROR


def test_unknown_exception_is_upstream():
    assert errors.classify_exception(RuntimeError("boom")) == errors.UPSTREAM_ERROR


def test_retry_after_numeric_seconds():
    assert errors.retry_after_seconds({"Retry-After": "30"}) == 30.0


def test_retry_after_is_case_insensitive():
    assert errors.retry_after_seconds({"retry-after": "12"}) == 12.0


def test_retry_after_absent_or_unparseable():
    assert errors.retry_after_seconds({}) is None
    assert errors.retry_after_seconds({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_errors.py -v`
Expected: FAIL con `ImportError`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/errors.py`:

```python
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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_errors.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: clasificación de errores (\`error_kind\`) del contrato con Nexus.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/errors.py tests/test_integration_errors.py CHANGELOG.md
git commit -m "feat(integrations): clasificación de errores"
```

---

### Task 6: Carga del escape a Python

**Files:**
- Create: `astromesh/integrations/handlers.py`
- Test: `tests/test_integration_handlers.py`

**Interfaces:**
- Consumes: nada.
- Produces: `load_handler(ref: str) -> Callable`, `HandlerError(Exception)`. Tasks 9, 15 y 16 lo usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_handlers.py`:

```python
import pytest

from astromesh.integrations.handlers import HandlerError, load_handler


async def sample_handler(arguments, ctx):
    return {"ok": True}


def test_loads_callable_from_reference():
    fn = load_handler("python:tests.test_integration_handlers:sample_handler")
    assert fn is sample_handler


def test_rejects_reference_without_python_prefix():
    with pytest.raises(HandlerError, match="python:"):
        load_handler("tests.test_integration_handlers:sample_handler")


def test_rejects_malformed_reference():
    with pytest.raises(HandlerError):
        load_handler("python:no_colon_here")


def test_rejects_unknown_module():
    with pytest.raises(HandlerError, match="módulo|module"):
        load_handler("python:astromesh.nope.nope:fn")


def test_rejects_unknown_symbol():
    with pytest.raises(HandlerError, match="símbolo|symbol"):
        load_handler("python:tests.test_integration_handlers:no_existe")


def test_rejects_non_callable_symbol():
    with pytest.raises(HandlerError, match="invocable|callable"):
        load_handler("python:tests.test_integration_handlers:NOT_CALLABLE")


NOT_CALLABLE = 42
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_handlers.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/handlers.py`:

```python
"""Resolución del escape `handler: python:modulo:funcion`.

Se resuelve al cargar el catálogo, no en la primera llamada: un handler
mal referenciado tiene que romper el arranque de esa integración, no una
corrida en producción seis semanas después.
"""

from __future__ import annotations

import importlib
from typing import Callable


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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_handlers.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: carga del escape \`handler: python:modulo:funcion\`.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/handlers.py tests/test_integration_handlers.py CHANGELOG.md
git commit -m "feat(integrations): carga de handlers Python"
```

---

### Task 7: Catálogo y descubrimiento

**Files:**
- Modify: `astromesh/integrations/__init__.py`
- Create: `astromesh/integrations/catalog/__init__.py` (vacío)
- Test: `tests/test_integration_catalog.py`

**Interfaces:**
- Consumes: `load_manifest`, `ManifestError` (Task 2); `load_handler`, `HandlerError` (Task 6).
- Produces: `IntegrationCatalog` con `.discover(root: Path | None = None) -> int`, `.get(slug: str) -> IntegrationManifest | None`, `.all() -> list[IntegrationManifest]`; y `default_catalog() -> IntegrationCatalog` (singleton perezoso). Tasks 11, 12 y 16 los usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_catalog.py`:

```python
import logging

from astromesh.integrations import IntegrationCatalog

GOOD = """
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: {slug}
  version: 0.1.0
  description: "demo"
spec:
  base_url: "https://api.demo.test"
  auth: {{scheme: bearer, credential: access_token}}
  actions:
    - name: ping
      description: "Ping"
      request: {{method: GET, path: "/ping"}}
"""


def _make(root, slug, text=None):
    d = root / slug
    d.mkdir(parents=True)
    (d / "integration.yaml").write_text(text if text is not None else GOOD.format(slug=slug))
    return d


def test_discovers_every_manifest(tmp_path):
    _make(tmp_path, "alpha")
    _make(tmp_path, "beta")
    catalog = IntegrationCatalog()
    assert catalog.discover(tmp_path) == 2
    assert {m.slug for m in catalog.all()} == {"alpha", "beta"}


def test_get_returns_manifest_and_none(tmp_path):
    _make(tmp_path, "alpha")
    catalog = IntegrationCatalog()
    catalog.discover(tmp_path)
    assert catalog.get("alpha").slug == "alpha"
    assert catalog.get("nope") is None


def test_invalid_manifest_is_skipped_not_fatal(tmp_path, caplog):
    _make(tmp_path, "alpha")
    _make(tmp_path, "roto", text="kind: Agent\nmetadata: {name: roto}\n")
    catalog = IntegrationCatalog()
    with caplog.at_level(logging.ERROR):
        assert catalog.discover(tmp_path) == 1
    assert catalog.get("alpha") is not None
    assert catalog.get("roto") is None
    assert "roto" in caplog.text


def test_unresolvable_handler_skips_the_integration(tmp_path, caplog):
    bad = GOOD.format(slug="malo").replace(
        '      request: {method: GET, path: "/ping"}',
        '      handler: "python:no.existe.modulo:fn"',
    )
    _make(tmp_path, "malo", text=bad)
    catalog = IntegrationCatalog()
    with caplog.at_level(logging.ERROR):
        assert catalog.discover(tmp_path) == 0
    assert catalog.get("malo") is None


def test_directory_without_manifest_is_ignored(tmp_path):
    (tmp_path / "vacia").mkdir()
    _make(tmp_path, "alpha")
    catalog = IntegrationCatalog()
    assert catalog.discover(tmp_path) == 1


def test_slug_must_match_directory_name(tmp_path, caplog):
    _make(tmp_path, "carpeta", text=GOOD.format(slug="otro_nombre"))
    catalog = IntegrationCatalog()
    with caplog.at_level(logging.ERROR):
        assert catalog.discover(tmp_path) == 0


def test_discover_is_idempotent(tmp_path):
    _make(tmp_path, "alpha")
    catalog = IntegrationCatalog()
    catalog.discover(tmp_path)
    assert catalog.discover(tmp_path) == 1
    assert len(catalog.all()) == 1


def test_shipped_catalog_loads():
    """El catálogo real del repo tiene que descubrirse sin errores."""
    catalog = IntegrationCatalog()
    assert catalog.discover() >= 1
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_catalog.py -v`
Expected: FAIL con `ImportError: cannot import name 'IntegrationCatalog'`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/catalog/__init__.py` vacío, y escribir `astromesh/integrations/__init__.py`:

```python
"""Catálogo de integraciones declarativas."""

from __future__ import annotations

import logging
from pathlib import Path

from astromesh.integrations.handlers import HandlerError, load_handler
from astromesh.integrations.manifest import IntegrationManifest, ManifestError, load_manifest

logger = logging.getLogger(__name__)

_CATALOG_ROOT = Path(__file__).parent / "catalog"


class IntegrationCatalog:
    """Descubre, valida y cachea los manifests de `catalog/`."""

    def __init__(self):
        self._manifests: dict[str, IntegrationManifest] = {}

    def discover(self, root: Path | None = None) -> int:
        """Escanea `<root>/*/integration.yaml`. Devuelve cuántas cargaron.

        Una integración inválida se registra y se saltea: el runtime tiene
        que arrancar aunque un manifest esté roto. Mismo criterio que el
        loader de tools del YAML de agentes.
        """
        root = Path(root) if root is not None else _CATALOG_ROOT
        self._manifests = {}
        if not root.is_dir():
            logger.warning("catálogo de integraciones ausente en %s", root)
            return 0
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            path = directory / "integration.yaml"
            if not path.is_file():
                continue
            try:
                manifest = load_manifest(path)
            except ManifestError as exc:
                logger.error("integración %r inválida, se saltea: %s", directory.name, exc)
                continue
            if manifest.slug != directory.name:
                logger.error(
                    "integración en %s declara metadata.name %r — debe coincidir con "
                    "el nombre del directorio; se saltea.",
                    directory,
                    manifest.slug,
                )
                continue
            try:
                for action in manifest.actions:
                    if action.handler:
                        load_handler(action.handler)
            except HandlerError as exc:
                logger.error(
                    "integración %r tiene un handler irresoluble, se saltea: %s",
                    manifest.slug,
                    exc,
                )
                continue
            self._manifests[manifest.slug] = manifest
        return len(self._manifests)

    def get(self, slug: str) -> IntegrationManifest | None:
        return self._manifests.get(slug)

    def all(self) -> list[IntegrationManifest]:
        return list(self._manifests.values())


_default: IntegrationCatalog | None = None


def default_catalog() -> IntegrationCatalog:
    """Catálogo compartido del proceso, descubierto la primera vez que se pide."""
    global _default
    if _default is None:
        _default = IntegrationCatalog()
        _default.discover()
    return _default


__all__ = ["IntegrationCatalog", "default_catalog"]
```

- [ ] **Step 4: Correr los tests, salvo el del catálogo real que aún está vacío**

Run: `uv run pytest tests/test_integration_catalog.py -v -k "not shipped"`
Expected: PASS, 7 tests. `test_shipped_catalog_loads` falla hasta Task 13 — es intencional y sirve de recordatorio.

- [ ] **Step 5: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: catálogo auto-descubierto en \`astromesh/integrations/catalog/\`.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/ tests/test_integration_catalog.py CHANGELOG.md
git commit -m "feat(integrations): catálogo auto-descubierto"
```

---

### Task 8: Resolución de credenciales

**Files:**
- Create: `astromesh/integrations/credentials.py`, `config/connections.yaml.example`
- Test: `tests/test_integration_credentials.py`

**Interfaces:**
- Consumes: nada.
- Produces: `ResolvedConnection` (dataclass con `.name: str`, `.material: dict`, `.base_url: str | None`), `CredentialResolver` con `__init__(connections_file: Path | None = None)` y `.resolve(connection_name: str, bundle: dict | None) -> ResolvedConnection | None`. Tasks 9 y 10 lo usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_credentials.py`:

```python
from astromesh.integrations.credentials import CredentialResolver

FILE = """
connections:
  ig_main:
    access_token: "${IG_TOKEN}"
  crm:
    api_key: "${CRM_KEY}"
    base_url: "${CRM_URL}"
  literal:
    api_key: "sin-env"
"""


def _file(tmp_path):
    path = tmp_path / "connections.yaml"
    path.write_text(FILE)
    return path


def test_bundle_wins_over_file(tmp_path, monkeypatch):
    monkeypatch.setenv("IG_TOKEN", "del-archivo")
    resolver = CredentialResolver(_file(tmp_path))
    resolved = resolver.resolve("ig_main", {"ig_main": {"access_token": "del-bundle"}})
    assert resolved.material["access_token"] == "del-bundle"


def test_falls_back_to_file_with_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("IG_TOKEN", "T-env")
    resolver = CredentialResolver(_file(tmp_path))
    resolved = resolver.resolve("ig_main", {})
    assert resolved.material["access_token"] == "T-env"


def test_literal_values_pass_through(tmp_path):
    resolver = CredentialResolver(_file(tmp_path))
    assert resolver.resolve("literal", None).material["api_key"] == "sin-env"


def test_unset_env_var_yields_empty_string(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_TOKEN", raising=False)
    resolver = CredentialResolver(_file(tmp_path))
    assert resolver.resolve("ig_main", {}).material["access_token"] == ""


def test_base_url_is_separated_from_material(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_KEY", "K")
    monkeypatch.setenv("CRM_URL", "https://crm.acme.internal")
    resolved = CredentialResolver(_file(tmp_path)).resolve("crm", {})
    assert resolved.base_url == "https://crm.acme.internal"
    assert "base_url" not in resolved.material
    assert resolved.material == {"api_key": "K"}


def test_bundle_can_carry_base_url(tmp_path):
    resolved = CredentialResolver(None).resolve(
        "x", {"x": {"api_key": "K", "base_url": "https://a.test"}}
    )
    assert resolved.base_url == "https://a.test"
    assert resolved.material == {"api_key": "K"}


def test_unknown_connection_returns_none(tmp_path):
    assert CredentialResolver(_file(tmp_path)).resolve("no_existe", {}) is None


def test_missing_file_is_not_fatal(tmp_path):
    resolver = CredentialResolver(tmp_path / "no-existe.yaml")
    assert resolver.resolve("x", {"x": {"api_key": "K"}}).material == {"api_key": "K"}
    assert resolver.resolve("y", {}) is None


def test_no_file_configured_uses_bundle_only():
    resolver = CredentialResolver(None)
    assert resolver.resolve("x", {"x": {"a": "1"}}).material == {"a": "1"}
    assert resolver.resolve("x", {}) is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_credentials.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/credentials.py`:

```python
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
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_credentials.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Crear la plantilla self-hosted**

Crear `config/connections.yaml.example`:

```yaml
# Conexiones de integraciones para despliegues self-hosted.
#
# En un despliegue con Nexus este archivo no hace falta: Nexus custodia las
# credenciales e inyecta un bundle `connections` en cada corrida, que tiene
# prioridad sobre lo que haya acá.
#
# Copiar a config/connections.yaml (que va en .gitignore) y completar.
# Los ${VAR} se resuelven contra el entorno, igual que en channels.yaml.

connections:
  # Nombre libre; es lo que el YAML del agente pone en `connection:`.
  wa_main:
    access_token: "${WHATSAPP_ACCESS_TOKEN}"

  drive_main:
    access_token: "${GOOGLE_ACCESS_TOKEN}"

  # La integración `http` toma base_url de la conexión, no del manifest.
  crm_interno:
    api_key: "${CRM_API_KEY}"
    base_url: "${CRM_BASE_URL}"
```

Agregar `config/connections.yaml` a `.gitignore` (crear la línea si el archivo no la tiene):

```bash
grep -qxF 'config/connections.yaml' .gitignore || echo 'config/connections.yaml' >> .gitignore
```

- [ ] **Step 6: Verificar que el archivo real no se puede commitear por accidente**

Run: `touch config/connections.yaml && git status --porcelain config/connections.yaml && rm config/connections.yaml`
Expected: sin salida de `git status` (ignorado)

- [ ] **Step 7: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: resolución de credenciales por corrida (bundle de Nexus) con respaldo en \`config/connections.yaml\`.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/credentials.py tests/test_integration_credentials.py \
        config/connections.yaml.example .gitignore CHANGELOG.md
git commit -m "feat(integrations): resolución de credenciales por corrida"
```

---

### Task 9: Ejecutor HTTP

El corazón declarativo: manifest + argumentos + credencial → `ToolResult`.

**Files:**
- Create: `astromesh/integrations/executor.py`
- Test: `tests/test_integration_executor.py`

**Interfaces:**
- Consumes: `IntegrationManifest`/`ActionSpec` (Task 2), `interpolate`/`interpolate_structure` (Task 3), `apply_auth`/`CredentialMissing` (Task 4), `errors` (Task 5), `load_handler` (Task 6), `ResolvedConnection` (Task 8), `ToolResult` de `astromesh/tools/base.py`.
- Produces:
  - `IntegrationContext` (dataclass): `.client: httpx.AsyncClient`, `.base_url: str`, `.material: dict`, `.auth_headers: dict`, `.agent_name: str`, `.session_id: str`
  - `HttpActionExecutor` con `async execute(manifest, action, arguments, resolved, *, agent_name="", session_id="") -> ToolResult`
  - Task 10 lo usa.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_executor.py`:

```python
import httpx
import respx

from astromesh.integrations import errors
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor
from astromesh.integrations.manifest import IntegrationManifest, load_manifest

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test/v1"
  auth: {scheme: bearer, credential: access_token}
  defaults: {timeout_seconds: 5, headers: {X-Demo: "1"}}
  actions:
    - name: list_items
      description: "Lista"
      parameters:
        owner: {type: string, required: true}
        limit: {type: integer, default: 25}
      request:
        method: GET
        path: "/{owner}/items"
        query: {limit: "{limit}"}
      response: {select: "data"}
      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}
    - name: create_item
      description: "Crea"
      parameters:
        title: {type: string, required: true}
        count: {type: integer, default: 1}
      request:
        method: POST
        path: "/items"
        body: {title: "{title}", count: "{count}"}
    - name: custom
      description: "Handler"
      handler: "python:tests.test_integration_executor:_handler"
      parameters:
        x: {type: string, required: true}
"""

CONN = ResolvedConnection(name="c", material={"access_token": "T0K3N"})


async def _handler(arguments, ctx):
    from astromesh.tools.base import ToolResult

    return ToolResult(success=True, data={"echo": arguments["x"], "base": ctx.base_url})


def _manifest(tmp_path) -> IntegrationManifest:
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    return load_manifest(path)


@respx.mock
async def test_get_builds_url_query_headers_and_selects(tmp_path):
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}], "paging": {"next": "C2"}})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "limit": 10}, CONN
    )
    assert result.success is True
    assert result.data == [{"id": 1}]
    assert result.metadata["next_cursor"] == "C2"
    assert result.metadata["status_code"] == 200
    request = route.calls[0].request
    assert request.url.params["limit"] == "10"
    assert request.headers["Authorization"] == "Bearer T0K3N"
    assert request.headers["X-Demo"] == "1"


@respx.mock
async def test_default_is_applied_when_argument_absent(tmp_path):
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert route.calls[0].request.url.params["limit"] == "25"


@respx.mock
async def test_cursor_argument_is_sent_as_configured_param(tmp_path):
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "cursor": "C9"}, CONN
    )
    assert route.calls[0].request.url.params["after"] == "C9"


@respx.mock
async def test_offset_pagination_sends_limit_and_offset(tmp_path):
    manifest_text = MANIFEST.replace(
        '      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}',
        "      pagination: {style: offset, limit_param: per_page, offset_param: skip}",
    )
    path = tmp_path / "integration.yaml"
    path.write_text(manifest_text)
    m = load_manifest(path)
    route = respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "limit": 10, "cursor": "40"}, CONN
    )
    params = route.calls[0].request.url.params
    assert params["skip"] == "40"
    assert params["per_page"] == "10"


@respx.mock
async def test_offset_pagination_reports_the_next_offset(tmp_path):
    manifest_text = MANIFEST.replace(
        '      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}',
        "      pagination: {style: offset, limit_param: per_page, offset_param: skip}",
    )
    path = tmp_path / "integration.yaml"
    path.write_text(manifest_text)
    m = load_manifest(path)
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}, {"id": 2}]})
    )
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme", "cursor": "40"}, CONN
    )
    # 40 ya consumidos + 2 devueltos = el modelo pide desde 42.
    assert result.metadata["next_cursor"] == "42"


@respx.mock
async def test_offset_pagination_ends_when_page_is_empty(tmp_path):
    manifest_text = MANIFEST.replace(
        '      pagination: {style: cursor, cursor_param: after, cursor_path: "paging.next"}',
        "      pagination: {style: offset, limit_param: per_page, offset_param: skip}",
    )
    path = tmp_path / "integration.yaml"
    path.write_text(manifest_text)
    m = load_manifest(path)
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["next_cursor"] is None


@respx.mock
async def test_absent_next_cursor_is_none(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["next_cursor"] is None


@respx.mock
async def test_post_body_preserves_argument_types(tmp_path):
    import json

    route = respx.post("https://api.demo.test/v1/items").mock(
        return_value=httpx.Response(201, json={"id": 9})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("create_item"), {"title": "hola", "count": 3}, CONN
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"title": "hola", "count": 3}


@respx.mock
async def test_connection_base_url_overrides_manifest(tmp_path):
    route = respx.get("https://sandbox.demo.test/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    conn = ResolvedConnection(
        name="c", material={"access_token": "T"}, base_url="https://sandbox.demo.test"
    )
    await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, conn)
    assert route.calls[0].request.url.host == "sandbox.demo.test"


@respx.mock
async def test_401_maps_to_credential_invalid(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(return_value=httpx.Response(401))
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID


@respx.mock
async def test_429_carries_retry_after(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "17"})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["error_kind"] == errors.RATE_LIMITED
    assert result.metadata["retry_after"] == 17.0


@respx.mock
async def test_500_is_upstream_error(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(return_value=httpx.Response(500))
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


@respx.mock
async def test_timeout_is_upstream_error_not_exception(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(side_effect=httpx.ConnectTimeout("t"))
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


async def test_missing_credential_is_a_result_not_an_exception(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "acme"}, ResolvedConnection(name="c", material={})
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_MISSING


async def test_missing_required_argument_is_bad_request(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.BAD_REQUEST


async def test_traversal_argument_is_bad_request(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(
        m, m.action("list_items"), {"owner": "../../me"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.BAD_REQUEST


async def test_handler_action_receives_context(tmp_path):
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("custom"), {"x": "hola"}, CONN)
    assert result.success is True
    assert result.data == {"echo": "hola", "base": "https://api.demo.test/v1"}


async def test_handler_exception_degrades_the_call_not_the_run(tmp_path):
    m = _manifest(tmp_path)
    action = m.action("custom")
    action.handler = "python:tests.test_integration_executor:_boom"
    result = await HttpActionExecutor().execute(m, action, {"x": "1"}, CONN)
    assert result.success is False
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


async def _boom(arguments, ctx):
    raise RuntimeError("boom")


@respx.mock
async def test_non_json_response_is_returned_as_text(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, text="no soy json")
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert result.success is True
    assert result.data == "no soy json"


@respx.mock
async def test_credential_never_appears_in_result(tmp_path):
    respx.get("https://api.demo.test/v1/acme/items").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    m = _manifest(tmp_path)
    result = await HttpActionExecutor().execute(m, m.action("list_items"), {"owner": "acme"}, CONN)
    assert "T0K3N" not in str(result.to_dict())
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_executor.py -v`
Expected: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

Crear `astromesh/integrations/executor.py`:

```python
"""Ejecutor de acciones de integración: declarativas y con handler Python."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from astromesh.integrations import errors
from astromesh.integrations.auth import CredentialMissing, apply_auth
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.handlers import HandlerError, load_handler
from astromesh.integrations.interpolation import (
    InterpolationError,
    interpolate,
    interpolate_structure,
)
from astromesh.integrations.manifest import ActionSpec, IntegrationManifest
from astromesh.tools.base import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class IntegrationContext:
    """Lo que recibe un handler Python.

    Trae un cliente ya configurado con timeout y auth: un handler no
    reimplementa autenticación ni construye clientes.
    """

    client: httpx.AsyncClient
    base_url: str
    material: dict = field(default_factory=dict)
    auth_headers: dict = field(default_factory=dict)
    agent_name: str = ""
    session_id: str = ""


def _select(payload: Any, path: str | None) -> Any:
    """Camino separado por puntos dentro del payload. Ausente → payload entero."""
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _fail(kind: str, message: str, **metadata) -> ToolResult:
    return ToolResult(
        success=False, data=None, error=message, metadata={"error_kind": kind, **metadata}
    )


class HttpActionExecutor:
    """Convierte una acción del manifest en una llamada HTTP y su resultado."""

    async def execute(
        self,
        manifest: IntegrationManifest,
        action: ActionSpec,
        arguments: dict,
        resolved: ResolvedConnection,
        *,
        agent_name: str = "",
        session_id: str = "",
    ) -> ToolResult:
        """Nunca levanta. Todo fallo sale como ToolResult(success=False).

        `tool_fn` re-lanza lo que reciba y eso mata la corrida entera; un 404
        de un proveedor externo no puede tumbar al agente.
        """
        base_url = (resolved.base_url or manifest.base_url or "").rstrip("/")
        if not base_url:
            return _fail(
                errors.BAD_REQUEST,
                f"la integración '{manifest.slug}' no tiene base_url: ni el manifest ni la "
                f"conexión '{resolved.name}' lo declaran",
            )

        try:
            auth_headers, auth_params = apply_auth(manifest.auth, resolved.material)
        except CredentialMissing as exc:
            return _fail(errors.CREDENTIAL_MISSING, str(exc))

        args = self._with_defaults(action, arguments)
        timeout = action.timeout_seconds or manifest.defaults.timeout_seconds
        headers = {**manifest.defaults.headers, **auth_headers}

        if action.handler:
            return await self._run_handler(
                action, args, base_url, headers, resolved, timeout, agent_name, session_id
            )
        return await self._run_request(
            manifest, action, args, base_url, headers, auth_params, timeout
        )

    @staticmethod
    def _with_defaults(action: ActionSpec, arguments: dict) -> dict:
        args = dict(arguments or {})
        for name, spec in (action.parameters or {}).items():
            if name not in args and isinstance(spec, dict) and "default" in spec:
                args[name] = spec["default"]
        return args

    async def _run_handler(
        self, action, args, base_url, headers, resolved, timeout, agent_name, session_id
    ) -> ToolResult:
        try:
            fn = load_handler(action.handler)
        except HandlerError as exc:
            return _fail(errors.UPSTREAM_ERROR, str(exc))
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                ctx = IntegrationContext(
                    client=client,
                    base_url=base_url,
                    material=resolved.material,
                    auth_headers=headers,
                    agent_name=agent_name,
                    session_id=session_id,
                )
                result = await fn(args, ctx)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, data=result, metadata={})
        except Exception as exc:
            logger.warning("handler %s falló: %s", action.handler, exc)
            return _fail(errors.classify_exception(exc), f"{type(exc).__name__}: {exc}")

    async def _run_request(
        self, manifest, action, args, base_url, headers, auth_params, timeout
    ) -> ToolResult:
        allow_slash = set(action.allow_slash or [])
        try:
            path = self._render_path(action.request.path, args, allow_slash)
            params = {
                key: interpolate(str(value), args, position="query")
                for key, value in (action.request.query or {}).items()
            }
            params.update(auth_params)
            params.update(self._pagination_params(action, args))
            request_headers = {
                **headers,
                **{
                    k: interpolate(str(v), args, position="raw")
                    for k, v in (action.request.headers or {}).items()
                },
            }
            body = (
                interpolate_structure(action.request.body, args, allow_slash_params=allow_slash)
                if action.request.body is not None
                else None
            )
        except InterpolationError as exc:
            return _fail(errors.BAD_REQUEST, str(exc))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    action.request.method,
                    f"{base_url}{path}",
                    params=params,
                    headers=request_headers,
                    json=body,
                )
        except Exception as exc:
            logger.warning("%s.%s falló: %s", manifest.slug, action.name, exc)
            return _fail(errors.classify_exception(exc), f"{type(exc).__name__}: {exc}")

        return self._to_result(action, response, args)

    @staticmethod
    def _pagination_params(action: ActionSpec, args: dict) -> dict:
        """Traduce el `cursor` uniforme de la tool al dialecto del proveedor.

        El modelo siempre ve un parámetro llamado `cursor`; cómo se llama en
        el cable lo decide el manifest. En estilo `offset` el cursor es el
        número de items ya consumidos.
        """
        pagination = action.pagination
        if pagination is None:
            return {}
        params: dict = {}
        cursor = args.get("cursor")
        if pagination.style == "cursor":
            if cursor:
                params[pagination.cursor_param] = str(cursor)
            return params
        if cursor:
            params[pagination.offset_param] = str(cursor)
        if pagination.limit_param and args.get("limit") is not None:
            params[pagination.limit_param] = str(args["limit"])
        return params

    @staticmethod
    def _next_cursor(action: ActionSpec, payload, data, args: dict) -> str | None:
        """Cursor de la página siguiente, o None si no hay más.

        Estilo `cursor`: sale del payload. Estilo `offset`: se calcula
        sumando lo devuelto a lo ya consumido; una página vacía es el final.
        """
        pagination = action.pagination
        if pagination is None:
            return None
        if pagination.style == "cursor":
            value = _select(payload, pagination.cursor_path) if isinstance(payload, dict) else None
            return str(value) if value else None
        if not isinstance(data, list) or not data:
            return None
        try:
            consumed = int(args.get("cursor") or 0)
        except (TypeError, ValueError):
            consumed = 0
        return str(consumed + len(data))

    @staticmethod
    def _render_path(template: str, args: dict, allow_slash: set[str]) -> str:
        """Interpola el path segmento a segmento para respetar allow_slash por parámetro."""
        import re

        def _replace(match: re.Match) -> str:
            param = match.group(1)
            return interpolate(
                "{" + param + "}", args, position="path", allow_slash=param in allow_slash
            )

        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", _replace, template)

    @staticmethod
    def _to_result(action: ActionSpec, response: httpx.Response, args: dict) -> ToolResult:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        if response.status_code >= 400:
            kind = errors.classify_status(response.status_code)
            metadata = {"error_kind": kind, "status_code": response.status_code}
            if kind == errors.RATE_LIMITED:
                metadata["retry_after"] = errors.retry_after_seconds(response.headers)
            return ToolResult(
                success=False,
                data=None,
                error=f"HTTP {response.status_code}: {str(payload)[:500]}",
                metadata=metadata,
            )

        metadata: dict = {"status_code": response.status_code}
        data = _select(payload, action.response.select) if action.response else payload
        if action.pagination is not None:
            metadata["next_cursor"] = HttpActionExecutor._next_cursor(action, payload, data, args)
        return ToolResult(success=True, data=data, metadata=metadata)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_executor.py -v`
Expected: PASS, 20 tests

- [ ] **Step 5: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Marco de integraciones: ejecutor HTTP declarativo con paginación, selección de respuesta y escape a handlers Python.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/executor.py tests/test_integration_executor.py CHANGELOG.md
git commit -m "feat(integrations): ejecutor HTTP declarativo"
```

---

### Task 10: Tipo de tool y ejecución en el registro

**Files:**
- Modify: `astromesh/core/tools.py` (enum en `:18-26`, `ToolDefinition` en `:29-42`, `execute` en `:141-194`)
- Test: `tests/test_integration_tool_registry.py`

**Interfaces:**
- Consumes: todo lo de Tasks 2-9.
- Produces: `ToolType.INTEGRATION`; `ToolDefinition.integration_config: dict | None`; `ToolRegistry.register_integration_tool(name, manifest, action, connection, resolver=None, **kwargs)`; rama `INTEGRATION` en `execute` que lee `context["connections"]`. Task 11 la usa.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_tool_registry.py`:

```python
import httpx
import respx

from astromesh.core.tools import ToolRegistry, ToolType
from astromesh.integrations import errors
from astromesh.integrations.credentials import CredentialResolver
from astromesh.integrations.manifest import load_manifest

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Ping al servicio"
      request: {method: GET, path: "/ping"}
    - name: write_thing
      description: "Escribe"
      writes: true
      request: {method: POST, path: "/thing"}
"""


def _registry(tmp_path):
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    manifest = load_manifest(path)
    registry = ToolRegistry()
    registry.register_integration_tool(
        name="demo_ping",
        manifest=manifest,
        action=manifest.action("ping"),
        connection="demo_conn",
        resolver=CredentialResolver(None),
    )
    return registry, manifest


def test_registers_with_integration_type(tmp_path):
    registry, _ = _registry(tmp_path)
    assert registry._tools["demo_ping"].tool_type == ToolType.INTEGRATION
    assert registry._tools["demo_ping"].integration_config["action"] == "ping"
    assert registry._tools["demo_ping"].integration_config["connection"] == "demo_conn"


def test_schema_uses_action_description_and_parameters(tmp_path):
    registry, _ = _registry(tmp_path)
    schema = next(s for s in registry.get_tool_schemas() if s["function"]["name"] == "demo_ping")
    assert schema["function"]["description"] == "Ping al servicio"
    assert schema["function"]["parameters"]["type"] == "object"


def test_writes_action_sets_requires_approval(tmp_path):
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    manifest = load_manifest(path)
    registry = ToolRegistry()
    registry.register_integration_tool(
        name="demo_write_thing",
        manifest=manifest,
        action=manifest.action("write_thing"),
        connection="c",
        resolver=CredentialResolver(None),
    )
    assert registry._tools["demo_write_thing"].requires_approval is True


@respx.mock
async def test_execute_uses_connections_from_context(tmp_path):
    route = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"pong": True})
    )
    registry, _ = _registry(tmp_path)
    result = await registry.execute(
        "demo_ping",
        {},
        {"agent": "a", "session": "s", "connections": {"demo_conn": {"access_token": "T"}}},
    )
    assert result["success"] is True
    assert result["data"] == {"pong": True}
    assert route.calls[0].request.headers["Authorization"] == "Bearer T"


async def test_execute_without_connection_returns_credential_missing(tmp_path):
    registry, _ = _registry(tmp_path)
    result = await registry.execute("demo_ping", {}, {"agent": "a", "session": "s"})
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == errors.CREDENTIAL_MISSING


async def test_execute_never_raises_on_unknown_connection(tmp_path):
    registry, _ = _registry(tmp_path)
    result = await registry.execute(
        "demo_ping", {}, {"connections": {"otra": {"access_token": "T"}}}
    )
    assert result["success"] is False


@respx.mock
async def test_rate_limit_still_applies_to_integration_tools(tmp_path):
    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    path = tmp_path / "integration.yaml"
    path.write_text(MANIFEST)
    manifest = load_manifest(path)
    registry = ToolRegistry()
    registry.register_integration_tool(
        name="demo_ping",
        manifest=manifest,
        action=manifest.action("ping"),
        connection="c",
        resolver=CredentialResolver(None),
        rate_limit={"window_seconds": 60, "max_calls": 1},
    )
    ctx = {"connections": {"c": {"access_token": "T"}}}
    first = await registry.execute("demo_ping", {}, ctx)
    second = await registry.execute("demo_ping", {}, ctx)
    assert first["success"] is True
    assert "error" in second and "Rate limit" in second["error"]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_tool_registry.py -v`
Expected: FAIL con `AttributeError: 'ToolRegistry' object has no attribute 'register_integration_tool'`

- [ ] **Step 3: Sumar el tipo y el campo**

En `astromesh/core/tools.py`, agregar al enum `ToolType` (después de `AGENT`, línea 26):

```python
    INTEGRATION = "integration"
```

Y a `ToolDefinition` (después de `context_transform`, línea 42):

```python
    integration_config: dict | None = None
```

- [ ] **Step 4: Agregar `register_integration_tool`**

En `ToolRegistry`, después de `register_client_tool` (línea 139):

```python
    def register_integration_tool(
        self,
        name: str,
        manifest,
        action,
        connection: str,
        resolver=None,
        **kwargs,
    ):
        """Registra una acción de integración como tool invocable.

        El nombre lo compone quien llama como `<slug>_<accion>` — con guion
        bajo, no punto: OpenAI y Anthropic validan los nombres de función
        contra `^[a-zA-Z0-9_-]{1,64}$` y un punto hace 400 la request entera.

        Las credenciales NO se capturan acá: se resuelven en cada `execute`
        desde el bundle de la corrida. El registro es por agente, el bundle
        es por corrida, y mezclarlos filtraría credenciales entre corridas.
        """
        self._tools[name] = ToolDefinition(
            name=name,
            description=action.description,
            tool_type=ToolType.INTEGRATION,
            parameters=action.tool_parameters(),
            requires_approval=action.writes,
            timeout_seconds=action.timeout_seconds or manifest.defaults.timeout_seconds,
            integration_config={
                "slug": manifest.slug,
                "action": action.name,
                "connection": connection,
                "manifest": manifest,
                "action_spec": action,
                "resolver": resolver,
            },
            **kwargs,
        )
```

- [ ] **Step 5: Agregar la rama de ejecución**

En `ToolRegistry.execute`, después de la rama `AGENT` y antes del `return` final de tipo no soportado:

```python
        elif tool.tool_type == ToolType.INTEGRATION:
            from astromesh.integrations import errors as integration_errors
            from astromesh.integrations.executor import HttpActionExecutor

            config = tool.integration_config or {}
            resolver = config.get("resolver")
            bundle = (context or {}).get("connections") or {}
            connection_name = config["connection"]
            resolved = (
                resolver.resolve(connection_name, bundle)
                if resolver is not None
                else None
            )
            if resolved is None:
                return {
                    "success": False,
                    "data": None,
                    "metadata": {"error_kind": integration_errors.CREDENTIAL_MISSING},
                    "error": (
                        f"la conexión '{connection_name}' no está configurada para la "
                        f"integración '{config['slug']}'"
                    ),
                }
            result = await HttpActionExecutor().execute(
                config["manifest"],
                config["action_spec"],
                arguments,
                resolved,
                agent_name=(context or {}).get("agent", ""),
                session_id=(context or {}).get("session", ""),
            )
            return result.to_dict()
```

Nota: el chequeo de rate limit ya corre para todos los tipos al principio de `execute` (`core/tools.py:145-146`), así que las integraciones lo heredan sin cambios.

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_tool_registry.py -v`
Expected: PASS, 7 tests

- [ ] **Step 7: Verificar que no se rompió nada del registro existente**

Run: `uv run pytest tests/test_tools.py tests/test_client_tools.py tests/test_agent_as_tool.py tests/test_all_tools_registry.py -q`
Expected: PASS

- [ ] **Step 8: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- \`ToolType.INTEGRATION\`: las acciones de integración se registran y ejecutan como tools, resolviendo credenciales por corrida.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/core/tools.py tests/test_integration_tool_registry.py CHANGELOG.md
git commit -m "feat(core): tipo de tool integration en el registro"
```

---

### Task 11: Wiring en el runtime

**Files:**
- Modify: `astromesh/runtime/engine.py` — rama nueva en `_build_agent` (junto a `:545-566`), `AgentRuntime.run` (`:612-620`), `Agent.run` (`:769`), `tool_fn` (`:897-899`)
- Test: `tests/test_integration_engine.py`

**Interfaces:**
- Consumes: `default_catalog` (Task 7), `CredentialResolver` (Task 8), `register_integration_tool` (Task 10).
- Produces: `AgentRuntime.run(..., connections: dict | None = None)`; `Agent.run(..., connections=None)`; soporte de `type: integration` en el YAML de agentes. Task 12 lo usa.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_engine.py`:

```python
import logging

import httpx
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: demo}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Ping"
      request: {method: GET, path: "/ping"}
    - name: pong
      description: "Pong"
      request: {method: GET, path: "/pong"}
"""

AGENT = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "demo-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "demo_conn",
                "actions": ["ping"],
            }
        ],
    },
}


def _catalog(tmp_path):
    from astromesh.integrations import IntegrationCatalog

    root = tmp_path / "catalog"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "integration.yaml").write_text(MANIFEST)
    catalog = IntegrationCatalog()
    catalog.discover(root)
    return catalog


def _runtime(tmp_path, agent_config, monkeypatch):
    import astromesh.runtime.engine as engine_module

    monkeypatch.setattr(engine_module, "default_catalog", lambda: _catalog(tmp_path))
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "demo-agent.agent.yaml").write_text(yaml.safe_dump(agent_config))
    runtime = AgentRuntime(config_dir=config_dir)
    runtime.load_agents()
    return runtime


def test_allowlisted_action_is_registered_with_underscore_name(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, AGENT, monkeypatch)
    tools = runtime._agents["demo-agent"]._tools
    assert "demo_ping" in tools._tools
    assert "demo_pong" not in tools._tools


def test_action_outside_allowlist_is_not_exposed_to_the_model(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, AGENT, monkeypatch)
    names = {
        s["function"]["name"] for s in runtime._agents["demo-agent"]._tools.get_tool_schemas()
    }
    assert names == {"demo_ping"}


def test_unknown_integration_warns_and_skips(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0]["name"] = "no_existe"
    with caplog.at_level(logging.WARNING):
        runtime = _runtime(tmp_path, config, monkeypatch)
    assert runtime._agents["demo-agent"]._tools._tools == {}
    assert "no_existe" in caplog.text


def test_unknown_action_skips_only_that_action(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0]["actions"] = ["ping", "no_existe"]
    with caplog.at_level(logging.WARNING):
        runtime = _runtime(tmp_path, config, monkeypatch)
    tools = runtime._agents["demo-agent"]._tools._tools
    assert "demo_ping" in tools
    assert "no_existe" in caplog.text


def test_missing_actions_key_warns_and_skips_integration(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0].pop("actions")
    with caplog.at_level(logging.WARNING):
        runtime = _runtime(tmp_path, config, monkeypatch)
    assert runtime._agents["demo-agent"]._tools._tools == {}
    assert "actions" in caplog.text


def test_missing_connection_key_warns_and_skips_integration(tmp_path, monkeypatch, caplog):
    config = yaml.safe_load(yaml.safe_dump(AGENT))
    config["spec"]["tools"][0].pop("connection")
    with caplog.at_level(logging.WARNING):
        runtime = _runtime(tmp_path, config, monkeypatch)
    assert runtime._agents["demo-agent"]._tools._tools == {}
    assert "connection" in caplog.text


@respx.mock
async def test_connections_bundle_reaches_the_tool(tmp_path, monkeypatch):
    route = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"pong": True})
    )
    runtime = _runtime(tmp_path, AGENT, monkeypatch)
    tools = runtime._agents["demo-agent"]._tools
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"demo_conn": {"access_token": "T"}}}
    )
    assert result["success"] is True
    assert route.calls[0].request.headers["Authorization"] == "Bearer T"


async def test_run_accepts_connections_and_defaults_to_empty(tmp_path, monkeypatch):
    import inspect

    from astromesh.runtime.engine import Agent

    assert "connections" in inspect.signature(AgentRuntime.run).parameters
    assert "connections" in inspect.signature(Agent.run).parameters
    assert inspect.signature(AgentRuntime.run).parameters["connections"].default is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_engine.py -v`
Expected: FAIL — la rama `integration` no existe, así que `_tools._tools` queda vacío y el warning dice "unsupported type"

- [ ] **Step 3: Importar el catálogo y el resolver en `engine.py`**

Agregar al bloque de imports de `astromesh/runtime/engine.py`:

```python
from astromesh.integrations import default_catalog
from astromesh.integrations.credentials import CredentialResolver
```

- [ ] **Step 4: Agregar la rama `integration` en `_build_agent`**

En el bucle de tools de `_build_agent`, entre la rama `client` y el `else` final (`engine.py:566-567`):

```python
            elif tool_type == "integration":
                slug = tool_def.get("name")
                integration = default_catalog().get(slug)
                if integration is None:
                    logger.warning(
                        "agent %r declara la integración %r, que no existe en el catálogo — "
                        "se ignora.",
                        metadata["name"],
                        slug,
                    )
                    continue
                connection = tool_def.get("connection")
                if not connection:
                    logger.warning(
                        "agent %r declara la integración %r sin 'connection' — se ignora.",
                        metadata["name"],
                        slug,
                    )
                    continue
                action_names = tool_def.get("actions")
                if not action_names:
                    # La allowlist es obligatoria: exponer todas las acciones de varias
                    # integraciones infla el prompt y empeora la elección del modelo.
                    logger.warning(
                        "agent %r declara la integración %r sin 'actions' — la allowlist "
                        "es obligatoria, se ignora.",
                        metadata["name"],
                        slug,
                    )
                    continue
                resolver = self._credential_resolver()
                for action_name in action_names:
                    action = integration.action(action_name)
                    if action is None:
                        logger.warning(
                            "agent %r declara la acción %r de la integración %r, que no "
                            "existe — se ignora sólo esa acción.",
                            metadata["name"],
                            action_name,
                            slug,
                        )
                        continue
                    tools.register_integration_tool(
                        name=f"{integration.slug}_{action.name}",
                        manifest=integration,
                        action=action,
                        connection=connection,
                        resolver=resolver,
                        rate_limit=(
                            tool_def.get("rate_limit")
                            or action.rate_limit
                            or integration.defaults.rate_limit
                        ),
                    )
```

- [ ] **Step 5: Agregar el resolver cacheado a `AgentRuntime`**

Como método de `AgentRuntime`, junto a los demás `_build_*`:

```python
    def _credential_resolver(self) -> CredentialResolver:
        """Un resolver por runtime; lee config/connections.yaml una sola vez."""
        if getattr(self, "_resolver", None) is None:
            self._resolver = CredentialResolver(self._config_dir / "connections.yaml")
        return self._resolver
```

- [ ] **Step 6: Enhebrar `connections` por `run`**

`AgentRuntime.run` (`engine.py:612-620`):

```python
    async def run(
        self,
        agent_name,
        query,
        session_id,
        context=None,
        parent_trace_id=None,
        on_event=None,
        connections=None,
    ):
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Agent '{agent_name}' not found")
        return await agent.run(
            query,
            session_id,
            context,
            parent_trace_id=parent_trace_id,
            on_event=on_event,
            connections=connections,
        )
```

`Agent.run` (`engine.py:769`):

```python
    async def run(
        self,
        query,
        session_id,
        context=None,
        parent_trace_id=None,
        on_event=None,
        connections=None,
    ):
```

Y dentro de `tool_fn` (`engine.py:897-899`):

```python
                    observation = await self._tools.execute(
                        name,
                        args,
                        {
                            "agent": self.name,
                            "session": session_id,
                            "connections": connections or {},
                        },
                    )
```

- [ ] **Step 7: Propagar `connections` a los sub-agentes**

En la rama `AGENT` de `ToolRegistry.execute` (`astromesh/core/tools.py:187-193`), pasar el bundle al runtime hijo para que una integración funcione igual dentro de un agente-como-tool:

```python
            return await self._runtime.run(
                agent_name,
                query,
                session_id=session_id,
                context=transform_ctx,
                parent_trace_id=parent_trace_id,
                connections=(context or {}).get("connections") or {},
            )
```

- [ ] **Step 8: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_engine.py -v`
Expected: PASS, 8 tests

- [ ] **Step 9: Correr la suite completa — nada existente puede romperse**

Run: `uv run pytest -q`
Expected: PASS (salvo `test_shipped_catalog_loads`, que espera Task 13)

- [ ] **Step 10: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- YAML de agentes: \`type: integration\` con \`connection\` y allowlist de \`actions\`.`
`- \`AgentRuntime.run()\` acepta \`connections\`: bundle de credenciales por corrida, propagado a los agentes-como-tool.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/runtime/engine.py astromesh/core/tools.py tests/test_integration_engine.py CHANGELOG.md
git commit -m "feat(runtime): tools de integración desde el YAML de agentes"
```

---

### Task 12: Superficie de API

**Files:**
- Create: `astromesh/api/routes/integrations.py`
- Modify: `astromesh/api/routes/agents.py` (`AgentRunRequest` en `:38-41`, la llamada en `:204`), `astromesh/api/main.py` (registro del router), `astromesh/api/routes/tools.py` (`list_tools` en `:12-14`)
- Test: `tests/test_integration_api.py`

**Interfaces:**
- Consumes: `default_catalog` (Task 7), `connections` en `run` (Task 11).
- Produces: `GET /v1/integrations`, `GET /v1/integrations/{slug}`, campo `connections` en `AgentRunRequest`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_api.py`:

```python
async def test_list_integrations(client):
    response = await client.get("/v1/integrations")
    assert response.status_code == 200
    body = response.json()
    slugs = {item["slug"] for item in body["integrations"]}
    assert {"http", "whatsapp", "google_drive"} <= slugs
    assert body["count"] == len(body["integrations"])


async def test_integration_detail_lists_actions_and_required_credentials(client):
    response = await client.get("/v1/integrations/whatsapp")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "whatsapp"
    assert body["auth"]["scheme"] == "bearer"
    assert body["auth"]["credential"] == "access_token"
    names = {a["name"] for a in body["actions"]}
    assert "send_text" in names
    action = next(a for a in body["actions"] if a["name"] == "send_text")
    assert action["writes"] is True
    assert action["parameters"]["type"] == "object"


async def test_unknown_integration_is_404(client):
    assert (await client.get("/v1/integrations/no_existe")).status_code == 404


async def test_detail_never_exposes_credential_values(client, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "SECRETO-XYZ")
    body = (await client.get("/v1/integrations/whatsapp")).text
    assert "SECRETO-XYZ" not in body


async def test_list_tools_reports_integration_actions(client):
    body = (await client.get("/v1/tools")).json()
    names = {t["name"] for t in body["tools"]}
    assert "whatsapp_send_text" in names


async def test_run_request_accepts_connections_field():
    from astromesh.api.routes.agents import AgentRunRequest

    request = AgentRunRequest(query="hola", connections={"c": {"access_token": "T"}})
    assert request.connections == {"c": {"access_token": "T"}}
    assert AgentRunRequest(query="hola").connections is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_api.py -v`
Expected: FAIL con 404 en `/v1/integrations`

- [ ] **Step 3: Crear el router**

Crear `astromesh/api/routes/integrations.py`:

```python
"""Catálogo de integraciones expuesto por HTTP.

Publica *qué* material de credencial hay que entregar, nunca valores: es lo
que Nexus consume para pintar la UI de conexiones y armar el OAuth.
"""

from fastapi import APIRouter, HTTPException

from astromesh.integrations import default_catalog

router = APIRouter()


def _action_payload(action) -> dict:
    return {
        "name": action.name,
        "description": action.description,
        "writes": action.writes,
        "parameters": action.tool_parameters(),
        "paginated": action.pagination is not None,
    }


def _manifest_payload(manifest, *, with_actions: bool) -> dict:
    payload = {
        "slug": manifest.slug,
        "version": manifest.version,
        "description": manifest.description,
        "base_url": manifest.base_url,
        "auth": {
            "scheme": manifest.auth.scheme,
            "credential": manifest.auth.credential,
        },
        "action_count": len(manifest.actions),
    }
    if with_actions:
        payload["actions"] = [_action_payload(a) for a in manifest.actions]
    return payload


@router.get("/integrations")
async def list_integrations():
    manifests = default_catalog().all()
    return {
        "integrations": [_manifest_payload(m, with_actions=False) for m in manifests],
        "count": len(manifests),
    }


@router.get("/integrations/{slug}")
async def get_integration(slug: str):
    manifest = default_catalog().get(slug)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Integration '{slug}' not found")
    return _manifest_payload(manifest, with_actions=True)
```

- [ ] **Step 4: Registrar el router**

En `astromesh/api/main.py`, seguir el patrón de los demás routers: importar `integrations` y sumar `app.include_router(integrations.router, prefix="/v1")` junto a los otros `include_router` con prefijo `/v1`. Este router no necesita `set_runtime` — el catálogo es estático.

- [ ] **Step 5: Aceptar `connections` en el run**

En `astromesh/api/routes/agents.py`, agregar el campo a `AgentRunRequest` (línea 38):

```python
class AgentRunRequest(BaseModel):
    query: str
    session_id: str = "default"
    context: dict | None = None
    connections: dict | None = None
    """Credenciales resueltas por corrida, inyectadas por el plano de control.

    No se persisten: no entran a la traza, ni a la memoria, ni a la respuesta.
    """
```

Y pasarlo en la llamada (línea 204):

```python
        result = await _runtime.run(
            agent_name,
            request.query,
            request.session_id,
            context,
            connections=request.connections,
        )
```

- [ ] **Step 6: Llenar `GET /v1/tools`**

En `astromesh/api/routes/tools.py`, reemplazar el cuerpo de `list_tools` (líneas 12-14):

```python
@router.get("/tools")
async def list_tools():
    """Todo lo invocable del catálogo: builtins y acciones de integración."""
    from astromesh.integrations import default_catalog
    from astromesh.tools import ToolLoader

    loader = ToolLoader()
    loader.auto_discover()
    tools = [
        {
            "name": loader.get(name).name,
            "description": loader.get(name).description,
            "type": "builtin",
        }
        for name in loader.list_available()
    ]
    for manifest in default_catalog().all():
        for action in manifest.actions:
            tools.append(
                {
                    "name": f"{manifest.slug}_{action.name}",
                    "description": action.description,
                    "type": "integration",
                    "integration": manifest.slug,
                    "writes": action.writes,
                }
            )
    return {"tools": tools, "count": len(tools)}
```

- [ ] **Step 7: Correr el test**

Run: `uv run pytest tests/test_integration_api.py -v`
Expected: FAIL en los que piden `whatsapp`/`google_drive`/`http` — esos manifests llegan en Tasks 13-14. `test_run_request_accepts_connections_field` y `test_unknown_integration_is_404` deben PASAR ya.

Run: `uv run pytest tests/test_integration_api.py -v -k "connections_field or 404"`
Expected: PASS, 2 tests

- [ ] **Step 8: Verificar que la API sigue arrancando sin extras**

Run: `uv run python -c "import astromesh.api.main; print('import ok')"`
Expected: `import ok`. Es la compuerta que decide si `astromesh-os` puede construir la imagen.

- [ ] **Step 9: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- \`GET /v1/integrations\` y \`GET /v1/integrations/{slug}\`: catálogo de integraciones con acciones y credenciales requeridas.`
`- \`POST /v1/agents/{name}/run\` acepta \`connections\`.`
Bajo `### Fixed`:
`- \`GET /v1/tools\` devolvía una lista vacía fija; ahora reporta builtins y acciones de integración.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/api/ tests/test_integration_api.py CHANGELOG.md
git commit -m "feat(api): catálogo de integraciones y connections en el run"
```

---

### Task 13: Manifests `http` y `whatsapp`

**Files:**
- Create: `astromesh/integrations/catalog/http/integration.yaml`, `astromesh/integrations/catalog/whatsapp/integration.yaml`
- Test: `tests/test_integration_catalog_http.py`, `tests/test_integration_catalog_whatsapp.py`

**Interfaces:**
- Consumes: todo el marco.
- Produces: las integraciones `http` (acciones `get`, `post`, `put`, `delete`) y `whatsapp` (`send_text`, `send_template`, `get_media`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_integration_catalog_http.py`:

```python
import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor


def _http():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("http")


def test_manifest_has_no_base_url_so_the_connection_must_bring_it():
    assert _http().base_url is None


def test_exposes_the_four_verbs():
    assert {a.name for a in _http().actions} == {"get", "post", "put", "delete"}


def test_write_verbs_are_marked_as_writes():
    actions = {a.name: a for a in _http().actions}
    assert actions["get"].writes is False
    assert actions["post"].writes is True
    assert actions["put"].writes is True
    assert actions["delete"].writes is True


@respx.mock
async def test_get_against_a_connection_base_url():
    route = respx.get("https://crm.acme.internal/customers").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    manifest = _http()
    conn = ResolvedConnection(
        name="crm", material={"api_key": "K"}, base_url="https://crm.acme.internal"
    )
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get"), {"path": "/customers"}, conn
    )
    assert result.success is True
    assert result.data == {"ok": True}
    assert route.calls[0].request.headers["X-Api-Key"] == "K"


async def test_without_base_url_it_fails_cleanly():
    manifest = _http()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get"), {"path": "/x"}, ResolvedConnection("c", {"api_key": "K"})
    )
    assert result.success is False
    assert "base_url" in result.error


@respx.mock
async def test_post_sends_the_body_through():
    import json

    route = respx.post("https://crm.acme.internal/customers").mock(
        return_value=httpx.Response(201, json={"id": 1})
    )
    manifest = _http()
    conn = ResolvedConnection("crm", {"api_key": "K"}, base_url="https://crm.acme.internal")
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("post"), {"path": "/customers", "body": {"name": "Ana"}}, conn
    )
    assert result.success is True
    assert json.loads(route.calls[0].request.content) == {"name": "Ana"}


async def test_path_traversal_is_rejected():
    manifest = _http()
    conn = ResolvedConnection("crm", {"api_key": "K"}, base_url="https://crm.acme.internal")
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get"), {"path": "/../../admin"}, conn
    )
    assert result.success is False
```

Crear `tests/test_integration_catalog_whatsapp.py`:

```python
import json

import httpx
import respx

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

CONN = ResolvedConnection(name="wa", material={"access_token": "T0K3N"})


def _whatsapp():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("whatsapp")


def test_uses_the_graph_api_base_and_bearer_auth():
    manifest = _whatsapp()
    assert manifest.base_url == "https://graph.facebook.com/v21.0"
    assert manifest.auth.scheme == "bearer"
    assert manifest.auth.credential == "access_token"


def test_exposes_the_outbound_actions():
    assert {a.name for a in _whatsapp().actions} == {"send_text", "send_template", "get_media"}


def test_send_actions_are_marked_as_writes():
    actions = {a.name: a for a in _whatsapp().actions}
    assert actions["send_text"].writes is True
    assert actions["send_template"].writes is True
    assert actions["get_media"].writes is False


@respx.mock
async def test_send_text_builds_the_graph_payload():
    route = respx.post("https://graph.facebook.com/v21.0/PHONE1/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})
    )
    manifest = _whatsapp()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("send_text"),
        {"phone_number_id": "PHONE1", "to": "5491100000000", "text": "hola"},
        CONN,
    )
    assert result.success is True
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer T0K3N"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "to": "5491100000000",
        "type": "text",
        "text": {"body": "hola"},
    }


@respx.mock
async def test_get_media_resolves_the_media_url():
    respx.get("https://graph.facebook.com/v21.0/MEDIA1").mock(
        return_value=httpx.Response(200, json={"url": "https://lookaside.test/x", "id": "MEDIA1"})
    )
    manifest = _whatsapp()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("get_media"), {"media_id": "MEDIA1"}, CONN
    )
    assert result.success is True
    assert result.data["url"] == "https://lookaside.test/x"


@respx.mock
async def test_expired_token_maps_to_credential_invalid():
    from astromesh.integrations import errors

    respx.post("https://graph.facebook.com/v21.0/PHONE1/messages").mock(
        return_value=httpx.Response(401, json={"error": {"message": "expired"}})
    )
    manifest = _whatsapp()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("send_text"),
        {"phone_number_id": "PHONE1", "to": "549110", "text": "x"},
        CONN,
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_integration_catalog_http.py tests/test_integration_catalog_whatsapp.py -v`
Expected: FAIL con `AttributeError: 'NoneType' object has no attribute ...` (el catálogo no las tiene)

- [ ] **Step 3: Crear el manifest `http`**

Crear `astromesh/integrations/catalog/http/integration.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: http
  version: 0.1.0
  description: >
    Integración HTTP genérica para APIs internas y sistemas legacy. El
    base_url y el material de auth vienen de la conexión, no del manifest:
    una sola integración sirve a cualquier cantidad de servicios propios.
spec:
  # Sin base_url a propósito. La conexión lo aporta.
  auth:
    scheme: header
    credential: api_key
    header_name: X-Api-Key
  defaults:
    timeout_seconds: 30
  actions:
    - name: get
      description: "Hace un GET a un path de la API configurada en la conexión"
      parameters:
        path:
          type: string
          description: "Path relativo al base_url, empezando con /"
          required: true
      request:
        method: GET
        path: "{path}"
      allow_slash: [path]

    - name: post
      description: "Hace un POST con cuerpo JSON a un path de la API configurada"
      writes: true
      parameters:
        path:
          type: string
          description: "Path relativo al base_url, empezando con /"
          required: true
        body:
          type: object
          description: "Cuerpo JSON a enviar"
      request:
        method: POST
        path: "{path}"
        body: "{body}"
      allow_slash: [path]

    - name: put
      description: "Hace un PUT con cuerpo JSON a un path de la API configurada"
      writes: true
      parameters:
        path:
          type: string
          description: "Path relativo al base_url, empezando con /"
          required: true
        body:
          type: object
          description: "Cuerpo JSON a enviar"
      request:
        method: PUT
        path: "{path}"
        body: "{body}"
      allow_slash: [path]

    - name: delete
      description: "Hace un DELETE a un path de la API configurada"
      writes: true
      parameters:
        path:
          type: string
          description: "Path relativo al base_url, empezando con /"
          required: true
      request:
        method: DELETE
        path: "{path}"
      allow_slash: [path]
```

Nota: `body: "{body}"` funciona por `interpolate_structure`, que conserva el tipo del argumento cuando el string es exactamente un placeholder (Task 3). `allow_slash: [path]` es imprescindible acá — un path de API tiene barras — y la guardia de `..` sigue activa igual.

- [ ] **Step 4: Crear el manifest `whatsapp`**

Crear `astromesh/integrations/catalog/whatsapp/integration.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: whatsapp
  version: 0.1.0
  description: >
    WhatsApp Business Cloud API (Meta Graph) — lado saliente. El webhook
    entrante y la verificación de firma siguen siendo del canal
    astromesh/channels/whatsapp.py; esta integración no lo reemplaza.
    Es también la plantilla de instagram y facebook: misma base_url y
    mismo esquema de auth.
spec:
  base_url: "https://graph.facebook.com/v21.0"
  auth:
    scheme: bearer
    credential: access_token
  defaults:
    timeout_seconds: 30
    rate_limit:
      window_seconds: 60
      max_calls: 30
  actions:
    - name: send_text
      description: "Envía un mensaje de texto de WhatsApp a un número"
      writes: true
      parameters:
        phone_number_id:
          type: string
          description: "ID del número emisor registrado en Meta"
          required: true
        to:
          type: string
          description: "Número destino en formato internacional, sin + ni espacios"
          required: true
        text:
          type: string
          description: "Texto del mensaje"
          required: true
      request:
        method: POST
        path: "/{phone_number_id}/messages"
        body:
          messaging_product: "whatsapp"
          to: "{to}"
          type: "text"
          text:
            body: "{text}"

    - name: send_template
      description: "Envía una plantilla aprobada de WhatsApp a un número"
      writes: true
      parameters:
        phone_number_id:
          type: string
          description: "ID del número emisor registrado en Meta"
          required: true
        to:
          type: string
          description: "Número destino en formato internacional, sin + ni espacios"
          required: true
        template_name:
          type: string
          description: "Nombre de la plantilla aprobada"
          required: true
        language_code:
          type: string
          description: "Código de idioma de la plantilla, por ejemplo es_AR"
          default: "es"
      request:
        method: POST
        path: "/{phone_number_id}/messages"
        body:
          messaging_product: "whatsapp"
          to: "{to}"
          type: "template"
          template:
            name: "{template_name}"
            language:
              code: "{language_code}"

    - name: get_media
      description: "Resuelve la URL de descarga y los metadatos de un media recibido"
      parameters:
        media_id:
          type: string
          description: "ID del media que llegó en el webhook"
          required: true
      request:
        method: GET
        path: "/{media_id}"
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_integration_catalog_http.py tests/test_integration_catalog_whatsapp.py -v`
Expected: PASS, 7 + 6 tests

- [ ] **Step 6: El test del catálogo real ya puede pasar**

Run: `uv run pytest tests/test_integration_catalog.py -v`
Expected: PASS, 8 tests (ahora incluido `test_shipped_catalog_loads`)

- [ ] **Step 7: Verificar que los manifests entran en el paquete distribuido**

Los `.yaml` no son `.py`: hatchling tiene que incluirlos o el wheel sale sin catálogo y `astromesh-os` arranca sin integraciones.

Run: `uv build --wheel --out-dir /tmp/am-wheel && unzip -l /tmp/am-wheel/*.whl | grep integration.yaml`
Expected: aparecen `astromesh/integrations/catalog/http/integration.yaml` y el de `whatsapp`.

Si **no** aparecen, agregar a `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["astromesh"]
artifacts = ["astromesh/integrations/catalog/**/*.yaml"]
```

y repetir el comando hasta que aparezcan.

- [ ] **Step 8: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Integración \`http\`: cliente genérico para APIs internas, con base_url y auth por conexión.`
`- Integración \`whatsapp\`: envío de texto y plantillas, y resolución de media, sobre Meta Graph API.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/catalog/ tests/test_integration_catalog_http.py \
        tests/test_integration_catalog_whatsapp.py pyproject.toml CHANGELOG.md
git commit -m "feat(integrations): manifests http y whatsapp"
```

---

### Task 14: Manifest `google_drive` con handler resumable

Es la única integración con escape a Python, y la plantilla de gmail y sheets.

**Files:**
- Create: `astromesh/integrations/catalog/google_drive/integration.yaml`, `astromesh/integrations/catalog/google_drive/__init__.py`, `astromesh/integrations/catalog/google_drive/handlers.py`
- Test: `tests/test_integration_catalog_drive.py`

**Interfaces:**
- Consumes: `IntegrationContext` (Task 9), `ToolResult`.
- Produces: integración `google_drive` con `list_files`, `get_file`, `search` (declarativas) y `upload_file` (handler).

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_integration_catalog_drive.py`:

```python
import httpx
import respx

from astromesh.integrations import IntegrationCatalog, errors
from astromesh.integrations.credentials import ResolvedConnection
from astromesh.integrations.executor import HttpActionExecutor

CONN = ResolvedConnection(name="drive", material={"access_token": "T0K3N"})


def _drive():
    catalog = IntegrationCatalog()
    catalog.discover()
    return catalog.get("google_drive")


def test_actions_and_modes():
    manifest = _drive()
    actions = {a.name: a for a in manifest.actions}
    assert set(actions) == {"list_files", "get_file", "search", "upload_file"}
    assert actions["list_files"].handler is None
    assert actions["upload_file"].handler is not None
    assert actions["upload_file"].writes is True


@respx.mock
async def test_list_files_paginates_by_token():
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200, json={"files": [{"id": "1"}], "nextPageToken": "TOK2"}
        )
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("list_files"), {"page_size": 10}, CONN
    )
    assert result.success is True
    assert result.data == [{"id": "1"}]
    assert result.metadata["next_cursor"] == "TOK2"
    assert route.calls[0].request.url.params["pageSize"] == "10"


@respx.mock
async def test_list_files_sends_cursor_as_page_token():
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    manifest = _drive()
    await HttpActionExecutor().execute(
        manifest, manifest.action("list_files"), {"cursor": "TOK2"}, CONN
    )
    assert route.calls[0].request.url.params["pageToken"] == "TOK2"


@respx.mock
async def test_search_passes_the_query():
    route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    manifest = _drive()
    await HttpActionExecutor().execute(
        manifest, manifest.action("search"), {"query": "name contains 'informe'"}, CONN
    )
    assert route.calls[0].request.url.params["q"] == "name contains 'informe'"


@respx.mock
async def test_upload_file_runs_the_resumable_session():
    init = respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(
            200, headers={"Location": "https://upload.googleapis.com/session/ABC"}
        )
    )
    put = respx.put("https://upload.googleapis.com/session/ABC").mock(
        return_value=httpx.Response(200, json={"id": "FILE1", "name": "notas.txt"})
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest,
        manifest.action("upload_file"),
        {"name": "notas.txt", "content": "hola mundo", "mime_type": "text/plain"},
        CONN,
    )
    assert result.success is True
    assert result.data["id"] == "FILE1"
    assert init.called and put.called
    assert init.calls[0].request.headers["Authorization"] == "Bearer T0K3N"
    assert put.calls[0].request.content == b"hola mundo"


@respx.mock
async def test_upload_without_session_url_fails_cleanly():
    respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(200)  # sin Location
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("upload_file"), {"name": "x", "content": "y"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.UPSTREAM_ERROR


@respx.mock
async def test_upload_init_error_is_classified():
    respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(401, json={"error": "expired"})
    )
    manifest = _drive()
    result = await HttpActionExecutor().execute(
        manifest, manifest.action("upload_file"), {"name": "x", "content": "y"}, CONN
    )
    assert result.success is False
    assert result.metadata["error_kind"] == errors.CREDENTIAL_INVALID
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_integration_catalog_drive.py -v`
Expected: FAIL con `AttributeError: 'NoneType' object has no attribute 'actions'`

- [ ] **Step 3: Crear el manifest**

Crear `astromesh/integrations/catalog/google_drive/integration.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: google_drive
  version: 0.1.0
  description: >
    Google Drive API v3. El access token lo entrega la conexión ya
    resuelto: el core no hace el flujo OAuth ni refresca. Es la plantilla
    de gmail y sheets — mismo esquema de auth, distinta base_url.
spec:
  base_url: "https://www.googleapis.com/drive/v3"
  auth:
    scheme: bearer
    credential: access_token
  defaults:
    timeout_seconds: 60
  actions:
    - name: list_files
      description: "Lista archivos del Drive del usuario, más recientes primero"
      parameters:
        page_size:
          type: integer
          description: "Cantidad de archivos por página, máximo 1000"
          default: 25
      request:
        method: GET
        path: "/files"
        query:
          pageSize: "{page_size}"
          fields: "files(id,name,mimeType,modifiedTime,size),nextPageToken"
          orderBy: "modifiedTime desc"
      response:
        select: "files"
      pagination:
        style: cursor
        cursor_param: pageToken
        cursor_path: "nextPageToken"

    - name: get_file
      description: "Devuelve los metadatos de un archivo por su ID"
      parameters:
        file_id:
          type: string
          description: "ID del archivo en Drive"
          required: true
      request:
        method: GET
        path: "/files/{file_id}"
        query:
          fields: "id,name,mimeType,modifiedTime,size,webViewLink"

    - name: search
      description: "Busca archivos con la sintaxis de consulta de Drive"
      parameters:
        query:
          type: string
          description: "Consulta Drive, por ejemplo: name contains 'informe'"
          required: true
        page_size:
          type: integer
          description: "Cantidad de resultados por página"
          default: 25
      request:
        method: GET
        path: "/files"
        query:
          q: "{query}"
          pageSize: "{page_size}"
          fields: "files(id,name,mimeType,modifiedTime),nextPageToken"
      response:
        select: "files"
      pagination:
        style: cursor
        cursor_param: pageToken
        cursor_path: "nextPageToken"

    - name: upload_file
      description: "Sube un archivo de texto a Drive y devuelve sus metadatos"
      writes: true
      handler: "python:astromesh.integrations.catalog.google_drive.handlers:upload_file"
      parameters:
        name:
          type: string
          description: "Nombre del archivo en Drive"
          required: true
        content:
          type: string
          description: "Contenido del archivo"
          required: true
        mime_type:
          type: string
          description: "Tipo MIME del contenido"
          default: "text/plain"
        parent_folder_id:
          type: string
          description: "ID de la carpeta destino; si se omite, va a la raíz"
```

- [ ] **Step 4: Crear el handler**

Crear `astromesh/integrations/catalog/google_drive/__init__.py` vacío, y `handlers.py`:

```python
"""Acciones de Google Drive que no caben en un solo request.

`upload_file` necesita una sesión resumable: primero un POST que devuelve
una URL de sesión en el header Location, después un PUT del contenido a esa
URL. Dos llamadas encadenadas, con el resultado de la primera alimentando a
la segunda — exactamente lo que el manifest declarativo no puede expresar.
"""

from __future__ import annotations

from astromesh.integrations import errors
from astromesh.integrations.executor import IntegrationContext
from astromesh.tools.base import ToolResult

_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"


async def upload_file(arguments: dict, ctx: IntegrationContext) -> ToolResult:
    metadata: dict = {"name": arguments["name"]}
    if arguments.get("parent_folder_id"):
        metadata["parents"] = [arguments["parent_folder_id"]]

    content = arguments["content"]
    payload = content.encode() if isinstance(content, str) else content
    mime_type = arguments.get("mime_type") or "text/plain"

    init = await ctx.client.post(
        _UPLOAD_ENDPOINT,
        params={"uploadType": "resumable"},
        json=metadata,
        headers={
            "X-Upload-Content-Type": mime_type,
            "X-Upload-Content-Length": str(len(payload)),
        },
    )
    if init.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"iniciar la subida falló: HTTP {init.status_code}: {init.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(init.status_code),
                "status_code": init.status_code,
            },
        )

    session_url = init.headers.get("Location")
    if not session_url:
        return ToolResult(
            success=False,
            data=None,
            error="Drive no devolvió una URL de sesión (header Location ausente)",
            metadata={"error_kind": errors.UPSTREAM_ERROR},
        )

    upload = await ctx.client.put(
        session_url, content=payload, headers={"Content-Type": mime_type}
    )
    if upload.status_code >= 400:
        return ToolResult(
            success=False,
            data=None,
            error=f"subir el contenido falló: HTTP {upload.status_code}: {upload.text[:300]}",
            metadata={
                "error_kind": errors.classify_status(upload.status_code),
                "status_code": upload.status_code,
            },
        )

    try:
        data = upload.json()
    except ValueError:
        data = {"raw": upload.text}
    return ToolResult(success=True, data=data, metadata={"status_code": upload.status_code})
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_integration_catalog_drive.py -v`
Expected: PASS, 7 tests

- [ ] **Step 6: Ahora la API tiene las tres — correr sus tests**

Run: `uv run pytest tests/test_integration_api.py -v`
Expected: PASS, 6 tests

- [ ] **Step 7: Lint y commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Integración \`google_drive\`: listar, buscar y leer metadatos de archivos, y subida por sesión resumable.`

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add astromesh/integrations/catalog/google_drive/ tests/test_integration_catalog_drive.py CHANGELOG.md
git commit -m "feat(integrations): manifest google_drive con subida resumable"
```

---

### Task 15: Test de conformidad del catálogo

El entregable central: lo que hace que el manifest número nueve venga con tests puestos.

**Files:**
- Create: `tests/test_integration_conformance.py`

**Interfaces:**
- Consumes: `IntegrationCatalog` (Task 7), `load_manifest`/`ManifestError` (Task 2), `load_handler` (Task 6).
- Produces: nada que consuma otra tarea.

- [ ] **Step 1: Escribir el test de conformidad**

Crear `tests/test_integration_conformance.py`:

```python
"""Conformidad del catálogo de integraciones.

Parametrizado sobre `astromesh/integrations/catalog/*/integration.yaml`: todo
manifest que se agregue en el futuro hereda estas verificaciones sin que su
autor tenga que escribir un solo test.
"""

import re
from pathlib import Path

import pytest

from astromesh.integrations import IntegrationCatalog
from astromesh.integrations.handlers import load_handler
from astromesh.integrations.manifest import load_manifest

CATALOG_ROOT = Path("astromesh/integrations/catalog")
TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

MANIFEST_PATHS = sorted(CATALOG_ROOT.glob("*/integration.yaml"))


def _ids(paths):
    return [p.parent.name for p in paths]


def test_the_catalog_is_not_empty():
    assert MANIFEST_PATHS, f"no se encontró ningún manifest bajo {CATALOG_ROOT}"


def test_every_shipped_manifest_is_discovered():
    """Descubrir tiene que cargar todas: si alguna se saltea, algo está roto."""
    catalog = IntegrationCatalog()
    assert catalog.discover() == len(MANIFEST_PATHS)


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_manifest_is_valid(path):
    load_manifest(path)


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_slug_matches_directory_and_is_a_valid_prefix(path):
    manifest = load_manifest(path)
    assert manifest.slug == path.parent.name
    assert TOOL_NAME_RE.match(manifest.slug)


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_tool_names_are_accepted_by_model_providers(path):
    """`<slug>_<accion>` contra el regex de OpenAI y Anthropic.

    Un nombre inválido no rompe sólo esa tool: hace 400 la request entera
    al proveedor, dejando al agente sin ninguna.
    """
    manifest = load_manifest(path)
    for action in manifest.actions:
        name = f"{manifest.slug}_{action.name}"
        assert TOOL_NAME_RE.match(name), f"nombre de tool inválido: {name}"
        assert len(name) <= 64, f"nombre de tool de {len(name)} caracteres: {name}"


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_parameters_normalize_to_valid_json_schema(path):
    manifest = load_manifest(path)
    for action in manifest.actions:
        schema = action.tool_parameters()
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        for prop_name, prop in schema["properties"].items():
            assert isinstance(prop, dict), f"{action.name}.{prop_name} no es un objeto"
            assert "type" in prop, f"{action.name}.{prop_name} no declara 'type'"
        for required in schema.get("required", []):
            assert required in schema["properties"], (
                f"{action.name}: '{required}' es required pero no está en properties"
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_every_action_has_exactly_one_mode(path):
    manifest = load_manifest(path)
    for action in manifest.actions:
        assert (action.request is None) != (action.handler is None), (
            f"{manifest.slug}.{action.name}: debe declarar 'request' o 'handler', no ambos"
        )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_every_handler_resolves(path):
    manifest = load_manifest(path)
    for action in manifest.actions:
        if action.handler:
            load_handler(action.handler)


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_every_placeholder_is_a_declared_parameter(path):
    """Un `{param}` sin declarar es un 'falta el argumento' en producción."""
    manifest = load_manifest(path)
    for action in manifest.actions:
        if action.request is None:
            continue
        declared = set(action.parameters or {})
        if action.pagination is not None:
            declared.add("cursor")
        blob = " ".join(
            [
                action.request.path,
                str(action.request.query or {}),
                str(action.request.headers or {}),
                str(action.request.body or {}),
            ]
        )
        for param in PLACEHOLDER_RE.findall(blob):
            assert param in declared, (
                f"{manifest.slug}.{action.name} usa '{{{param}}}' pero no lo declara "
                f"en parameters"
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_allow_slash_only_names_declared_parameters(path):
    manifest = load_manifest(path)
    for action in manifest.actions:
        for param in action.allow_slash or []:
            assert param in (action.parameters or {}), (
                f"{manifest.slug}.{action.name}: allow_slash nombra '{param}', no declarado"
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_descriptions_are_useful(path):
    """La descripción es lo único que el modelo lee para decidir si llamar."""
    manifest = load_manifest(path)
    assert manifest.description.strip(), f"{manifest.slug}: falta description"
    for action in manifest.actions:
        assert len(action.description.strip()) >= 15, (
            f"{manifest.slug}.{action.name}: descripción demasiado corta para que el "
            f"modelo elija bien"
        )
        for param_name, spec in (action.parameters or {}).items():
            assert isinstance(spec, dict) and spec.get("description", "").strip(), (
                f"{manifest.slug}.{action.name}.{param_name}: falta description"
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_write_actions_are_declared_as_such(path):
    """Un método mutante sin `writes: true` deja al cliente sin la señal."""
    manifest = load_manifest(path)
    for action in manifest.actions:
        if action.request and action.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            assert action.writes, (
                f"{manifest.slug}.{action.name} usa {action.request.method} pero no "
                f"declara 'writes: true'"
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_no_credentials_are_hardcoded(path):
    """Un manifest es código versionado: no puede traer material de auth."""
    text = path.read_text().lower()
    for needle in ("bearer ", "api_key:", "password:", "client_secret", "sk-", "eaag"):
        assert needle not in text, f"{path} parece traer una credencial escrita: {needle!r}"
```

- [ ] **Step 2: Correr el test contra el catálogo real**

Run: `uv run pytest tests/test_integration_conformance.py -v`
Expected: PASS. Son ~13 tests × 3 manifests.

Si `test_no_credentials_are_hardcoded` falla en `http` por la cadena `api_key:` del bloque `auth`, ajustar la aserción para que ignore la línea `credential: api_key` — es un *nombre de clave*, no un valor. Corregir el needle a `"api_key: \""` (con comillas, que es como se vería un valor literal) y volver a correr.

- [ ] **Step 3: Verificar que el test agarra un manifest malo**

Crear temporalmente `astromesh/integrations/catalog/_malo/integration.yaml` con una acción que use `{no_declarado}` en el path sin declararlo:

```yaml
apiVersion: astromesh/v1
kind: Integration
metadata: {name: _malo, version: 0.1.0, description: "prueba de la red"}
spec:
  base_url: "https://x.test"
  auth: {scheme: none}
  actions:
    - name: roto
      description: "Acción con un placeholder no declarado"
      request: {method: GET, path: "/{no_declarado}"}
```

Run: `uv run pytest tests/test_integration_conformance.py -v -k "placeholder"`
Expected: FAIL nombrando `_malo.roto` y `no_declarado`.

Después borrar el directorio:

```bash
rm -rf astromesh/integrations/catalog/_malo
```

Run: `uv run pytest tests/test_integration_conformance.py -q`
Expected: PASS

- [ ] **Step 4: Lint y commit**

Este commit es `test:`, no requiere entrada de changelog.

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format astromesh/ tests/
git add tests/test_integration_conformance.py
git commit -m "test(integrations): conformidad parametrizada del catálogo"
```

---

### Task 16: Seguridad extremo a extremo, observabilidad y documentación

**Files:**
- Create: `tests/test_integration_security.py`
- Modify: `astromesh/integrations/executor.py` (span), `docs/CONFIGURATION_GUIDE.md`
- Test: `tests/test_integration_security.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: nada que consuma otra tarea.

- [ ] **Step 1: Escribir los tests de seguridad**

Crear `tests/test_integration_security.py`:

```python
"""Contención de credenciales, extremo a extremo.

Lo que se verifica acá no es una convención sino el contrato de §5.4 del
spec: el material de credencial entra por `connections`, firma un request y
muere ahí.
"""

import httpx
import respx
import yaml

from astromesh.runtime.engine import AgentRuntime

SECRET = "SUPER-SECRETO-9Z"

MANIFEST = """
apiVersion: astromesh/v1
kind: Integration
metadata: {name: demo, version: 0.1.0, description: "demo de seguridad"}
spec:
  base_url: "https://api.demo.test"
  auth: {scheme: bearer, credential: access_token}
  actions:
    - name: ping
      description: "Hace ping al servicio de demostración"
      request: {method: GET, path: "/ping"}
    - name: fetch
      description: "Trae un recurso por su identificador de path"
      parameters:
        resource: {type: string, description: "Identificador del recurso", required: true}
      request: {method: GET, path: "/r/{resource}"}
"""

AGENT = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "sec-agent", "version": "0.1.0"},
    "spec": {
        "identity": {"description": "demo"},
        "model": {"primary": {"source": "ollama", "model": "llama3"}},
        "prompts": {"system": "sos un agente"},
        "tools": [
            {
                "type": "integration",
                "name": "demo",
                "connection": "conn_a",
                "actions": ["ping", "fetch"],
            }
        ],
    },
}


def _runtime(tmp_path, monkeypatch, agent_config=AGENT):
    import astromesh.runtime.engine as engine_module
    from astromesh.integrations import IntegrationCatalog

    root = tmp_path / "catalog"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "integration.yaml").write_text(MANIFEST)
    catalog = IntegrationCatalog()
    catalog.discover(root)
    monkeypatch.setattr(engine_module, "default_catalog", lambda: catalog)

    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "sec-agent.agent.yaml").write_text(yaml.safe_dump(agent_config))
    runtime = AgentRuntime(config_dir=config_dir)
    runtime.load_agents()
    return runtime


@respx.mock
async def test_credential_reaches_the_wire_but_not_the_result(tmp_path, monkeypatch):
    route = respx.get("https://api.demo.test/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"conn_a": {"access_token": SECRET}}}
    )
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in str(result)


@respx.mock
async def test_credential_never_appears_in_the_trace(tmp_path, monkeypatch):
    from astromesh.observability.tracing import TracingContext

    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    tracing = TracingContext(agent_name="sec-agent", session_id="s1")
    span = tracing.start_span("tool.call", {"tool": "demo_ping"})
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"conn_a": {"access_token": SECRET}}}
    )
    span.set_attribute("tool_args", {})
    span.set_attribute("tool_result", str(result))
    tracing.finish_span(span)
    assert SECRET not in str(getattr(span, "attributes", {}))


@respx.mock
async def test_credential_is_not_in_debug_logs(tmp_path, monkeypatch, caplog):
    import logging

    respx.get("https://api.demo.test/ping").mock(return_value=httpx.Response(200, json={}))
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    with caplog.at_level(logging.DEBUG):
        await tools.execute("demo_ping", {}, {"connections": {"conn_a": {"access_token": SECRET}}})
    assert SECRET not in caplog.text


async def test_agent_cannot_reach_a_connection_it_did_not_declare(tmp_path, monkeypatch):
    """El bundle puede traer varias conexiones; el agente sólo usa la suya."""
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_ping", {}, {"connections": {"conn_b": {"access_token": SECRET}}}
    )
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == "credential_missing"


@respx.mock
async def test_traversal_argument_cannot_escape_the_base_path(tmp_path, monkeypatch):
    route = respx.get(url__startswith="https://api.demo.test/").mock(
        return_value=httpx.Response(200, json={})
    )
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_fetch",
        {"resource": "../../admin/keys"},
        {"connections": {"conn_a": {"access_token": SECRET}}},
    )
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == "bad_request"
    assert not route.called


@respx.mock
async def test_slash_in_path_argument_is_rejected_by_default(tmp_path, monkeypatch):
    route = respx.get(url__startswith="https://api.demo.test/").mock(
        return_value=httpx.Response(200, json={})
    )
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute(
        "demo_fetch",
        {"resource": "a/b"},
        {"connections": {"conn_a": {"access_token": SECRET}}},
    )
    assert result["success"] is False
    assert not route.called


async def test_run_without_connections_does_not_crash(tmp_path, monkeypatch):
    """Retrocompatibilidad: `connections` ausente es `{}`, no un error."""
    runtime = _runtime(tmp_path, monkeypatch)
    tools = runtime._agents["sec-agent"]._tools
    result = await tools.execute("demo_ping", {}, {"agent": "sec-agent", "session": "s"})
    assert result["success"] is False
    assert result["metadata"]["error_kind"] == "credential_missing"
```

- [ ] **Step 2: Correr los tests**

Run: `uv run pytest tests/test_integration_security.py -v`
Expected: PASS, 7 tests. Si alguno falla, es un defecto real de contención — arreglar el código, no el test.

- [ ] **Step 3: Agregar el span de integración**

En `astromesh/integrations/executor.py`, dentro de `_run_request`, envolver la llamada HTTP con el span. Importar arriba:

```python
from astromesh.observability.tracing import SpanStatus, TracingContext
```

Y alrededor del `async with httpx.AsyncClient(...)` de `_run_request`, tomando `manifest` y `action` que ya están en el alcance:

```python
        tracing = TracingContext(agent_name="", session_id="")
        span = tracing.start_span(
            "integration.call",
            {"integration.slug": manifest.slug, "integration.action": action.name},
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    action.request.method,
                    f"{base_url}{path}",
                    params=params,
                    headers=request_headers,
                    json=body,
                )
        except Exception as exc:
            span.set_attribute("error_kind", errors.classify_exception(exc))
            tracing.finish_span(span, status=SpanStatus.ERROR)
            logger.warning("%s.%s falló: %s", manifest.slug, action.name, exc)
            return _fail(errors.classify_exception(exc), f"{type(exc).__name__}: {exc}")

        span.set_attribute("http.status_code", response.status_code)
        if response.status_code >= 400:
            span.set_attribute("error_kind", errors.classify_status(response.status_code))
            tracing.finish_span(span, status=SpanStatus.ERROR)
        else:
            tracing.finish_span(span)
        return self._to_result(action, response)
```

El span lleva slug, acción y status. **No** lleva headers, body ni credencial — por eso el test de traza del Step 2 sigue pasando.

- [ ] **Step 4: Verificar que la contención sobrevive al span**

Run: `uv run pytest tests/test_integration_security.py tests/test_integration_executor.py -v`
Expected: PASS

- [ ] **Step 5: Documentar en la guía de configuración**

En `docs/CONFIGURATION_GUIDE.md`, junto a la documentación de tools, agregar una sección. **Además, corregir la línea 123**, que hoy promete `type: internal # internal | mcp | webhook | rag` — los cuatro son falsos, ninguno se carga desde YAML. La lista real es `builtin | agent | client | integration`.

```markdown
## Integraciones

Una integración es un servicio externo descrito por un manifest en
`astromesh/integrations/catalog/<slug>/integration.yaml`. Un agente habilita
las acciones que necesita:

```yaml
tools:
  - type: integration
    name: whatsapp          # slug del catálogo
    connection: wa_main     # nombre de conexión
    actions:                # allowlist obligatoria
      - send_text
      - get_media
```

La tool que ve el modelo se llama `<slug>_<accion>` — `whatsapp_send_text`.
Una acción fuera de `actions` no existe para ese agente: la allowlist controla
el gasto de contexto y es la superficie de permisos.

### Conexiones

Las credenciales no viven en el YAML del agente. Se resuelven en este orden:

1. El bundle `connections` del request de corrida, que inyecta el plano de
   control (Nexus):

   ```json
   {"query": "...", "connections": {"wa_main": {"access_token": "..."}}}
   ```

2. `config/connections.yaml` para self-hosted, con `${VAR}` como en
   `channels.yaml`. Ver `config/connections.yaml.example`.

Si no hay ninguna, la acción devuelve `credential_missing` y el agente sigue
corriendo.

### Ver qué hay disponible

- `GET /v1/integrations` — catálogo
- `GET /v1/integrations/{slug}` — acciones y qué credenciales pide

### Agregar una integración

Una carpeta con un `integration.yaml`. El test de conformidad
(`tests/test_integration_conformance.py`) la valida sola: esquema, nombres
aceptados por los proveedores, placeholders declarados y descripciones útiles.
Si una acción necesita más de un request, se declara
`handler: python:modulo:funcion` en vez de `request:`.
```

- [ ] **Step 6: Suite completa y lint**

Run: `uv run pytest -q`
Expected: PASS, todo verde

Run: `uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/`
Expected: sin errores

- [ ] **Step 7: Verificar la compuerta de astromesh-os**

Run: `uv run python -c "import astromesh.api.main; from astromesh.integrations import default_catalog; print(len(default_catalog().all()), 'integraciones')"`
Expected: `3 integraciones`, sin ImportError. Esta es la condición que decide si la imagen del OS arranca.

- [ ] **Step 8: Commit**

Bajo `## [Unreleased]` → `### Added (Backend)`:
`- Span \`integration.call\` con slug, acción, status y error_kind.`
Bajo `### Fixed`:
`- \`docs/CONFIGURATION_GUIDE.md\` documentaba tipos de tool inexistentes (\`internal\`, \`mcp\`, \`webhook\`, \`rag\`); ahora lista los reales.`

```bash
git add tests/test_integration_security.py astromesh/integrations/executor.py \
        docs/CONFIGURATION_GUIDE.md CHANGELOG.md
git commit -m "feat(integrations): observabilidad y contención de credenciales verificada"
```

---

## Verificación final

Después de la Task 16, antes de dar por terminado:

- [ ] `uv run pytest -q` — toda la suite en verde
- [ ] `uv run ruff check astromesh/ tests/` — sin errores
- [ ] `uv run python -c "import astromesh.api.main"` — importa sin extras (compuerta de `astromesh-os`)
- [ ] `uv build --wheel --out-dir /tmp/am-check && unzip -l /tmp/am-check/*.whl | grep -c integration.yaml` — devuelve `3`
- [ ] `curl -s localhost:8000/v1/integrations | jq '.count'` con el servidor levantado — devuelve `3`
- [ ] `CHANGELOG.md` tiene la sección `[Unreleased]` con todas las entradas

**La prueba real del entregable:** agregar un manifest `instagram` copiando `whatsapp`, cambiando el slug y las acciones. Debe descubrirse, aparecer en `/v1/integrations` y pasar el test de conformidad **sin escribir un solo test ni tocar un archivo compartido**. Si eso no ocurre, el marco no cumplió su objetivo.
