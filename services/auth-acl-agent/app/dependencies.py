"""
FastAPI dependencies for request handling.

This module provides dependency injection functions for FastAPI endpoints,
including authentication, user claims extraction, and database sessions.
"""

import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.oidc import extract_user_claims, validate_token_cached
from app.schemas import UserClaims

logger = logging.getLogger(__name__)


# ============================================================================
# Authentication Dependencies
# ============================================================================

async def get_token_from_header(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> str:
    """
    Extract JWT token from Authorization header.
    
    Args:
        authorization: Authorization header value
        
    Returns:
        JWT token string
        
    Raises:
        HTTPException: If token is missing or invalid format
    """
    if not authorization:
        logger.warning("Missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check for Bearer token format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"Invalid Authorization header format: {authorization[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return parts[1]


async def get_current_user(
    token: str = Depends(get_token_from_header)
) -> UserClaims:
    """
    Validate token and extract user claims.
    
    Args:
        token: JWT token from Authorization header
        
    Returns:
        UserClaims object
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Validate token and get claims
        token_claims = await validate_token_cached(token)
        
        if not token_claims:
            logger.warning("Token validation failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Extract and normalize user claims
        user_claims = extract_user_claims(token_claims)
        
        # Validate required claims
        if not user_claims.get("user_id"):
            logger.error("Token missing user_id claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing required claims",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if not user_claims.get("tenant_id"):
            logger.error("Token missing tenant_id claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant_id claim",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Convert to UserClaims model
        claims = UserClaims(**user_claims)
        
        logger.debug(f"Authenticated user: {claims.user_id} (tenant: {claims.tenant_id})")
        return claims
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_optional_user(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Optional[UserClaims]:
    """
    Get user claims if token is provided, otherwise return None.
    
    Useful for endpoints that support both authenticated and unauthenticated access.
    
    Args:
        authorization: Authorization header value
        
    Returns:
        UserClaims if authenticated, None otherwise
    """
    if not authorization:
        return None
    
    try:
        token = await get_token_from_header(authorization)
        return await get_current_user(token)
    except HTTPException:
        return None


# ============================================================================
# Tenant Context Dependencies
# ============================================================================

def get_tenant_id(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")
) -> Optional[str]:
    """
    Extract tenant ID from request header.
    
    Args:
        x_tenant_id: Tenant ID from X-Tenant-ID header
        
    Returns:
        Tenant ID or None
    """
    if settings.require_tenant_id and not x_tenant_id:
        logger.warning("Missing X-Tenant-ID header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required"
        )
    
    return x_tenant_id


def verify_tenant_match(
    user_claims: UserClaims = Depends(get_current_user),
    tenant_id: Optional[str] = Depends(get_tenant_id)
) -> UserClaims:
    """
    Verify that user's tenant matches the requested tenant.
    
    Args:
        user_claims: User claims from token
        tenant_id: Tenant ID from header
        
    Returns:
        UserClaims if tenant matches
        
    Raises:
        HTTPException: If tenant mismatch
    """
    if settings.strict_tenant_isolation and tenant_id:
        if user_claims.tenant_id != tenant_id:
            logger.warning(
                f"Tenant mismatch: user={user_claims.tenant_id}, requested={tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch"
            )
    
    return user_claims


# ============================================================================
# Database Dependencies
# ============================================================================

def get_db_session() -> Session:
    """
    Get database session.
    
    This is a simple wrapper around get_db for consistency.
    
    Returns:
        Database session
    """
    return next(get_db())


# ============================================================================
# Combined Dependencies
# ============================================================================

def get_authenticated_user_with_db(
    user_claims: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> tuple[UserClaims, Session]:
    """
    Get authenticated user and database session together.
    
    Args:
        user_claims: User claims from token
        db: Database session
        
    Returns:
        Tuple of (UserClaims, Session)
    """
    return user_claims, db

# Made with Bob
