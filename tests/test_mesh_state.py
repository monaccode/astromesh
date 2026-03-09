"""Tests for astromesh.mesh.state data models."""

from astromesh.mesh.state import ClusterState, NodeLoad, NodeState


def _make_node(
    node_id: str = "node-1",
    name: str = "alpha",
    url: str = "http://localhost:8000",
    last_heartbeat: float = 1000.0,
    **kwargs,
) -> NodeState:
    return NodeState(
        node_id=node_id,
        name=name,
        url=url,
        services=kwargs.get("services", ["llm"]),
        agents=kwargs.get("agents", ["assistant"]),
        load=kwargs.get("load", NodeLoad()),
        joined_at=kwargs.get("joined_at", 900.0),
        last_heartbeat=last_heartbeat,
        **{k: v for k, v in kwargs.items() if k not in ("services", "agents", "load", "joined_at")},
    )


# ── NodeLoad ────────────────────────────────────────────────────────────────


def test_node_load_defaults():
    load = NodeLoad()
    assert load.cpu_percent == 0.0
    assert load.memory_percent == 0.0
    assert load.active_requests == 0


def test_node_load_custom():
    load = NodeLoad(cpu_percent=55.5, memory_percent=72.3, active_requests=4)
    d = load.to_dict()
    assert d == {"cpu_percent": 55.5, "memory_percent": 72.3, "active_requests": 4}
    restored = NodeLoad.from_dict(d)
    assert restored == load


# ── NodeState ───────────────────────────────────────────────────────────────


def test_node_state_creation():
    node = _make_node()
    assert node.leader is False
    assert node.status == "alive"


def test_node_state_to_dict():
    node = _make_node(leader=True, status="suspect")
    d = node.to_dict()
    assert d["node_id"] == "node-1"
    assert d["leader"] is True
    assert d["status"] == "suspect"
    assert "cpu_percent" in d["load"]


def test_node_state_from_dict():
    original = _make_node()
    d = original.to_dict()
    restored = NodeState.from_dict(d)
    assert restored.node_id == original.node_id
    assert restored.load == original.load
    assert restored.status == "alive"


# ── ClusterState ────────────────────────────────────────────────────────────


def test_cluster_state_empty():
    cs = ClusterState()
    assert cs.nodes == {}
    assert cs.leader_id is None
    assert cs.version == 0


def test_cluster_state_add_node():
    cs = ClusterState()
    cs.add_node(_make_node())
    assert len(cs.nodes) == 1
    assert cs.version == 1


def test_cluster_state_remove_node():
    cs = ClusterState()
    cs.add_node(_make_node())
    cs.remove_node("node-1")
    assert len(cs.nodes) == 0
    assert cs.version == 2


def test_cluster_state_merge_keeps_latest():
    cs = ClusterState()
    cs.add_node(_make_node(last_heartbeat=1000.0))

    newer = _make_node(last_heartbeat=2000.0)
    cs.merge([newer])

    assert cs.nodes["node-1"].last_heartbeat == 2000.0


def test_cluster_state_merge_adds_unknown():
    cs = ClusterState()
    cs.add_node(_make_node(node_id="node-1"))

    unknown = _make_node(node_id="node-2", name="beta")
    cs.merge([unknown])

    assert "node-2" in cs.nodes
    assert len(cs.nodes) == 2


def test_cluster_state_alive_nodes():
    cs = ClusterState()
    cs.add_node(_make_node(node_id="a1"))
    cs.add_node(_make_node(node_id="a2", status="dead"))
    cs.add_node(_make_node(node_id="a3"))

    alive = cs.alive_nodes()
    assert len(alive) == 2
    assert all(n.status == "alive" for n in alive)


def test_cluster_state_to_dict():
    cs = ClusterState()
    cs.add_node(_make_node())
    cs.leader_id = "node-1"
    d = cs.to_dict()
    assert len(d["nodes"]) == 1
    assert d["leader_id"] == "node-1"
    assert d["version"] == 1
