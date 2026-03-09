"""MeshManager — gossip, heartbeats, and cluster state."""

from __future__ import annotations

import logging
import random
import time
import uuid

import httpx
import psutil

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.state import ClusterState, NodeLoad, NodeState
from astromesh.runtime.services import ServiceManager

logger = logging.getLogger("astromesh.mesh")


class MeshManager:
    """Manages gossip, heartbeats, and cluster state for this node."""

    def __init__(self, config: MeshConfig, service_manager: ServiceManager):
        self._config = config
        self._service_manager = service_manager
        self._cluster = ClusterState()
        self._http = httpx.AsyncClient(timeout=10.0)
        self._left = False

        self.node_id = str(uuid.uuid4())
        self._cluster.add_node(self._make_local_state())

    def _make_local_state(self) -> NodeState:
        return NodeState(
            node_id=self.node_id,
            name=self._config.node_name,
            url=f"http://{self._config.bind}",
            services=self._service_manager.enabled_services(),
            agents=[],
            load=NodeLoad(),
            joined_at=time.time(),
            last_heartbeat=time.time(),
        )

    def local_node_state(self) -> NodeState:
        return self._cluster.nodes[self.node_id]

    def cluster_state(self) -> ClusterState:
        return self._cluster

    def is_alive(self, node_id: str) -> bool:
        node = self._cluster.nodes.get(node_id)
        return node is not None and node.status == "alive"

    def update_node(self, node_id: str, state: NodeState) -> None:
        self._cluster.nodes[node_id] = state
        self._cluster.version += 1

    def update_load(self, active_requests: int = 0) -> None:
        local = self._cluster.nodes[self.node_id]
        local.load = NodeLoad(
            cpu_percent=psutil.cpu_percent(),
            memory_percent=psutil.virtual_memory().percent,
            active_requests=active_requests,
        )
        local.last_heartbeat = time.time()

    def update_agents(self, agent_names: list[str]) -> None:
        self._cluster.nodes[self.node_id].agents = agent_names

    def check_timeouts(self) -> list[str]:
        now = time.time()
        changed = []
        for node_id, node in self._cluster.nodes.items():
            if node_id == self.node_id:
                continue
            elapsed = now - node.last_heartbeat
            if elapsed > self._config.dead_timeout and node.status != "dead":
                node.status = "dead"
                changed.append(node_id)
                logger.warning("Node %s (%s) is dead", node.name, node_id)
            elif elapsed > self._config.failure_timeout and node.status == "alive":
                node.status = "suspect"
                changed.append(node_id)
                logger.warning("Node %s (%s) is suspect", node.name, node_id)
        return changed

    def get_gossip_targets(self) -> list[NodeState]:
        others = [
            n
            for nid, n in self._cluster.nodes.items()
            if nid != self.node_id and n.status != "dead"
        ]
        count = min(self._config.gossip_fanout, len(others))
        return random.sample(others, count) if others else []

    async def join(self) -> None:
        if not self._config.seeds:
            logger.info("No seeds configured, starting as standalone node")
            return

        local_state = self.local_node_state()
        for seed_url in self._config.seeds:
            try:
                resp = await self._http.post(
                    f"{seed_url}/v1/mesh/join",
                    json=local_state.to_dict(),
                )
                resp.raise_for_status()
                data = resp.json()
                incoming = [NodeState.from_dict(n) for n in data.get("nodes", [])]
                self._cluster.merge(incoming)
                if data.get("leader_id"):
                    self._cluster.leader_id = data["leader_id"]
                logger.info(
                    "Joined mesh via seed %s, cluster size: %d",
                    seed_url,
                    len(self._cluster.nodes),
                )
                return
            except Exception as e:
                logger.warning("Failed to join via seed %s: %s", seed_url, e)
                continue

        logger.warning("Could not reach any seed node, starting as standalone")

    async def leave(self) -> None:
        self._left = True
        for node in self.get_gossip_targets():
            try:
                await self._http.post(
                    f"{node.url}/v1/mesh/leave",
                    json={"node_id": self.node_id},
                )
            except Exception:
                pass
        logger.info("Left mesh")

    async def gossip_once(self) -> None:
        self.update_load()
        self.check_timeouts()
        local_state = self.local_node_state()
        local_state.last_heartbeat = time.time()
        targets = self.get_gossip_targets()
        all_nodes = [n.to_dict() for n in self._cluster.nodes.values()]

        for target in targets:
            try:
                resp = await self._http.post(
                    f"{target.url}/v1/mesh/gossip",
                    json={"nodes": all_nodes},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    incoming = [NodeState.from_dict(n) for n in data.get("nodes", [])]
                    self._cluster.merge(incoming)
            except Exception as e:
                logger.debug("Gossip to %s failed: %s", target.name, e)

    async def heartbeat_once(self) -> None:
        self.update_load()
        local = self.local_node_state()
        local.last_heartbeat = time.time()
        targets = self.get_gossip_targets()
        for target in targets:
            try:
                await self._http.post(
                    f"{target.url}/v1/mesh/heartbeat",
                    json=local.to_dict(),
                )
            except Exception:
                pass

    async def close(self) -> None:
        await self._http.aclose()
