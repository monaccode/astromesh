import pytest
from httpx import AsyncClient, ASGITransport
from astromesh.api.main import app

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


async def test_create_agent_no_runtime_returns_503(client):
    resp = await client.post("/v1/agents", json={"metadata": {"name": "test-agent"}})
    assert resp.status_code == 503


async def test_delete_agent_no_runtime_returns_503(client):
    resp = await client.delete("/v1/agents/some-agent")
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


async def test_clear_memory_no_runtime_returns_503(client):
    resp = await client.delete("/v1/memory/test-agent/history/test-session")
    assert resp.status_code == 503


def test_run_response_usage_schema():
    from astromesh.api.routes.agents import AgentRunResponse, UsageInfo

    usage = UsageInfo(tokens_in=10, tokens_out=20, model="gpt-4o")
    resp = AgentRunResponse(answer="hello", steps=[], usage=usage)
    assert resp.usage.tokens_in == 10
    assert resp.usage.tokens_out == 20
    assert resp.usage.model == "gpt-4o"


def test_run_response_usage_defaults_to_none():
    from astromesh.api.routes.agents import AgentRunResponse

    resp = AgentRunResponse(answer="hello")
    assert resp.usage is None
    assert resp.steps == []
