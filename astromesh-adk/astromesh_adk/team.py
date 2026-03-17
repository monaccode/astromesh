"""AgentTeam — multi-agent composition with orchestration patterns."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from astromesh_adk.result import RunResult
from astromesh_adk.callbacks import Callbacks

if TYPE_CHECKING:
    from astromesh_adk.agent import AgentWrapper

VALID_TEAM_PATTERNS = {"supervisor", "swarm", "pipeline", "parallel"}


class AgentTeam:
    """Compose multiple agents into a team with an orchestration pattern.

    Patterns:
        - supervisor: A supervisor agent delegates tasks to workers
        - swarm: Agents hand off control to each other
        - pipeline: Sequential execution through a chain of agents
        - parallel: All agents execute in parallel, results are aggregated
    """

    def __init__(
        self,
        name: str,
        pattern: str,
        agents: list[AgentWrapper] | None = None,
        supervisor: AgentWrapper | None = None,
        workers: list[AgentWrapper] | None = None,
        entry_agent: AgentWrapper | None = None,
    ):
        if pattern not in VALID_TEAM_PATTERNS:
            raise ValueError(f"Unknown team pattern: {pattern!r}. Available: {VALID_TEAM_PATTERNS}")

        self.name = name
        self.pattern = pattern
        self.agents = agents or []
        self.supervisor = supervisor
        self.workers = workers or []
        self.entry_agent = entry_agent

    async def run(
        self,
        query: str,
        session_id: str = "default",
        context: dict | None = None,
        callbacks: Callbacks | None = None,
        runtime: Any = None,
    ) -> RunResult:
        """Execute the team with the configured pattern."""
        from astromesh_adk.runner import get_or_create_runtime

        rt = runtime or get_or_create_runtime()
        return await rt.run_team(self, query, session_id, context, callbacks)

    def _build_workers_dict(self) -> dict:
        """Build workers config dict for SupervisorPattern."""
        return {
            w.name: {"description": w.description}
            for w in self.workers
        }

    def _build_agent_configs(self) -> dict:
        """Build agent_configs dict for SwarmPattern."""
        return {
            a.name: {"description": a.description}
            for a in self.agents
        }

    def _build_stages(self) -> list[str]:
        """Build stages list for PipelinePattern."""
        return [a.name for a in self.agents]

    def __repr__(self):
        count = len(self.workers or self.agents)
        return f"<AgentTeam {self.name!r} pattern={self.pattern!r} agents={count}>"
