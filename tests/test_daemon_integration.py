"""Integration tests for astromeshd + system API."""

import pytest
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app
from astromesh.api.routes import system
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture
async def bootstrapped_client(tmp_path):
    """Client with a bootstrapped runtime."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
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
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()
    system.set_runtime(runtime)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    system.set_runtime(None)


async def test_status_with_bootstrapped_runtime(bootstrapped_client):
    resp = await bootstrapped_client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_loaded"] == 1
    assert data["version"] == "0.10.0"


async def test_doctor_with_bootstrapped_runtime(bootstrapped_client):
    resp = await bootstrapped_client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["runtime"]["status"] == "ok"
