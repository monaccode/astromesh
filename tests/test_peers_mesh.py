"""Tests for PeerClient.from_mesh() bridge."""

from __future__ import annotations

import time

import pytest

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.state import NodeLoad, NodeState
from astromesh.runtime.peers import PeerClient
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def service_manager():
    return ServiceManager({"api": True, "agents": True, "tools": True})


@pytest.fixture
def mesh(service_manager):
    config = MeshConfig(
        enabled=True,
        node_name="local-node",
        bind="0.0.0.0:8000",
        seeds=[],
    )
    mgr = MeshManager(config, service_manager)

    worker = NodeState(
        node_id="worker-1-id",
        name="worker-1",
        url="http://worker-1:8000",
        services=["agents", "tools"],
        agents=["assistant"],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    inference = NodeState(
        node_id="inference-1-id",
        name="inference-1",
        url="http://inference-1:8000",
        services=["inference"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    mgr.update_node(worker.node_id, worker)
    mgr.update_node(inference.node_id, inference)
    return mgr


def test_from_mesh_creates_client(mesh):
    client = PeerClient.from_mesh(mesh)
    assert isinstance(client, PeerClient)


def test_from_mesh_finds_peers(mesh):
    client = PeerClient.from_mesh(mesh)
    agents_peers = client.find_peers("agents")
    assert len(agents_peers) == 1
    assert agents_peers[0]["name"] == "worker-1"


def test_from_mesh_finds_inference(mesh):
    client = PeerClient.from_mesh(mesh)
    inference_peers = client.find_peers("inference")
    assert len(inference_peers) == 1
    assert inference_peers[0]["name"] == "inference-1"


def test_from_mesh_excludes_self(mesh):
    client = PeerClient.from_mesh(mesh)
    peers = client.list_peers()
    peer_names = [p["name"] for p in peers]
    assert "local-node" not in peer_names


def test_from_mesh_excludes_dead(mesh):
    mesh.cluster_state().nodes["worker-1-id"].status = "dead"
    client = PeerClient.from_mesh(mesh)
    agents_peers = client.find_peers("agents")
    assert len(agents_peers) == 0


def test_from_mesh_to_dict(mesh):
    client = PeerClient.from_mesh(mesh)
    result = client.to_dict()
    assert len(result) == 2
    names = {p["name"] for p in result}
    assert names == {"worker-1", "inference-1"}


def test_from_mesh_updates_dynamically(mesh):
    client1 = PeerClient.from_mesh(mesh)
    assert len(client1.find_peers("inference")) == 1

    new_inference = NodeState(
        node_id="inference-2-id",
        name="inference-2",
        url="http://inference-2:8000",
        services=["inference"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    mesh.update_node(new_inference.node_id, new_inference)

    client2 = PeerClient.from_mesh(mesh)
    assert len(client2.find_peers("inference")) == 2
