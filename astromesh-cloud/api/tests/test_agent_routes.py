"""Tests for agent CRUD and lifecycle routes."""
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/api/v1/auth/dev/login", params={"email": "dev@test.com", "name": "Dev"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def org_slug(client, auth_headers):
    resp = await client.get("/api/v1/orgs/me", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()["slug"]


@pytest.fixture
def agent_payload():
    return {
        "config": {
            "name": "test-agent",
            "display_name": "Test Agent",
            "system_prompt": "You are a helpful assistant.",
            "tone": "professional",
            "model": "gpt-4o-mini",
            "routing_strategy": "cost_optimized",
            "tools": [],
            "tool_configs": {},
            "memory_enabled": False,
            "pii_filter": False,
            "content_filter": False,
            "orchestration": "react",
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_create_agent(client, auth_headers, org_slug, agent_payload):
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-agent"
    assert data["display_name"] == "Test Agent"
    assert data["status"] == "draft"
    assert data["runtime_name"] == f"{org_slug}--test-agent"
    assert "id" in data
    assert "created_at" in data


async def test_list_agents(client, auth_headers, org_slug, agent_payload):
    # Create one agent first
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )

    resp = await client.get(f"/api/v1/orgs/{org_slug}/agents", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    names = [a["name"] for a in data]
    assert "test-agent" in names


async def test_get_agent_detail(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/orgs/{org_slug}/agents/test-agent",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test-agent"
    assert data["status"] == "draft"
    assert "config" in data
    assert data["config"]["model"] == "gpt-4o-mini"


async def test_get_agent_not_found(client, auth_headers, org_slug):
    resp = await client.get(
        f"/api/v1/orgs/{org_slug}/agents/nonexistent",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_create_agent_duplicate_name(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 409


async def test_update_agent(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )

    updated_payload = dict(agent_payload)
    updated_payload["config"] = dict(agent_payload["config"])
    updated_payload["config"]["display_name"] = "Updated Display Name"

    resp = await client.put(
        f"/api/v1/orgs/{org_slug}/agents/test-agent",
        json=updated_payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Updated Display Name"
    assert data["status"] == "draft"


async def test_delete_agent(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )

    resp = await client.delete(
        f"/api/v1/orgs/{org_slug}/agents/test-agent",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # Confirm it's gone
    resp = await client.get(
        f"/api/v1/orgs/{org_slug}/agents/test-agent",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_deploy_agent_no_proxy(client, auth_headers, org_slug, agent_payload):
    """Deploy succeeds in DB (status→deployed) even without a live runtime proxy."""
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/deploy",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deployed"
    assert data["deployed_at"] is not None


async def test_deploy_already_deployed(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/deploy",
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/deploy",
        headers=auth_headers,
    )
    assert resp.status_code == 409


async def test_pause_agent(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/deploy",
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/pause",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paused"


async def test_pause_non_deployed_agent(client, auth_headers, org_slug, agent_payload):
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/pause",
        headers=auth_headers,
    )
    assert resp.status_code == 409


async def test_test_agent_no_proxy(client, auth_headers, org_slug, agent_payload):
    """Test endpoint returns graceful message when proxy is not configured."""
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/test-agent/test",
        json={"query": "Hello, agent!"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["runtime_available"] is False


async def test_unauthenticated_request(client, org_slug):
    resp = await client.get(f"/api/v1/orgs/{org_slug}/agents")
    assert resp.status_code == 403 or resp.status_code == 401


async def test_wrong_org_returns_403(client, org_slug):
    # Login as a different user who belongs to a different org
    resp2 = await client.post(
        "/api/v1/auth/dev/login",
        params={"email": "other@test.com", "name": "Other"},
    )
    other_token = resp2.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Try to access the first user's org slug
    resp = await client.get(f"/api/v1/orgs/{org_slug}/agents", headers=other_headers)
    assert resp.status_code == 403
