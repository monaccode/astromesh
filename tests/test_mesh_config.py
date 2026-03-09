"""Tests for MeshConfig."""

from astromesh.mesh.config import MeshConfig


def test_mesh_config_defaults():
    cfg = MeshConfig()
    assert cfg.enabled is False
    assert cfg.node_name == ""
    assert cfg.bind == "0.0.0.0:8000"
    assert cfg.seeds == []
    assert cfg.heartbeat_interval == 5
    assert cfg.gossip_interval == 2
    assert cfg.gossip_fanout == 3
    assert cfg.failure_timeout == 15
    assert cfg.dead_timeout == 30


def test_mesh_config_custom():
    cfg = MeshConfig(
        enabled=True,
        node_name="node-1",
        bind="127.0.0.1:9000",
        seeds=["10.0.0.1:8000", "10.0.0.2:8000"],
        heartbeat_interval=10,
        gossip_interval=4,
        gossip_fanout=5,
        failure_timeout=30,
        dead_timeout=60,
    )
    assert cfg.enabled is True
    assert cfg.node_name == "node-1"
    assert cfg.bind == "127.0.0.1:9000"
    assert cfg.seeds == ["10.0.0.1:8000", "10.0.0.2:8000"]
    assert cfg.heartbeat_interval == 10
    assert cfg.gossip_interval == 4
    assert cfg.gossip_fanout == 5
    assert cfg.failure_timeout == 30
    assert cfg.dead_timeout == 60


def test_mesh_config_from_dict():
    data = {"enabled": True, "node_name": "alpha", "seeds": ["peer:8000"]}
    cfg = MeshConfig.from_dict(data)
    assert cfg.enabled is True
    assert cfg.node_name == "alpha"
    assert cfg.seeds == ["peer:8000"]
    # Defaults for missing keys
    assert cfg.bind == "0.0.0.0:8000"
    assert cfg.heartbeat_interval == 5
    assert cfg.gossip_interval == 2
    assert cfg.gossip_fanout == 3
    assert cfg.failure_timeout == 15
    assert cfg.dead_timeout == 30


def test_mesh_config_from_dict_empty():
    cfg = MeshConfig.from_dict({})
    assert cfg.enabled is False
    assert cfg.node_name == ""
    assert cfg.bind == "0.0.0.0:8000"
    assert cfg.seeds == []
    assert cfg.heartbeat_interval == 5


def test_mesh_config_from_dict_none():
    cfg = MeshConfig.from_dict(None)
    assert cfg.enabled is False
    assert cfg.node_name == ""
    assert cfg.bind == "0.0.0.0:8000"
    assert cfg.seeds == []
    assert cfg.heartbeat_interval == 5
