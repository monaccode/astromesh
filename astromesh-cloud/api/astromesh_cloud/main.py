from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from astromesh_cloud.routes import auth as auth_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Astromesh Cloud", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "astromesh-cloud"}
