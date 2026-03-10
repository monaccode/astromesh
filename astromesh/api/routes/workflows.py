# astromesh/api/routes/workflows.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/workflows", tags=["workflows"])

_engine = None


def set_workflow_engine(engine) -> None:
    global _engine
    _engine = engine


class WorkflowRunRequest(BaseModel):
    query: str = ""
    trigger: dict[str, Any] | None = None


@router.get("/")
async def list_workflows():
    if not _engine:
        return {"workflows": []}
    return {"workflows": _engine.list_workflows()}


@router.get("/{name}")
async def get_workflow(name: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    wf = _engine.get_workflow(name)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return {
        "name": wf.name,
        "version": wf.version,
        "namespace": wf.namespace,
        "description": wf.description,
        "trigger": wf.trigger,
        "timeout_seconds": wf.timeout_seconds,
        "steps": [
            {"name": s.name, "type": s.step_type.value}
            for s in wf.steps
        ],
    }


@router.post("/{name}/run")
async def run_workflow(name: str, request: WorkflowRunRequest):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    trigger = request.trigger or {"query": request.query}
    try:
        result = await _engine.run(name, trigger=trigger)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "workflow_name": result.workflow_name,
        "status": result.status,
        "output": result.output,
        "steps": {
            k: {"status": v.status.value, "output": v.output, "error": v.error}
            for k, v in result.steps.items()
        },
        "trace": result.trace,
        "duration_ms": result.duration_ms,
    }
