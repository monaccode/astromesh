"""Shared fixtures. httpx ASGITransport does not run ASGI lifespan unless wrapped."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app


@pytest.fixture
def use_native(monkeypatch):
    """Prefer Rust native extensions when installed (parity tests in test_native_*.py)."""
    monkeypatch.delenv("ASTROMESH_FORCE_PYTHON", raising=False)


@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
