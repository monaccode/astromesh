from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ToolExecuteRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


@router.get("/tools")
async def list_tools():
    return {"tools": []}


@router.post("/tools/execute")
async def execute_tool(request: ToolExecuteRequest):
    return {"tool": request.tool_name, "result": {}, "status": "not_configured"}
