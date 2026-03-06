import pytest
from httpx import AsyncClient, ASGITransport
from astromech.api.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

async def test_health(client):
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data

async def test_list_agents_empty(client):
    resp = await client.get("/v1/agents")
    assert resp.status_code == 200
    assert resp.json()["agents"] == []
