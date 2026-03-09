# Astromesh Mesh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add gossip-based mesh networking to Astromesh so nodes dynamically discover each other, elect a leader, and intelligently schedule agent placement and request routing.

**Architecture:** HTTP-based gossip protocol over existing FastAPI. Each node runs a MeshManager that propagates cluster state via periodic gossip rounds. A lightweight leader (bully algorithm) coordinates agent placement and request routing. PeerClient is extended with `from_mesh()` to bridge mesh discovery into existing forwarding infrastructure.

**Tech Stack:** Python 3.12, FastAPI, httpx, psutil, pydantic, pytest

---

## Parallelization Waves

Tasks are grouped into waves of independent work that can be executed in parallel:

- **Wave 1 (foundation):** Tasks 1, 2, 3 — data models, MeshConfig, psutil dependency
- **Wave 2 (core mesh):** Tasks 4, 5, 6 — MeshManager, LeaderElector, Scheduler
- **Wave 3 (integration):** Tasks 7, 8, 9 — Mesh API routes, PeerClient.from_mesh, daemon wiring
- **Wave 4 (user-facing):** Tasks 10, 11, 12 — CLI commands, config profiles, Docker Compose
- **Wave 5 (system test):** Task 13 — integration tests

---

### Task 1: Mesh State Data Models

**Files:**
- Create: `astromesh/mesh/__init__.py`
- Create: `astromesh/mesh/state.py`
- Test: `tests/test_mesh_state.py`

**Step 1: Write the failing tests**

```python
"""Tests for mesh state data models."""

import time

from astromesh.mesh.state import ClusterState, NodeLoad, NodeState


def test_node_load_defaults():
    load = NodeLoad()
    assert load.cpu_percent == 0.0
    assert load.memory_percent == 0.0
    assert load.active_requests == 0


def test_node_load_custom():
    load = NodeLoad(cpu_percent=45.2, memory_percent=60.1, active_requests=5)
    assert load.cpu_percent == 45.2
    assert load.active_requests == 5


def test_node_state_creation():
    state = NodeState(
        node_id="abc-123",
        name="worker-1",
        url="http://worker:8000",
        services=["agents", "tools"],
        agents=["support-agent"],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    assert state.node_id == "abc-123"
    assert state.name == "worker-1"
    assert state.leader is False
    assert state.status == "alive"


def test_node_state_to_dict():
    now = time.time()
    state = NodeState(
        node_id="abc-123",
        name="worker-1",
        url="http://worker:8000",
        services=["agents"],
        agents=[],
        load=NodeLoad(cpu_percent=10.0, memory_percent=20.0, active_requests=1),
        joined_at=now,
        last_heartbeat=now,
    )
    d = state.to_dict()
    assert d["node_id"] == "abc-123"
    assert d["load"]["cpu_percent"] == 10.0
    assert d["status"] == "alive"


def test_node_state_from_dict():
    now = time.time()
    d = {
        "node_id": "abc-123",
        "name": "worker-1",
        "url": "http://worker:8000",
        "services": ["agents"],
        "agents": [],
        "load": {"cpu_percent": 10.0, "memory_percent": 20.0, "active_requests": 1},
        "leader": False,
        "joined_at": now,
        "last_heartbeat": now,
        "status": "alive",
    }
    state = NodeState.from_dict(d)
    assert state.node_id == "abc-123"
    assert state.load.cpu_percent == 10.0


def test_cluster_state_empty():
    cluster = ClusterState()
    assert cluster.nodes == {}
    assert cluster.leader_id is None
    assert cluster.version == 0


def test_cluster_state_add_node():
    cluster = ClusterState()
    node = NodeState(
        node_id="abc-123",
        name="worker-1",
        url="http://worker:8000",
        services=["agents"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    cluster.add_node(node)
    assert "abc-123" in cluster.nodes
    assert cluster.version == 1


def test_cluster_state_remove_node():
    cluster = ClusterState()
    node = NodeState(
        node_id="abc-123",
        name="worker-1",
        url="http://worker:8000",
        services=["agents"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    cluster.add_node(node)
    cluster.remove_node("abc-123")
    assert "abc-123" not in cluster.nodes
    assert cluster.version == 2


def test_cluster_state_merge_keeps_latest():
    cluster = ClusterState()
    now = time.time()
    old_node = NodeState(
        node_id="abc-123",
        name="worker-1",
        url="http://worker:8000",
        services=["agents"],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now - 10,
    )
    new_node = NodeState(
        node_id="abc-123",
        name="worker-1",
        url="http://worker:8000",
        services=["agents", "tools"],
        agents=["support-agent"],
        load=NodeLoad(active_requests=3),
        joined_at=now,
        last_heartbeat=now,
    )
    cluster.add_node(old_node)
    cluster.merge([new_node])
    assert cluster.nodes["abc-123"].last_heartbeat == now
    assert cluster.nodes["abc-123"].load.active_requests == 3


def test_cluster_state_merge_adds_unknown():
    cluster = ClusterState()
    node = NodeState(
        node_id="new-node",
        name="inference-1",
        url="http://inference:8000",
        services=["inference"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    cluster.merge([node])
    assert "new-node" in cluster.nodes


def test_cluster_state_alive_nodes():
    cluster = ClusterState()
    now = time.time()
    alive = NodeState(
        node_id="alive-1",
        name="w1",
        url="http://w1:8000",
        services=[],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    dead = NodeState(
        node_id="dead-1",
        name="w2",
        url="http://w2:8000",
        services=[],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
        status="dead",
    )
    cluster.add_node(alive)
    cluster.add_node(dead)
    alive_nodes = cluster.alive_nodes()
    assert len(alive_nodes) == 1
    assert alive_nodes[0].node_id == "alive-1"


def test_cluster_state_to_dict():
    cluster = ClusterState()
    node = NodeState(
        node_id="abc-123",
        name="w1",
        url="http://w1:8000",
        services=["agents"],
        agents=[],
        load=NodeLoad(),
        joined_at=time.time(),
        last_heartbeat=time.time(),
    )
    cluster.add_node(node)
    cluster.leader_id = "abc-123"
    d = cluster.to_dict()
    assert d["leader_id"] == "abc-123"
    assert len(d["nodes"]) == 1
    assert d["version"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'astromesh.mesh'`

**Step 3: Write minimal implementation**

Create `astromesh/mesh/__init__.py`:
```python
"""Astromesh Mesh — distributed multi-node agent execution."""
```

Create `astromesh/mesh/state.py`:
```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_state.py -v`
Expected: All 12 tests PASS

**Step 5: Commit**

```bash
git add astromesh/mesh/__init__.py astromesh/mesh/state.py tests/test_mesh_state.py
git commit -m "feat(mesh): add NodeState, NodeLoad, and ClusterState data models"
```

---

### Task 2: MeshConfig Data Model

**Files:**
- Create: `astromesh/mesh/config.py`
- Test: `tests/test_mesh_config.py`

**Step 1: Write the failing tests**

```python
"""Tests for MeshConfig."""

from astromesh.mesh.config import MeshConfig


def test_mesh_config_defaults():
    config = MeshConfig()
    assert config.enabled is False
    assert config.node_name == ""
    assert config.bind == "0.0.0.0:8000"
    assert config.seeds == []
    assert config.heartbeat_interval == 5
    assert config.gossip_interval == 2
    assert config.gossip_fanout == 3
    assert config.failure_timeout == 15
    assert config.dead_timeout == 30


def test_mesh_config_custom():
    config = MeshConfig(
        enabled=True,
        node_name="gateway-1",
        bind="0.0.0.0:9000",
        seeds=["http://worker:8000"],
        heartbeat_interval=10,
    )
    assert config.enabled is True
    assert config.node_name == "gateway-1"
    assert config.seeds == ["http://worker:8000"]
    assert config.heartbeat_interval == 10


def test_mesh_config_from_dict():
    data = {
        "enabled": True,
        "node_name": "worker-1",
        "bind": "0.0.0.0:8000",
        "seeds": ["http://gateway:8000", "http://worker-2:8000"],
        "gossip_fanout": 5,
    }
    config = MeshConfig.from_dict(data)
    assert config.enabled is True
    assert config.node_name == "worker-1"
    assert len(config.seeds) == 2
    assert config.gossip_fanout == 5
    assert config.heartbeat_interval == 5  # default


def test_mesh_config_from_dict_empty():
    config = MeshConfig.from_dict({})
    assert config.enabled is False
    assert config.seeds == []


def test_mesh_config_from_dict_none():
    config = MeshConfig.from_dict(None)
    assert config.enabled is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `astromesh/mesh/config.py`:
```python
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_config.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add astromesh/mesh/config.py tests/test_mesh_config.py
git commit -m "feat(mesh): add MeshConfig data model with defaults and from_dict"
```

---

### Task 3: Add psutil Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add mesh optional dependency**

In `pyproject.toml`, add the `mesh` extra after the `daemon` line (line 34):

```toml
mesh = ["psutil>=5.9.0"]
```

And update the `all` extra to include `mesh`:

```toml
all = [
    "astromesh[redis,postgres,sqlite,chromadb,qdrant,faiss,embeddings,onnx,observability,mcp,cli,daemon,mesh]",
]
```

**Step 2: Install**

Run: `uv sync --extra mesh`
Expected: psutil installed successfully

**Step 3: Verify import**

Run: `uv run python -c "import psutil; print(psutil.cpu_percent())"`
Expected: A number (CPU percentage)

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add psutil dependency for mesh node load metrics"
```

---

### Task 4: MeshManager

**Files:**
- Create: `astromesh/mesh/manager.py`
- Test: `tests/test_mesh_manager.py`

**Step 1: Write the failing tests**

```python
"""Tests for MeshManager."""

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
        heartbeat_interval=5,
        gossip_interval=2,
        gossip_fanout=3,
        failure_timeout=15,
        dead_timeout=30,
    )


@pytest.fixture
def manager(mesh_config, service_manager):
    return MeshManager(mesh_config, service_manager)


def test_manager_init(manager):
    assert manager.node_id is not None
    assert len(manager.node_id) > 0
    state = manager.cluster_state()
    assert manager.node_id in state.nodes
    assert state.nodes[manager.node_id].name == "test-node"


def test_manager_local_node_state(manager):
    state = manager.local_node_state()
    assert state.name == "test-node"
    assert "api" in state.services
    assert "agents" in state.services
    assert state.status == "alive"


def test_manager_cluster_state(manager):
    cluster = manager.cluster_state()
    assert isinstance(cluster, ClusterState)
    assert len(cluster.nodes) == 1


def test_manager_is_alive(manager):
    assert manager.is_alive(manager.node_id) is True
    assert manager.is_alive("nonexistent") is False


def test_manager_update_node(manager):
    now = time.time()
    remote = NodeState(
        node_id="remote-1",
        name="remote",
        url="http://remote:8000",
        services=["inference"],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    manager.update_node("remote-1", remote)
    assert manager.is_alive("remote-1") is True
    cluster = manager.cluster_state()
    assert "remote-1" in cluster.nodes


def test_manager_check_timeouts(manager):
    now = time.time()
    old_node = NodeState(
        node_id="old-1",
        name="old",
        url="http://old:8000",
        services=[],
        agents=[],
        load=NodeLoad(),
        joined_at=now - 100,
        last_heartbeat=now - 20,  # > failure_timeout (15)
    )
    manager.update_node("old-1", old_node)
    manager.check_timeouts()
    assert manager._cluster.nodes["old-1"].status == "suspect"


def test_manager_check_timeouts_dead(manager):
    now = time.time()
    old_node = NodeState(
        node_id="old-1",
        name="old",
        url="http://old:8000",
        services=[],
        agents=[],
        load=NodeLoad(),
        joined_at=now - 100,
        last_heartbeat=now - 35,  # > dead_timeout (30)
    )
    manager.update_node("old-1", old_node)
    manager.check_timeouts()
    assert manager._cluster.nodes["old-1"].status == "dead"


def test_manager_get_gossip_targets(manager):
    now = time.time()
    for i in range(5):
        node = NodeState(
            node_id=f"node-{i}",
            name=f"n{i}",
            url=f"http://n{i}:8000",
            services=[],
            agents=[],
            load=NodeLoad(),
            joined_at=now,
            last_heartbeat=now,
        )
        manager.update_node(f"node-{i}", node)
    targets = manager.get_gossip_targets()
    assert len(targets) == 3  # gossip_fanout
    assert all(t.node_id != manager.node_id for t in targets)


def test_manager_get_gossip_targets_fewer_than_fanout(manager):
    now = time.time()
    node = NodeState(
        node_id="only-1",
        name="n1",
        url="http://n1:8000",
        services=[],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    manager.update_node("only-1", node)
    targets = manager.get_gossip_targets()
    assert len(targets) == 1


async def test_manager_join_success(manager):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "nodes": [
            {
                "node_id": "seed-1",
                "name": "seed",
                "url": "http://seed:8000",
                "services": ["api"],
                "agents": [],
                "load": {"cpu_percent": 0, "memory_percent": 0, "active_requests": 0},
                "leader": True,
                "joined_at": time.time(),
                "last_heartbeat": time.time(),
                "status": "alive",
            }
        ],
        "leader_id": "seed-1",
        "version": 1,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch.object(manager, "_http") as mock_http:
        mock_http.post = AsyncMock(return_value=mock_resp)
        await manager.join()

    assert "seed-1" in manager._cluster.nodes


async def test_manager_join_no_seeds():
    config = MeshConfig(enabled=True, node_name="lonely", seeds=[])
    sm = ServiceManager({"api": True})
    mgr = MeshManager(config, sm)
    await mgr.join()
    assert len(mgr._cluster.nodes) == 1  # only self


async def test_manager_leave(manager):
    now = time.time()
    remote = NodeState(
        node_id="remote-1",
        name="remote",
        url="http://remote:8000",
        services=[],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    manager.update_node("remote-1", remote)

    with patch.object(manager, "_http") as mock_http:
        mock_http.post = AsyncMock(return_value=MagicMock(status_code=200))
        await manager.leave()

    assert manager._left is True


def test_manager_update_load(manager):
    with patch("astromesh.mesh.manager.psutil") as mock_psutil:
        mock_psutil.cpu_percent.return_value = 55.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=70.0)
        manager.update_load(active_requests=3)
    local = manager._cluster.nodes[manager.node_id]
    assert local.load.cpu_percent == 55.0
    assert local.load.memory_percent == 70.0
    assert local.load.active_requests == 3
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `astromesh/mesh/manager.py`:
```python
"""MeshManager — gossip, heartbeats, and cluster state."""

from __future__ import annotations

import logging
import random
import time
import uuid

import httpx
import psutil

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.state import ClusterState, NodeLoad, NodeState
from astromesh.runtime.services import ServiceManager

logger = logging.getLogger("astromesh.mesh")


class MeshManager:
    """Manages gossip, heartbeats, and cluster state for this node."""

    def __init__(self, config: MeshConfig, service_manager: ServiceManager):
        self._config = config
        self._service_manager = service_manager
        self._cluster = ClusterState()
        self._http = httpx.AsyncClient(timeout=10.0)
        self._left = False

        self.node_id = str(uuid.uuid4())
        self._cluster.add_node(self._make_local_state())

    def _make_local_state(self) -> NodeState:
        return NodeState(
            node_id=self.node_id,
            name=self._config.node_name,
            url=f"http://{self._config.bind}",
            services=self._service_manager.enabled_services(),
            agents=[],
            load=NodeLoad(),
            joined_at=time.time(),
            last_heartbeat=time.time(),
        )

    def local_node_state(self) -> NodeState:
        return self._cluster.nodes[self.node_id]

    def cluster_state(self) -> ClusterState:
        return self._cluster

    def is_alive(self, node_id: str) -> bool:
        node = self._cluster.nodes.get(node_id)
        return node is not None and node.status == "alive"

    def update_node(self, node_id: str, state: NodeState) -> None:
        self._cluster.nodes[node_id] = state
        if node_id not in self._cluster.nodes or self._cluster.version == 0:
            self._cluster.version += 1
        else:
            self._cluster.version += 1

    def update_load(self, active_requests: int = 0) -> None:
        local = self._cluster.nodes[self.node_id]
        local.load = NodeLoad(
            cpu_percent=psutil.cpu_percent(),
            memory_percent=psutil.virtual_memory().percent,
            active_requests=active_requests,
        )
        local.last_heartbeat = time.time()

    def update_agents(self, agent_names: list[str]) -> None:
        self._cluster.nodes[self.node_id].agents = agent_names

    def check_timeouts(self) -> list[str]:
        now = time.time()
        changed = []
        for node_id, node in self._cluster.nodes.items():
            if node_id == self.node_id:
                continue
            elapsed = now - node.last_heartbeat
            if elapsed > self._config.dead_timeout and node.status != "dead":
                node.status = "dead"
                changed.append(node_id)
                logger.warning("Node %s (%s) is dead", node.name, node_id)
            elif elapsed > self._config.failure_timeout and node.status == "alive":
                node.status = "suspect"
                changed.append(node_id)
                logger.warning("Node %s (%s) is suspect", node.name, node_id)
        return changed

    def get_gossip_targets(self) -> list[NodeState]:
        others = [n for nid, n in self._cluster.nodes.items()
                  if nid != self.node_id and n.status != "dead"]
        count = min(self._config.gossip_fanout, len(others))
        return random.sample(others, count) if others else []

    async def join(self) -> None:
        if not self._config.seeds:
            logger.info("No seeds configured, starting as standalone node")
            return

        local_state = self.local_node_state()
        for seed_url in self._config.seeds:
            try:
                resp = await self._http.post(
                    f"{seed_url}/v1/mesh/join",
                    json=local_state.to_dict(),
                )
                resp.raise_for_status()
                data = resp.json()
                incoming = [NodeState.from_dict(n) for n in data.get("nodes", [])]
                self._cluster.merge(incoming)
                if data.get("leader_id"):
                    self._cluster.leader_id = data["leader_id"]
                logger.info("Joined mesh via seed %s, cluster size: %d",
                            seed_url, len(self._cluster.nodes))
                return
            except Exception as e:
                logger.warning("Failed to join via seed %s: %s", seed_url, e)
                continue

        logger.warning("Could not reach any seed node, starting as standalone")

    async def leave(self) -> None:
        self._left = True
        for node in self.get_gossip_targets():
            try:
                await self._http.post(
                    f"{node.url}/v1/mesh/leave",
                    json={"node_id": self.node_id},
                )
            except Exception:
                pass
        logger.info("Left mesh")

    async def gossip_once(self) -> None:
        self.update_load()
        self.check_timeouts()
        local_state = self.local_node_state()
        local_state.last_heartbeat = time.time()
        targets = self.get_gossip_targets()
        all_nodes = [n.to_dict() for n in self._cluster.nodes.values()]

        for target in targets:
            try:
                resp = await self._http.post(
                    f"{target.url}/v1/mesh/gossip",
                    json={"nodes": all_nodes},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    incoming = [NodeState.from_dict(n) for n in data.get("nodes", [])]
                    self._cluster.merge(incoming)
            except Exception as e:
                logger.debug("Gossip to %s failed: %s", target.name, e)

    async def heartbeat_once(self) -> None:
        self.update_load()
        local = self.local_node_state()
        local.last_heartbeat = time.time()
        targets = self.get_gossip_targets()
        for target in targets:
            try:
                await self._http.post(
                    f"{target.url}/v1/mesh/heartbeat",
                    json=local.to_dict(),
                )
            except Exception:
                pass

    async def close(self) -> None:
        await self._http.aclose()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_manager.py -v`
Expected: All 13 tests PASS

**Step 5: Commit**

```bash
git add astromesh/mesh/manager.py tests/test_mesh_manager.py
git commit -m "feat(mesh): add MeshManager with gossip, heartbeats, and failure detection"
```

---

### Task 5: LeaderElector

**Files:**
- Create: `astromesh/mesh/leader.py`
- Test: `tests/test_mesh_leader.py`

**Step 1: Write the failing tests**

```python
"""Tests for LeaderElector."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_elector_init(elector, mesh):
    assert elector.current_leader() is None
    assert elector.is_leader() is False


def test_elector_elect_self_when_alone(elector, mesh):
    elector.elect()
    assert elector.current_leader() == mesh.node_id
    assert elector.is_leader() is True
    assert mesh.cluster_state().leader_id == mesh.node_id
    assert mesh.local_node_state().leader is True


def test_elector_highest_id_wins(elector, mesh):
    now = time.time()
    # Add a node with a higher ID (zzz... > any UUID)
    higher = NodeState(
        node_id="zzz-highest",
        name="higher",
        url="http://higher:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    mesh.update_node("zzz-highest", higher)
    elector.elect()
    assert elector.current_leader() == "zzz-highest"
    assert elector.is_leader() is False


def test_elector_ignores_dead_nodes(elector, mesh):
    now = time.time()
    dead = NodeState(
        node_id="zzz-dead",
        name="dead",
        url="http://dead:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
        status="dead",
    )
    mesh.update_node("zzz-dead", dead)
    elector.elect()
    assert elector.current_leader() == mesh.node_id


def test_elector_on_node_failed_triggers_election(elector, mesh):
    now = time.time()
    leader = NodeState(
        node_id="zzz-leader",
        name="leader",
        url="http://leader:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    mesh.update_node("zzz-leader", leader)
    elector.elect()
    assert elector.current_leader() == "zzz-leader"

    # Leader dies
    mesh._cluster.nodes["zzz-leader"].status = "dead"
    elector.on_node_failed("zzz-leader")
    assert elector.current_leader() == mesh.node_id


def test_elector_on_node_joined_higher(elector, mesh):
    elector.elect()
    assert elector.is_leader() is True

    now = time.time()
    higher = NodeState(
        node_id="zzz-new",
        name="new",
        url="http://new:8000",
        services=["api"],
        agents=[],
        load=NodeLoad(),
        joined_at=now,
        last_heartbeat=now,
    )
    mesh.update_node("zzz-new", higher)
    elector.on_node_joined("zzz-new")
    assert elector.current_leader() == "zzz-new"
    assert elector.is_leader() is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_leader.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `astromesh/mesh/leader.py`:
```python
"""Leader election using bully algorithm."""

from __future__ import annotations

import logging

from astromesh.mesh.manager import MeshManager

logger = logging.getLogger("astromesh.mesh.leader")


class LeaderElector:
    """Bully algorithm leader election — highest node ID wins."""

    def __init__(self, mesh: MeshManager):
        self._mesh = mesh
        self._leader_id: str | None = None

    def current_leader(self) -> str | None:
        return self._leader_id

    def is_leader(self) -> bool:
        return self._leader_id == self._mesh.node_id

    def elect(self) -> str | None:
        alive = self._mesh.cluster_state().alive_nodes()
        if not alive:
            self._leader_id = None
            return None

        winner = max(alive, key=lambda n: n.node_id)
        self._leader_id = winner.node_id
        self._mesh.cluster_state().leader_id = winner.node_id

        # Update leader flag on all nodes
        for node in self._mesh.cluster_state().nodes.values():
            node.leader = node.node_id == winner.node_id

        logger.info("Leader elected: %s (%s)", winner.name, winner.node_id)
        return winner.node_id

    def on_node_joined(self, node_id: str) -> None:
        self.elect()

    def on_node_failed(self, node_id: str) -> None:
        if node_id == self._leader_id:
            logger.info("Leader %s failed, triggering election", node_id)
            self.elect()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_leader.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add astromesh/mesh/leader.py tests/test_mesh_leader.py
git commit -m "feat(mesh): add LeaderElector with bully algorithm"
```

---

### Task 6: Scheduler

**Files:**
- Create: `astromesh/mesh/scheduler.py`
- Test: `tests/test_mesh_scheduler.py`

**Step 1: Write the failing tests**

```python
"""Tests for Scheduler."""

import time

import pytest

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.scheduler import Scheduler
from astromesh.mesh.state import NodeLoad, NodeState
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def mesh():
    config = MeshConfig(enabled=True, node_name="leader-node")
    sm = ServiceManager({"api": True})
    mgr = MeshManager(config, sm)
    now = time.time()
    # Add worker nodes
    mgr.update_node("worker-1", NodeState(
        node_id="worker-1", name="w1", url="http://w1:8000",
        services=["agents", "tools"], agents=["support-agent", "sales-agent"],
        load=NodeLoad(active_requests=3), joined_at=now, last_heartbeat=now,
    ))
    mgr.update_node("worker-2", NodeState(
        node_id="worker-2", name="w2", url="http://w2:8000",
        services=["agents", "tools"], agents=["support-agent"],
        load=NodeLoad(active_requests=7), joined_at=now, last_heartbeat=now,
    ))
    mgr.update_node("inference-1", NodeState(
        node_id="inference-1", name="inf1", url="http://inf1:8000",
        services=["inference"], agents=[],
        load=NodeLoad(active_requests=1), joined_at=now, last_heartbeat=now,
    ))
    return mgr


@pytest.fixture
def scheduler(mesh):
    return Scheduler(mesh)


def test_placement_returns_all_workers(scheduler):
    nodes = scheduler.place_agent("new-agent")
    assert "worker-1" in nodes
    assert "worker-2" in nodes
    assert "inference-1" not in nodes


def test_placement_empty_when_no_workers(mesh):
    # Remove workers, keep only inference
    mesh._cluster.nodes = {
        k: v for k, v in mesh._cluster.nodes.items()
        if "agents" not in v.services
    }
    sched = Scheduler(mesh)
    assert sched.place_agent("new-agent") == []


def test_route_request_least_connections(scheduler):
    # worker-1 has 3 active, worker-2 has 7 — should route to worker-1
    node_id = scheduler.route_request("support-agent")
    assert node_id == "worker-1"


def test_route_request_agent_on_single_node(scheduler):
    # sales-agent only on worker-1
    node_id = scheduler.route_request("sales-agent")
    assert node_id == "worker-1"


def test_route_request_agent_not_found(scheduler):
    node_id = scheduler.route_request("nonexistent-agent")
    assert node_id is None


def test_placement_table(scheduler):
    table = scheduler.placement_table()
    assert "support-agent" in table
    assert "worker-1" in table["support-agent"]
    assert "worker-2" in table["support-agent"]
    assert "sales-agent" in table
    assert table["sales-agent"] == ["worker-1"]


def test_route_ignores_dead_nodes(mesh, scheduler):
    mesh._cluster.nodes["worker-1"].status = "dead"
    node_id = scheduler.route_request("support-agent")
    assert node_id == "worker-2"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `astromesh/mesh/scheduler.py`:
```python
"""Scheduler — agent placement and request routing."""

from __future__ import annotations

import logging

from astromesh.mesh.manager import MeshManager

logger = logging.getLogger("astromesh.mesh.scheduler")


class Scheduler:
    """Schedules agent placement and routes requests. Active on leader only."""

    def __init__(self, mesh: MeshManager):
        self._mesh = mesh

    def place_agent(self, agent_name: str) -> list[str]:
        """Return node IDs of all alive worker nodes with 'agents' service."""
        alive = self._mesh.cluster_state().alive_nodes()
        return [n.node_id for n in alive if "agents" in n.services]

    def route_request(self, agent_name: str) -> str | None:
        """Route to the alive node with the agent loaded and fewest active requests."""
        alive = self._mesh.cluster_state().alive_nodes()
        candidates = [n for n in alive if agent_name in n.agents]
        if not candidates:
            return None
        best = min(candidates, key=lambda n: n.load.active_requests)
        return best.node_id

    def placement_table(self) -> dict[str, list[str]]:
        """Return mapping of agent_name → [node_ids] for all loaded agents."""
        table: dict[str, list[str]] = {}
        alive = self._mesh.cluster_state().alive_nodes()
        for node in alive:
            for agent in node.agents:
                table.setdefault(agent, []).append(node.node_id)
        return table
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_scheduler.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add astromesh/mesh/scheduler.py tests/test_mesh_scheduler.py
git commit -m "feat(mesh): add Scheduler with least-loaded placement and least-connections routing"
```

---

### Task 7: Mesh API Routes

**Files:**
- Create: `astromesh/api/routes/mesh.py`
- Modify: `astromesh/api/main.py`
- Test: `tests/test_mesh_api.py`

**Step 1: Write the failing tests**

```python
"""Tests for mesh API endpoints."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from astromesh.api.main import app
from astromesh.api.routes import mesh as mesh_routes
from astromesh.mesh.config import MeshConfig
from astromesh.mesh.leader import LeaderElector
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.state import NodeLoad, NodeState
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def mesh_manager():
    config = MeshConfig(enabled=True, node_name="test-node")
    sm = ServiceManager({"api": True, "agents": True})
    return MeshManager(config, sm)


@pytest.fixture
def client(mesh_manager):
    elector = LeaderElector(mesh_manager)
    elector.elect()
    mesh_routes.set_mesh(mesh_manager, elector)
    return TestClient(app)


def test_mesh_state(client, mesh_manager):
    resp = client.get("/v1/mesh/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "leader_id" in data
    assert len(data["nodes"]) == 1


def test_mesh_join(client, mesh_manager):
    now = time.time()
    new_node = {
        "node_id": "new-1",
        "name": "new-node",
        "url": "http://new:8000",
        "services": ["inference"],
        "agents": [],
        "load": {"cpu_percent": 0, "memory_percent": 0, "active_requests": 0},
        "leader": False,
        "joined_at": now,
        "last_heartbeat": now,
        "status": "alive",
    }
    resp = client.post("/v1/mesh/join", json=new_node)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 2  # self + new node


def test_mesh_leave(client, mesh_manager):
    now = time.time()
    node = NodeState(
        node_id="leaving-1", name="leaving", url="http://leaving:8000",
        services=[], agents=[], load=NodeLoad(),
        joined_at=now, last_heartbeat=now,
    )
    mesh_manager.update_node("leaving-1", node)
    resp = client.post("/v1/mesh/leave", json={"node_id": "leaving-1"})
    assert resp.status_code == 200
    assert "leaving-1" not in mesh_manager._cluster.nodes


def test_mesh_heartbeat(client, mesh_manager):
    now = time.time()
    node = NodeState(
        node_id="hb-1", name="hb", url="http://hb:8000",
        services=["agents"], agents=[], load=NodeLoad(),
        joined_at=now, last_heartbeat=now,
    )
    mesh_manager.update_node("hb-1", node)
    updated = {
        "node_id": "hb-1", "name": "hb", "url": "http://hb:8000",
        "services": ["agents"], "agents": ["support-agent"],
        "load": {"cpu_percent": 50, "memory_percent": 60, "active_requests": 2},
        "leader": False, "joined_at": now, "last_heartbeat": time.time(),
        "status": "alive",
    }
    resp = client.post("/v1/mesh/heartbeat", json=updated)
    assert resp.status_code == 200
    assert mesh_manager._cluster.nodes["hb-1"].load.active_requests == 2


def test_mesh_gossip(client, mesh_manager):
    now = time.time()
    gossip_nodes = [
        {
            "node_id": "gossip-1", "name": "g1", "url": "http://g1:8000",
            "services": ["inference"], "agents": [],
            "load": {"cpu_percent": 0, "memory_percent": 0, "active_requests": 0},
            "leader": False, "joined_at": now, "last_heartbeat": now, "status": "alive",
        }
    ]
    resp = client.post("/v1/mesh/gossip", json={"nodes": gossip_nodes})
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "gossip-1" in mesh_manager._cluster.nodes


def test_mesh_election(client, mesh_manager):
    resp = client.post("/v1/mesh/election", json={
        "candidate_id": "candidate-1",
        "node_id": "some-node",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "leader_id" in data


def test_mesh_state_not_enabled():
    mesh_routes.set_mesh(None, None)
    client = TestClient(app)
    resp = client.get("/v1/mesh/state")
    assert resp.status_code == 503
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_api.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `astromesh/api/routes/mesh.py`:
```python
"""Mesh API endpoints for gossip, join/leave, and cluster state."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from astromesh.mesh.leader import LeaderElector
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.state import NodeState

router = APIRouter(prefix="/mesh", tags=["mesh"])

_mesh: MeshManager | None = None
_elector: LeaderElector | None = None


def set_mesh(mesh: MeshManager | None, elector: LeaderElector | None) -> None:
    global _mesh, _elector
    _mesh = mesh
    _elector = elector


def _require_mesh() -> MeshManager:
    if not _mesh:
        raise HTTPException(status_code=503, detail="Mesh not enabled on this node")
    return _mesh


class LeaveRequest(BaseModel):
    node_id: str


class GossipRequest(BaseModel):
    nodes: list[dict]


class ElectionRequest(BaseModel):
    candidate_id: str
    node_id: str


@router.get("/state")
async def mesh_state():
    mesh = _require_mesh()
    return mesh.cluster_state().to_dict()


@router.post("/join")
async def mesh_join(node_data: dict):
    mesh = _require_mesh()
    node = NodeState.from_dict(node_data)
    mesh.update_node(node.node_id, node)
    if _elector:
        _elector.on_node_joined(node.node_id)
    return mesh.cluster_state().to_dict()


@router.post("/leave")
async def mesh_leave(request: LeaveRequest):
    mesh = _require_mesh()
    mesh._cluster.remove_node(request.node_id)
    if _elector:
        _elector.on_node_failed(request.node_id)
    return {"status": "ok"}


@router.post("/heartbeat")
async def mesh_heartbeat(node_data: dict):
    mesh = _require_mesh()
    node = NodeState.from_dict(node_data)
    mesh.update_node(node.node_id, node)
    return {"status": "ok"}


@router.post("/gossip")
async def mesh_gossip(request: GossipRequest):
    mesh = _require_mesh()
    incoming = [NodeState.from_dict(n) for n in request.nodes]
    mesh._cluster.merge(incoming)
    # Respond with our view of the cluster
    all_nodes = [n.to_dict() for n in mesh._cluster.nodes.values()]
    return {"nodes": all_nodes}


@router.post("/election")
async def mesh_election(request: ElectionRequest):
    mesh = _require_mesh()
    if _elector:
        _elector.elect()
    return {"leader_id": mesh.cluster_state().leader_id}
```

Modify `astromesh/api/main.py` — add mesh router import and registration. Add after line 3:

```python
from astromesh.api.routes import agents, memory, tools, rag, whatsapp, system, mesh
```

And add after line 14 (`app.include_router(system.router, prefix="/v1")`):

```python
app.include_router(mesh.router, prefix="/v1")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_api.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add astromesh/api/routes/mesh.py astromesh/api/main.py tests/test_mesh_api.py
git commit -m "feat(mesh): add mesh API endpoints (join, leave, heartbeat, gossip, election, state)"
```

---

### Task 8: PeerClient.from_mesh() Bridge

**Files:**
- Modify: `astromesh/runtime/peers.py`
- Test: `tests/test_peers_mesh.py`

**Step 1: Write the failing tests**

```python
"""Tests for PeerClient.from_mesh() bridge."""

import time

import pytest

from astromesh.mesh.config import MeshConfig
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.state import NodeLoad, NodeState
from astromesh.runtime.peers import PeerClient
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def mesh():
    config = MeshConfig(enabled=True, node_name="local-node")
    sm = ServiceManager({"api": True, "agents": True})
    mgr = MeshManager(config, sm)
    now = time.time()
    mgr.update_node("worker-1", NodeState(
        node_id="worker-1", name="w1", url="http://w1:8000",
        services=["agents", "tools"], agents=["support-agent"],
        load=NodeLoad(active_requests=2), joined_at=now, last_heartbeat=now,
    ))
    mgr.update_node("inference-1", NodeState(
        node_id="inference-1", name="inf1", url="http://inf1:8000",
        services=["inference"], agents=[],
        load=NodeLoad(), joined_at=now, last_heartbeat=now,
    ))
    return mgr


def test_from_mesh_creates_client(mesh):
    client = PeerClient.from_mesh(mesh)
    assert client is not None


def test_from_mesh_finds_peers(mesh):
    client = PeerClient.from_mesh(mesh)
    agents_peers = client.find_peers("agents")
    assert len(agents_peers) == 1
    assert agents_peers[0]["name"] == "w1"


def test_from_mesh_finds_inference(mesh):
    client = PeerClient.from_mesh(mesh)
    inference_peers = client.find_peers("inference")
    assert len(inference_peers) == 1
    assert inference_peers[0]["name"] == "inf1"


def test_from_mesh_excludes_self(mesh):
    client = PeerClient.from_mesh(mesh)
    all_peers = client.list_peers()
    local_id = mesh.node_id
    assert not any(p["name"] == "local-node" for p in all_peers
                   if p.get("node_id") == local_id)


def test_from_mesh_excludes_dead(mesh):
    mesh._cluster.nodes["worker-1"].status = "dead"
    client = PeerClient.from_mesh(mesh)
    agents_peers = client.find_peers("agents")
    assert len(agents_peers) == 0


def test_from_mesh_to_dict(mesh):
    client = PeerClient.from_mesh(mesh)
    d = client.to_dict()
    assert len(d) == 2  # worker-1 + inference-1 (not self)
    names = {p["name"] for p in d}
    assert "w1" in names
    assert "inf1" in names


def test_from_mesh_updates_dynamically(mesh):
    client = PeerClient.from_mesh(mesh)
    # Initially 1 inference peer
    assert len(client.find_peers("inference")) == 1

    # Add another inference node to mesh
    now = time.time()
    mesh.update_node("inference-2", NodeState(
        node_id="inference-2", name="inf2", url="http://inf2:8000",
        services=["inference"], agents=[],
        load=NodeLoad(), joined_at=now, last_heartbeat=now,
    ))

    # Client should see the new peer (dynamic)
    client_refreshed = PeerClient.from_mesh(mesh)
    assert len(client_refreshed.find_peers("inference")) == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_peers_mesh.py -v`
Expected: FAIL with `AttributeError: type object 'PeerClient' has no attribute 'from_mesh'`

**Step 3: Write minimal implementation**

Add the following classmethod to `PeerClient` in `astromesh/runtime/peers.py`. Add after the `__init__` method (after line 17):

```python
    @classmethod
    def from_mesh(cls, mesh) -> "PeerClient":
        """Create a PeerClient backed by live mesh cluster state.

        Excludes the local node and dead nodes. Returns a snapshot;
        call again to get updated peers.
        """
        local_id = mesh.node_id
        peers = []
        for node in mesh.cluster_state().alive_nodes():
            if node.node_id == local_id:
                continue
            peers.append({
                "name": node.name,
                "url": node.url,
                "services": node.services,
                "node_id": node.node_id,
            })
        return cls(peers)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_peers_mesh.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add astromesh/runtime/peers.py tests/test_peers_mesh.py
git commit -m "feat(mesh): add PeerClient.from_mesh() to bridge mesh discovery into peer forwarding"
```

---

### Task 9: Daemon Wiring and Background Loops

**Files:**
- Modify: `daemon/astromeshd.py`
- Modify: `astromesh/api/routes/system.py`
- Test: `tests/test_daemon_mesh.py`

**Step 1: Write the failing tests**

```python
"""Tests for daemon mesh wiring."""

import pytest
import yaml

from daemon.astromeshd import DaemonConfig


def test_daemon_config_parses_mesh(tmp_path):
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text(yaml.dump({
        "apiVersion": "astromesh/v1",
        "kind": "RuntimeConfig",
        "metadata": {"name": "test"},
        "spec": {
            "api": {"host": "0.0.0.0", "port": 8000},
            "mesh": {
                "enabled": True,
                "node_name": "worker-1",
                "seeds": ["http://gateway:8000"],
                "heartbeat_interval": 10,
            },
        },
    }))
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.mesh["enabled"] is True
    assert config.mesh["node_name"] == "worker-1"
    assert config.mesh["seeds"] == ["http://gateway:8000"]


def test_daemon_config_no_mesh(tmp_path):
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text(yaml.dump({
        "apiVersion": "astromesh/v1",
        "kind": "RuntimeConfig",
        "metadata": {"name": "test"},
        "spec": {"api": {"host": "0.0.0.0", "port": 8000}},
    }))
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.mesh == {}


def test_daemon_config_mesh_disabled(tmp_path):
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text(yaml.dump({
        "apiVersion": "astromesh/v1",
        "kind": "RuntimeConfig",
        "metadata": {"name": "test"},
        "spec": {
            "api": {"host": "0.0.0.0", "port": 8000},
            "mesh": {"enabled": False},
        },
    }))
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.mesh["enabled"] is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daemon_mesh.py -v`
Expected: FAIL (DaemonConfig doesn't have `mesh` field yet)

**Step 3: Write minimal implementation**

Modify `daemon/astromeshd.py`:

1. Add `mesh` field to `DaemonConfig` (add after `peers` field, line 33):

```python
    mesh: dict = field(default_factory=dict)
```

2. In `DaemonConfig.from_config_dir()`, add mesh parsing (add in the `return cls(...)` call, after `peers=`):

```python
            mesh=spec.get("mesh", {}),
```

3. In `run_daemon()`, add mesh initialization. After the peer_client creation (after line 143) and before `mode = "system"` (line 152), add:

```python
    # Create mesh if enabled
    mesh_manager = None
    elector = None
    from astromesh.mesh.config import MeshConfig
    mesh_config = MeshConfig.from_dict(daemon_config.mesh)
    if mesh_config.enabled:
        from astromesh.mesh.manager import MeshManager
        from astromesh.mesh.leader import LeaderElector

        mesh_manager = MeshManager(mesh_config, service_manager)
        elector = LeaderElector(mesh_manager)

        # PeerClient from mesh instead of static config
        peer_client = PeerClient.from_mesh(mesh_manager)
        logger.info("Mesh enabled, node: %s", mesh_config.node_name)

        if daemon_config.peers:
            logger.warning("spec.peers ignored when mesh is enabled")
```

4. After `system.set_runtime(runtime)` (line 166), add mesh route wiring:

```python
    from astromesh.api.routes import mesh as mesh_routes
    mesh_routes.set_mesh(mesh_manager, elector)
```

5. After `await runtime.bootstrap()` and agent count logging, add mesh join and agent update:

```python
    if mesh_manager:
        mesh_manager.update_agents([a["name"] for a in runtime.list_agents()])
        await mesh_manager.join()
        elector.elect()
        logger.info("Mesh joined, cluster size: %d", len(mesh_manager.cluster_state().nodes))
```

6. In the `try/finally` block around `await server.serve()`, add mesh background loops startup before `await server.serve()`:

```python
    mesh_tasks = []
    if mesh_manager:
        async def _gossip_loop():
            import asyncio
            while not server.should_exit:
                try:
                    await mesh_manager.gossip_once()
                except Exception as e:
                    logger.debug("Gossip error: %s", e)
                await asyncio.sleep(mesh_config.gossip_interval)

        async def _heartbeat_loop():
            import asyncio
            while not server.should_exit:
                try:
                    await mesh_manager.heartbeat_once()
                except Exception as e:
                    logger.debug("Heartbeat error: %s", e)
                await asyncio.sleep(mesh_config.heartbeat_interval)

        mesh_tasks.append(asyncio.create_task(_gossip_loop()))
        mesh_tasks.append(asyncio.create_task(_heartbeat_loop()))
```

7. In the `finally` block, add mesh cleanup before `remove_pid_file`:

```python
        for task in mesh_tasks:
            task.cancel()
        if mesh_manager:
            await mesh_manager.leave()
            await mesh_manager.close()
```

8. Modify `astromesh/api/routes/system.py` — add mesh info to StatusResponse. Add field to `StatusResponse` class (after `peers` field):

```python
    mesh: dict | None = None
```

In `system_status()`, add mesh info gathering after the peers section:

```python
    mesh_info = None
    if _runtime and hasattr(_runtime, "mesh_manager") and _runtime.mesh_manager:
        mm = _runtime.mesh_manager
        mesh_info = {
            "enabled": True,
            "node_id": mm.node_id,
            "node_name": mm._config.node_name,
            "leader": mm.cluster_state().leader_id,
            "cluster_size": len(mm.cluster_state().nodes),
            "status": mm.local_node_state().status,
        }
```

And add `mesh=mesh_info` to the StatusResponse return.

**Note:** Also store `mesh_manager` on the runtime in `run_daemon()` after creating it:

```python
    runtime.mesh_manager = mesh_manager
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_daemon_mesh.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add daemon/astromeshd.py astromesh/api/routes/system.py tests/test_daemon_mesh.py
git commit -m "feat(mesh): wire MeshManager into daemon startup with gossip/heartbeat background loops"
```

---

### Task 10: CLI Mesh Commands

**Files:**
- Create: `cli/commands/mesh.py`
- Modify: `cli/main.py`
- Modify: `cli/client.py`
- Test: `tests/test_cli_mesh.py`

**Step 1: Write the failing tests**

```python
"""Tests for astromeshctl mesh commands."""

import time
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_mesh_status():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "nodes": [
            {
                "node_id": "abc-123",
                "name": "gateway-1",
                "url": "http://gateway:8000",
                "services": ["api", "channels"],
                "agents": [],
                "load": {"cpu_percent": 25.0, "memory_percent": 40.0, "active_requests": 2},
                "leader": True,
                "joined_at": time.time(),
                "last_heartbeat": time.time(),
                "status": "alive",
            },
            {
                "node_id": "def-456",
                "name": "worker-1",
                "url": "http://worker:8000",
                "services": ["agents", "tools"],
                "agents": ["support-agent"],
                "load": {"cpu_percent": 55.0, "memory_percent": 60.0, "active_requests": 5},
                "leader": False,
                "joined_at": time.time(),
                "last_heartbeat": time.time(),
                "status": "alive",
            },
        ],
        "leader_id": "abc-123",
        "version": 5,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "status"])
    assert result.exit_code == 0
    assert "2" in result.output  # 2 nodes
    assert "gateway-1" in result.output or "abc-123" in result.output


def test_mesh_nodes():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "nodes": [
            {
                "node_id": "abc-123",
                "name": "gateway-1",
                "url": "http://gateway:8000",
                "services": ["api", "channels"],
                "agents": [],
                "load": {"cpu_percent": 25.0, "memory_percent": 40.0, "active_requests": 2},
                "leader": True,
                "joined_at": time.time(),
                "last_heartbeat": time.time(),
                "status": "alive",
            },
        ],
        "leader_id": "abc-123",
        "version": 3,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "nodes"])
    assert result.exit_code == 0
    assert "gateway-1" in result.output
    assert "alive" in result.output.lower()


def test_mesh_leave():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "leave"])
    assert result.exit_code == 0


def test_mesh_status_not_enabled():
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.raise_for_status = MagicMock(
        side_effect=Exception("503: Mesh not enabled")
    )

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["mesh", "status"])
    assert result.exit_code == 0
    assert "not enabled" in result.output.lower() or "error" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_mesh.py -v`
Expected: FAIL (no mesh command registered)

**Step 3: Write minimal implementation**

Add `api_post` to `cli/client.py` (add after the `api_get` function):

```python
def api_post(path: str, json: dict | None = None) -> dict:
    url = f"{get_base_url()}{path}"
    resp = httpx.post(url, json=json, timeout=5.0)
    resp.raise_for_status()
    return resp.json()
```

Create `cli/commands/mesh.py`:
```python
"""astromeshctl mesh commands."""

import typer
from rich.table import Table

from cli.client import api_get, api_post
from cli.output import console, print_error, print_json

app = typer.Typer(help="Mesh cluster management.")


@app.command("status")
def mesh_status(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Show mesh cluster summary."""
    try:
        data = api_get("/v1/mesh/state")
        if json:
            print_json(data)
            return

        nodes = data.get("nodes", [])
        leader_id = data.get("leader_id")
        leader_name = ""
        for n in nodes:
            if n.get("node_id") == leader_id:
                leader_name = n.get("name", leader_id)
                break

        console.print(f"[bold]Mesh Cluster[/bold]")
        console.print(f"  Nodes:   {len(nodes)}")
        console.print(f"  Leader:  {leader_name or 'none'}")
        console.print(f"  Version: {data.get('version', 0)}")

        alive = sum(1 for n in nodes if n.get("status") == "alive")
        suspect = sum(1 for n in nodes if n.get("status") == "suspect")
        dead = sum(1 for n in nodes if n.get("status") == "dead")
        console.print(f"  Alive:   {alive}  Suspect: {suspect}  Dead: {dead}")
    except Exception:
        print_error("Mesh not enabled or daemon not reachable.")
        raise typer.Exit(code=0)


@app.command("nodes")
def mesh_nodes(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List all nodes in the mesh."""
    try:
        data = api_get("/v1/mesh/state")
        if json:
            print_json(data)
            return

        nodes = data.get("nodes", [])
        leader_id = data.get("leader_id")

        if not nodes:
            console.print("[dim]No nodes in mesh.[/dim]")
            return

        table = Table(title="Mesh Nodes")
        table.add_column("Name", style="cyan")
        table.add_column("URL", style="green")
        table.add_column("Services", style="dim")
        table.add_column("Agents", style="dim")
        table.add_column("Load", style="yellow")
        table.add_column("Status")
        table.add_column("Leader")

        for node in nodes:
            services = ", ".join(node.get("services", []))
            agents = ", ".join(node.get("agents", []))
            load = node.get("load", {})
            load_str = f"CPU:{load.get('cpu_percent', 0):.0f}% Req:{load.get('active_requests', 0)}"
            status = node.get("status", "unknown")
            status_display = {
                "alive": "[green]alive[/green]",
                "suspect": "[yellow]suspect[/yellow]",
                "dead": "[red]dead[/red]",
            }.get(status, status)
            is_leader = "[bold green]YES[/bold green]" if node.get("node_id") == leader_id else ""

            table.add_row(
                node.get("name", ""),
                node.get("url", ""),
                services,
                agents,
                load_str,
                status_display,
                is_leader,
            )

        console.print(table)
    except Exception:
        print_error("Mesh not enabled or daemon not reachable.")
        raise typer.Exit(code=0)


@app.command("leave")
def mesh_leave():
    """Gracefully leave the mesh."""
    try:
        api_post("/v1/mesh/leave", json={"node_id": "self"})
        console.print("[green]Left mesh successfully.[/green]")
    except Exception:
        print_error("Failed to leave mesh.")
        raise typer.Exit(code=0)
```

Modify `cli/main.py` — add mesh import and registration:

Add `mesh` to the import line (line 6):

```python
from cli.commands import agents, config, doctor, mesh, peers, providers, services, status
```

Add after `app.add_typer(services.app, name="services")` (line 20):

```python
app.add_typer(mesh.app, name="mesh")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_mesh.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add cli/commands/mesh.py cli/main.py cli/client.py tests/test_cli_mesh.py
git commit -m "feat(mesh): add astromeshctl mesh status/nodes/leave commands"
```

---

### Task 11: Mesh Config Profiles

**Files:**
- Create: `config/profiles/mesh-gateway.yaml`
- Create: `config/profiles/mesh-worker.yaml`
- Create: `config/profiles/mesh-inference.yaml`

**Step 1: Create mesh-gateway.yaml**

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: mesh-gateway
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: false
    inference: false
    memory: false
    tools: false
    channels: true
    rag: false
    observability: true
  mesh:
    enabled: true
    node_name: gateway
    bind: "0.0.0.0:8000"
    seeds: []
    heartbeat_interval: 5
    gossip_interval: 2
    gossip_fanout: 3
    failure_timeout: 15
    dead_timeout: 30
```

**Step 2: Create mesh-worker.yaml**

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: mesh-worker
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: true
    inference: false
    memory: true
    tools: true
    channels: false
    rag: true
    observability: true
  mesh:
    enabled: true
    node_name: worker
    bind: "0.0.0.0:8000"
    seeds:
      - http://gateway:8000
    heartbeat_interval: 5
    gossip_interval: 2
    gossip_fanout: 3
    failure_timeout: 15
    dead_timeout: 30
```

**Step 3: Create mesh-inference.yaml**

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: mesh-inference
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: false
    inference: true
    memory: false
    tools: false
    channels: false
    rag: false
    observability: true
  mesh:
    enabled: true
    node_name: inference
    bind: "0.0.0.0:8000"
    seeds:
      - http://gateway:8000
    heartbeat_interval: 5
    gossip_interval: 2
    gossip_fanout: 3
    failure_timeout: 15
    dead_timeout: 30
```

**Step 4: Commit**

```bash
git add config/profiles/mesh-gateway.yaml config/profiles/mesh-worker.yaml config/profiles/mesh-inference.yaml
git commit -m "feat(mesh): add mesh-enabled config profiles (gateway, worker, inference)"
```

---

### Task 12: Docker Compose Mesh Update

**Files:**
- Create: `docker/docker-compose.gossip.yml`

**Step 1: Create the gossip-enabled Docker Compose file**

```yaml
# Astromesh OS — Gossip mesh for local development
# Usage: docker compose -f docker/docker-compose.gossip.yml up

services:
  gateway:
    build:
      context: ..
      dockerfile: Dockerfile
    volumes:
      - ../config/profiles/mesh-gateway.yaml:/etc/astromesh/runtime.yaml:ro
      - ../config/channels.yaml:/etc/astromesh/channels.yaml:ro
    ports:
      - "8000:8000"
    networks:
      - astromesh-gossip

  worker:
    build:
      context: ..
      dockerfile: Dockerfile
    volumes:
      - ../config/profiles/mesh-worker.yaml:/etc/astromesh/runtime.yaml:ro
      - ../config/agents:/etc/astromesh/agents:ro
      - ../config/providers.yaml:/etc/astromesh/providers.yaml:ro
    depends_on:
      gateway:
        condition: service_started
      redis:
        condition: service_started
      postgres:
        condition: service_started
    networks:
      - astromesh-gossip

  inference:
    build:
      context: ..
      dockerfile: Dockerfile
    volumes:
      - ../config/profiles/mesh-inference.yaml:/etc/astromesh/runtime.yaml:ro
      - ../config/providers.yaml:/etc/astromesh/providers.yaml:ro
    depends_on:
      gateway:
        condition: service_started
    networks:
      - astromesh-gossip

  # --- Supporting infrastructure ---

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - astromesh-gossip

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - astromesh-gossip

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: astromesh
      POSTGRES_USER: astromesh
      POSTGRES_PASSWORD: astromesh
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - astromesh-gossip

volumes:
  ollama-models:
  redis-data:
  postgres-data:

networks:
  astromesh-gossip:
    driver: bridge
```

**Step 2: Commit**

```bash
git add docker/docker-compose.gossip.yml
git commit -m "feat(mesh): add Docker Compose gossip mesh for local development"
```

---

### Task 13: Integration Tests

**Files:**
- Create: `tests/test_mesh_integration.py`

**Step 1: Write integration tests**

```python
"""Integration tests for the full mesh stack."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from astromesh.api.main import app
from astromesh.api.routes import mesh as mesh_routes
from astromesh.api.routes import system
from astromesh.mesh.config import MeshConfig
from astromesh.mesh.leader import LeaderElector
from astromesh.mesh.manager import MeshManager
from astromesh.mesh.scheduler import Scheduler
from astromesh.mesh.state import NodeLoad, NodeState
from astromesh.runtime.engine import AgentRuntime
from astromesh.runtime.peers import PeerClient
from astromesh.runtime.services import ServiceManager


@pytest.fixture
def three_node_mesh():
    """Create a 3-node mesh: gateway, worker, inference."""
    # Gateway
    gw_config = MeshConfig(enabled=True, node_name="gateway")
    gw_sm = ServiceManager({"api": True, "channels": True, "observability": True,
                            "agents": False, "inference": False, "memory": False,
                            "tools": False, "rag": False})
    gw_mesh = MeshManager(gw_config, gw_sm)

    # Worker
    wk_config = MeshConfig(enabled=True, node_name="worker")
    wk_sm = ServiceManager({"api": True, "agents": True, "tools": True, "memory": True,
                            "rag": True, "observability": True,
                            "inference": False, "channels": False})
    wk_mesh = MeshManager(wk_config, wk_sm)

    # Inference
    inf_config = MeshConfig(enabled=True, node_name="inference")
    inf_sm = ServiceManager({"api": True, "inference": True, "observability": True,
                             "agents": False, "tools": False, "memory": False,
                             "channels": False, "rag": False})
    inf_mesh = MeshManager(inf_config, inf_sm)

    # Simulate join: each node knows about all others
    now = time.time()
    gw_state = gw_mesh.local_node_state()
    wk_state = wk_mesh.local_node_state()
    inf_state = inf_mesh.local_node_state()

    # Worker has agents loaded
    wk_mesh.update_agents(["support-agent", "sales-agent"])
    wk_state = wk_mesh.local_node_state()

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
    gw_elector = LeaderElector(gw)
    gw_elector.elect()
    # Highest node_id wins — we don't know which UUID is highest
    # but exactly one should be leader
    assert gw_elector.current_leader() is not None
    leader_id = gw_elector.current_leader()
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
    assert gw.node_id not in nodes  # no agents service
    assert inf.node_id not in nodes  # no agents service


def test_peer_client_from_mesh_integration(three_node_mesh):
    gw, wk, inf = three_node_mesh
    client = PeerClient.from_mesh(gw)
    # Gateway should see worker and inference as peers
    assert len(client.list_peers()) == 2
    agents_peers = client.find_peers("agents")
    assert len(agents_peers) == 1
    inference_peers = client.find_peers("inference")
    assert len(inference_peers) == 1


def test_node_failure_detection(three_node_mesh):
    gw, wk, inf = three_node_mesh
    # Simulate worker heartbeat timeout
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

    # Kill the leader
    gw._cluster.nodes[leader_before].status = "dead"
    elector.on_node_failed(leader_before)

    new_leader = elector.current_leader()
    assert new_leader is not None
    assert new_leader != leader_before or leader_before == gw.node_id


def test_gossip_merge_propagates(three_node_mesh):
    gw, wk, inf = three_node_mesh
    # Worker updates its load
    wk._cluster.nodes[wk.node_id].load.active_requests = 42
    wk._cluster.nodes[wk.node_id].last_heartbeat = time.time()

    # Gateway receives gossip from worker
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

    system.set_runtime(runtime)
    client = TestClient(app)
    resp = client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("mesh") is not None
    assert data["mesh"]["enabled"] is True
    assert data["mesh"]["cluster_size"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mesh_integration.py -v`
Expected: FAIL (imports should work if all prior tasks are done; tests should FAIL if mesh is not wired correctly)

Note: If prior tasks are all committed, this should mostly pass. If there are failures, fix them.

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_mesh_integration.py -v`
Expected: All 10 tests PASS

**Step 4: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS (existing 254 + new ~60 mesh tests)

**Step 5: Commit**

```bash
git add tests/test_mesh_integration.py
git commit -m "test(mesh): add integration tests for 3-node mesh with gossip, election, and scheduling"
```

---

## Summary

| Task | Component | Files | Tests |
|------|-----------|-------|-------|
| 1 | NodeState, NodeLoad, ClusterState | `astromesh/mesh/state.py` | 12 |
| 2 | MeshConfig | `astromesh/mesh/config.py` | 5 |
| 3 | psutil dependency | `pyproject.toml` | 0 |
| 4 | MeshManager | `astromesh/mesh/manager.py` | 13 |
| 5 | LeaderElector | `astromesh/mesh/leader.py` | 6 |
| 6 | Scheduler | `astromesh/mesh/scheduler.py` | 7 |
| 7 | Mesh API routes | `astromesh/api/routes/mesh.py` | 7 |
| 8 | PeerClient.from_mesh() | `astromesh/runtime/peers.py` | 7 |
| 9 | Daemon wiring + system status | `daemon/astromeshd.py`, `system.py` | 3 |
| 10 | CLI mesh commands | `cli/commands/mesh.py` | 4 |
| 11 | Config profiles | `config/profiles/mesh-*.yaml` | 0 |
| 12 | Docker Compose gossip | `docker/docker-compose.gossip.yml` | 0 |
| 13 | Integration tests | `tests/test_mesh_integration.py` | 10 |

**Total new tests: ~74**
**Total new/modified files: ~20**
**Parallelization: 5 waves**
