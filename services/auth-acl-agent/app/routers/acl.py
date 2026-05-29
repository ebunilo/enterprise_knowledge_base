"""
Access Control List (ACL) API endpoints.

This module provides endpoints for access authorization checks,
chunk filtering, and retrieval filter building.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import acl
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import (
    AccessCheckRequest,
    AccessDecision,
    BatchAccessCheckRequest,
    BatchAccessCheckResponse,
    FilterChunksRequest,
    FilterChunksResponse,
    RetrievalFilterRequest,
    RetrievalFilterResponse,
    UserClaims,
    UserPermissionsResponse,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# Access Authorization Endpoints
# ============================================================================

@router.post(
    "/authorize",
    response_model=AccessDecision,
    summary="Check document/chunk access",
    description="Check if user can access a specific document or chunk",
    tags=["Access Control"]
)
async def authorize_access(
    request: AccessCheckRequest,
    user_claims: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if user can access a document or chunk.
    
    Args:
        request: Access check request with document_id or chunk_id
        user_claims: User claims from token
        db: Database session
        
    Returns:
        AccessDecision with granted/denied and reason
        
    Raises:
        400: If neither document_id nor chunk_id is provided
    """
    if not request.document_id and not request.chunk_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either document_id or chunk_id must be provided"
        )
    
    item_id = request.document_id or request.chunk_id
    item_type = "document" if request.document_id else "chunk"
    
    logger.debug(f"Checking access for user {user_claims.user_id} to {item_type} {item_id}")
    
    # TODO: In production, fetch document/chunk metadata from canonical-db-agent
    # For MVP, we'll use placeholder values
    granted, reason = acl.can_access(
        user_claims=user_claims,
        document_id=item_id,
        tenant_id=user_claims.tenant_id,
        classification="INTERNAL_GENERAL",
        status="active",
        policy=None
    )
    
    # Cache the decision
    acl.cache_access_decision(
        user_id=user_claims.user_id,
        item_id=item_id,
        granted=granted,
        reason=reason
    )
    
    logger.info(f"Access {'' if granted else 'denied'} for user {user_claims.user_id}: {reason}")
    
    return AccessDecision(
        granted=granted,
        reason=reason,
        checked_at=datetime.utcnow(),
        user_id=user_claims.user_id,
        item_id=item_id,
        item_type=item_type
    )


@router.post(
    "/authorize/batch",
    response_model=BatchAccessCheckResponse,
    summary="Batch access check",
    description="Check access to multiple documents or chunks",
    tags=["Access Control"]
)
async def authorize_batch(
    request: BatchAccessCheckRequest,
    user_claims: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check access to multiple documents or chunks.
    
    Args:
        request: Batch access check request
        user_claims: User claims from token
        db: Database session
        
    Returns:
        BatchAccessCheckResponse with results map
        
    Raises:
        400: If neither document_ids nor chunk_ids is provided
    """
    if not request.document_ids and not request.chunk_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either document_ids or chunk_ids must be provided"
        )
    
    ids_to_check = request.document_ids or request.chunk_ids
    
    logger.debug(f"Batch checking access for {len(ids_to_check)} items")
    
    # Perform batch access check
    results = acl.batch_check_access(
        user_claims=user_claims,
        document_ids=ids_to_check,
        db=db
    )
    
    granted_count = sum(1 for granted in results.values() if granted)
    denied_count = len(results) - granted_count
    
    logger.info(f"Batch check complete: {granted_count} granted, {denied_count} denied")
    
    return BatchAccessCheckResponse(
        results=results,
        granted_count=granted_count,
        denied_count=denied_count
    )


# ============================================================================
# Chunk Filtering Endpoints
# ============================================================================

@router.post(
    "/filter",
    response_model=FilterChunksResponse,
    summary="Filter chunk IDs by access",
    description="Filter a list of chunk IDs to only those the user can access",
    tags=["Access Control"]
)
async def filter_chunks(
    request: FilterChunksRequest,
    user_claims: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Filter chunk IDs to only those the user can access.
    
    This is a critical security boundary before context building.
    
    Args:
        request: Filter request with chunk IDs
        user_claims: User claims from token
        db: Database session
        
    Returns:
        FilterChunksResponse with authorized and denied chunk IDs
    """
    logger.debug(f"Filtering {len(request.chunk_ids)} chunks for user {user_claims.user_id}")
    
    # Filter chunks by access
    authorized, denied = acl.filter_authorized_chunks(
        user_claims=user_claims,
        chunk_ids=request.chunk_ids,
        db=db
    )
    
    logger.info(
        f"Filtered chunks: {len(authorized)} authorized, {len(denied)} denied "
        f"out of {len(request.chunk_ids)} total"
    )
    
    return FilterChunksResponse(
        authorized_chunk_ids=authorized,
        denied_chunk_ids=denied,
        total_requested=len(request.chunk_ids),
        total_authorized=len(authorized)
    )


# ============================================================================
# Retrieval Filter Endpoints
# ============================================================================

@router.post(
    "/retrieval-filter",
    response_model=RetrievalFilterResponse,
    summary="Build retrieval filter",
    description="Build metadata filter for pre-filtering retrieval results",
    tags=["Access Control"]
)
async def build_retrieval_filter_endpoint(
    request: RetrievalFilterRequest,
    user_claims: UserClaims = Depends(get_current_user)
):
    """
    Build metadata filter for pre-filtering retrieval results.
    
    Used by Qdrant, BM25, and Knowledge Graph retrievers.
    
    Args:
        request: Retrieval filter request
        user_claims: User claims from token
        
    Returns:
        RetrievalFilterResponse with metadata filter
    """
    logger.debug(f"Building retrieval filter for user {user_claims.user_id}")
    
    # Build filter
    filter_dict = acl.build_retrieval_filter(user_claims)
    
    logger.info(f"Built retrieval filter for user {user_claims.user_id}")
    
    return RetrievalFilterResponse(
        filter=filter_dict,
        user_id=user_claims.user_id,
        tenant_id=user_claims.tenant_id
    )


# ============================================================================
# User Permissions Endpoints
# ============================================================================

@router.get(
    "/user/permissions",
    response_model=UserPermissionsResponse,
    summary="Get user permissions",
    description="Get summary of user's permissions and accessible classifications",
    tags=["Access Control"]
)
async def get_user_permissions(
    user_claims: UserClaims = Depends(get_current_user)
):
    """
    Get summary of user's permissions.
    
    Args:
        user_claims: User claims from token
        
    Returns:
        UserPermissionsResponse with permissions summary
    """
    logger.debug(f"Getting permissions for user {user_claims.user_id}")
    
    # Get permissions summary
    permissions = acl.get_user_permissions_summary(user_claims)
    
    return UserPermissionsResponse(**permissions)


# ============================================================================
# Cache Management Endpoints
# ============================================================================

@router.post(
    "/cache/invalidate/user",
    summary="Invalidate user cache",
    description="Invalidate all cached access decisions for the current user",
    tags=["Cache Management"]
)
async def invalidate_user_cache(
    user_claims: UserClaims = Depends(get_current_user)
):
    """
    Invalidate all cached access decisions for the current user.
    
    Args:
        user_claims: User claims from token
        
    Returns:
        Cache invalidation result
    """
    logger.info(f"Invalidating cache for user {user_claims.user_id}")
    
    count = acl.invalidate_user_cache(user_claims.user_id)
    
    return {
        "message": "User cache invalidated",
        "user_id": user_claims.user_id,
        "entries_deleted": count
    }


@router.post(
    "/cache/invalidate/document/{document_id}",
    summary="Invalidate document cache",
    description="Invalidate all cached access decisions for a document",
    tags=["Cache Management"]
)
async def invalidate_document_cache(
    document_id: UUID,
    user_claims: UserClaims = Depends(get_current_user)
):
    """
    Invalidate all cached access decisions for a document.
    
    Args:
        document_id: Document UUID
        user_claims: User claims from token
        
    Returns:
        Cache invalidation result
    """
    logger.info(f"Invalidating cache for document {document_id}")
    
    count = acl.invalidate_document_cache(document_id)
    
    return {
        "message": "Document cache invalidated",
        "document_id": str(document_id),
        "entries_deleted": count
    }

# Made with Bob
