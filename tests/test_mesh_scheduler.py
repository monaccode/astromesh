"""Tests for astromesh.mesh.scheduler."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from astromesh.mesh.scheduler import Scheduler
from astromesh.mesh.state import ClusterState, NodeLoad, NodeState


def _make_node(
    node_id: str,
    name: str,
    services: list[str],
    agents: list[str],
    active_requests: int = 0,
    status: str = "alive",
) -> NodeState:
    return NodeState(
        node_id=node_id,
        name=name,
        url=f"http://{name}:8000",
        services=services,
        agents=agents,
        load=NodeLoad(active_requests=active_requests),
        joined_at=time.time(),
        last_heartbeat=time.time(),
        status=status,
    )


@pytest.fixture()
def cluster() -> ClusterState:
    cs = ClusterState()
    cs.add_node(_make_node("leader-node", "leader", services=["api"], agents=[]))
    cs.add_node(
        _make_node(
            "worker-1",
            "worker-1",
            services=["agents", "tools"],
            agents=["support-agent", "sales-agent"],
            active_requests=3,
        )
    )
    cs.add_node(
        _make_node(
            "worker-2",
            "worker-2",
            services=["agents", "tools"],
            agents=["support-agent"],
            active_requests=7,
        )
    )
    cs.add_node(
        _make_node(
            "inference-1",
            "inference-1",
            services=["inference"],
            agents=[],
            active_requests=1,
        )
    )
    return cs


@pytest.fixture()
def scheduler(cluster: ClusterState) -> Scheduler:
    mesh = MagicMock()
    mesh.cluster_state.return_value = cluster
    return Scheduler(mesh)


def test_placement_returns_all_workers(scheduler: Scheduler) -> None:
    result = scheduler.place_agent("support-agent")
    assert sorted(result) == ["worker-1", "worker-2"]


def test_placement_empty_when_no_workers(cluster: ClusterState) -> None:
    # Remove worker nodes, keep only leader and inference
    cluster.remove_node("worker-1")
    cluster.remove_node("worker-2")
    mesh = MagicMock()
    mesh.cluster_state.return_value = cluster
    sched = Scheduler(mesh)
    assert sched.place_agent("support-agent") == []


def test_route_request_least_connections(scheduler: Scheduler) -> None:
    result = scheduler.route_request("support-agent")
    assert result == "worker-1"  # 3 < 7


def test_route_request_agent_on_single_node(scheduler: Scheduler) -> None:
    result = scheduler.route_request("sales-agent")
    assert result == "worker-1"


def test_route_request_agent_not_found(scheduler: Scheduler) -> None:
    result = scheduler.route_request("nonexistent-agent")
    assert result is None


def test_placement_table(scheduler: Scheduler) -> None:
    table = scheduler.placement_table()
    assert sorted(table["support-agent"]) == ["worker-1", "worker-2"]
    assert table["sales-agent"] == ["worker-1"]
    assert "nonexistent-agent" not in table


def test_route_ignores_dead_nodes(cluster: ClusterState) -> None:
    cluster.nodes["worker-1"].status = "dead"
    mesh = MagicMock()
    mesh.cluster_state.return_value = cluster
    sched = Scheduler(mesh)
    result = sched.route_request("support-agent")
    assert result == "worker-2"
