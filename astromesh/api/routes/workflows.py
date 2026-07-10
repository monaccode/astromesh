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


class ResumeRequest(BaseModel):
    payload: dict[str, Any] = {}


@router.get("/")
async def list_workflows():
    if not _engine:
        return {"workflows": []}
    return {"workflows": _engine.list_workflows()}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    run = await _engine._store.load(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {
        "run_id": run.run_id,
        "workflow_name": run.workflow_name,
        "status": run.status,
        "current_index": run.current_index,
        "context": run.context,
        "error": run.error,
    }


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, request: ResumeRequest):
    if not _engine:
        raise HTTPException(status_code=503, detail="Workflow engine not initialized")
    try:
        result = await _engine.resume(run_id, request.payload)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    if result.status == "suspended":
        return {"run_id": result.run_id, "status": result.status}
    return {
        "run_id": result.run_id,
        "status": result.status,
        "steps": {
            k: {"status": v.status.value, "output": v.output, "error": v.error}
            for k, v in result.steps.items()
        },
    }


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
        "steps": [{"name": s.name, "type": s.step_type.value} for s in wf.steps],
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
    if result.status == "suspended":
        return {"run_id": result.run_id, "status": result.status}
    return {
        "run_id": result.run_id,
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
