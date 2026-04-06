import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from astromesh import __version__
from astromesh.api import ws
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
from astromesh.logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap AgentRuntime for `uvicorn astromesh.api.main:app` (astromeshd sets runtime before serve)."""
    skip = os.environ.get("ASTROMESH_SKIP_RUNTIME", "").lower() in ("1", "true", "yes")
    if skip:
        yield
        return

    from astromesh.api.routes import agents as agents_route
    from astromesh.api.routes import memory as memory_route
    from astromesh.api.routes import system as system_route
    from astromesh.api.routes import whatsapp as whatsapp_route
    from astromesh.runtime.engine import AgentRuntime

    if agents_route._runtime is not None:
        # Runtime was injected before serve (e.g. astromeshd). Keep other route modules
        # in sync — tests that temporarily replace agents._runtime can otherwise leave
        # memory/system/whatsapp unwired on the next lifespan if teardown order restores
        # agents._runtime after the prior finally cleared the other routes.
        r = agents_route._runtime
        system_route.set_runtime(r)
        memory_route.set_runtime(r)
        whatsapp_route.set_runtime(r)
        yield
        return

    config_dir = os.environ.get("ASTROMESH_CONFIG_DIR", "config")
    runtime = AgentRuntime(config_dir=config_dir)
    try:
        await runtime.bootstrap()
    except Exception:
        logger.exception("AgentRuntime bootstrap failed (config_dir=%s)", config_dir)
        raise

    n_agents = len(runtime.list_agents())
    logger.info(
        "AgentRuntime ready: config_dir=%s agents_loaded=%d",
        config_dir,
        n_agents,
    )

    agents_route.set_runtime(runtime)
    system_route.set_runtime(runtime)
    memory_route.set_runtime(runtime)
    whatsapp_route.set_runtime(runtime)

    try:
        yield
    finally:
        agents_route.set_runtime(None)
        system_route.set_runtime(None)
        memory_route.set_runtime(None)
        whatsapp_route.set_runtime(None)


app = FastAPI(
    title="Astromesh Agent Runtime API",
    version=__version__,
    lifespan=lifespan,
)

# CORS — allow Cortex (Electron), Forge, and any origin for Cloud Run deployments
cors_origins = os.getenv("ASTROMESH_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
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
