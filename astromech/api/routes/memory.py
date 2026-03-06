from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class MemoryQueryRequest(BaseModel):
    session_id: str
    query: str = ""
    max_tokens: int = 4096


@router.get("/memory/{agent_name}/history/{session_id}")
async def get_history(agent_name: str, session_id: str, limit: int = 50):
    return {"agent": agent_name, "session_id": session_id, "history": [], "limit": limit}


@router.delete("/memory/{agent_name}/history/{session_id}")
async def clear_history(agent_name: str, session_id: str):
    return {"status": "cleared", "agent": agent_name, "session_id": session_id}


@router.get("/memory/{agent_name}/semantic")
async def search_semantic(agent_name: str, query: str = "", top_k: int = 10):
    return {"agent": agent_name, "query": query, "results": [], "top_k": top_k}
