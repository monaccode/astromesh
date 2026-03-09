"""Mesh state data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeLoad:
    """Resource usage metrics for a node."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    active_requests: int = 0

    def to_dict(self) -> dict:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "active_requests": self.active_requests,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NodeLoad:
        return cls(
            cpu_percent=data.get("cpu_percent", 0.0),
            memory_percent=data.get("memory_percent", 0.0),
            active_requests=data.get("active_requests", 0),
        )


@dataclass
class NodeState:
    """State of a single node in the mesh."""

    node_id: str
    name: str
    url: str
    services: list[str]
    agents: list[str]
    load: NodeLoad
    joined_at: float
    last_heartbeat: float
    leader: bool = False
    status: str = "alive"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "url": self.url,
            "services": self.services,
            "agents": self.agents,
            "load": self.load.to_dict(),
            "leader": self.leader,
            "joined_at": self.joined_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NodeState:
        return cls(
            node_id=data["node_id"],
            name=data["name"],
            url=data["url"],
            services=data.get("services", []),
            agents=data.get("agents", []),
            load=NodeLoad.from_dict(data.get("load", {})),
            leader=data.get("leader", False),
            joined_at=data["joined_at"],
            last_heartbeat=data["last_heartbeat"],
            status=data.get("status", "alive"),
        )


@dataclass
class ClusterState:
    """State of the entire mesh cluster."""

    nodes: dict[str, NodeState] = field(default_factory=dict)
    leader_id: str | None = None
    version: int = 0

    def add_node(self, node: NodeState) -> None:
        self.nodes[node.node_id] = node
        self.version += 1

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.version += 1

    def merge(self, incoming: list[NodeState]) -> None:
        for node in incoming:
            existing = self.nodes.get(node.node_id)
            if not existing or node.last_heartbeat > existing.last_heartbeat:
                self.nodes[node.node_id] = node
                self.version += 1

    def alive_nodes(self) -> list[NodeState]:
        return [n for n in self.nodes.values() if n.status == "alive"]

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "leader_id": self.leader_id,
            "version": self.version,
        }
