import pytest
from astromesh_adk.team import AgentTeam
from astromesh_adk.agent import agent


@agent(name="researcher", model="ollama/llama3", description="Research agent")
async def researcher(ctx):
    """You research topics."""
    return None


@agent(name="writer", model="ollama/llama3", description="Writing agent")
async def writer(ctx):
    """You write content."""
    return None


@agent(name="editor", model="ollama/llama3", description="Editing agent")
async def editor(ctx):
    """You edit content."""
    return None


def test_supervisor_team_creation():
    team = AgentTeam(
        name="content-team",
        pattern="supervisor",
        supervisor=researcher,
        workers=[writer, editor],
    )
    assert team.name == "content-team"
    assert team.pattern == "supervisor"
    assert team.supervisor is researcher
    assert len(team.workers) == 2


def test_swarm_team_creation():
    team = AgentTeam(
        name="pipeline",
        pattern="swarm",
        agents=[researcher, writer, editor],
        entry_agent=researcher,
    )
    assert team.pattern == "swarm"
    assert team.entry_agent is researcher
    assert len(team.agents) == 3


def test_pipeline_team_creation():
    team = AgentTeam(
        name="doc-pipeline",
        pattern="pipeline",
        agents=[researcher, writer, editor],
    )
    assert team.pattern == "pipeline"


def test_parallel_team_creation():
    team = AgentTeam(
        name="research-team",
        pattern="parallel",
        agents=[researcher, writer],
    )
    assert team.pattern == "parallel"


def test_team_has_run():
    team = AgentTeam(name="t", pattern="pipeline", agents=[researcher, writer])
    assert hasattr(team, "run")
    assert callable(team.run)


def test_team_build_workers_dict():
    team = AgentTeam(
        name="t",
        pattern="supervisor",
        supervisor=researcher,
        workers=[writer, editor],
    )
    workers_dict = team._build_workers_dict()
    assert "writer" in workers_dict
    assert "editor" in workers_dict
    assert workers_dict["writer"]["description"] == "Writing agent"


def test_team_build_agent_configs():
    team = AgentTeam(
        name="t",
        pattern="swarm",
        agents=[researcher, writer],
        entry_agent=researcher,
    )
    configs = team._build_agent_configs()
    assert "researcher" in configs
    assert "writer" in configs


def test_team_build_stages():
    team = AgentTeam(
        name="t",
        pattern="pipeline",
        agents=[researcher, writer, editor],
    )
    stages = team._build_stages()
    assert stages == ["researcher", "writer", "editor"]


def test_team_invalid_pattern():
    with pytest.raises(ValueError, match="Unknown team pattern"):
        AgentTeam(name="t", pattern="invalid", agents=[researcher])
