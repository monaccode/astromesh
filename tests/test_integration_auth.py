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
