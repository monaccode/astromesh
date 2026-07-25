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
    assert action.mutates is False


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
    with pytest.raises(ManifestError, match=r"request.*handler|handler.*request"):
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
