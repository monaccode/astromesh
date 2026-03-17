"""Usage aggregation route — returns token and cost summaries per org."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.organization import OrgMember, Organization
from astromesh_cloud.models.usage_log import UsageLog
from astromesh_cloud.schemas.usage import UsageSummary

router = APIRouter(prefix="/api/v1/orgs", tags=["usage"])


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


@router.get("/{slug}/usage", response_model=UsageSummary)
async def get_usage(
    slug: str,
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_org_id(slug, user, db)

    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    result = await db.execute(
        select(
            func.count().label("total_requests"),
            func.coalesce(func.sum(UsageLog.tokens_in), 0).label("total_tokens_in"),
            func.coalesce(func.sum(UsageLog.tokens_out), 0).label("total_tokens_out"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
        )
        .select_from(UsageLog)
        .where(
            UsageLog.org_id == org_id,
            UsageLog.created_at >= period_start,
            UsageLog.created_at <= period_end,
        )
    )
    row = result.one()

    return UsageSummary(
        total_requests=row.total_requests,
        total_tokens_in=int(row.total_tokens_in),
        total_tokens_out=int(row.total_tokens_out),
        total_cost_usd=row.total_cost_usd,
        period_start=period_start.date().isoformat(),
        period_end=period_end.date().isoformat(),
    )
