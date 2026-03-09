"""Scheduler — agent placement and request routing."""

from __future__ import annotations

import logging

from astromesh.mesh.manager import MeshManager

logger = logging.getLogger("astromesh.mesh.scheduler")


class Scheduler:
    """Schedules agent placement and routes requests. Active on leader only."""

    def __init__(self, mesh: MeshManager):
        self._mesh = mesh

    def place_agent(self, agent_name: str) -> list[str]:
        """Return node IDs of all alive worker nodes with 'agents' service."""
        alive = self._mesh.cluster_state().alive_nodes()
        return [n.node_id for n in alive if "agents" in n.services]

    def route_request(self, agent_name: str) -> str | None:
        """Route to the alive node with the agent loaded and fewest active requests."""
        alive = self._mesh.cluster_state().alive_nodes()
        candidates = [n for n in alive if agent_name in n.agents]
        if not candidates:
            return None
        best = min(candidates, key=lambda n: n.load.active_requests)
        return best.node_id

    def placement_table(self) -> dict[str, list[str]]:
        """Return mapping of agent_name → [node_ids] for all loaded agents."""
        table: dict[str, list[str]] = {}
        alive = self._mesh.cluster_state().alive_nodes()
        for node in alive:
            for agent in node.agents:
                table.setdefault(agent, []).append(node.node_id)
        return table
