from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ToolExecuteRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


@router.get("/tools")
async def list_tools():
    """Todo lo invocable del catálogo: builtins y acciones de integración."""
    from astromesh.integrations import default_catalog
    from astromesh.tools import ToolLoader

    loader = ToolLoader()
    loader.auto_discover()
    tools = [
        {
            "name": loader.get(name).name,
            "description": loader.get(name).description,
            "type": "builtin",
        }
        for name in loader.list_available()
    ]
    for manifest in default_catalog().all():
        tools.extend(
            {
                "name": f"{manifest.slug}_{action.name}",
                "description": action.description,
                "type": "integration",
                "integration": manifest.slug,
                "writes": action.mutates,
            }
            for action in manifest.actions
        )
    return {"tools": tools, "count": len(tools)}


@router.get("/tools/builtin")
async def list_builtin_tools():
    """Return all registered builtin tools with metadata."""
    from astromesh.tools import ToolLoader

    loader = ToolLoader()
    loader.auto_discover()

    tools = []
    for name in loader.list_available():
        tool_cls = loader.get(name)
        tools.append(
            {
                "name": tool_cls.name,
                "description": tool_cls.description,
                "parameters": tool_cls.parameters,
            }
        )

    return {"tools": tools, "count": len(tools)}


@router.post("/tools/execute")
async def execute_tool(request: ToolExecuteRequest):
    return {"tool": request.tool_name, "result": {}, "status": "not_configured"}
