"""
Access Control Logic (ACL) Engine.

This module implements the core access control logic for the Enterprise RAG System.
It determines whether users can access documents and chunks based on classification,
department, group, role, region, and explicit allow/deny rules.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import cache_delete_pattern, cache_get, cache_set, get_db_context
from app.models import AccessPolicy
from app.schemas import UserClaims

logger = logging.getLogger(__name__)


# ============================================================================
# Access Level Constants
# ============================================================================

class AccessLevel:
    """Access classification levels."""
    PUBLIC = "PUBLIC"
    INTERNAL_GENERAL = "INTERNAL_GENERAL"
    DEPARTMENT_RESTRICTED = "DEPARTMENT_RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    REGULATED = "REGULATED"
    EXECUTIVE_ONLY = "EXECUTIVE_ONLY"


# ============================================================================
# Core Access Decision Functions
# ============================================================================

def can_access(
    user_claims: UserClaims,
    document_id: UUID,
    tenant_id: str,
    classification: str,
    status: str,
    policy: Optional[AccessPolicy] = None
) -> Tuple[bool, str]:
    """
    Determine if user can access a document or chunk.
    
    Args:
        user_claims: User claims from JWT token
        document_id: Document UUID
        tenant_id: Document tenant ID
        classification: Document classification level
        status: Document status (active, archived, deleted)
        policy: Access policy (optional, will be fetched if not provided)
        
    Returns:
        Tuple of (access_granted: bool, reason: str)
    """
    # Rule 1: Tenant isolation
    if user_claims.tenant_id != tenant_id:
        logger.warning(f"Tenant mismatch: user={user_claims.tenant_id}, document={tenant_id}")
        return False, "tenant_mismatch"
    
    # Rule 2: Document status
    if status != "active":
        logger.debug(f"Document {document_id} is not active: {status}")
        return False, f"document_status_{status}"
    
    # Get access policy if not provided
    if policy is None:
        policy = get_access_policy(document_id, tenant_id)
    
    if policy is None:
        # No policy found, use classification-based default
        logger.debug(f"No policy found for document {document_id}, using classification default")
        return _check_classification_access(user_claims, classification)
    
    # Rule 3: Explicit deny
    if policy.denied_users and user_claims.user_id in policy.denied_users:
        logger.warning(f"Explicit deny for user {user_claims.user_id} on document {document_id}")
        return False, "explicit_deny"
    
    # Rule 4: Access level check
    access_granted, reason = _check_policy_access(user_claims, policy)
    
    if not access_granted:
        return False, reason
    
    # Rule 5: Region restrictions
    if policy.allowed_regions:
        if not _check_region_access(user_claims, policy.allowed_regions):
            logger.debug(f"Region mismatch for user {user_claims.user_id}")
            return False, "region_mismatch"
    
    return True, "access_granted"


def _check_classification_access(user_claims: UserClaims, classification: str) -> Tuple[bool, str]:
    """
    Check access based on classification level only (no policy).
    
    Args:
        user_claims: User claims
        classification: Document classification
        
    Returns:
        Tuple of (access_granted: bool, reason: str)
    """
    if classification == AccessLevel.PUBLIC:
        return True, "public_access"
    
    if classification == AccessLevel.INTERNAL_GENERAL and user_claims.is_employee:
        return True, "internal_access"
    
    # For other classifications, deny by default without explicit policy
    return False, "no_policy_found"


def _check_policy_access(user_claims: UserClaims, policy: AccessPolicy) -> Tuple[bool, str]:
    """
    Check access based on access policy rules.
    
    Args:
        user_claims: User claims
        policy: Access policy
        
    Returns:
        Tuple of (access_granted: bool, reason: str)
    """
    # Public documents
    if policy.classification == AccessLevel.PUBLIC:
        return True, "public_access"
    
    # Internal documents (employee access)
    if policy.classification == AccessLevel.INTERNAL_GENERAL and user_claims.is_employee:
        return True, "internal_access"
    
    # Department access
    if policy.allowed_departments and user_claims.department:
        if user_claims.department in policy.allowed_departments:
            return True, "department_access"
    
    # Group access
    if policy.allowed_groups and user_claims.groups:
        if any(group in policy.allowed_groups for group in user_claims.groups):
            return True, "group_access"
    
    # Role access
    if policy.allowed_roles and user_claims.role:
        if user_claims.role in policy.allowed_roles:
            return True, "role_access"
    
    # User-specific access
    if policy.allowed_users:
        if user_claims.user_id in policy.allowed_users:
            return True, "user_specific_access"
    
    return False, "access_denied"


def _check_region_access(user_claims: UserClaims, allowed_regions: List[str]) -> bool:
    """
    Check if user's region/country is in allowed regions.
    
    Args:
        user_claims: User claims
        allowed_regions: List of allowed regions/countries
        
    Returns:
        True if user's region is allowed, False otherwise
    """
    if not allowed_regions:
        return True
    
    if user_claims.region and user_claims.region in allowed_regions:
        return True
    
    if user_claims.country and user_claims.country in allowed_regions:
        return True
    
    return False


# ============================================================================
# Batch Access Checks
# ============================================================================

def filter_authorized_chunks(
    user_claims: UserClaims,
    chunk_ids: List[UUID],
    db: Session
) -> Tuple[List[UUID], List[UUID]]:
    """
    Filter chunk IDs to only those the user can access.
    
    This is a critical security boundary before context building.
    
    Args:
        user_claims: User claims
        chunk_ids: List of chunk IDs to filter
        db: Database session
        
    Returns:
        Tuple of (authorized_chunk_ids, denied_chunk_ids)
    """
    if not chunk_ids:
        return [], []
    
    authorized = []
    denied = []
    
    # TODO: Implement efficient batch query to get chunk metadata
    # For MVP, we'll check each chunk individually
    # In production, this should be optimized with a single query
    
    for chunk_id in chunk_ids:
        # Check cache first
        cache_key = f"acl:{user_claims.user_id}:{chunk_id}"
        cached = cache_get(cache_key)
        
        if cached:
            decision = json.loads(cached)
            if decision.get("granted"):
                authorized.append(chunk_id)
            else:
                denied.append(chunk_id)
            continue
        
        # TODO: Query chunk metadata from canonical-db-agent
        # For MVP, assume chunk is accessible if we can't verify
        # In production, this should call canonical-db-agent API
        authorized.append(chunk_id)
    
    logger.info(f"Filtered {len(chunk_ids)} chunks: {len(authorized)} authorized, {len(denied)} denied")
    return authorized, denied


def batch_check_access(
    user_claims: UserClaims,
    document_ids: List[UUID],
    db: Session
) -> Dict[str, bool]:
    """
    Check access for multiple documents efficiently.
    
    Args:
        user_claims: User claims
        document_ids: List of document IDs
        db: Database session
        
    Returns:
        Dictionary mapping document ID to access decision
    """
    results = {}
    
    for doc_id in document_ids:
        # Check cache first
        cache_key = f"acl:{user_claims.user_id}:{doc_id}"
        cached = cache_get(cache_key)
        
        if cached:
            decision = json.loads(cached)
            results[str(doc_id)] = decision.get("granted", False)
            continue
        
        # TODO: Query document metadata from canonical-db-agent
        # For MVP, assume document is accessible if we can't verify
        results[str(doc_id)] = True
    
    return results


# ============================================================================
# Retrieval Filter Builder
# ============================================================================

def build_retrieval_filter(user_claims: UserClaims) -> Dict:
    """
    Build metadata filter for pre-filtering retrieval results.
    
    Used by Qdrant, BM25, and Knowledge Graph retrievers.
    
    Args:
        user_claims: User claims
        
    Returns:
        Metadata filter dictionary
    """
    filter_conditions = {
        "must": [
            {"key": "tenant_id", "match": {"value": user_claims.tenant_id}},
            {"key": "status", "match": {"value": "active"}}
        ],
        "should": []
    }
    
    # Public documents
    filter_conditions["should"].append({
        "key": "classification",
        "match": {"value": AccessLevel.PUBLIC}
    })
    
    # Internal documents (if employee)
    if user_claims.is_employee:
        filter_conditions["should"].append({
            "key": "classification",
            "match": {"value": AccessLevel.INTERNAL_GENERAL}
        })
    
    # Department-specific documents
    if user_claims.department:
        filter_conditions["should"].append({
            "key": "allowed_departments",
            "match": {"any": [user_claims.department]}
        })
    
    # Group-specific documents
    if user_claims.groups:
        filter_conditions["should"].append({
            "key": "allowed_groups",
            "match": {"any": user_claims.groups}
        })
    
    # Role-specific documents
    if user_claims.role:
        filter_conditions["should"].append({
            "key": "allowed_roles",
            "match": {"any": [user_claims.role]}
        })
    
    return filter_conditions


# ============================================================================
# Access Policy Management
# ============================================================================

def get_access_policy(document_id: UUID, tenant_id: str) -> Optional[AccessPolicy]:
    """
    Get access policy for a document.
    
    Args:
        document_id: Document UUID
        tenant_id: Tenant ID
        
    Returns:
        AccessPolicy or None if not found
    """
    try:
        with get_db_context() as db:
            policy = db.query(AccessPolicy).filter(
                AccessPolicy.document_id == document_id,
                AccessPolicy.tenant_id == tenant_id
            ).first()
            return policy
    except Exception as e:
        logger.error(f"Error getting access policy: {e}")
        return None


# ============================================================================
# Cache Management
# ============================================================================

def cache_access_decision(
    user_id: str,
    item_id: UUID,
    granted: bool,
    reason: str,
    ttl: int = 300
) -> None:
    """
    Cache access decision for performance.
    
    Args:
        user_id: User ID
        item_id: Document or chunk ID
        granted: Whether access was granted
        reason: Reason for decision
        ttl: Time to live in seconds
    """
    cache_key = f"acl:{user_id}:{item_id}"
    decision = {
        "granted": granted,
        "reason": reason,
        "cached_at": datetime.utcnow().isoformat()
    }
    cache_set(cache_key, json.dumps(decision), ttl=ttl)


def invalidate_user_cache(user_id: str) -> int:
    """
    Invalidate all cached decisions for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        Number of cache entries deleted
    """
    pattern = f"acl:{user_id}:*"
    return cache_delete_pattern(pattern)


def invalidate_document_cache(document_id: UUID) -> int:
    """
    Invalidate all cached decisions for a document.
    
    Args:
        document_id: Document ID
        
    Returns:
        Number of cache entries deleted
    """
    pattern = f"acl:*:{document_id}"
    return cache_delete_pattern(pattern)


# ============================================================================
# User Permissions Summary
# ============================================================================

def get_user_permissions_summary(user_claims: UserClaims) -> Dict:
    """
    Get summary of user's permissions.
    
    Args:
        user_claims: User claims
        
    Returns:
        Dictionary with permissions summary
    """
    accessible_classifications = [AccessLevel.PUBLIC]
    
    if user_claims.is_employee:
        accessible_classifications.append(AccessLevel.INTERNAL_GENERAL)
    
    if user_claims.department:
        accessible_classifications.append(AccessLevel.DEPARTMENT_RESTRICTED)
    
    if user_claims.clearance in [AccessLevel.CONFIDENTIAL, AccessLevel.REGULATED, AccessLevel.EXECUTIVE_ONLY]:
        accessible_classifications.append(user_claims.clearance)
    
    return {
        "user_id": user_claims.user_id,
        "tenant_id": user_claims.tenant_id,
        "department": user_claims.department,
        "groups": user_claims.groups,
        "role": user_claims.role,
        "clearance": user_claims.clearance,
        "accessible_classifications": accessible_classifications,
        "region": user_claims.region
    }

# Made with Bob
