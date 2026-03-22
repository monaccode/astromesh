"""Shared fixtures. httpx ASGITransport does not run ASGI lifespan unless wrapped."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app


@pytest.fixture(autouse=True)
def _disable_agent_yaml_persist(monkeypatch):
    """Avoid writing into the repo's config/agents during API tests."""
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "0")


@pytest.fixture
def use_native(monkeypatch):
    """Prefer Rust native extensions when installed (parity tests in test_native_*.py)."""
    monkeypatch.delenv("ASTROMESH_FORCE_PYTHON", raising=False)


@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
