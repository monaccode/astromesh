async def test_health(client):
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data

async def test_list_agents_includes_bundled_config(client):
    resp = await client.get("/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert isinstance(agents, list)
    assert len(agents) >= 1


async def test_get_agent_not_found(client):
    resp = await client.get("/v1/agents/nonexistent")
    assert resp.status_code == 404


async def test_get_agent_returns_full_config(client):
    resp = await client.get("/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert len(agents) >= 1
    name = agents[0]["name"]
    detail = await client.get(f"/v1/agents/{name}")
    assert detail.status_code == 200
    body = detail.json()
    assert body.get("kind") == "Agent"
    assert "metadata" in body and "spec" in body
    assert "identity" in body["spec"]
    assert "display_name" in body["spec"]["identity"]


async def test_run_agent_unknown_returns_404(client):
    resp = await client.post(
        "/v1/agents/definitely-nonexistent-agent/run",
        json={"query": "hello"},
    )
    assert resp.status_code == 404


async def test_create_agent_minimal_returns_201(client):
    resp = await client.post("/v1/agents", json={"metadata": {"name": "api-test-draft-agent"}})
    assert resp.status_code == 201


async def test_delete_unknown_agent_returns_404(client):
    resp = await client.delete("/v1/agents/unknown-agent-that-does-not-exist")
    assert resp.status_code == 404


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


async def test_clear_memory_unknown_agent_returns_404(client):
    resp = await client.delete("/v1/memory/unknown-agent-xyz/history/test-session")
    assert resp.status_code == 404


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
