"""Tests for MeshManager."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.state import ClusterState, NodeLoad, NodeState
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def service_manager():
    return ServiceManager({"api": True, "agents": True, "tools": True})


@pytest.fixture
def mesh_config():
    return MeshConfig(
        enabled=True,
        node_name="test-node",
        bind="0.0.0.0:8000",
        seeds=["http://seed:8000"],
    )


@pytest.fixture
def mesh_config_no_seeds():
    return MeshConfig(
        enabled=True,
        node_name="test-node",
        bind="0.0.0.0:8000",
        seeds=[],
    )


@pytest.fixture
def manager(mesh_config, service_manager):
    return MeshManager(mesh_config, service_manager)


def test_manager_init(manager):
    assert manager.node_id is not None
    assert manager.node_id in manager.cluster_state().nodes


def test_manager_local_node_state(manager, service_manager):
    state = manager.local_node_state()
    assert state.name == "test-node"
    assert state.services == service_manager.enabled_services()


def test_manager_cluster_state(manager):
    cluster = manager.cluster_state()
    assert isinstance(cluster, ClusterState)
    assert len(cluster.nodes) == 1


def test_manager_is_alive(manager):
    assert manager.is_alive(manager.node_id) is True
    assert manager.is_alive("nonexistent-node") is False


def test_manager_update_node(manager):
    remote = NodeState(
        node_id="remote-1",
        name="remote-node",
        url="http://remote:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    manager.update_node("remote-1", remote)
    assert "remote-1" in manager.cluster_state().nodes


def test_manager_check_timeouts(manager):
    old_heartbeat = time.time() - 20  # > failure_timeout (15)
    remote = NodeState(
        node_id="remote-1",
        name="remote-node",
        url="http://remote:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=old_heartbeat,
    )
    manager.update_node("remote-1", remote)
    changed = manager.check_timeouts()
    assert "remote-1" in changed
    assert manager.cluster_state().nodes["remote-1"].status == "suspect"


def test_manager_check_timeouts_dead(manager):
    old_heartbeat = time.time() - 60  # > dead_timeout (30)
    remote = NodeState(
        node_id="remote-1",
        name="remote-node",
        url="http://remote:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=old_heartbeat,
    )
    manager.update_node("remote-1", remote)
    changed = manager.check_timeouts()
    assert "remote-1" in changed
    assert manager.cluster_state().nodes["remote-1"].status == "dead"


def test_manager_get_gossip_targets(manager):
    for i in range(5):
        remote = NodeState(
            node_id=f"remote-{i}",
            name=f"remote-{i}",
            url=f"http://remote-{i}:8000",
            services=["api"],
            agents=[],
            load=NodeLoad(),
            joined_at=time.time(),
            last_heartbeat=time.time(),
        )
        manager.update_node(f"remote-{i}", remote)

    targets = manager.get_gossip_targets()
    assert len(targets) == 3  # gossip_fanout default
    for t in targets:
        assert t.node_id != manager.node_id


def test_manager_get_gossip_targets_fewer_than_fanout(manager):
    remote = NodeState(
        node_id="remote-0",
        name="remote-0",
        url="http://remote-0:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    manager.update_node("remote-0", remote)
    targets = manager.get_gossip_targets()
    assert len(targets) == 1


@pytest.mark.asyncio
async def test_manager_join_success(manager):
    seed_node = NodeState(
        node_id="seed-node",
        name="seed",
        url="http://seed:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "nodes": [seed_node.to_dict()],
        "leader_id": "seed-node",
    }

    manager._http.post = AsyncMock(return_value=mock_response)
    await manager.join()

    assert "seed-node" in manager.cluster_state().nodes
    assert manager.cluster_state().leader_id == "seed-node"


@pytest.mark.asyncio
async def test_manager_join_no_seeds(mesh_config_no_seeds, service_manager):
    mgr = MeshManager(mesh_config_no_seeds, service_manager)
    await mgr.join()
    assert len(mgr.cluster_state().nodes) == 1


@pytest.mark.asyncio
async def test_manager_leave(manager):
    manager._http.post = AsyncMock()
    await manager.leave()
    assert manager._left is True


@patch("astromesh.mesh.manager.psutil")
def test_manager_update_load(mock_psutil, manager):
    mock_psutil.cpu_percent.return_value = 42.0
    mock_mem = MagicMock()
    mock_mem.percent = 65.0
    mock_psutil.virtual_memory.return_value = mock_mem

    manager.update_load(active_requests=3)

    load = manager.local_node_state().load
    assert load.cpu_percent == 42.0
    assert load.memory_percent == 65.0
    assert load.active_requests == 3
