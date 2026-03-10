"""Tests for mesh API endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from astromesh.api.main import app
from astromesh.api.routes import mesh as mesh_routes
from astromesh.mesh.config import MeshConfig
from astromesh.mesh.leader import LeaderElector
from astromesh.mesh.manager import MeshManager
from astromesh.runtime.services import ServiceManager


def _make_node(node_id: str = "node-2", name: str = "peer") -> dict:
    return {
        "node_id": node_id,
        "name": name,
        "url": "http://127.0.0.1:9000",
        "services": ["api"],
        "agents": [],
        "load": {"cpu_percent": 10.0, "memory_percent": 20.0, "active_requests": 0},
        "leader": False,
        "joined_at": time.time(),
        "last_heartbeat": time.time(),
        "status": "alive",
    }


@pytest.fixture()
def mesh_manager():
    config = MeshConfig(enabled=True, node_name="test-node", bind="127.0.0.1:8000")
    svc = ServiceManager({"api": True})
    return MeshManager(config, svc)


@pytest.fixture()
def elector(mesh_manager):
    return LeaderElector(mesh_manager)


@pytest.fixture()
def client(mesh_manager, elector):
    mesh_routes.set_mesh(mesh_manager, elector)
    yield TestClient(app)
    mesh_routes.set_mesh(None, None)


def test_mesh_state(client, mesh_manager):
    resp = client.get("/v1/mesh/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "leader_id" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["node_id"] == mesh_manager.node_id


def test_mesh_join(client, mesh_manager):
    node_data = _make_node()
    resp = client.post("/v1/mesh/join", json=node_data)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 2
    node_ids = [n["node_id"] for n in data["nodes"]]
    assert "node-2" in node_ids
    assert mesh_manager.node_id in node_ids


def test_mesh_leave(client, mesh_manager):
    # First join a node
    node_data = _make_node()
    client.post("/v1/mesh/join", json=node_data)
    assert len(mesh_manager.cluster_state().nodes) == 2

    # Then leave
    resp = client.post("/v1/mesh/leave", json={"node_id": "node-2"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert len(mesh_manager.cluster_state().nodes) == 1


def test_mesh_heartbeat(client, mesh_manager):
    node_data = _make_node()
    resp = client.post("/v1/mesh/heartbeat", json=node_data)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert "node-2" in mesh_manager.cluster_state().nodes


def test_mesh_gossip(client, mesh_manager):
    nodes = [_make_node("node-3", "gossip-peer")]
    resp = client.post("/v1/mesh/gossip", json={"nodes": nodes})
    assert resp.status_code == 200
    data = resp.json()
    returned_ids = [n["node_id"] for n in data["nodes"]]
    assert "node-3" in returned_ids
    assert mesh_manager.node_id in returned_ids


def test_mesh_election(client, mesh_manager):
    resp = client.post(
        "/v1/mesh/election",
        json={"candidate_id": mesh_manager.node_id, "node_id": mesh_manager.node_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "leader_id" in data
    assert data["leader_id"] == mesh_manager.node_id


def test_mesh_state_not_enabled():
    mesh_routes.set_mesh(None, None)
    with TestClient(app) as c:
        resp = c.get("/v1/mesh/state")
        assert resp.status_code == 503
        assert "Mesh not enabled" in resp.json()["detail"]
