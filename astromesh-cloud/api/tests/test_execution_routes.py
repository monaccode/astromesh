"""Tests for the execution proxy route and usage aggregation route."""
import pytest
from unittest.mock import AsyncMock, patch

from astromesh_cloud.routes import execution as execution_module
from astromesh_cloud.routes import agents as agents_module


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/api/v1/auth/dev/login", params={"email": "exec@test.com", "name": "Exec"})
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
            "name": "exec-agent",
            "display_name": "Exec Agent",
            "system_prompt": "You are a test assistant.",
            "tone": "professional",
            "model": "ollama/llama3",
            "routing_strategy": "cost_optimized",
            "tools": [],
            "tool_configs": {},
            "memory_enabled": False,
            "pii_filter": False,
            "content_filter": False,
            "orchestration": "react",
        }
    }


@pytest.fixture
async def deployed_agent(client, auth_headers, org_slug, agent_payload):
    """Create and deploy an agent, return agent data dict."""
    create_resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    assert create_resp.status_code == 201

    deploy_resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/exec-agent/deploy",
        headers=auth_headers,
    )
    assert deploy_resp.status_code == 200
    return deploy_resp.json()


# ---------------------------------------------------------------------------
# Execution route tests
# ---------------------------------------------------------------------------


async def test_run_agent_no_proxy(client, auth_headers, org_slug, deployed_agent):
    """Returns 503 when proxy is None."""
    original_proxy = execution_module._proxy
    execution_module._proxy = None
    try:
        resp = await client.post(
            f"/api/v1/orgs/{org_slug}/agents/exec-agent/run",
            json={"query": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 503
    finally:
        execution_module._proxy = original_proxy


async def test_run_agent_not_deployed(client, auth_headers, org_slug, agent_payload):
    """Returns 422 when agent is in draft status."""
    # Create but don't deploy
    await client.post(
        f"/api/v1/orgs/{org_slug}/agents",
        json=agent_payload,
        headers=auth_headers,
    )
    mock_proxy = AsyncMock()
    execution_module.set_proxy(mock_proxy)
    try:
        resp = await client.post(
            f"/api/v1/orgs/{org_slug}/agents/exec-agent/run",
            json={"query": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        execution_module.set_proxy(None)


async def test_run_agent_not_found(client, auth_headers, org_slug):
    """Returns 404 for a nonexistent agent."""
    mock_proxy = AsyncMock()
    execution_module.set_proxy(mock_proxy)
    try:
        resp = await client.post(
            f"/api/v1/orgs/{org_slug}/agents/ghost-agent/run",
            json={"query": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        execution_module.set_proxy(None)


async def test_run_agent_success(client, auth_headers, org_slug, deployed_agent):
    """Proxies to runtime and logs usage."""
    runtime_response = {
        "answer": "Hi there!",
        "steps": [{"action": "respond"}],
        "usage": {"tokens_in": 10, "tokens_out": 20, "cost_usd": 0.0001},
    }
    mock_proxy = AsyncMock()
    mock_proxy.run_agent = AsyncMock(return_value=runtime_response)
    execution_module.set_proxy(mock_proxy)
    try:
        resp = await client.post(
            f"/api/v1/orgs/{org_slug}/agents/exec-agent/run",
            json={"query": "Hello", "session_id": "s1"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Hi there!"
        assert data["steps"] == [{"action": "respond"}]
        assert data["usage"]["tokens_in"] == 10
        mock_proxy.run_agent.assert_awaited_once()
    finally:
        execution_module.set_proxy(None)


async def test_run_agent_runtime_error(client, auth_headers, org_slug, deployed_agent):
    """Returns 502 when runtime proxy raises."""
    mock_proxy = AsyncMock()
    mock_proxy.run_agent = AsyncMock(side_effect=Exception("connection refused"))
    execution_module.set_proxy(mock_proxy)
    try:
        resp = await client.post(
            f"/api/v1/orgs/{org_slug}/agents/exec-agent/run",
            json={"query": "Hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 502
    finally:
        execution_module.set_proxy(None)


async def test_run_agent_rate_limit(client, auth_headers, org_slug, deployed_agent, db_session):
    """Returns 429 when daily usage limit is reached."""
    import uuid
    from datetime import datetime, timezone
    from astromesh_cloud.models.usage_log import UsageLog
    from astromesh_cloud.models.agent import Agent
    from astromesh_cloud.models.organization import Organization
    from sqlalchemy import select
    from astromesh_cloud.config import settings

    # Resolve org_id and agent_id
    org_result = await db_session.execute(
        select(Organization).where(Organization.slug == org_slug)
    )
    org = org_result.scalar_one()
    agent_result = await db_session.execute(
        select(Agent).where(Agent.org_id == org.id, Agent.name == "exec-agent")
    )
    agent = agent_result.scalar_one()

    # Insert max_requests_per_day usage log entries
    for _ in range(settings.max_requests_per_day):
        log = UsageLog(
            org_id=org.id,
            agent_id=agent.id,
            tokens_in=1,
            tokens_out=1,
            model="ollama/llama3",
            cost_usd=0.0,
        )
        db_session.add(log)
    await db_session.commit()

    mock_proxy = AsyncMock()
    execution_module.set_proxy(mock_proxy)
    try:
        resp = await client.post(
            f"/api/v1/orgs/{org_slug}/agents/exec-agent/run",
            json={"query": "Over limit"},
            headers=auth_headers,
        )
        assert resp.status_code == 429
    finally:
        execution_module.set_proxy(None)


async def test_run_agent_unauthenticated(client, org_slug):
    resp = await client.post(
        f"/api/v1/orgs/{org_slug}/agents/exec-agent/run",
        json={"query": "Hello"},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Usage route tests
# ---------------------------------------------------------------------------


async def test_get_usage_empty(client, auth_headers, org_slug):
    """Usage endpoint returns zeros when no logs exist."""
    resp = await client.get(f"/api/v1/orgs/{org_slug}/usage", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 0
    assert data["total_tokens_in"] == 0
    assert data["total_tokens_out"] == 0
    assert "period_start" in data
    assert "period_end" in data


async def test_get_usage_with_logs(client, auth_headers, org_slug, deployed_agent, db_session):
    """Usage endpoint aggregates existing usage logs."""
    from astromesh_cloud.models.usage_log import UsageLog
    from astromesh_cloud.models.agent import Agent
    from astromesh_cloud.models.organization import Organization
    from sqlalchemy import select

    org_result = await db_session.execute(
        select(Organization).where(Organization.slug == org_slug)
    )
    org = org_result.scalar_one()
    agent_result = await db_session.execute(
        select(Agent).where(Agent.org_id == org.id, Agent.name == "exec-agent")
    )
    agent = agent_result.scalar_one()

    for i in range(3):
        log = UsageLog(
            org_id=org.id,
            agent_id=agent.id,
            tokens_in=100,
            tokens_out=50,
            model="ollama/llama3",
            cost_usd=0.001,
        )
        db_session.add(log)
    await db_session.commit()

    resp = await client.get(f"/api/v1/orgs/{org_slug}/usage", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 3
    assert data["total_tokens_in"] == 300
    assert data["total_tokens_out"] == 150


async def test_get_usage_custom_days(client, auth_headers, org_slug):
    """Usage endpoint accepts a custom days parameter."""
    resp = await client.get(
        f"/api/v1/orgs/{org_slug}/usage?days=7",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_requests" in data


async def test_get_usage_wrong_org(client, org_slug):
    # Different user who doesn't belong to this org
    resp2 = await client.post(
        "/api/v1/auth/dev/login",
        params={"email": "stranger@test.com", "name": "Stranger"},
    )
    stranger_token = resp2.json()["access_token"]
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

    resp = await client.get(
        f"/api/v1/orgs/{org_slug}/usage",
        headers=stranger_headers,
    )
    assert resp.status_code == 403
