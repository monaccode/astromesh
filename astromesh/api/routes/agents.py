from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-memory storage (will be replaced by runtime in production)
_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class AgentRunRequest(BaseModel):
    query: str
    session_id: str = "default"
    context: dict | None = None


class AgentRunResponse(BaseModel):
    answer: str
    steps: list[dict] = []


@router.get("/agents")
async def list_agents():
    if _runtime:
        return {"agents": _runtime.list_agents()}
    return {"agents": []}


@router.get("/agents/{agent_name}")
async def get_agent(agent_name: str):
    if not _runtime:
        raise HTTPException(status_code=404, detail="Runtime not initialized")
    agent = _runtime._agents.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {
        "name": agent.name,
        "version": agent.version,
        "namespace": agent.namespace,
        "description": agent.description,
    }


@router.post("/agents", status_code=201)
async def create_agent(config: dict):
    """Register a new agent dynamically."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        await _runtime.register_agent(config)
        name = config.get("metadata", {}).get("name") or config.get("spec", {}).get("identity", {}).get("name", "unknown")
        return {"name": name, "status": "registered"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """Remove a dynamically registered agent."""
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        _runtime.unregister_agent(agent_name)
        return {"name": agent_name, "status": "removed"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_name}/run")
async def run_agent(agent_name: str, request: AgentRunRequest):
    if not _runtime:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    try:
        result = await _runtime.run(agent_name, request.query, request.session_id, request.context)
        return AgentRunResponse(answer=result.get("answer", ""), steps=result.get("steps", []))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
