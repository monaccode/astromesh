"""Integration tests for the full mesh stack."""

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from astromesh.api.main import app
from astromesh.api.routes import mesh as mesh_routes
from astromesh.api.routes import system
from astromesh.mesh.config import MeshConfig
from astromesh.mesh.leader import LeaderElector
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.scheduler import Scheduler
from astromesh.runtime.peers import PeerClient
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def three_node_mesh():
    """Create a 3-node mesh: gateway, worker, inference."""
    gw_config = MeshConfig(enabled=True, node_name="gateway")
    gw_sm = ServiceManager({"api": True, "channels": True, "observability": True,
                            "agents": False, "inference": False, "memory": False,
                            "tools": False, "rag": False})
    gw_mesh = MeshManager(gw_config, gw_sm)

    wk_config = MeshConfig(enabled=True, node_name="worker")
    wk_sm = ServiceManager({"api": True, "agents": True, "tools": True, "memory": True,
                            "rag": True, "observability": True,
                            "inference": False, "channels": False})
    wk_mesh = MeshManager(wk_config, wk_sm)

    inf_config = MeshConfig(enabled=True, node_name="inference")
    inf_sm = ServiceManager({"api": True, "inference": True, "observability": True,
                             "agents": False, "tools": False, "memory": False,
                             "channels": False, "rag": False})
    inf_mesh = MeshManager(inf_config, inf_sm)

    # Worker has agents loaded
    wk_mesh.update_agents(["support-agent", "sales-agent"])

    # Cross-register all nodes
    gw_state = gw_mesh.local_node_state()
    wk_state = wk_mesh.local_node_state()
    inf_state = inf_mesh.local_node_state()

    for mesh in [gw_mesh, wk_mesh, inf_mesh]:
        for state in [gw_state, wk_state, inf_state]:
            if state.node_id != mesh.node_id:
                mesh.update_node(state.node_id, state)

    return gw_mesh, wk_mesh, inf_mesh


def test_three_node_cluster_state(three_node_mesh):
    gw, wk, inf = three_node_mesh
    assert len(gw.cluster_state().nodes) == 3
    assert len(wk.cluster_state().nodes) == 3
    assert len(inf.cluster_state().nodes) == 3


def test_leader_election_across_cluster(three_node_mesh):
    gw, wk, inf = three_node_mesh
    elector = LeaderElector(gw)
    elector.elect()
    assert elector.current_leader() is not None
    leader_id = elector.current_leader()
    assert leader_id in [gw.node_id, wk.node_id, inf.node_id]


def test_scheduler_routes_to_worker(three_node_mesh):
    gw, wk, inf = three_node_mesh
    scheduler = Scheduler(gw)
    node_id = scheduler.route_request("support-agent")
    assert node_id == wk.node_id


def test_scheduler_placement_only_workers(three_node_mesh):
    gw, wk, inf = three_node_mesh
    scheduler = Scheduler(gw)
    nodes = scheduler.place_agent("new-agent")
    assert wk.node_id in nodes
    assert gw.node_id not in nodes
    assert inf.node_id not in nodes


def test_peer_client_from_mesh_integration(three_node_mesh):
    gw, wk, inf = three_node_mesh
    client = PeerClient.from_mesh(gw)
    assert len(client.list_peers()) == 2
    assert len(client.find_peers("agents")) == 1
    assert len(client.find_peers("inference")) == 1


def test_node_failure_detection(three_node_mesh):
    gw, wk, inf = three_node_mesh
    wk_id = wk.node_id
    gw._cluster.nodes[wk_id].last_heartbeat = time.time() - 20
    gw._config.failure_timeout = 15
    gw.check_timeouts()
    assert gw._cluster.nodes[wk_id].status == "suspect"


def test_node_failure_triggers_election(three_node_mesh):
    gw, wk, inf = three_node_mesh
    elector = LeaderElector(gw)
    elector.elect()
    leader_before = elector.current_leader()

    # Mark the current leader as dead so on_node_failed triggers re-election
    gw._cluster.nodes[leader_before].status = "dead"
    elector.on_node_failed(leader_before)

    new_leader = elector.current_leader()
    assert new_leader is not None
    # New leader must be different since the old leader is dead (filtered by alive_nodes)
    assert new_leader != leader_before


def test_gossip_merge_propagates(three_node_mesh):
    gw, wk, inf = three_node_mesh
    wk._cluster.nodes[wk.node_id].load.active_requests = 42
    wk._cluster.nodes[wk.node_id].last_heartbeat = time.time()

    incoming = [wk._cluster.nodes[wk.node_id]]
    gw._cluster.merge(incoming)
    assert gw._cluster.nodes[wk.node_id].load.active_requests == 42


def test_mesh_api_shows_cluster(three_node_mesh):
    gw, wk, inf = three_node_mesh
    elector = LeaderElector(gw)
    elector.elect()
    mesh_routes.set_mesh(gw, elector)
    client = TestClient(app)
    resp = client.get("/v1/mesh/state")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 3
    assert data["leader_id"] is not None


def test_system_status_includes_mesh_info():
    config = MeshConfig(enabled=True, node_name="test")
    sm = ServiceManager({"api": True})
    mesh = MeshManager(config, sm)
    elector = LeaderElector(mesh)
    elector.elect()

    runtime = MagicMock()
    runtime.list_agents.return_value = []
    runtime.service_manager = sm
    runtime.peer_client = PeerClient.from_mesh(mesh)
    runtime.mesh_manager = mesh
    runtime._agents = {}

    with TestClient(app) as client:
        system.set_runtime(runtime)
        try:
            resp = client.get("/v1/system/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("mesh") is not None
            assert data["mesh"]["enabled"] is True
            assert data["mesh"]["cluster_size"] == 1
        finally:
            system.set_runtime(None)
