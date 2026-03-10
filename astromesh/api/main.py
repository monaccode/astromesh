from fastapi import FastAPI
from astromesh import __version__
from astromesh.api.routes import (
    agents,
    memory,
    tools,
    rag,
    whatsapp,
    system,
    mesh,
    traces,
    metrics,
)
from astromesh.api import ws

app = FastAPI(title="Astromesh Agent Runtime API", version=__version__)

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


@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": __version__}
