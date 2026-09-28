"""AgentRuntime.reload(): relee config/agents y config/rag sin reiniciar el proceso."""

import pytest
import yaml

from astromesh.runtime.engine import AgentRuntime


def _config(name: str, *, system: str = "You are a test agent.", tools=None) -> dict:
    spec = {
        "model": {"primary": {"provider": "ollama", "model": "llama3:8b"}},
        "prompts": {"system": system},
        "orchestration": {"pattern": "react", "max_iterations": 5},
    }
    if tools is not None:
        spec["tools"] = tools
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": name, "version": "0.1.0", "namespace": "test"},
        "spec": spec,
    }


def _write(tmp_path, config: dict) -> None:
    name = config["metadata"]["name"]
    (tmp_path / "agents" / f"{name}.agent.yaml").write_text(yaml.safe_dump(config))


@pytest.fixture
async def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "1")
    (tmp_path / "agents").mkdir()
    _write(tmp_path, _config("uno"))
    _write(tmp_path, _config("dos"))
    rt = AgentRuntime(config_dir=str(tmp_path))
    await rt.bootstrap()
    return rt


def _statuses(rt) -> dict:
    return {a["name"]: a["status"] for a in rt.list_agents()}


async def test_adds_updates_and_removes(runtime, tmp_path):
    (tmp_path / "agents" / "dos.agent.yaml").unlink()
    _write(tmp_path, _config("uno", system="Otro prompt."))
    _write(tmp_path, _config("tres"))

    result = await runtime.reload()

    assert result == {"added": ["tres"], "updated": ["uno"], "removed": ["dos"], "failed": {}}
    assert _statuses(runtime) == {"uno": "deployed", "tres": "deployed"}
    assert runtime.agent_configs["uno"]["spec"]["prompts"]["system"] == "Otro prompt."


async def test_a_broken_agent_goes_draft_without_taking_the_others_down(runtime, tmp_path):
    _write(tmp_path, _config("dos", tools=[{"name": "x", "type": "agent"}]))  # sin `agent:`

    result = await runtime.reload()

    assert set(result["failed"]) == {"dos"}
    assert _statuses(runtime) == {"uno": "deployed", "dos": "draft"}


async def test_unparseable_yaml_is_reported_by_file(runtime, tmp_path):
    (tmp_path / "agents" / "roto.agent.yaml").write_text("metadata: [sin cerrar")

    result = await runtime.reload()

    assert set(result["failed"]) == {"roto"}
    assert _statuses(runtime) == {"uno": "deployed", "dos": "deployed"}


async def test_a_cycle_leaves_the_runtime_untouched(runtime, tmp_path):
    _write(tmp_path, _config("uno", tools=[{"name": "d", "type": "agent", "agent": "dos"}]))
    _write(tmp_path, _config("dos", tools=[{"name": "u", "type": "agent", "agent": "uno"}]))
    _write(tmp_path, _config("tres"))
    before = dict(runtime.agent_configs)

    with pytest.raises(ValueError, match="Circular"):
        await runtime.reload()

    assert runtime.agent_configs == before
    assert _statuses(runtime) == {"uno": "deployed", "dos": "deployed"}


async def test_a_paused_agent_stays_paused(runtime, tmp_path):
    runtime.pause_agent("uno")
    _write(tmp_path, _config("uno", system="Cambió."))

    result = await runtime.reload()

    assert _statuses(runtime)["uno"] == "paused"
    assert "uno" in result["updated"]
    assert runtime.agent_configs["uno"]["spec"]["prompts"]["system"] == "Cambió."


async def test_refused_when_disk_is_not_the_source(runtime, monkeypatch):
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "0")
    with pytest.raises(RuntimeError, match="ASTROMESH_PERSIST_AGENTS"):
        await runtime.reload()
    assert _statuses(runtime) == {"uno": "deployed", "dos": "deployed"}


async def test_bootstrap_survives_a_sub_agent_without_agent_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTROMESH_PERSIST_AGENTS", "1")
    (tmp_path / "agents").mkdir()
    _write(tmp_path, _config("uno"))
    _write(tmp_path, _config("dos", tools=[{"name": "x", "type": "agent"}]))
    rt = AgentRuntime(config_dir=str(tmp_path))
    await rt.bootstrap()
    assert _statuses(rt) == {"uno": "deployed", "dos": "draft"}
