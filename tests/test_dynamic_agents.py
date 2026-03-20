import pytest
from astromesh.runtime.engine import AgentRuntime


def _make_config(name: str, version: str = "0.1.0", namespace: str = "test") -> dict:
    """Build a minimal agent config dict matching the schema expected by _build_agent()."""
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {
            "name": name,
            "version": version,
            "namespace": namespace,
        },
        "spec": {
            "identity": {
                "display_name": f"{name} display",
                "description": f"Dynamic test agent: {name}",
            },
            "model": {
                "primary": {
                    "provider": "ollama",
                    "model": "llama3:8b",
                    "endpoint": "http://ollama:11434",
                },
                "routing": {"strategy": "cost_optimized"},
            },
            "prompts": {
                "system": "You are a dynamic test agent.",
            },
            "orchestration": {
                "pattern": "react",
                "max_iterations": 5,
            },
        },
    }


@pytest.fixture
def runtime(tmp_path):
    """An AgentRuntime with an empty (but valid) config dir — no bootstrap needed."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    return AgentRuntime(config_dir=str(tmp_path))


async def test_register_agent_adds_to_configs(runtime):
    config = _make_config("dynamic-agent")
    await runtime.register_agent(config)

    # register_agent stores in _agent_configs with status 'draft' (not in _agents)
    assert "dynamic-agent" in runtime._agent_configs
    assert runtime._agent_status["dynamic-agent"] == "draft"


async def test_register_agent_upsert_overwrites(runtime):
    config_v1 = _make_config("my-agent", version="0.1.0")
    config_v2 = _make_config("my-agent", version="0.2.0")

    await runtime.register_agent(config_v1)
    assert runtime._agent_configs["my-agent"]["metadata"]["version"] == "0.1.0"

    # Second register must not raise — upsert semantics
    await runtime.register_agent(config_v2)
    assert runtime._agent_configs["my-agent"]["metadata"]["version"] == "0.2.0"


async def test_unregister_agent_removes(runtime):
    config = _make_config("to-remove")
    await runtime.register_agent(config)
    assert "to-remove" in runtime._agent_configs

    runtime.unregister_agent("to-remove")
    assert "to-remove" not in runtime._agent_configs
    assert "to-remove" not in runtime._agent_status


async def test_unregister_agent_not_found_raises(runtime):
    with pytest.raises(ValueError, match="not found"):
        runtime.unregister_agent("ghost-agent")
