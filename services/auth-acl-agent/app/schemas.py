"""
Pydantic schemas for request/response validation.

This module defines all Pydantic models used for API request validation
and response serialization in the Auth ACL Agent.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# User Claims Schemas
# ============================================================================

class UserClaims(BaseModel):
    """User claims extracted from JWT token."""
    user_id: str = Field(..., description="User ID")
    email: Optional[str] = Field(None, description="User email")
    tenant_id: str = Field(..., description="Tenant ID")
    department: Optional[str] = Field(None, description="User department")
    groups: List[str] = Field(default_factory=list, description="User groups")
    role: Optional[str] = Field(None, description="User role")
    region: Optional[str] = Field(None, description="User region")
    country: Optional[str] = Field(None, description="User country")
    clearance: str = Field(default="INTERNAL_GENERAL", description="User clearance level")
    is_employee: bool = Field(default=True, description="Is employee")
    exp: Optional[int] = Field(None, description="Token expiration timestamp")
    iat: Optional[int] = Field(None, description="Token issued at timestamp")


# ============================================================================
# Token Validation Schemas
# ============================================================================

class TokenValidateRequest(BaseModel):
    """Request to validate a token."""
    token: str = Field(..., description="JWT token to validate")


class TokenValidateResponse(BaseModel):
    """Response from token validation."""
    valid: bool = Field(..., description="Whether token is valid")
    claims: Optional[UserClaims] = Field(None, description="User claims if valid")
    error: Optional[str] = Field(None, description="Error message if invalid")


# ============================================================================
# Access Decision Schemas
# ============================================================================

class AccessCheckRequest(BaseModel):
    """Request to check access to a document or chunk."""
    document_id: Optional[UUID] = Field(None, description="Document ID")
    chunk_id: Optional[UUID] = Field(None, description="Chunk ID")


class AccessDecision(BaseModel):
    """Access decision result."""
    granted: bool = Field(..., description="Whether access is granted")
    reason: str = Field(..., description="Reason for decision")
    checked_at: datetime = Field(default_factory=datetime.utcnow, description="When check was performed")
    user_id: str = Field(..., description="User ID")
    item_id: UUID = Field(..., description="Document or chunk ID")
    item_type: str = Field(..., description="Type: document or chunk")


class BatchAccessCheckRequest(BaseModel):
    """Request to check access to multiple items."""
    document_ids: Optional[List[UUID]] = Field(None, description="List of document IDs")
    chunk_ids: Optional[List[UUID]] = Field(None, description="List of chunk IDs")


class BatchAccessCheckResponse(BaseModel):
    """Response from batch access check."""
    results: Dict[str, bool] = Field(..., description="Map of item ID to access decision")
    denied_count: int = Field(..., description="Number of denied items")
    granted_count: int = Field(..., description="Number of granted items")


# ============================================================================
# Filter Schemas
# ============================================================================

class FilterChunksRequest(BaseModel):
    """Request to filter chunk IDs by access."""
    chunk_ids: List[UUID] = Field(..., min_length=1, max_length=10000, description="Chunk IDs to filter")


class FilterChunksResponse(BaseModel):
    """Response from chunk filtering."""
    authorized_chunk_ids: List[UUID] = Field(..., description="Authorized chunk IDs")
    denied_chunk_ids: List[UUID] = Field(..., description="Denied chunk IDs")
    total_requested: int = Field(..., description="Total chunks requested")
    total_authorized: int = Field(..., description="Total chunks authorized")


class RetrievalFilterRequest(BaseModel):
    """Request to build retrieval filter."""
    include_public: bool = Field(default=True, description="Include public documents")
    include_internal: bool = Field(default=True, description="Include internal documents")


class RetrievalFilterResponse(BaseModel):
    """Response with retrieval filter."""
    filter: Dict = Field(..., description="Metadata filter for retrievers")
    user_id: str = Field(..., description="User ID")
    tenant_id: str = Field(..., description="Tenant ID")


# ============================================================================
# User Permissions Schemas
# ============================================================================

class UserPermissionsResponse(BaseModel):
    """User permissions summary."""
    user_id: str = Field(..., description="User ID")
    tenant_id: str = Field(..., description="Tenant ID")
    department: Optional[str] = Field(None, description="User department")
    groups: List[str] = Field(default_factory=list, description="User groups")
    role: Optional[str] = Field(None, description="User role")
    clearance: str = Field(..., description="User clearance level")
    accessible_classifications: List[str] = Field(..., description="Accessible classification levels")
    region: Optional[str] = Field(None, description="User region")


# ============================================================================
# Access Policy Schemas
# ============================================================================

class AccessPolicyBase(BaseModel):
    """Base schema for access policy."""
    classification: str = Field(..., description="Classification level")
    allowed_departments: Optional[List[str]] = Field(None, description="Allowed departments")
    allowed_groups: Optional[List[str]] = Field(None, description="Allowed groups")
    allowed_roles: Optional[List[str]] = Field(None, description="Allowed roles")
    allowed_users: Optional[List[str]] = Field(None, description="Allowed users")
    denied_users: Optional[List[str]] = Field(None, description="Denied users")
    allowed_regions: Optional[List[str]] = Field(None, description="Allowed regions")


class AccessPolicyCreate(AccessPolicyBase):
    """Schema for creating access policy."""
    tenant_id: str = Field(..., description="Tenant ID")
    document_id: Optional[UUID] = Field(None, description="Document ID")


class AccessPolicyResponse(AccessPolicyBase):
    """Schema for access policy response."""
    policy_id: UUID = Field(..., description="Policy ID")
    tenant_id: str = Field(..., description="Tenant ID")
    document_id: Optional[UUID] = Field(None, description="Document ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")
    
    class Config:
        from_attributes = True


# ============================================================================
# Health Check Schemas
# ============================================================================

class HealthCheckResponse(BaseModel):
    """Schema for health check response."""
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(..., description="Check timestamp")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    checks: Dict = Field(..., description="Component health checks")


# ============================================================================
# Error Schemas
# ============================================================================

class ErrorResponse(BaseModel):
    """Schema for error response."""
    error: str = Field(..., description="Error type")
    detail: Optional[str] = Field(None, description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

# Made with Bob
