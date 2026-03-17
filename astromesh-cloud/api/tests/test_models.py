"""Tests for SQLAlchemy ORM models."""

import uuid

import pytest
from sqlalchemy import select

from astromesh_cloud.models import Agent, OrgMember, Organization, User


class TestUserModel:
    async def test_create_user(self, db_session):
        user = User(
            email="alice@example.com",
            name="Alice",
            auth_provider="google",
            auth_provider_id="google-uid-123",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert isinstance(user.id, uuid.UUID)
        assert user.email == "alice@example.com"
        assert user.name == "Alice"
        assert user.auth_provider == "google"
        assert user.avatar_url is None
        assert user.last_login_at is None
        assert user.created_at is not None

    async def test_user_avatar_url(self, db_session):
        user = User(
            email="bob@example.com",
            name="Bob",
            auth_provider="github",
            auth_provider_id="gh-456",
            avatar_url="https://avatars.githubusercontent.com/u/456",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.avatar_url == "https://avatars.githubusercontent.com/u/456"
        assert user.auth_provider == "github"


class TestOrganizationModel:
    async def test_create_organization(self, db_session):
        org = Organization(slug="acme-corp", name="Acme Corp")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)

        assert isinstance(org.id, uuid.UUID)
        assert org.slug == "acme-corp"
        assert org.name == "Acme Corp"
        assert org.created_at is not None

    async def test_create_org_member(self, db_session):
        user = User(
            email="owner@example.com",
            name="Owner",
            auth_provider="google",
            auth_provider_id="g-owner-1",
        )
        org = Organization(slug="my-org", name="My Org")
        db_session.add_all([user, org])
        await db_session.commit()

        member = OrgMember(user_id=user.id, org_id=org.id, role="owner")
        db_session.add(member)
        await db_session.commit()

        result = await db_session.execute(
            select(OrgMember).where(OrgMember.org_id == org.id)
        )
        fetched = result.scalar_one()
        assert fetched.user_id == user.id
        assert fetched.role == "owner"

    async def test_org_member_default_role(self, db_session):
        user = User(
            email="member@example.com",
            name="Member",
            auth_provider="github",
            auth_provider_id="gh-member-2",
        )
        org = Organization(slug="another-org", name="Another Org")
        db_session.add_all([user, org])
        await db_session.commit()

        member = OrgMember(user_id=user.id, org_id=org.id)
        db_session.add(member)
        await db_session.commit()

        result = await db_session.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
        fetched = result.scalar_one()
        assert fetched.role == "member"


class TestAgentModel:
    async def test_create_agent(self, db_session):
        org = Organization(slug="bot-factory", name="Bot Factory")
        db_session.add(org)
        await db_session.commit()

        agent = Agent(
            org_id=org.id,
            name="support-bot",
            display_name="Support Bot",
            runtime_name="astromesh-v1",
            config={"model": "gpt-4o", "temperature": 0.7},
        )
        db_session.add(agent)
        await db_session.commit()
        await db_session.refresh(agent)

        assert isinstance(agent.id, uuid.UUID)
        assert agent.name == "support-bot"
        assert agent.display_name == "Support Bot"
        assert agent.status == "draft"
        assert agent.config == {"model": "gpt-4o", "temperature": 0.7}
        assert agent.deployed_at is None
        assert agent.updated_at is not None

    async def test_agent_unique_name_per_org(self, db_session):
        from sqlalchemy.exc import IntegrityError

        org = Organization(slug="unique-test-org", name="Unique Test Org")
        db_session.add(org)
        await db_session.commit()

        agent1 = Agent(
            org_id=org.id,
            name="duplicate-agent",
            display_name="Agent One",
            runtime_name="astromesh-v1",
        )
        db_session.add(agent1)
        await db_session.commit()

        agent2 = Agent(
            org_id=org.id,
            name="duplicate-agent",
            display_name="Agent Two",
            runtime_name="astromesh-v1",
        )
        db_session.add(agent2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_agent_status_values(self, db_session):
        org = Organization(slug="status-org", name="Status Org")
        db_session.add(org)
        await db_session.commit()

        for status in ("draft", "deployed", "paused"):
            agent = Agent(
                org_id=org.id,
                name=f"agent-{status}",
                display_name=f"Agent {status}",
                runtime_name="astromesh-v1",
                status=status,
            )
            db_session.add(agent)
        await db_session.commit()

        result = await db_session.execute(
            select(Agent).where(Agent.org_id == org.id)
        )
        agents = result.scalars().all()
        statuses = {a.status for a in agents}
        assert statuses == {"draft", "deployed", "paused"}
