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

CATALOG_ROOT = Path(__file__).resolve().parents[1] / "astromesh" / "integrations" / "catalog"
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
                f"{manifest.slug}.{action.name} usa '{{{param}}}' pero no lo declara en parameters"
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
def test_mutating_methods_declare_writes_explicitly(path):
    """Un método mutante tiene que decir si muta — sí o no, pero dicho.

    No se exige `writes: true` a rajatabla: leer por POST es común y legítimo
    (búsquedas con cuerpo, GraphQL, la Display API de TikTok). Lo que no se
    permite es el silencio, que deja al cliente sin señal y se parece
    demasiado a un olvido.
    """
    manifest = load_manifest(path)
    for action in manifest.actions:
        if action.request and action.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            assert action.writes is not None, (
                f"{manifest.slug}.{action.name} usa {action.request.method} y no declara "
                f"'writes'. Poné 'writes: true' si muta, o 'writes: false' si sólo lee."
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_handler_actions_declare_writes_explicitly(path):
    """Un handler es opaco al validador: sólo su autor sabe si muta."""
    manifest = load_manifest(path)
    for action in manifest.actions:
        if action.handler:
            assert action.writes is not None, (
                f"{manifest.slug}.{action.name} es un handler y no declara 'writes'."
            )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=_ids(MANIFEST_PATHS))
def test_no_credentials_are_hardcoded(path):
    """Un manifest es código versionado: no puede traer material de auth.

    Se buscan formas de *valor*, no de clave: `credential: api_key` nombra qué
    hace falta y es legítimo; `api_key: "abc123"` sería la filtración.
    """
    text = path.read_text().lower()
    for needle in ("bearer ", 'api_key: "', 'password: "', "client_secret", "sk-", "eaag"):
        assert needle not in text, f"{path} parece traer una credencial escrita: {needle!r}"
