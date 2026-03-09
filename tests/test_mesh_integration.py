"""Integration tests for Astromesh OS Phase 2 — services and peers."""

import pytest
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app
from astromesh.api.routes import system
from astromesh.runtime.engine import AgentRuntime
from astromesh.runtime.peers import PeerClient
from astromesh.runtime.services import ServiceManager

AGENT_YAML = """
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
"""


@pytest.fixture
async def worker_node(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text(AGENT_YAML)

    sm = ServiceManager({"agents": True, "inference": False, "channels": False})
    pc = PeerClient(
        [
            {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
        ]
    )

    runtime = AgentRuntime(config_dir=str(tmp_path), service_manager=sm, peer_client=pc)
    await runtime.bootstrap()
    system.set_runtime(runtime)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, runtime

    system.set_runtime(None)
    await pc.close()


async def test_worker_node_status(worker_node):
    client, runtime = worker_node
    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["agents_loaded"] == 1
    assert data["services"]["agents"] is True
    assert data["services"]["inference"] is False
    assert data["services"]["channels"] is False
    assert len(data["peers"]) == 1
    assert data["peers"][0]["name"] == "inference-1"


async def test_worker_node_doctor(worker_node):
    client, runtime = worker_node
    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()

    assert data["checks"]["runtime"]["status"] == "ok"
    assert "peer:inference-1" in data["checks"]
    assert data["checks"]["peer:inference-1"]["status"] == "unreachable"


@pytest.fixture
async def gateway_node(tmp_path):
    sm = ServiceManager(
        {"agents": False, "inference": False, "tools": False, "memory": False, "rag": False}
    )
    pc = PeerClient(
        [
            {
                "name": "worker-1",
                "url": "http://worker:8000",
                "services": ["agents", "tools", "memory"],
            },
        ]
    )

    runtime = AgentRuntime(config_dir=str(tmp_path), service_manager=sm, peer_client=pc)
    await runtime.bootstrap()
    system.set_runtime(runtime)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, runtime

    system.set_runtime(None)
    await pc.close()


async def test_gateway_node_no_agents(gateway_node):
    client, runtime = gateway_node
    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_loaded"] == 0
    assert data["services"]["agents"] is False
