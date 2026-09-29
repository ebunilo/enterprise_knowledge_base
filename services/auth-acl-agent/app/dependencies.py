"""
FastAPI dependencies: bearer-token authentication and tenant-bound DB sessions.

The tenant is always taken from the validated token, never from a request
header, so a caller cannot evaluate access in another tenant.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims import normalize_claims
from app.config import settings
from app.database import get_db, set_tenant_context
from app.models import Tenant
from app.oidc import validate_token_cached
from app.schemas import UserClaims

logger = logging.getLogger(__name__)

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def get_token_from_header(authorization: Optional[str] = Header(None, alias="Authorization")) -> str:
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authorization header is required", _UNAUTHORIZED)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Expected: Bearer <token>", _UNAUTHORIZED)
    return token.strip()


def resolve_tenant(db: Session, tenant_ref: str) -> Optional[Tenant]:
    """Keycloak sends the tenant slug; accept a UUID too."""
    try:
        condition = Tenant.tenant_id == UUID(tenant_ref)
    except ValueError:
        condition = Tenant.tenant_slug == tenant_ref
    return db.execute(select(Tenant).where(condition)).scalar_one_or_none()


def claims_from_token(token_claims: dict, db: Session) -> UserClaims:
    normalised = normalize_claims(token_claims, settings.oidc_client_id, settings.external_group_set)
    if not normalised["user_id"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing sub claim", _UNAUTHORIZED)
    tenant_ref = normalised.pop("tenant_ref")
    if not tenant_ref:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing tenant_id claim", _UNAUTHORIZED)

    tenant = resolve_tenant(db, tenant_ref)
    if tenant is None or not tenant.is_active:
        logger.warning("Token for unknown or inactive tenant %r", tenant_ref)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant not found or inactive")

    return UserClaims(tenant_id=str(tenant.tenant_id), tenant_slug=tenant.tenant_slug, **normalised)


async def get_token_claims(token: str = Depends(get_token_from_header)) -> dict:
    token_claims = await validate_token_cached(token)
    if not token_claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", _UNAUTHORIZED)
    return token_claims


def get_current_user(
    token_claims: dict = Depends(get_token_claims),
    db: Session = Depends(get_db),
) -> UserClaims:
    # Sync dependency: FastAPI runs it in the threadpool, so the tenant lookup
    # does not block the event loop.
    return claims_from_token(token_claims, db)


def get_tenant_db(
    user: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Session:
    """Database session bound to the caller's tenant for RLS."""
    set_tenant_context(db, UUID(user.tenant_id))
    return db
