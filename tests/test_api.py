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


async def test_get_agent_not_found(client):
    resp = await client.get("/v1/agents/nonexistent")
    assert resp.status_code == 404


async def test_run_agent_no_runtime(client):
    resp = await client.post("/v1/agents/test/run", json={"query": "hello"})
    assert resp.status_code == 503


async def test_list_tools(client):
    resp = await client.get("/v1/tools")
    assert resp.status_code == 200
    assert resp.json()["tools"] == []


async def test_rag_query(client):
    resp = await client.post("/v1/rag/query", json={"query": "test"})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


async def test_memory_history(client):
    resp = await client.get("/v1/memory/test-agent/history/session1")
    assert resp.status_code == 200
    assert resp.json()["history"] == []
