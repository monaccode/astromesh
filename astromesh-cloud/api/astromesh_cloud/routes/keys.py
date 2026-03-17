import secrets

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from astromesh_cloud.database import get_db
from astromesh_cloud.middleware.auth import get_current_user
from astromesh_cloud.models.api_key import ApiKey
from astromesh_cloud.models.organization import OrgMember, Organization
from astromesh_cloud.models.provider_key import ProviderKey
from astromesh_cloud.schemas.keys import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    ProviderKeyCreate,
    ProviderKeyResponse,
)
from astromesh_cloud.services.encryption import encrypt_key

router = APIRouter(prefix="/api/v1/orgs/{slug}", tags=["keys"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_org_id(slug: str, user: dict, db: AsyncSession) -> str:
    result = await db.execute(
        select(OrgMember.org_id)
        .join(Organization, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user["user_id"], Organization.slug == slug)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=403, detail="Not a member of this org")
    return str(org_id)


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


@router.get("/keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List API keys for the org — prefix only, full key is never returned."""
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(select(ApiKey).where(ApiKey.org_id == org_id))
    api_keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=str(k.id),
            prefix=k.prefix,
            name=k.name,
            scopes=k.scopes,
            created_at=k.created_at,
        )
        for k in api_keys
    ]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    slug: str,
    body: ApiKeyCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The full key is returned only once."""
    org_id = await _get_org_id(slug, user, db)

    raw_key = f"am_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:12]  # e.g. "am_xxxxxxxxx"
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    api_key = ApiKey(
        org_id=org_id,
        key_hash=key_hash,
        prefix=prefix,
        name=body.name,
        scopes=body.scopes,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    validated = ApiKeyResponse(
        id=str(api_key.id),
        prefix=api_key.prefix,
        name=api_key.name,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
    )
    return ApiKeyCreated(**validated.model_dump(), key=raw_key)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_api_key(
    slug: str,
    key_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (delete) an API key."""
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == org_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(api_key)
    await db.commit()


# ---------------------------------------------------------------------------
# Provider Keys
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=list[ProviderKeyResponse])
async def list_provider_keys(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List configured provider credentials — encrypted keys are never returned."""
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(select(ProviderKey).where(ProviderKey.org_id == org_id))
    provider_keys = result.scalars().all()
    return [
        ProviderKeyResponse(
            id=str(pk.id),
            provider=pk.provider,
            created_at=pk.created_at,
        )
        for pk in provider_keys
    ]


@router.post("/providers", response_model=ProviderKeyResponse, status_code=201)
async def upsert_provider_key(
    slug: str,
    body: ProviderKeyCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save (upsert) a Fernet-encrypted provider key."""
    org_id = await _get_org_id(slug, user, db)

    # Delete any existing key for this provider (upsert semantics)
    await db.execute(
        delete(ProviderKey).where(
            ProviderKey.org_id == org_id,
            ProviderKey.provider == body.provider,
        )
    )

    encrypted = encrypt_key(body.key)
    provider_key = ProviderKey(
        org_id=org_id,
        provider=body.provider,
        encrypted_key=encrypted,
    )
    db.add(provider_key)
    await db.commit()
    await db.refresh(provider_key)

    return ProviderKeyResponse(
        id=str(provider_key.id),
        provider=provider_key.provider,
        created_at=provider_key.created_at,
    )


@router.delete("/providers/{provider}", status_code=204)
async def delete_provider_key(
    slug: str,
    provider: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a provider key by provider name."""
    org_id = await _get_org_id(slug, user, db)
    result = await db.execute(
        select(ProviderKey).where(
            ProviderKey.org_id == org_id,
            ProviderKey.provider == provider,
        )
    )
    provider_key = result.scalar_one_or_none()
    if not provider_key:
        raise HTTPException(status_code=404, detail="Provider key not found")
    await db.delete(provider_key)
    await db.commit()
