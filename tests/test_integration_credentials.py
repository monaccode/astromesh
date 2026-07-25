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
