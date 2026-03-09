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
    all_nodes = [n.to_dict() for n in mesh._cluster.nodes.values()]
    return {"nodes": all_nodes}


@router.post("/election")
async def mesh_election(request: ElectionRequest):
    mesh = _require_mesh()
    if _elector:
        _elector.elect()
    return {"leader_id": mesh.cluster_state().leader_id}
