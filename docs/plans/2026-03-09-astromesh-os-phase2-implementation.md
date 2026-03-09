# Astromesh OS Phase 2 — Containerized Node Roles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform Astromesh into a containerized unit of processing with configurable roles, peer communication, and Docker-based deployment.

**Architecture:** `ServiceManager` controls which subsystems activate at boot. `PeerClient` forwards requests to peer nodes for disabled services. A single Docker image serves all roles via mounted config. Pre-built profiles define common node roles.

**Tech Stack:** Python 3.12+, FastAPI, httpx (async peer client), Docker SDK >= 7.0, Typer + Rich, pytest + httpx

**Design doc:** `docs/plans/2026-03-09-astromesh-os-phase2-design.md`

---

## Task 1: ServiceManager

**Files:**
- Create: `astromesh/runtime/services.py`
- Create: `tests/test_services.py`

**Step 1: Write the failing tests**

Create `tests/test_services.py`:

```python
"""Tests for ServiceManager."""

import pytest

from astromesh.runtime.services import ServiceManager, DEFAULT_SERVICES


def test_default_services():
    """All services enabled by default."""
    sm = ServiceManager({})
    for service in DEFAULT_SERVICES:
        assert sm.is_enabled(service) is True


def test_explicit_disable():
    """Explicitly disabled services are off."""
    sm = ServiceManager({"inference": False, "channels": False})
    assert sm.is_enabled("inference") is False
    assert sm.is_enabled("channels") is False
    assert sm.is_enabled("agents") is True
    assert sm.is_enabled("api") is True


def test_enabled_services_list():
    """enabled_services returns only active ones."""
    sm = ServiceManager({"inference": False, "rag": False})
    enabled = sm.enabled_services()
    assert "inference" not in enabled
    assert "rag" not in enabled
    assert "agents" in enabled
    assert "api" in enabled


def test_unknown_service():
    """Unknown service is not enabled."""
    sm = ServiceManager({})
    assert sm.is_enabled("nonexistent") is False


def test_validate_warns_agents_without_tools():
    """Warn if agents enabled but tools disabled."""
    sm = ServiceManager({"agents": True, "tools": False})
    warnings = sm.validate()
    assert any("tools" in w.lower() for w in warnings)


def test_validate_no_warnings_when_consistent():
    """No warnings for valid config."""
    sm = ServiceManager({"agents": True, "tools": True})
    warnings = sm.validate()
    assert len(warnings) == 0


def test_to_dict():
    """to_dict returns full service state."""
    sm = ServiceManager({"inference": False})
    d = sm.to_dict()
    assert d["inference"] is False
    assert d["api"] is True
    assert isinstance(d, dict)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_services.py -v`
Expected: FAIL (module not found)

**Step 3: Implement ServiceManager**

Create `astromesh/runtime/services.py`:

```python
"""Service manager for Astromesh OS node roles."""

DEFAULT_SERVICES = (
    "api",
    "agents",
    "inference",
    "memory",
    "tools",
    "channels",
    "rag",
    "observability",
)


class ServiceManager:
    """Controls which services are active on this node."""

    def __init__(self, services_config: dict[str, bool]):
        self._services: dict[str, bool] = {}
        for service in DEFAULT_SERVICES:
            self._services[service] = services_config.get(service, True)

    def is_enabled(self, service: str) -> bool:
        return self._services.get(service, False)

    def enabled_services(self) -> list[str]:
        return [s for s, enabled in self._services.items() if enabled]

    def validate(self) -> list[str]:
        warnings: list[str] = []
        if self._services.get("agents") and not self._services.get("tools"):
            warnings.append("agents enabled without tools — agents won't be able to use tools")
        if self._services.get("agents") and not self._services.get("memory"):
            warnings.append("agents enabled without memory — agents won't have conversation history")
        return warnings

    def to_dict(self) -> dict[str, bool]:
        return dict(self._services)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check astromesh/runtime/services.py tests/test_services.py`
Run: `uv run ruff format astromesh/runtime/services.py tests/test_services.py`

**Step 6: Commit**

```bash
git add astromesh/runtime/services.py tests/test_services.py
git commit -m "feat: add ServiceManager for node role configuration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: PeerClient

**Files:**
- Create: `astromesh/runtime/peers.py`
- Create: `tests/test_peers.py`

**Step 1: Write the failing tests**

Create `tests/test_peers.py`:

```python
"""Tests for PeerClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astromesh.runtime.peers import PeerClient


@pytest.fixture
def peer_config():
    return [
        {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
        {"name": "worker-1", "url": "http://worker:8000", "services": ["agents", "tools", "memory"]},
        {"name": "worker-2", "url": "http://worker2:8000", "services": ["agents", "tools"]},
    ]


def test_find_peers(peer_config):
    """Find peers by service."""
    client = PeerClient(peer_config)
    inference_peers = client.find_peers("inference")
    assert len(inference_peers) == 1
    assert inference_peers[0]["name"] == "inference-1"


def test_find_peers_multiple(peer_config):
    """Multiple peers can have same service."""
    client = PeerClient(peer_config)
    agent_peers = client.find_peers("agents")
    assert len(agent_peers) == 2


def test_find_peers_none(peer_config):
    """No peers for unknown service."""
    client = PeerClient(peer_config)
    assert client.find_peers("channels") == []


def test_peer_list(peer_config):
    """List all peers."""
    client = PeerClient(peer_config)
    peers = client.list_peers()
    assert len(peers) == 3
    assert peers[0]["name"] == "inference-1"


async def test_health_check_success(peer_config):
    """Health check succeeds for reachable peer."""
    client = PeerClient(peer_config)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}

    with patch.object(client, "_http") as mock_http:
        mock_http.get = AsyncMock(return_value=mock_resp)
        result = await client.health_check("inference-1")
    assert result is True


async def test_health_check_failure(peer_config):
    """Health check fails for unreachable peer."""
    client = PeerClient(peer_config)

    with patch.object(client, "_http") as mock_http:
        mock_http.get = AsyncMock(side_effect=Exception("Connection refused"))
        result = await client.health_check("inference-1")
    assert result is False


async def test_health_check_unknown_peer(peer_config):
    """Health check returns False for unknown peer."""
    client = PeerClient(peer_config)
    result = await client.health_check("nonexistent")
    assert result is False


async def test_forward_request(peer_config):
    """Forward request to peer with matching service."""
    client = PeerClient(peer_config)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"answer": "hello"}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(client, "_http") as mock_http:
        mock_http.request = AsyncMock(return_value=mock_resp)
        result = await client.forward("inference", "POST", "/v1/agents/test/run", json={"query": "hi"})
    assert result == {"answer": "hello"}


async def test_forward_no_peer_raises(peer_config):
    """Forward raises when no peer has the service."""
    client = PeerClient(peer_config)
    with pytest.raises(RuntimeError, match="No peer available"):
        await client.forward("channels", "GET", "/v1/channels")


def test_to_dict(peer_config):
    """to_dict returns peer summary."""
    client = PeerClient(peer_config)
    d = client.to_dict()
    assert len(d) == 3
    assert d[0]["name"] == "inference-1"
    assert d[0]["url"] == "http://inference:8000"
    assert d[0]["services"] == ["inference"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_peers.py -v`
Expected: FAIL (module not found)

**Step 3: Implement PeerClient**

Create `astromesh/runtime/peers.py`:

```python
"""Peer client for inter-node communication in Astromesh OS."""

import logging

import httpx

logger = logging.getLogger("astromesh.peers")


class PeerClient:
    """Manages communication with peer Astromesh nodes."""

    def __init__(self, peers_config: list[dict]):
        self._peers = peers_config or []
        self._http = httpx.AsyncClient(timeout=30.0)
        self._peer_index: dict[str, dict] = {p["name"]: p for p in self._peers}
        self._round_robin: dict[str, int] = {}

    def find_peers(self, service: str) -> list[dict]:
        return [p for p in self._peers if service in p.get("services", [])]

    def list_peers(self) -> list[dict]:
        return list(self._peers)

    def to_dict(self) -> list[dict]:
        return [
            {"name": p["name"], "url": p["url"], "services": p.get("services", [])}
            for p in self._peers
        ]

    async def health_check(self, peer_name: str) -> bool:
        peer = self._peer_index.get(peer_name)
        if not peer:
            return False
        try:
            resp = await self._http.get(f"{peer['url']}/v1/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def health_check_all(self) -> dict[str, bool]:
        results = {}
        for peer in self._peers:
            results[peer["name"]] = await self.health_check(peer["name"])
        return results

    async def forward(self, service: str, method: str, path: str, **kwargs) -> dict:
        peers = self.find_peers(service)
        if not peers:
            raise RuntimeError(f"No peer available for service '{service}'")

        idx = self._round_robin.get(service, 0) % len(peers)
        self._round_robin[service] = idx + 1

        peer = peers[idx]
        url = f"{peer['url']}{path}"

        try:
            resp = await self._http.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Failed to forward to peer %s: %s", peer["name"], e)
            # Try next peer if available
            for i in range(1, len(peers)):
                next_peer = peers[(idx + i) % len(peers)]
                try:
                    resp = await self._http.request(method, f"{next_peer['url']}{path}", **kwargs)
                    resp.raise_for_status()
                    return resp.json()
                except Exception:
                    continue
            raise RuntimeError(f"All peers for service '{service}' failed") from e

    async def close(self):
        await self._http.aclose()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_peers.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check astromesh/runtime/peers.py tests/test_peers.py`
Run: `uv run ruff format astromesh/runtime/peers.py tests/test_peers.py`

**Step 6: Commit**

```bash
git add astromesh/runtime/peers.py tests/test_peers.py
git commit -m "feat: add PeerClient for inter-node communication

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Config profiles

**Files:**
- Create: `config/profiles/full.yaml`
- Create: `config/profiles/gateway.yaml`
- Create: `config/profiles/worker.yaml`
- Create: `config/profiles/inference.yaml`

**Step 1: Create profile configs**

Create `config/profiles/full.yaml`:

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: full
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    api: true
    agents: true
    inference: true
    memory: true
    tools: true
    channels: true
    rag: true
    observability: true
  peers: []
  defaults:
    orchestration:
      pattern: react
      max_iterations: 10
```

Create `config/profiles/gateway.yaml`:

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: gateway
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
  peers:
    - name: worker-1
      url: http://worker:8000
      services: [agents, tools, memory, rag]
```

Create `config/profiles/worker.yaml`:

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: worker
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
  peers:
    - name: inference-1
      url: http://inference:8000
      services: [inference]
```

Create `config/profiles/inference.yaml`:

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: inference
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
  peers: []
```

**Step 2: Commit**

```bash
git add config/profiles/
git commit -m "feat: add node role config profiles (full, gateway, worker, inference)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Runtime modifications — conditional bootstrap

**Files:**
- Modify: `astromesh/runtime/engine.py`
- Modify: `tests/test_engine.py` or create `tests/test_engine_services.py`

**Step 1: Write the failing tests**

Create `tests/test_engine_services.py`:

```python
"""Tests for AgentRuntime with ServiceManager integration."""

import pytest

from astromesh.runtime.engine import AgentRuntime
from astromesh.runtime.services import ServiceManager


async def test_bootstrap_with_agents_enabled(tmp_path):
    """Agents load when agents service is enabled."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    sm = ServiceManager({"agents": True})
    runtime = AgentRuntime(config_dir=str(tmp_path), service_manager=sm)
    await runtime.bootstrap()
    assert len(runtime._agents) == 1


async def test_bootstrap_with_agents_disabled(tmp_path):
    """Agents don't load when agents service is disabled."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    sm = ServiceManager({"agents": False})
    runtime = AgentRuntime(config_dir=str(tmp_path), service_manager=sm)
    await runtime.bootstrap()
    assert len(runtime._agents) == 0


async def test_bootstrap_without_service_manager(tmp_path):
    """Without ServiceManager, all services are enabled (backward compat)."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()
    assert len(runtime._agents) == 1


def test_runtime_exposes_service_manager():
    """Runtime exposes service_manager and peer_client."""
    sm = ServiceManager({"agents": True})
    runtime = AgentRuntime(service_manager=sm)
    assert runtime.service_manager is sm
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_engine_services.py -v`
Expected: FAIL (AgentRuntime doesn't accept service_manager)

**Step 3: Modify AgentRuntime**

Modify `astromesh/runtime/engine.py`. The constructor adds optional `service_manager` and `peer_client` parameters. `bootstrap()` checks `service_manager.is_enabled("agents")` before loading agents.

Changes to `AgentRuntime.__init__()`:
```python
def __init__(self, config_dir="./config", service_manager=None, peer_client=None):
    self._config_dir = Path(config_dir)
    self._agents: dict[str, "Agent"] = {}
    self._prompt_engine = PromptEngine()
    self.service_manager = service_manager
    self.peer_client = peer_client
```

Changes to `AgentRuntime.bootstrap()`:
```python
async def bootstrap(self):
    # Skip agent loading if agents service is disabled
    if self.service_manager and not self.service_manager.is_enabled("agents"):
        return
    agents_dir = self._config_dir / "agents"
    if not agents_dir.exists():
        return
    for f in agents_dir.glob("*.agent.yaml"):
        config = yaml.safe_load(f.read_text())
        agent = self._build_agent(config)
        self._agents[agent.name] = agent
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_engine_services.py -v`
Expected: ALL PASS

**Step 5: Run existing tests for no regressions**

Run: `uv run pytest tests/test_engine.py tests/test_integration.py -v`
Expected: ALL PASS (backward compatible — no service_manager means all enabled)

**Step 6: Lint**

Run: `uv run ruff check astromesh/runtime/engine.py tests/test_engine_services.py`
Run: `uv run ruff format astromesh/runtime/engine.py tests/test_engine_services.py`

**Step 7: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_engine_services.py
git commit -m "feat: integrate ServiceManager into AgentRuntime for conditional bootstrap

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: API updates — status and doctor with services/peers

**Files:**
- Modify: `astromesh/api/routes/system.py`
- Modify: `tests/test_system_api.py`

**Step 1: Write the failing tests**

Append to `tests/test_system_api.py`:

```python
async def test_system_status_includes_services(client):
    """Status includes services list."""
    from astromesh.api.routes import system
    from astromesh.runtime.services import ServiceManager

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = []
    mock_runtime.service_manager = ServiceManager({"inference": False})
    mock_runtime.peer_client = None
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "services" in data
    assert data["services"]["inference"] is False
    assert data["services"]["api"] is True
    system.set_runtime(None)


async def test_system_status_includes_peers(client):
    """Status includes peers list."""
    from astromesh.api.routes import system
    from astromesh.runtime.peers import PeerClient

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = []
    mock_runtime.service_manager = None
    mock_runtime.peer_client = PeerClient([
        {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
    ])
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "peers" in data
    assert len(data["peers"]) == 1
    assert data["peers"][0]["name"] == "inference-1"
    system.set_runtime(None)


async def test_system_doctor_checks_peers(client):
    """Doctor checks peer health."""
    from astromesh.api.routes import system
    from astromesh.runtime.peers import PeerClient

    mock_runtime = MagicMock()
    mock_runtime.list_agents.return_value = []
    mock_runtime._agents = {}
    mock_runtime.service_manager = None

    pc = PeerClient([
        {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
    ])
    pc.health_check = AsyncMock(return_value=False)
    mock_runtime.peer_client = pc
    system.set_runtime(mock_runtime)

    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert "peer:inference-1" in data["checks"]
    system.set_runtime(None)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_system_api.py::test_system_status_includes_services -v`
Expected: FAIL (no "services" in response)

**Step 3: Update system routes**

Modify `astromesh/api/routes/system.py`:

Update `StatusResponse` model to include services and peers:
```python
class StatusResponse(BaseModel):
    version: str
    uptime_seconds: float
    mode: str
    agents_loaded: int
    pid: int
    services: dict[str, bool] = {}
    peers: list[dict] = []
```

Update `system_status()` endpoint:
```python
@router.get("/status", response_model=StatusResponse)
async def system_status():
    agents_loaded = 0
    services = {}
    peers = []
    if _runtime:
        agents_loaded = len(_runtime.list_agents())
        if hasattr(_runtime, "service_manager") and _runtime.service_manager:
            services = _runtime.service_manager.to_dict()
        if hasattr(_runtime, "peer_client") and _runtime.peer_client:
            peers = _runtime.peer_client.to_dict()

    return StatusResponse(
        version=__version__,
        uptime_seconds=round(time.time() - _start_time, 2),
        mode=_detect_mode(),
        agents_loaded=agents_loaded,
        pid=os.getpid(),
        services=services,
        peers=peers,
    )
```

Update `system_doctor()` to check peers:
```python
@router.get("/doctor", response_model=DoctorResponse)
async def system_doctor():
    checks: dict[str, CheckResult] = {}

    if not _runtime:
        checks["runtime"] = CheckResult(status="unavailable", message="Runtime not initialized")
        return DoctorResponse(healthy=False, checks=checks)

    checks["runtime"] = CheckResult(status="ok", message="Runtime initialized")

    # Check providers (existing code unchanged)
    providers_checked = set()
    for agent in _runtime._agents.values():
        if hasattr(agent, "_router") and hasattr(agent._router, "_providers"):
            for name, provider in agent._router._providers.items():
                if name not in providers_checked:
                    providers_checked.add(name)
                    try:
                        healthy = await provider.health_check()
                        checks[f"provider:{name}"] = CheckResult(
                            status="ok" if healthy else "degraded",
                            message=f"Provider {name} health check",
                        )
                    except Exception as e:
                        checks[f"provider:{name}"] = CheckResult(status="error", message=str(e))

    # Check peers (NEW)
    if hasattr(_runtime, "peer_client") and _runtime.peer_client:
        for peer in _runtime.peer_client.list_peers():
            healthy = await _runtime.peer_client.health_check(peer["name"])
            checks[f"peer:{peer['name']}"] = CheckResult(
                status="ok" if healthy else "unreachable",
                message=f"Peer {peer['name']} at {peer['url']}",
            )

    all_ok = all(c.status == "ok" for c in checks.values())
    return DoctorResponse(healthy=all_ok, checks=checks)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_system_api.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check astromesh/api/routes/system.py tests/test_system_api.py`
Run: `uv run ruff format astromesh/api/routes/system.py tests/test_system_api.py`

**Step 6: Commit**

```bash
git add astromesh/api/routes/system.py tests/test_system_api.py
git commit -m "feat: extend /v1/system/status and doctor with services and peers

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Daemon modifications — wire ServiceManager and PeerClient

**Files:**
- Modify: `daemon/astromeshd.py`
- Modify: `tests/test_daemon.py`

**Step 1: Write the failing tests**

Append to `tests/test_daemon.py`:

```python
def test_daemon_config_parses_services(tmp_path):
    """DaemonConfig reads services from runtime.yaml."""
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    agents: true
    inference: false
    channels: false
""")
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.services == {"agents": True, "inference": False, "channels": False}


def test_daemon_config_parses_peers(tmp_path):
    """DaemonConfig reads peers from runtime.yaml."""
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  peers:
    - name: inference-1
      url: http://inference:8000
      services: [inference]
""")
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert len(config.peers) == 1
    assert config.peers[0]["name"] == "inference-1"


def test_daemon_config_defaults_services_and_peers(tmp_path):
    """DaemonConfig defaults to empty services and peers."""
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.services == {}
    assert config.peers == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daemon.py::test_daemon_config_parses_services -v`
Expected: FAIL (DaemonConfig has no services attribute)

**Step 3: Update DaemonConfig and run_daemon**

Modify `daemon/astromeshd.py`:

Update `DaemonConfig` dataclass:
```python
from dataclasses import dataclass, field

@dataclass
class DaemonConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    pid_file: str = DEFAULT_PID_FILE
    services: dict[str, bool] = field(default_factory=dict)
    peers: list[dict] = field(default_factory=list)

    @classmethod
    def from_config_dir(cls, config_dir: str) -> "DaemonConfig":
        runtime_path = Path(config_dir) / "runtime.yaml"
        if not runtime_path.exists():
            return cls()

        data = yaml.safe_load(runtime_path.read_text()) or {}
        spec = data.get("spec", {})
        api = spec.get("api", {})

        return cls(
            host=api.get("host", cls.host),
            port=api.get("port", cls.port),
            services=spec.get("services", {}),
            peers=spec.get("peers", []),
        )
```

Update `run_daemon()` to create ServiceManager and PeerClient:
```python
async def run_daemon(args: argparse.Namespace) -> None:
    import uvicorn

    from astromesh.api.main import app
    from astromesh.api.routes import agents, system
    from astromesh.runtime.engine import AgentRuntime
    from astromesh.runtime.peers import PeerClient
    from astromesh.runtime.services import ServiceManager

    config_dir = detect_config_dir(args.config)
    daemon_config = DaemonConfig.from_config_dir(config_dir)

    host = args.host or daemon_config.host
    port = args.port or daemon_config.port
    pid_file = args.pid_file or daemon_config.pid_file

    mode = "system" if config_dir == SYSTEM_CONFIG_DIR else "dev"
    logger.info("Starting astromeshd in %s mode", mode)
    logger.info("Config directory: %s", config_dir)

    # Create service manager and peer client
    service_manager = ServiceManager(daemon_config.services)
    peer_client = PeerClient(daemon_config.peers)

    # Log services and peers
    enabled = service_manager.enabled_services()
    logger.info("Enabled services: %s", ", ".join(enabled))
    for warning in service_manager.validate():
        logger.warning("Config warning: %s", warning)
    if daemon_config.peers:
        logger.info("Peers: %s", ", ".join(p["name"] for p in daemon_config.peers))

    write_pid_file(pid_file)

    runtime = AgentRuntime(
        config_dir=config_dir,
        service_manager=service_manager,
        peer_client=peer_client,
    )
    await runtime.bootstrap()

    agents.set_runtime(runtime)
    system.set_runtime(runtime)

    agent_count = len(runtime.list_agents())
    logger.info("Loaded %d agent(s)", agent_count)

    # ... rest unchanged (sdnotify, uvicorn, signals, cleanup)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: ALL PASS

**Step 5: Lint**

Run: `uv run ruff check daemon/astromeshd.py tests/test_daemon.py`
Run: `uv run ruff format daemon/astromeshd.py tests/test_daemon.py`

**Step 6: Commit**

```bash
git add daemon/astromeshd.py tests/test_daemon.py
git commit -m "feat: wire ServiceManager and PeerClient into daemon startup

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: CLI — peers command

**Files:**
- Create: `cli/commands/peers.py`
- Modify: `cli/main.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_peers_list():
    """Peers list shows configured peers."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": "0.6.0",
        "uptime_seconds": 100.0,
        "mode": "dev",
        "agents_loaded": 0,
        "pid": 1234,
        "services": {},
        "peers": [
            {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
            {"name": "worker-1", "url": "http://worker:8000", "services": ["agents", "tools"]},
        ],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["peers", "list"])
    assert result.exit_code == 0
    assert "inference-1" in result.output
    assert "worker-1" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_peers_list -v`
Expected: FAIL

**Step 3: Implement peers command**

Create `cli/commands/peers.py`:

```python
"""astromeshctl peers commands."""

import typer
from rich.table import Table

from cli.client import api_get
from cli.output import console, print_error, print_json

app = typer.Typer(help="Manage peer nodes.")


@app.command("list")
def list_peers(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """List configured peer nodes."""
    try:
        data = api_get("/v1/system/status")
        if json:
            print_json({"peers": data.get("peers", [])})
            return

        peers = data.get("peers", [])
        if not peers:
            console.print("[dim]No peers configured.[/dim]")
            return

        table = Table(title="Peer Nodes")
        table.add_column("Name", style="cyan")
        table.add_column("URL", style="green")
        table.add_column("Services", style="dim")

        for peer in peers:
            services = ", ".join(peer.get("services", []))
            table.add_row(peer.get("name", ""), peer.get("url", ""), services)

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
```

**Step 4: Register in main.py**

Add `peers` to imports in `cli/main.py`:
```python
from cli.commands import agents, config, doctor, peers, providers, status
```

Add after existing `add_typer` calls:
```python
app.add_typer(peers.app, name="peers")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add cli/commands/peers.py cli/main.py tests/test_cli.py
git commit -m "feat: add astromeshctl peers command

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: CLI — services command

**Files:**
- Create: `cli/commands/services.py`
- Modify: `cli/main.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_services_list():
    """Services shows enabled/disabled services."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "version": "0.6.0",
        "uptime_seconds": 100.0,
        "mode": "dev",
        "agents_loaded": 0,
        "pid": 1234,
        "services": {
            "api": True,
            "agents": True,
            "inference": False,
            "memory": True,
            "tools": True,
            "channels": False,
            "rag": False,
            "observability": True,
        },
        "peers": [],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("cli.client.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["services"])
    assert result.exit_code == 0
    assert "agents" in result.output
    assert "inference" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_services_list -v`
Expected: FAIL

**Step 3: Implement services command**

Create `cli/commands/services.py`:

```python
"""astromeshctl services command."""

import typer
from rich.table import Table

from cli.client import api_get
from cli.output import console, print_error, print_json

app = typer.Typer()

STATUS_DISPLAY = {
    True: "[green]ENABLED[/green]",
    False: "[dim]DISABLED[/dim]",
}


@app.callback(invoke_without_command=True)
def services(json: bool = typer.Option(False, "--json", help="Output as JSON")):
    """Show enabled services on this node."""
    try:
        data = api_get("/v1/system/status")
        if json:
            print_json({"services": data.get("services", {})})
            return

        svc = data.get("services", {})
        if not svc:
            console.print("[dim]No service information available.[/dim]")
            return

        table = Table(title="Node Services")
        table.add_column("Service", style="cyan")
        table.add_column("Status")

        for name, enabled in svc.items():
            table.add_row(name, STATUS_DISPLAY.get(enabled, str(enabled)))

        console.print(table)
    except Exception:
        print_error("Daemon not reachable.")
        raise typer.Exit(code=0)
```

**Step 4: Register in main.py**

Add `services` to imports:
```python
from cli.commands import agents, config, doctor, peers, providers, services, status
```

Add:
```python
app.add_typer(services.app, name="services")
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add cli/commands/services.py cli/main.py tests/test_cli.py
git commit -m "feat: add astromeshctl services command

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Dockerfile

**Files:**
- Create: `Dockerfile`

**Step 1: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/

# Install all dependencies
RUN uv pip install --system ".[all]"

# Stage 2: Runtime image
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Astromesh OS" \
      org.opencontainers.image.description="Astromesh Agent Runtime Platform" \
      org.opencontainers.image.source="https://github.com/monaccode/astromech-platform"

WORKDIR /opt/astromesh

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/astromeshd /usr/local/bin/astromeshctl /usr/local/bin/

# Copy application code
COPY astromesh/ astromesh/
COPY daemon/ daemon/
COPY cli/ cli/

# Default config (overridden via volume mount)
COPY config/ /etc/astromesh/

# Create runtime directories
RUN mkdir -p /var/lib/astromesh/data /var/lib/astromesh/models \
             /var/lib/astromesh/memory /var/log/astromesh/audit

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/v1/health').raise_for_status()"

ENTRYPOINT ["astromeshd"]
CMD ["--config", "/etc/astromesh"]
```

**Step 2: Commit**

```bash
git add Dockerfile
git commit -m "feat: add universal Dockerfile for Astromesh OS nodes

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Docker Compose mesh

**Files:**
- Create: `docker/docker-compose.mesh.yml`

**Step 1: Create compose file**

Create `docker/docker-compose.mesh.yml`:

```yaml
# Astromesh OS — Multi-node mesh for local development
# Usage: docker compose -f docker/docker-compose.mesh.yml up

services:
  gateway:
    build:
      context: ..
      dockerfile: Dockerfile
    volumes:
      - ../config/profiles/gateway.yaml:/etc/astromesh/runtime.yaml:ro
      - ../config/channels.yaml:/etc/astromesh/channels.yaml:ro
    ports:
      - "8000:8000"
    depends_on:
      worker:
        condition: service_started
    networks:
      - astromesh-mesh

  worker:
    build:
      context: ..
      dockerfile: Dockerfile
    volumes:
      - ../config/profiles/worker.yaml:/etc/astromesh/runtime.yaml:ro
      - ../config/agents:/etc/astromesh/agents:ro
      - ../config/providers.yaml:/etc/astromesh/providers.yaml:ro
    depends_on:
      inference:
        condition: service_started
      redis:
        condition: service_started
      postgres:
        condition: service_started
    networks:
      - astromesh-mesh

  inference:
    build:
      context: ..
      dockerfile: Dockerfile
    volumes:
      - ../config/profiles/inference.yaml:/etc/astromesh/runtime.yaml:ro
      - ../config/providers.yaml:/etc/astromesh/providers.yaml:ro
    networks:
      - astromesh-mesh

  # --- Supporting infrastructure ---

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - astromesh-mesh

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - astromesh-mesh

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: astromesh
      POSTGRES_USER: astromesh
      POSTGRES_PASSWORD: astromesh
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - astromesh-mesh

volumes:
  ollama-models:
  redis-data:
  postgres-data:

networks:
  astromesh-mesh:
    driver: bridge
```

**Step 2: Commit**

```bash
git add docker/docker-compose.mesh.yml
git commit -m "feat: add Docker Compose mesh for multi-node local development

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Integration tests and full validation

**Files:**
- Create: `tests/test_mesh_integration.py`

**Step 1: Write integration tests**

Create `tests/test_mesh_integration.py`:

```python
"""Integration tests for Astromesh OS Phase 2 — services and peers."""

import pytest
from httpx import ASGITransport, AsyncClient

from astromesh.api.main import app
from astromesh.api.routes import system
from astromesh.runtime.engine import AgentRuntime
from astromesh.runtime.peers import PeerClient
from astromesh.runtime.services import ServiceManager


@pytest.fixture
async def worker_node(tmp_path):
    """Simulate a worker node with agents enabled, inference disabled."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test.agent.yaml").write_text("""
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: test-agent
  version: "1.0.0"
  namespace: testing
spec:
  identity:
    display_name: Test Agent
    description: A test agent
  model:
    primary:
      provider: ollama
      model: test-model
      endpoint: http://localhost:11434
  prompts:
    system: "You are a test agent."
  orchestration:
    pattern: react
    max_iterations: 3
""")

    sm = ServiceManager({"agents": True, "inference": False, "channels": False})
    pc = PeerClient([
        {"name": "inference-1", "url": "http://inference:8000", "services": ["inference"]},
    ])

    runtime = AgentRuntime(config_dir=str(tmp_path), service_manager=sm, peer_client=pc)
    await runtime.bootstrap()
    system.set_runtime(runtime)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, runtime

    system.set_runtime(None)
    await pc.close()


async def test_worker_node_status(worker_node):
    """Worker node reports its services and peers."""
    client, runtime = worker_node
    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["agents_loaded"] == 1
    assert data["services"]["agents"] is True
    assert data["services"]["inference"] is False
    assert data["services"]["channels"] is False
    assert len(data["peers"]) == 1
    assert data["peers"][0]["name"] == "inference-1"


async def test_worker_node_doctor(worker_node):
    """Worker node doctor includes peer check."""
    client, runtime = worker_node
    resp = await client.get("/v1/system/doctor")
    assert resp.status_code == 200
    data = resp.json()

    assert data["checks"]["runtime"]["status"] == "ok"
    # Peer will be unreachable in test (no actual peer running)
    assert "peer:inference-1" in data["checks"]
    assert data["checks"]["peer:inference-1"]["status"] == "unreachable"


@pytest.fixture
async def gateway_node(tmp_path):
    """Simulate a gateway node with only api and channels."""
    sm = ServiceManager({"agents": False, "inference": False, "tools": False, "memory": False, "rag": False})
    pc = PeerClient([
        {"name": "worker-1", "url": "http://worker:8000", "services": ["agents", "tools", "memory"]},
    ])

    runtime = AgentRuntime(config_dir=str(tmp_path), service_manager=sm, peer_client=pc)
    await runtime.bootstrap()
    system.set_runtime(runtime)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, runtime

    system.set_runtime(None)
    await pc.close()


async def test_gateway_node_no_agents(gateway_node):
    """Gateway node has no agents loaded."""
    client, runtime = gateway_node
    resp = await client.get("/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents_loaded"] == 0
    assert data["services"]["agents"] is False
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/test_mesh_integration.py -v`
Expected: ALL PASS

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS (no regressions)

**Step 4: Lint all new code**

Run: `uv run ruff check astromesh/runtime/services.py astromesh/runtime/peers.py astromesh/api/routes/system.py daemon/astromeshd.py cli/commands/peers.py cli/commands/services.py tests/test_services.py tests/test_peers.py tests/test_engine_services.py tests/test_mesh_integration.py`
Run: `uv run ruff format astromesh/runtime/services.py astromesh/runtime/peers.py astromesh/api/routes/system.py daemon/astromeshd.py cli/commands/peers.py cli/commands/services.py tests/test_services.py tests/test_peers.py tests/test_engine_services.py tests/test_mesh_integration.py`

**Step 5: Commit**

```bash
git add tests/test_mesh_integration.py
git commit -m "test: add mesh integration tests for worker and gateway nodes

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task Summary

| Task | Component | Dependencies | Can Parallelize |
|------|-----------|-------------|-----------------|
| 1 | ServiceManager | None | Independent |
| 2 | PeerClient | None | Independent |
| 3 | Config profiles | None | Independent |
| 4 | Runtime modifications | Tasks 1, 2 | After 1+2 |
| 5 | API updates (status/doctor) | Tasks 1, 2 | After 1+2, parallel with 4 |
| 6 | Daemon modifications | Tasks 1, 2 | After 1+2, parallel with 4+5 |
| 7 | CLI peers command | Task 5 | After 5 |
| 8 | CLI services command | Task 5 | After 5, parallel with 7 |
| 9 | Dockerfile | Task 4 | After 4 |
| 10 | Docker Compose mesh | Tasks 3, 9 | After 3+9 |
| 11 | Integration tests | Tasks 4, 5, 6 | After 4+5+6 |

**Parallelization plan:**
- **Wave 1:** Tasks 1, 2, 3 (all independent)
- **Wave 2:** Tasks 4, 5, 6 (depend on 1+2, parallel with each other)
- **Wave 3:** Tasks 7, 8, 9 (depend on prior waves, parallel with each other)
- **Wave 4:** Tasks 10, 11 (Compose + integration tests)
