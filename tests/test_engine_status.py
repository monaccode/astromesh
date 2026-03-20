import pytest
from astromesh.runtime.engine import AgentRuntime

SAMPLE_CONFIG = {
    "apiVersion": "astromesh/v1",
    "kind": "Agent",
    "metadata": {"name": "test-status", "version": "1.0.0", "namespace": "test"},
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
        "prompts": {"system": "You are a test agent."},
        "orchestration": {"pattern": "react", "max_iterations": 5},
    },
}


@pytest.fixture
def runtime(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agents").mkdir()
    return AgentRuntime(config_dir=str(config_dir))


async def test_register_agent_starts_as_draft(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "draft"


async def test_deploy_agent_changes_status(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    await runtime.deploy_agent("test-status")
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "deployed"


async def test_pause_agent_changes_status(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    await runtime.deploy_agent("test-status")
    runtime.pause_agent("test-status")
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "paused"


async def test_deploy_nonexistent_raises(runtime):
    with pytest.raises(ValueError, match="not found"):
        await runtime.deploy_agent("nonexistent")


async def test_pause_nondeployed_raises(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    with pytest.raises(ValueError, match="not deployed"):
        runtime.pause_agent("test-status")


async def test_update_agent_config(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    updated = {**SAMPLE_CONFIG}
    updated["spec"] = {**SAMPLE_CONFIG["spec"], "prompts": {"system": "Updated prompt"}}
    await runtime.update_agent("test-status", updated)
    agents = runtime.list_agents()
    agent = next(a for a in agents if a["name"] == "test-status")
    assert agent["status"] == "draft"  # update resets to draft


async def test_unregister_cleans_all_dicts(runtime):
    await runtime.register_agent(SAMPLE_CONFIG)
    runtime.unregister_agent("test-status")
    agents = runtime.list_agents()
    assert not any(a["name"] == "test-status" for a in agents)
