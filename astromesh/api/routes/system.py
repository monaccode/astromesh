"""System management endpoints for Astromesh Node."""

import os
import time

from fastapi import APIRouter
from pydantic import BaseModel

from astromesh import __version__

router = APIRouter(prefix="/system", tags=["system"])

_runtime = None
_start_time = time.time()


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class CheckResult(BaseModel):
    status: str
    message: str = ""


class StatusResponse(BaseModel):
    version: str
    uptime_seconds: float
    mode: str
    agents_loaded: int
    pid: int
    services: dict[str, bool] = {}
    peers: list[dict] = []
    mesh: dict | None = None


class DoctorResponse(BaseModel):
    healthy: bool
    checks: dict[str, CheckResult]


def _detect_mode() -> str:
    if os.path.exists("/etc/astromesh/runtime.yaml"):
        return "system"
    return "dev"


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

    return StatusResponse(
        version=__version__,
        uptime_seconds=round(time.time() - _start_time, 2),
        mode=_detect_mode(),
        agents_loaded=agents_loaded,
        pid=os.getpid(),
        services=services,
        peers=peers,
        mesh=mesh_info,
    )


@router.get("/doctor", response_model=DoctorResponse)
async def system_doctor():
    checks: dict[str, CheckResult] = {}

    if not _runtime:
        checks["runtime"] = CheckResult(status="unavailable", message="Runtime not initialized")
        return DoctorResponse(healthy=False, checks=checks)

    checks["runtime"] = CheckResult(status="ok", message="Runtime initialized")

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

    # Check peers
    if hasattr(_runtime, "peer_client") and _runtime.peer_client:
        for peer in _runtime.peer_client.list_peers():
            healthy = await _runtime.peer_client.health_check(peer["name"])
            checks[f"peer:{peer['name']}"] = CheckResult(
                status="ok" if healthy else "unreachable",
                message=f"Peer {peer['name']} at {peer['url']}",
            )

    all_ok = all(c.status == "ok" for c in checks.values())
    return DoctorResponse(healthy=all_ok, checks=checks)
