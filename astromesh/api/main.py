import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from astromesh import __version__
from astromesh.api.routes import (
    agents,
    dashboard,
    memory,
    tools,
    rag,
    whatsapp,
    system,
    mesh,
    traces,
    metrics,
    workflows,
    templates,
)
from astromesh.api import ws

app = FastAPI(title="Astromesh Agent Runtime API", version=__version__)

# CORS for standalone Forge
cors_origins = os.getenv("ASTROMESH_CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router, prefix="/v1")
app.include_router(memory.router, prefix="/v1")
app.include_router(tools.router, prefix="/v1")
app.include_router(rag.router, prefix="/v1")
app.include_router(ws.router, prefix="/v1")
app.include_router(whatsapp.router, prefix="/v1")
app.include_router(system.router, prefix="/v1")
app.include_router(mesh.router, prefix="/v1")
app.include_router(traces.router, prefix="/v1")
app.include_router(metrics.router, prefix="/v1")
app.include_router(workflows.router, prefix="/v1")
app.include_router(dashboard.router, prefix="/v1")
app.include_router(templates.router, prefix="/v1")

# Optional Forge static files (embedded mode)
forge_static = Path(__file__).parent.parent / "static" / "forge"
if forge_static.exists():
    app.mount("/forge", StaticFiles(directory=str(forge_static), html=True), name="forge")


@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": __version__}
