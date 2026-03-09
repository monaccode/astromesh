"""Tests for /v1/system/* API endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_system_status_no_runtime(client):
    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "uptime_seconds" in data
    assert data["mode"] in ("dev", "system")
    assert "agents_loaded" in data


async def test_system_status_with_runtime(client):
    from astromesh.api.routes import system

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = [{"name": "agent1"}, {"name": "agent2"}]
    mock_runtime.service_manager = None
    mock_runtime.peer_client = None
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_loaded"] == 2
    system.set_runtime(None)


async def test_system_doctor_no_runtime(client):
    from astromesh.api.routes import system

    system.set_runtime(None)

    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is False
    assert data["checks"]["runtime"]["status"] == "unavailable"


async def test_system_doctor_with_runtime(client):
    from astromesh.api.routes import system

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = [{"name": "a1"}]
    mock_runtime._agents = {"a1": MagicMock()}

    mock_provider = AsyncMock()
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_runtime._agents["a1"]._router._providers = {"ollama": mock_provider}

    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["runtime"]["status"] == "ok"
    system.set_runtime(None)


async def test_system_status_includes_services(client):
    from astromesh.api.routes import system
    from astromesh.runtime.services import ServiceManager

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = []
    mock_runtime.service_manager = ServiceManager({"inference": False})
    mock_runtime.peer_client = None
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "services" in data
    assert data["services"]["inference"] is False
    assert data["services"]["api"] is True
    system.set_runtime(None)


async def test_system_status_includes_peers(client):
    from astromesh.api.routes import system
    from astromesh.runtime.peers import PeerClient

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = []
    mock_runtime.service_manager = None
    mock_runtime.peer_client = PeerClient(
        [
            {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
        ]
    )
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "peers" in data
    assert len(data["peers"]) == 1
    assert data["peers"][0]["name"] == "inference-1"
    system.set_runtime(None)


async def test_system_doctor_checks_peers(client):
    from astromesh.api.routes import system
    from astromesh.runtime.peers import PeerClient

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = []
    mock_runtime._agents = {}
    mock_runtime.service_manager = None

    pc = PeerClient(
        [
            {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
        ]
    )
    pc.health_check = AsyncMock(return_value=False)
    mock_runtime.peer_client = pc
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert "peer:inference-1" in data["checks"]
    system.set_runtime(None)
