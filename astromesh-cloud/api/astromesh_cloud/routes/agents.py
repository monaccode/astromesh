import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.config import settings
from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.schemas.agent import AgentCreate, AgentListItem, AgentResponse, AgentUpdate
from astromesh_cloud.services import agent_service

router = APIRouter(prefix="/api/v1/orgs/{slug}/agents", tags=["agents"])

# Module-level proxy — set to a RuntimeProxy instance in production via main.py
_proxy = None


async def _get_org_id(slug: str, user: dict, db: AsyncSession) -> str:
    result = await db.execute(
        select(OrgMember.org_id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return str(org_id)


# ---------------------------------------------------------------------------
# List agents
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AgentListItem])
async def list_agents(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agents = await agent_service.get_agents(db, org_id)
    return agents


# ---------------------------------------------------------------------------
# Create agent (status=draft)
# ---------------------------------------------------------------------------

@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    slug: str,
    body: AgentCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    config = body.config.model_dump()

    # Guard: name must be unique within org
    existing = await agent_service.get_agent(db, org_id, config["name"])
    if existing:
        raise HTTPException(status_code=409, detail="Agent name already exists in this organization")

    agent = await agent_service.create_agent(db, org_id, slug, config)
    return agent


# ---------------------------------------------------------------------------
# Get agent detail
# ---------------------------------------------------------------------------

@router.get("/{name}", response_model=AgentResponse)
async def get_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# ---------------------------------------------------------------------------
# Update agent config
# If currently deployed → transition back to draft and remove from runtime
# ---------------------------------------------------------------------------

@router.put("/{name}", response_model=AgentResponse)
async def update_agent(
    slug: str,
    name: str,
    body: AgentUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.status == "deployed" and _proxy is not None:
        try:
            await _proxy.unregister_agent(agent.runtime_name)
        except Exception:
            pass  # best-effort; continue with DB update

    new_config = body.config.model_dump()
    agent.config = new_config
    agent.display_name = new_config["display_name"]
    agent.status = "draft"
    agent.deployed_at = None
    await db.commit()
    await db.refresh(agent)
    return agent


# ---------------------------------------------------------------------------
# Delete agent
# If deployed → remove from runtime first
# ---------------------------------------------------------------------------

@router.delete("/{name}", status_code=204)
async def delete_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.status == "deployed" and _proxy is not None:
        try:
            await _proxy.unregister_agent(agent.runtime_name)
        except Exception:
            pass

    await db.delete(agent)
    await db.commit()


# ---------------------------------------------------------------------------
# Deploy agent → status=deployed
# Enforces max agents limit (default: 5)
# ---------------------------------------------------------------------------

@router.post("/{name}/deploy", response_model=AgentResponse)
async def deploy_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.status == "deployed":
        raise HTTPException(status_code=409, detail="Agent is already deployed")

    deployed_count = await agent_service.count_deployed(db, org_id)
    if deployed_count >= settings.max_agents_per_org:
        raise HTTPException(
            status_code=422,
            detail=f"Deployed agent limit reached ({settings.max_agents_per_org}). Pause an agent before deploying another.",
        )

    if _proxy is not None:
        try:
            runtime_config = dict(agent.config or {})
            runtime_config["name"] = agent.runtime_name
            await _proxy.register_agent(runtime_config)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Runtime registration failed: {exc}") from exc

    agent = await agent_service.update_agent_status(
        db, agent, "deployed", deployed_at=datetime.now(timezone.utc)
    )
    return agent


# ---------------------------------------------------------------------------
# Pause agent → status=paused, remove from runtime
# ---------------------------------------------------------------------------

@router.post("/{name}/pause", response_model=AgentResponse)
async def pause_agent(
    slug: str,
    name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.status != "deployed":
        raise HTTPException(status_code=409, detail="Only deployed agents can be paused")

    if _proxy is not None:
        try:
            await _proxy.unregister_agent(agent.runtime_name)
        except Exception:
            pass

    agent = await agent_service.update_agent_status(db, agent, "paused")
    return agent


# ---------------------------------------------------------------------------
# Test agent — run with a disposable session (no persistent memory side-effects)
# ---------------------------------------------------------------------------

@router.post("/{name}/test")
async def test_agent(
    slug: str,
    name: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)
    agent = await agent_service.get_agent(db, org_id, name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    query: str = body.get("query", "")
    if not query:
        raise HTTPException(status_code=422, detail="'query' is required")

    if _proxy is None:
        return {
            "status": "ok",
            "runtime_available": False,
            "response": "Runtime proxy not configured — cannot execute test query.",
        }

    disposable_session = f"test-{uuid.uuid4().hex}"
    try:
        result = await _proxy.run_agent(
            runtime_name=agent.runtime_name,
            query=query,
            session_id=disposable_session,
            org_slug=slug,
            context=body.get("context"),
        )
        # Clean up ephemeral memory
        try:
            await _proxy.delete_memory(agent.runtime_name, f"{slug}:{disposable_session}")
        except Exception:
            pass
        return {"status": "ok", "runtime_available": True, "response": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Runtime test failed: {exc}") from exc
