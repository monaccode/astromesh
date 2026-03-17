import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from astromesh_cloud.database import get_db
from astromesh_cloud.models.user import User
from astromesh_cloud.models.organization import Organization, OrgMember
from astromesh_cloud.schemas.auth import OAuthCallback, TokenResponse
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

@router.post("/dev/login", response_model=TokenResponse)
async def dev_login(email: str, name: str, db: AsyncSession = Depends(get_db)):
    """Dev-only: create/login user without OAuth."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
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
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=900,
    )
