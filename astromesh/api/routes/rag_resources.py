import copy
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from astromesh.rag.loader import spec_from_raw

router = APIRouter()

_CONFIG_RAG_DIR = "./config/rag"
_pipelines: dict[str, dict] = {}
_seeded = False


def _seed() -> None:
    """Lazily load config/rag/*.rag.yaml into the in-memory store (once)."""
    global _seeded
    if _seeded:
        return
    _seeded = True
    directory = Path(_CONFIG_RAG_DIR)
    if not directory.exists():
        return
    for f in sorted(directory.glob("*.rag.yaml")):
        try:
            raw = yaml.safe_load(f.read_text())
            spec = spec_from_raw(raw)
        except Exception:
            continue  # skip invalid files
        _pipelines[spec.name] = raw


def _summary(raw: dict) -> dict:
    meta = raw.get("metadata", {})
    spec = raw.get("spec", {})
    return {
        "name": meta.get("name", ""),
        "description": spec.get("description", ""),
        "backend": spec.get("vector_store", {}).get("backend", ""),
    }


@router.get("/rag/pipelines")
async def list_pipelines():
    _seed()
    return {"pipelines": [_summary(r) for r in _pipelines.values()]}


@router.get("/rag/pipelines/{name}")
async def get_pipeline(name: str):
    _seed()
    raw = _pipelines.get(name)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {name}")
    return copy.deepcopy(raw)


@router.post("/rag/pipelines", status_code=201)
async def create_pipeline(config: dict):
    _seed()
    try:
        spec = spec_from_raw(config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if spec.name in _pipelines:
        raise HTTPException(status_code=409, detail=f"RAGPipeline already exists: {spec.name}")
    _pipelines[spec.name] = config
    return {"name": spec.name, "status": "created"}


@router.put("/rag/pipelines/{name}")
async def update_pipeline(name: str, config: dict):
    _seed()
    if name not in _pipelines:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {name}")
    try:
        spec_from_raw(config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _pipelines[name] = config
    return {"name": name, "status": "updated"}


@router.delete("/rag/pipelines/{name}")
async def delete_pipeline(name: str):
    _seed()
    if name not in _pipelines:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {name}")
    del _pipelines[name]
    return {"name": name, "status": "removed"}
