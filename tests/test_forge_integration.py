"""End-to-end integration test simulating what Forge SPA does."""

import pytest
import yaml
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app


@pytest.fixture
def forge_config_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agents").mkdir()
    templates_dir = config_dir / "templates"
    templates_dir.mkdir()

    tpl = {
        "apiVersion": "astromesh/v1",
        "kind": "AgentTemplate",
        "metadata": {"name": "test-tpl", "version": "1.0.0", "category": "test", "tags": []},
        "template": {
            "display_name": "Test Template",
            "description": "A test template",
            "recommended_channels": [],
            "variables": [{"key": "name", "label": "Name", "required": True}],
            "agent_config": {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {
                    "name": "test-agent",
                    "version": "1.0.0",
                    "namespace": "test",
                },
                "spec": {
                    "identity": {
                        "display_name": "Test Agent",
                        "description": "Test",
                    },
                    "model": {
                        "primary": {
                            "provider": "ollama",
                            "model": "test",
                            "endpoint": "http://localhost:11434",
                        },
                        "routing": {"strategy": "cost_optimized"},
                    },
                    "prompts": {"system": "You are a test agent."},
                    "orchestration": {"pattern": "react", "max_iterations": 5},
                },
            },
        },
    }
    (templates_dir / "test-tpl.template.yaml").write_text(yaml.dump(tpl))

    monkeypatch.setenv("ASTROMESH_CONFIG_DIR", str(config_dir))
    yield config_dir


async def test_full_forge_flow(forge_config_dir):
    """Simulates: list templates -> get template -> create agent -> deploy -> update -> delete."""
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. List templates
            resp = await client.get("/v1/templates")
            assert resp.status_code == 200
            templates = resp.json()
            names = {t["name"] for t in templates}
            assert "test-tpl" in names

            # 2. Get template detail
            resp = await client.get("/v1/templates/test-tpl")
            assert resp.status_code == 200
            detail = resp.json()
            assert "agent_config" in detail

            # 3. Create agent (Forge resolves variables client-side)
            agent_config = detail["agent_config"]
            agent_config["metadata"]["name"] = "acme-agent"
            agent_config["spec"]["identity"]["display_name"] = "Acme Agent"
            resp = await client.post("/v1/agents", json=agent_config)
            assert resp.status_code == 201

            # 4. List agents — should show as draft
            resp = await client.get("/v1/agents")
            assert resp.status_code == 200
            agents = resp.json()["agents"]
            agent = next(a for a in agents if a["name"] == "acme-agent")
            assert agent["status"] == "draft"

            # 5. Update agent
            agent_config["spec"]["prompts"]["system"] = "Updated prompt"
            resp = await client.put("/v1/agents/acme-agent", json=agent_config)
            assert resp.status_code == 200

            # 6. Delete agent
            resp = await client.delete("/v1/agents/acme-agent")
            assert resp.status_code == 200

            # 7. Verify deleted
            resp = await client.get("/v1/agents")
            agents = resp.json()["agents"]
            assert not any(a["name"] == "acme-agent" for a in agents)
