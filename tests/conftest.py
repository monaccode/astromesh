"""Shared fixtures. httpx ASGITransport does not run ASGI lifespan unless wrapped."""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app


@pytest.fixture(autouse=True)
def _disable_agent_yaml_persist(monkeypatch):
    """Avoid writing into the repo's config/agents during API tests."""
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "0")


@pytest.fixture(autouse=True)
def _clean_otlp_env(monkeypatch):
    """Remove ASTROMESH_OTLP_ENABLED so an ambiently-exported var (dev shell, CI runner) can't
    make bootstrap() clobber collectors that tests inject. Autouse fixtures run in registration
    order, so tests that need it (tests/test_otlp_wiring.py) set it via monkeypatch after this
    delenv, which still wins for that test."""
    monkeypatch.delenv("ASTROMESH_OTLP_ENABLED", raising=False)


@pytest.fixture(autouse=True)
def _fast_sse_for_tests(monkeypatch):
    """Use very short SSE idle timeouts so generators terminate quickly in TestClient."""
    monkeypatch.setenv("ASTROMESH_SSE_POLL_INTERVAL", "0.05")
    monkeypatch.setenv("ASTROMESH_SSE_KEEPALIVE_EVERY", "100")
    monkeypatch.setenv("ASTROMESH_SSE_IDLE_EXIT_AFTER", "1")


@pytest.fixture
def use_native(monkeypatch):
    """Prefer Rust native extensions when installed (parity tests in test_native_*.py)."""
    monkeypatch.delenv("ASTROMESH_FORCE_PYTHON", raising=False)


@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
