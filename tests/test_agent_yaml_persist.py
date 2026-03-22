"""Agent YAML persistence when ASTROMESH_PERSIST_AGENTS=1 (overrides conftest default)."""

from astromesh.runtime.engine import AgentRuntime


def _full_config(name: str) -> dict:
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {
            "name": name,
            "version": "0.1.0",
            "namespace": "test",
        },
        "spec": {
            "identity": {
                "display_name": f"{name} display",
                "description": "persist test",
            },
            "model": {
                "primary": {
                    "provider": "ollama",
                    "model": "llama3:8b",
                    "endpoint": "http://ollama:11434",
                },
                "routing": {"strategy": "cost_optimized"},
            },
            "prompts": {"system": "You are a test agent."},
            "orchestration": {"pattern": "react", "max_iterations": 5},
        },
    }


async def test_register_writes_yaml_when_persist_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "1")
    (tmp_path / "agents").mkdir()
    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.register_agent(_full_config("persisted-draft"))
    path = tmp_path / "agents" / "persisted-draft.agent.yaml"
    assert path.is_file()


async def test_unregister_removes_yaml_when_persist_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "1")
    (tmp_path / "agents").mkdir()
    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.register_agent(_full_config("gone"))
    path = tmp_path / "agents" / "gone.agent.yaml"
    assert path.is_file()
    runtime.unregister_agent("gone")
    assert not path.exists()


async def test_yaml_survives_new_runtime_bootstrap(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "1")
    (tmp_path / "agents").mkdir()
    r1 = AgentRuntime(config_dir=str(tmp_path))
    await r1.register_agent(_full_config("survivor"))
    r2 = AgentRuntime(config_dir=str(tmp_path))
    await r2.bootstrap()
    assert "survivor" in r2._agents
    assert r2._agent_status.get("survivor") == "deployed"
