"""Leader election using bully algorithm."""

from __future__ import annotations

import logging

from astromesh.mesh.manager import MeshManager

logger = logging.getLogger("astromesh.mesh.leader")


class LeaderElector:
    """Bully algorithm leader election — highest node ID wins."""

    def __init__(self, mesh: MeshManager):
        self._mesh = mesh
        self._leader_id: str | None = None

    def current_leader(self) -> str | None:
        return self._leader_id

    def is_leader(self) -> bool:
        return self._leader_id == self._mesh.node_id

    def elect(self) -> str | None:
        alive = self._mesh.cluster_state().alive_nodes()
        if not alive:
            self._leader_id = None
            return None

        winner = max(alive, key=lambda n: n.node_id)
        self._leader_id = winner.node_id
        self._mesh.cluster_state().leader_id = winner.node_id

        # Update leader flag on all nodes
        for node in self._mesh.cluster_state().nodes.values():
            node.leader = node.node_id == winner.node_id

        logger.info("Leader elected: %s (%s)", winner.name, winner.node_id)
        return winner.node_id

    def on_node_joined(self, node_id: str) -> None:
        self.elect()

    def on_node_failed(self, node_id: str) -> None:
        if node_id == self._leader_id:
            logger.info("Leader %s failed, triggering election", node_id)
            self.elect()
