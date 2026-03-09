"""Mesh configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MeshConfig:
    """Configuration for mesh networking."""

    enabled: bool = False
    node_name: str = ""
    bind: str = "0.0.0.0:8000"
    seeds: list[str] = field(default_factory=list)
    heartbeat_interval: int = 5
    gossip_interval: int = 2
    gossip_fanout: int = 3
    failure_timeout: int = 15
    dead_timeout: int = 30

    @classmethod
    def from_dict(cls, data: dict | None) -> MeshConfig:
        if not data:
            return cls()
        return cls(
            enabled=data.get("enabled", False),
            node_name=data.get("node_name", ""),
            bind=data.get("bind", "0.0.0.0:8000"),
            seeds=data.get("seeds", []),
            heartbeat_interval=data.get("heartbeat_interval", 5),
            gossip_interval=data.get("gossip_interval", 2),
            gossip_fanout=data.get("gossip_fanout", 3),
            failure_timeout=data.get("failure_timeout", 15),
            dead_timeout=data.get("dead_timeout", 30),
        )
