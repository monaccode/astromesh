"""Tests for the reconciliation service."""
import pytest
from unittest.mock import AsyncMock, patch

from astromesh_cloud.models.agent import Agent
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.models.user import User
from astromesh_cloud.services.reconciliation import reconcile_agents


@pytest.fixture
async def org_and_agent(db_session):
    """Seed a deployed agent and return (org, agent)."""
    import uuid

    user = User(
        id=uuid.uuid4(),
        email="reconcile@test.com",
        name="Reconcile",
        auth_provider="google",
        auth_provider_id="dev-reconcile@test.com",
    )
    db_session.add(user)
    await db_session.flush()

    org = Organization(id=uuid.uuid4(), slug="recon-org", name="Recon Org")
    db_session.add(org)
    await db_session.flush()

    member = OrgMember(user_id=user.id, org_id=org.id, role="owner")
    db_session.add(member)
    await db_session.flush()

    agent = Agent(
        org_id=org.id,
        name="my-bot",
        display_name="My Bot",
        config={
            "name": "my-bot",
            "display_name": "My Bot",
            "system_prompt": "You are helpful.",
            "tone": "professional",
            "model": "ollama/llama3",
            "routing_strategy": "cost_optimized",
            "tools": [],
            "tool_configs": {},
            "memory_enabled": False,
            "pii_filter": False,
            "content_filter": False,
            "orchestration": "react",
        },
        status="deployed",
        runtime_name="recon-org--my-bot",
    )
    db_session.add(agent)
    await db_session.commit()
    return org, agent


async def test_reconcile_no_deployed_agents(db_session):
    """Returns 0 when there are no deployed agents."""
    proxy = AsyncMock()
    count = await reconcile_agents(db_session, proxy)
    assert count == 0
    proxy.list_agents.assert_not_called()


async def test_reconcile_agent_already_in_runtime(db_session, org_and_agent):
    """Returns 0 when deployed agent is already registered in runtime."""
    _, agent = org_and_agent
    proxy = AsyncMock()
    proxy.list_agents = AsyncMock(return_value=[{"name": agent.runtime_name}])

    count = await reconcile_agents(db_session, proxy)
    assert count == 0
    proxy.register_agent.assert_not_called()


async def test_reconcile_missing_agent_re_registers(db_session, org_and_agent):
    """Re-registers an agent that is deployed in DB but missing from runtime."""
    _, agent = org_and_agent
    proxy = AsyncMock()
    proxy.list_agents = AsyncMock(return_value=[])  # empty runtime
    proxy.register_agent = AsyncMock(return_value={"status": "ok"})

    count = await reconcile_agents(db_session, proxy)
    assert count == 1
    proxy.register_agent.assert_awaited_once()
    call_config = proxy.register_agent.call_args[0][0]
    assert call_config["metadata"]["name"] == agent.runtime_name


async def test_reconcile_runtime_list_failure(db_session, org_and_agent):
    """Falls back to empty runtime names set when list_agents raises."""
    _, agent = org_and_agent
    proxy = AsyncMock()
    proxy.list_agents = AsyncMock(side_effect=Exception("network error"))
    proxy.register_agent = AsyncMock(return_value={"status": "ok"})

    count = await reconcile_agents(db_session, proxy)
    # Should still attempt to re-register since runtime_names defaults to empty set
    assert count == 1


async def test_reconcile_register_failure_is_logged(db_session, org_and_agent, caplog):
    """Logs error and continues when register_agent fails for one agent."""
    import logging

    _, agent = org_and_agent
    proxy = AsyncMock()
    proxy.list_agents = AsyncMock(return_value=[])
    proxy.register_agent = AsyncMock(side_effect=Exception("502 Bad Gateway"))

    with caplog.at_level(logging.ERROR, logger="astromesh_cloud.services.reconciliation"):
        count = await reconcile_agents(db_session, proxy)

    assert count == 0
    assert any("Reconciliation failed" in r.message for r in caplog.records)
