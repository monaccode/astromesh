"""Execution proxy route — forwards agent run requests to the Astromesh runtime."""
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.config import settings
from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.agent import Agent
from astromesh_cloud.models.organization import OrgMember, Organization
from astromesh_cloud.models.provider_key import ProviderKey
from astromesh_cloud.models.usage_log import UsageLog
from astromesh_cloud.services.encryption import decrypt_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orgs/{slug}/agents", tags=["execution"])

# Module-level proxy — injected by main.py lifespan via set_proxy()
_proxy = None


def set_proxy(proxy) -> None:
    global _proxy
    _proxy = proxy


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    query: str
    session_id: str = "default"
    context: dict | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_org(slug: str, user: dict, db: AsyncSession) -> tuple[str, str]:
    """Return (org_id_str, org_id_uuid_str) for the org the user belongs to."""
    result = await db.execute(
        select(OrgMember.org_id, Organization.id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return str(row[0]), str(row[1])


# ---------------------------------------------------------------------------
# POST /api/v1/orgs/{slug}/agents/{name}/run
# ---------------------------------------------------------------------------


@router.post("/{name}/run")
async def run_agent(
    slug: str,
    name: str,
    body: RunRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Resolve org membership
    org_id_str, _ = await _resolve_org(slug, user, db)

    # 2. Fetch agent — must exist and be deployed
    agent_result = await db.execute(
        select(Agent)
        .join(Organization, Agent.org_id == Organization.id)
        .where(Organization.slug == slug, Agent.name == name)
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != "deployed":
        raise HTTPException(status_code=422, detail="Agent is not deployed")

    # 3. Rate limiting: count today's UsageLog entries for the org
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    count_result = await db.execute(
        select(func.count())
        .select_from(UsageLog)
        .where(UsageLog.org_id == agent.org_id, UsageLog.created_at >= today_start)
    )
    today_count = count_result.scalar_one()
    if today_count >= settings.max_requests_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Daily request limit of {settings.max_requests_per_day} reached.",
        )

    # 4. BYOK provider key lookup for non-free (non-ollama) models
    provider_key_plaintext: str | None = None
    provider_name: str | None = None
    model_config = (agent.config or {}).get("model", "")
    if "/" in model_config:
        provider_name = model_config.split("/", 1)[0]
    else:
        provider_name = "ollama"

    if provider_name and provider_name != "ollama":
        pk_result = await db.execute(
            select(ProviderKey).where(
                ProviderKey.org_id == agent.org_id,
                ProviderKey.provider == provider_name,
            )
        )
        provider_key_row = pk_result.scalar_one_or_none()
        if provider_key_row:
            try:
                provider_key_plaintext = decrypt_key(provider_key_row.encrypted_key)
            except Exception:
                logger.warning("Failed to decrypt provider key for %s/%s", slug, name)

    # 5. Proxy to runtime
    if _proxy is None:
        raise HTTPException(status_code=503, detail="Runtime proxy not available")

    try:
        result = await _proxy.run_agent(
            runtime_name=agent.runtime_name,
            query=body.query,
            session_id=body.session_id,
            org_slug=slug,
            context=body.context,
            provider_key=provider_key_plaintext,
            provider_name=provider_name if provider_key_plaintext else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Runtime error: {exc}") from exc

    # 6. Log usage
    usage_data = result.get("usage") or {}
    log = UsageLog(
        org_id=agent.org_id,
        agent_id=agent.id,
        tokens_in=usage_data.get("tokens_in", 0),
        tokens_out=usage_data.get("tokens_out", 0),
        model=model_config or "unknown",
        cost_usd=usage_data.get("cost_usd", 0.0),
    )
    db.add(log)
    await db.commit()

    # 7. Return answer + steps + usage
    return {
        "answer": result.get("answer", ""),
        "steps": result.get("steps", []),
        "usage": usage_data,
    }
