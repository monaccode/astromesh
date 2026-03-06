from fastapi import FastAPI
from astromech import __version__
from astromech.api.routes import agents

app = FastAPI(title="Astromech Agent Runtime API", version=__version__)
app.include_router(agents.router, prefix="/v1")

@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": __version__}
