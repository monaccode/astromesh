import pytest
from httpx import ASGITransport, AsyncClient
from astromesh.api.main import app
from astromesh.api.routes import agents as agents_route
from unittest.mock import AsyncMock, MagicMock

SAMPLE_CONFIG = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "test-agent", "version": "1.0.0", "namespace": "test"},
    "spec": {
        "identity": {"display_name": "Test", "description": "Test agent"},
        "model": {
            "primary": {
                "provider": "ollama",
                "model": "llama3.1:8b",
                "endpoint": "http://localhost:11434",
            },
            "routing": {"strategy": "cost_optimized"},
        },
        "prompts": {"system": "Test prompt."},
        "orchestration": {"pattern": "react", "max_iterations": 5},
    },
}


@pytest.fixture
def mock_runtime():
    runtime = MagicMock()
    runtime.update_agent = AsyncMock()
    runtime.deploy_agent = AsyncMock()
    runtime.pause_agent = MagicMock()
    runtime.list_agents.return_value = [
        {"name": "test-agent", "version": "1.0.0", "namespace": "test", "status": "draft"}
    ]
    agents_route.set_runtime(runtime)
    yield runtime
    agents_route.set_runtime(None)


async def test_put_agent(mock_runtime):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/v1/agents/test-agent", json=SAMPLE_CONFIG)
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    mock_runtime.update_agent.assert_awaited_once_with("test-agent", SAMPLE_CONFIG)


async def test_deploy_agent(mock_runtime):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents/test-agent/deploy")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deployed"
    mock_runtime.deploy_agent.assert_awaited_once_with("test-agent")


async def test_pause_agent(mock_runtime):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents/test-agent/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    mock_runtime.pause_agent.assert_called_once_with("test-agent")


async def test_deploy_nonexistent_returns_404(mock_runtime):
    mock_runtime.deploy_agent.side_effect = ValueError("Agent 'nope' not found")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/agents/nope/deploy")
    assert resp.status_code == 404


async def test_put_agent_no_runtime():
    agents_route.set_runtime(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/v1/agents/test-agent", json=SAMPLE_CONFIG)
    assert resp.status_code == 503
