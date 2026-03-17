"""Tests for API key and provider key management routes."""

import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Module-level setup: provide Fernet key for encryption
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ASTROMESH_CLOUD_FERNET_KEY", key)
    import astromesh_cloud.config as cfg
    monkeypatch.setattr(cfg.settings, "fernet_key", key)
    import astromesh_cloud.services.encryption as enc
    enc._fernet = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client):
    resp = await client.post(
        "/api/v1/auth/dev/login",
        params={"email": "keys_test@test.com", "name": "Keys Test"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def org_slug(client, auth_headers):
    resp = await client.get("/api/v1/orgs/me", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()["slug"]


# ---------------------------------------------------------------------------
# API Key tests
# ---------------------------------------------------------------------------


async def test_list_api_keys_empty(client, auth_headers, org_slug):
    resp = await client.get(f"/api/v1/orgs/{org_slug}/keys", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_api_key_returns_full_key_once(client, auth_headers, org_slug):
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/keys",
        json={"name": "my-key", "scopes": ["agent:run"]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "key" in data
    assert data["key"].startswith("am_")
    assert "id" in data
    assert "prefix" in data
    assert data["name"] == "my-key"
    assert data["scopes"] == ["agent:run"]
    # Full key must not be stored in the prefix field
    assert data["prefix"] != data["key"]


async def test_list_api_keys_hides_full_key(client, auth_headers, org_slug):
    # Create a key
    await client.post(
        f"/api/v1/orgs/{org_slug}/keys",
        json={"name": "hidden-key"},
        headers=auth_headers,
    )
    resp = await client.get(f"/api/v1/orgs/{org_slug}/keys", headers=auth_headers)
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) >= 1
    for k in keys:
        assert "key" not in k  # full key never returned in list


async def test_revoke_api_key(client, auth_headers, org_slug):
    create_resp = await client.post(
        f"/api/v1/orgs/{org_slug}/keys",
        json={"name": "to-revoke"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/orgs/{org_slug}/keys/{key_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    # Key should no longer appear in list
    list_resp = await client.get(f"/api/v1/orgs/{org_slug}/keys", headers=auth_headers)
    ids = [k["id"] for k in list_resp.json()]
    assert key_id not in ids


async def test_revoke_nonexistent_api_key_returns_404(client, auth_headers, org_slug):
    resp = await client.delete(
        f"/api/v1/orgs/{org_slug}/keys/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_api_keys_require_auth(client, org_slug):
    resp = await client.get(f"/api/v1/orgs/{org_slug}/keys")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Provider key tests
# ---------------------------------------------------------------------------


async def test_list_providers_empty(client, auth_headers, org_slug):
    resp = await client.get(f"/api/v1/orgs/{org_slug}/providers", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_upsert_provider_key(client, auth_headers, org_slug):
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/providers",
        json={"provider": "openai", "key": "sk-test-1234"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "openai"
    assert "id" in data
    assert "key" not in data  # encrypted key must not be in response


async def test_upsert_provider_key_replaces_existing(client, auth_headers, org_slug):
    # Insert initial key
    resp1 = await client.post(
        f"/api/v1/orgs/{org_slug}/providers",
        json={"provider": "anthropic", "key": "old-key"},
        headers=auth_headers,
    )
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    # Upsert with new key
    resp2 = await client.post(
        f"/api/v1/orgs/{org_slug}/providers",
        json={"provider": "anthropic", "key": "new-key"},
        headers=auth_headers,
    )
    assert resp2.status_code == 201
    id2 = resp2.json()["id"]

    # Only one anthropic entry should exist
    list_resp = await client.get(
        f"/api/v1/orgs/{org_slug}/providers", headers=auth_headers
    )
    providers = [p for p in list_resp.json() if p["provider"] == "anthropic"]
    assert len(providers) == 1
    assert providers[0]["id"] == id2
    assert providers[0]["id"] != id1


async def test_delete_provider_key(client, auth_headers, org_slug):
    await client.post(
        f"/api/v1/orgs/{org_slug}/providers",
        json={"provider": "cohere", "key": "cohere-key"},
        headers=auth_headers,
    )
    del_resp = await client.delete(
        f"/api/v1/orgs/{org_slug}/providers/cohere", headers=auth_headers
    )
    assert del_resp.status_code == 204

    list_resp = await client.get(
        f"/api/v1/orgs/{org_slug}/providers", headers=auth_headers
    )
    providers = [p for p in list_resp.json() if p["provider"] == "cohere"]
    assert len(providers) == 0


async def test_delete_nonexistent_provider_returns_404(client, auth_headers, org_slug):
    resp = await client.delete(
        f"/api/v1/orgs/{org_slug}/providers/nonexistent-provider",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_provider_keys_require_auth(client, org_slug):
    resp = await client.get(f"/api/v1/orgs/{org_slug}/providers")
    assert resp.status_code in (401, 403)


async def test_wrong_org_slug_returns_403(client):
    # Login and get token
    login = await client.post(
        "/api/v1/auth/dev/login",
        params={"email": "other_user@test.com", "name": "Other User"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Try to access a non-member org
    resp = await client.get("/api/v1/orgs/nonexistent-org/keys", headers=headers)
    assert resp.status_code == 403
