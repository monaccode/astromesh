from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.models.user import User
from astromesh_cloud.schemas.organization import OrgResponse, OrgUpdate, MemberInvite, MemberResponse
from astromesh_cloud.config import settings

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])

@router.get("/me", response_model=OrgResponse)
async def get_my_org(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization).join(OrgMember).where(OrgMember.user_id == user["user_id"]).order_by(Organization.created_at).limit(1)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="No organization found")
    return OrgResponse(id=str(org.id), slug=org.slug, name=org.name)

@router.patch("/{slug}", response_model=OrgResponse)
async def update_org(slug: str, body: OrgUpdate, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization).where(Organization.slug == slug))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.name = body.name
    await db.commit()
    await db.refresh(org)
    return OrgResponse(id=str(org.id), slug=org.slug, name=org.name)

@router.get("/{slug}/members")
async def list_members(slug: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OrgMember, User).join(User, OrgMember.user_id == User.id).join(Organization, OrgMember.org_id == Organization.id).where(Organization.slug == slug)
    )
    rows = result.all()
    return [MemberResponse(user_id=str(member.user_id), email=u.email, name=u.name, role=member.role) for member, u in rows]

@router.post("/{slug}/members/invite", status_code=201)
async def invite_member(slug: str, body: MemberInvite, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.count()).select_from(OrgMember).join(Organization).where(Organization.slug == slug)
    )
    count = result.scalar_one()
    if count >= settings.max_members_per_org:
        raise HTTPException(status_code=429, detail=f"Maximum {settings.max_members_per_org} members per org")
    return {"status": "invited", "email": body.email}
