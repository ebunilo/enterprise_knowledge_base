"""
FastAPI dependencies for request handling.

This module provides dependency injection functions for FastAPI endpoints,
including tenant context management, authentication, and database sessions.
"""

import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, set_tenant_context

logger = logging.getLogger(__name__)


# ============================================================================
# Tenant Context Dependencies
# ============================================================================

def get_tenant_id(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID")
) -> str:
    """
    Extract and validate tenant ID from request header.
    
    Args:
        x_tenant_id: Tenant ID from X-Tenant-ID header
        
    Returns:
        Validated tenant ID
        
    Raises:
        HTTPException: If tenant ID is missing or invalid
    """
    if not x_tenant_id or not x_tenant_id.strip():
        logger.warning("Request missing X-Tenant-ID header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required"
        )
    
    # Basic validation
    if len(x_tenant_id) > 100:
        logger.warning(f"Invalid tenant ID length: {len(x_tenant_id)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID exceeds maximum length"
        )
    
    logger.debug(f"Extracted tenant ID: {x_tenant_id}")
    return x_tenant_id


def get_db_with_tenant_context(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
) -> Session:
    """
    Get database session with tenant context set for Row-Level Security.
    
    This dependency combines tenant ID extraction and database session
    management, automatically setting the tenant context for RLS policies.
    
    Args:
        tenant_id: Tenant ID from header
        db: Database session
        
    Returns:
        Database session with tenant context set
        
    Raises:
        HTTPException: If tenant context cannot be set
    """
    try:
        if settings.rls_enabled:
            set_tenant_context(db, tenant_id)
            logger.debug(f"Set tenant context to {tenant_id}")
        return db
    except Exception as e:
        logger.error(f"Failed to set tenant context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize tenant context"
        )


# ============================================================================
# Authentication Dependencies
# ============================================================================

def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Verify API key for service-to-service authentication.
    
    This is a simple API key validation for MVP. In production,
    this should be replaced with proper JWT validation or mTLS.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not x_api_key:
        logger.warning("Request missing X-API-Key header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    # Simple validation against configured secret
    # TODO: Replace with proper JWT validation in production
    if x_api_key != settings.secret_key:
        logger.warning("Invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    logger.debug("API key validated successfully")
    return x_api_key


def get_optional_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[str]:
    """
    Get optional API key without enforcing authentication.
    
    Useful for endpoints that support both authenticated and
    unauthenticated access.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        API key if provided, None otherwise
    """
    return x_api_key


# ============================================================================
# Combined Dependencies
# ============================================================================

def get_authenticated_db_with_tenant(
    tenant_id: str = Depends(get_tenant_id),
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
) -> Session:
    """
    Get authenticated database session with tenant context.
    
    This dependency combines authentication, tenant extraction,
    and database session management for secure endpoints.
    
    Args:
        tenant_id: Tenant ID from header
        api_key: Validated API key
        db: Database session
        
    Returns:
        Database session with tenant context set
        
    Raises:
        HTTPException: If authentication fails or tenant context cannot be set
    """
    try:
        if settings.rls_enabled:
            set_tenant_context(db, tenant_id)
            logger.debug(f"Set authenticated tenant context to {tenant_id}")
        return db
    except Exception as e:
        logger.error(f"Failed to set authenticated tenant context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize authenticated session"
        )


# ============================================================================
# Pagination Dependencies
# ============================================================================

def get_pagination_params(
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    Get and validate pagination parameters.
    
    Args:
        limit: Maximum number of items to return (default: 100)
        offset: Number of items to skip (default: 0)
        
    Returns:
        Dictionary with validated pagination parameters
        
    Raises:
        HTTPException: If pagination parameters are invalid
    """
    # Validate limit
    if limit < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be at least 1"
        )
    if limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit cannot exceed 1000"
        )
    
    # Validate offset
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Offset must be non-negative"
        )
    
    return {"limit": limit, "offset": offset}


# ============================================================================
# Request Validation Dependencies
# ============================================================================

def validate_uuid(uuid_str: str, field_name: str = "ID") -> str:
    """
    Validate UUID string format.
    
    Args:
        uuid_str: UUID string to validate
        field_name: Name of the field for error messages
        
    Returns:
        Validated UUID string
        
    Raises:
        HTTPException: If UUID format is invalid
    """
    import uuid
    
    try:
        uuid.UUID(uuid_str)
        return uuid_str
    except ValueError:
        logger.warning(f"Invalid UUID format for {field_name}: {uuid_str}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format. Must be a valid UUID."
        )


def validate_status(status_value: str) -> str:
    """
    Validate document status value.
    
    Args:
        status_value: Status string to validate
        
    Returns:
        Validated status string
        
    Raises:
        HTTPException: If status is invalid
    """
    valid_statuses = ['active', 'archived', 'deleted']
    
    if status_value not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    return status_value

# Made with Bob
