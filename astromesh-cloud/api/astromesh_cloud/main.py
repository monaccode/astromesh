from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from astromesh_cloud.routes import auth as auth_routes
from astromesh_cloud.routes import organizations as org_routes
from astromesh_cloud.routes import agents as agent_routes
from astromesh_cloud.routes import keys as keys_routes
from astromesh_cloud.routes import execution as execution_routes
from astromesh_cloud.routes import usage as usage_routes
from astromesh_cloud.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    from astromesh_cloud.services.runtime_proxy import RuntimeProxy
    from astromesh_cloud.services.reconciliation import reconcile_agents
    from astromesh_cloud.database import async_session
    from astromesh_cloud.routes.execution import set_proxy

    await init_db()

    proxy = RuntimeProxy()
    set_proxy(proxy)
    if await proxy.health():
        async with async_session() as db:
            await reconcile_agents(db, proxy)
    yield
    await proxy.close()


app = FastAPI(title="Astromesh Cloud", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(org_routes.router)
app.include_router(agent_routes.router)
app.include_router(keys_routes.router)
app.include_router(execution_routes.router)
app.include_router(usage_routes.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "astromesh-cloud"}
