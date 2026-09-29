"""
FastAPI dependencies: service authentication, tenant resolution, DB sessions.

Every /api/v1 route requires a service API key. This API is the canonical
store behind the RAG pipeline, not a user-facing API; end-user authorization
happens in auth-acl-agent before any chunk text reaches the LLM.
"""

import hmac
import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db, set_tenant_context

logger = logging.getLogger(__name__)


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """Reject requests without a valid service API key (constant-time compare)."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not any(hmac.compare_digest(x_api_key.encode(), key.encode()) for key in settings.api_keys):
        logger.warning("Invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def get_tenant_id(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID", min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> UUID:
    """Resolve X-Tenant-ID (UUID or slug) to an active tenant's UUID."""
    tenant = crud.resolve_tenant(db, x_tenant_id)
    if tenant is None or not tenant.is_active:
        # Same response for unknown and inactive tenants to avoid enumeration.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.tenant_id


def get_db_with_tenant_context(
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Session:
    """Database session bound to the request's tenant for RLS."""
    set_tenant_context(db, tenant_id)
    return db


def get_pagination_params(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    return {"limit": limit, "offset": offset}
