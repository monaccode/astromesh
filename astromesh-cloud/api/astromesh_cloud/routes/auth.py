import uuid
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from astromesh_cloud.database import get_db
from astromesh_cloud.models.user import User
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.schemas.auth import DevLoginRequest, DevLoginResponse, OAuthCallback, TokenResponse
from astromesh_cloud.services.auth_service import create_access_token, create_refresh_token, verify_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/google", response_model=TokenResponse)
async def google_callback(callback: OAuthCallback, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="Google OAuth not yet implemented")

@router.post("/github", response_model=TokenResponse)
async def github_callback(callback: OAuthCallback, db: AsyncSession = Depends(get_db)):
    raise HTTPException(status_code=501, detail="GitHub OAuth not yet implemented")

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_token(refresh_token, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=900,
    )

@router.post("/logout")
async def logout():
    return {"status": "ok"}

@router.post("/dev/login", response_model=DevLoginResponse)
async def dev_login(
    payload: DevLoginRequest | None = Body(default=None),
    email: str | None = None,
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Dev-only: create/login user without OAuth."""
    if payload is not None:
        email = payload.email
        name = payload.name

    if not email or not name:
        raise HTTPException(
            status_code=422,
            detail="Provide 'email' and 'name' via JSON body or query params.",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    org_slug: str | None = None
    if not user:
        user = User(email=email, name=name, auth_provider="google", auth_provider_id=f"dev-{email}")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        base_slug = email.split("@")[0].lower().replace(".", "-")
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        org = Organization(slug=slug, name=f"{name}'s Org")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        member = OrgMember(user_id=user.id, org_id=org.id, role="owner")
        db.add(member)
        await db.commit()
        org_slug = org.slug
    else:
        org_result = await db.execute(
            select(Organization)
            .join(OrgMember, OrgMember.org_id == Organization.id)
            .where(OrgMember.user_id == user.id)
            .order_by(Organization.created_at)
            .limit(1)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            base_slug = email.split("@")[0].lower().replace(".", "-")
            slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            org = Organization(slug=slug, name=f"{name}'s Org")
            db.add(org)
            await db.commit()
            await db.refresh(org)
            member = OrgMember(user_id=user.id, org_id=org.id, role="owner")
            db.add(member)
            await db.commit()
        org_slug = org.slug

    access = create_access_token(str(user.id), user.email)
    refresh = create_refresh_token(str(user.id))
    return DevLoginResponse(
        token=access,
        refresh_token=refresh,
        expires_in=900,
        user={"email": user.email, "name": user.name},
        org_slug=org_slug,
    )
