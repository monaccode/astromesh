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
