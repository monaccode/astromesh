from fastapi import FastAPI
from astromech import __version__
from astromech.api.routes import agents, memory, tools, rag, whatsapp
from astromech.api import ws

app = FastAPI(title="Astromech Agent Runtime API", version=__version__)

app.include_router(agents.router, prefix="/v1")
app.include_router(memory.router, prefix="/v1")
app.include_router(tools.router, prefix="/v1")
app.include_router(rag.router, prefix="/v1")
app.include_router(ws.router, prefix="/v1")
app.include_router(whatsapp.router, prefix="/v1")


@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": __version__}
