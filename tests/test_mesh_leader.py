"""Tests for astromesh.mesh.leader — bully algorithm leader election."""

import time

import pytest

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.leader import LeaderElector
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.state import NodeLoad, NodeState
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def mesh():
    config = MeshConfig(enabled=True, node_name="test-node")
    sm = ServiceManager({"api": True, "agents": True})
    return MeshManager(config, sm)


@pytest.fixture
def elector(mesh):
    return LeaderElector(mesh)


def _make_node(
    node_id: str,
    name: str = "peer",
    status: str = "alive",
) -> NodeState:
    return NodeState(
        node_id=node_id,
        name=name,
        url="http://localhost:9000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
        status=status,
    )


def test_elector_init(elector):
    assert elector.current_leader() is None
    assert elector.is_leader() is False


def test_elector_elect_self_when_alone(mesh, elector):
    leader_id = elector.elect()
    assert leader_id == mesh.node_id
    assert elector.is_leader() is True
    assert elector.current_leader() == mesh.node_id


def test_elector_highest_id_wins(mesh, elector):
    high_node = _make_node(node_id="zzz-highest", name="high-peer")
    mesh.cluster_state().add_node(high_node)

    leader_id = elector.elect()
    assert leader_id == "zzz-highest"
    assert elector.is_leader() is False
    assert mesh.cluster_state().leader_id == "zzz-highest"
    assert mesh.cluster_state().nodes["zzz-highest"].leader is True


def test_elector_ignores_dead_nodes(mesh, elector):
    dead_node = _make_node(node_id="zzz-dead", name="dead-peer", status="dead")
    mesh.cluster_state().add_node(dead_node)

    leader_id = elector.elect()
    assert leader_id == mesh.node_id
    assert elector.is_leader() is True
    assert mesh.cluster_state().nodes["zzz-dead"].leader is False


def test_elector_on_node_failed_triggers_election(mesh, elector):
    high_node = _make_node(node_id="zzz-highest", name="high-peer")
    mesh.cluster_state().add_node(high_node)
    elector.elect()
    assert elector.current_leader() == "zzz-highest"

    # Simulate failure: mark node as dead
    mesh.cluster_state().nodes["zzz-highest"].status = "dead"
    elector.on_node_failed("zzz-highest")

    # New leader should be the local node (only alive node left)
    assert elector.current_leader() == mesh.node_id
    assert elector.is_leader() is True


def test_elector_on_node_joined_higher(mesh, elector):
    elector.elect()
    assert elector.is_leader() is True

    # A node with higher ID joins
    high_node = _make_node(node_id="zzz-highest", name="high-peer")
    mesh.cluster_state().add_node(high_node)
    elector.on_node_joined("zzz-highest")

    assert elector.current_leader() == "zzz-highest"
    assert elector.is_leader() is False
