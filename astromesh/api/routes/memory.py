from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


class MemoryQueryRequest(BaseModel):
    session_id: str
    query: str = ""
    max_tokens: int = 4096


@router.get("/memory/{agent_name}/history/{session_id}")
async def get_history(agent_name: str, session_id: str, limit: int = 50):
    return {"agent": agent_name, "session_id": session_id, "history": [], "limit": limit}


@router.delete("/memory/{agent_name}/history/{session_id}")
async def clear_history(agent_name: str, session_id: str):
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    agent = _runtime._agents.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    try:
        await agent.memory_manager.clear_history(session_id)
        return {"status": "cleared", "agent": agent_name, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/{agent_name}/semantic")
async def search_semantic(agent_name: str, query: str = "", top_k: int = 10):
    return {"agent": agent_name, "query": query, "results": [], "top_k": top_k}
