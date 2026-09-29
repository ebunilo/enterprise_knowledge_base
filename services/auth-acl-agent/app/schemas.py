"""
Pydantic schemas for request/response validation.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class UserClaims(BaseModel):
    """Normalised identity of the caller (see app.claims)."""
    user_id: str
    email: Optional[str] = None
    username: Optional[str] = None
    tenant_id: str = Field(..., description="Resolved tenant UUID")
    tenant_slug: Optional[str] = None
    department: Optional[str] = None
    groups: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    region: Optional[str] = None
    country: Optional[str] = None
    clearance: str = "PUBLIC"
    is_employee: bool = False
    exp: Optional[int] = None
    iat: Optional[int] = None


class TokenValidateRequest(BaseModel):
    token: str


class TokenValidateResponse(BaseModel):
    valid: bool
    claims: Optional[UserClaims] = None
    error: Optional[str] = None


class AccessCheckRequest(BaseModel):
    document_id: Optional[UUID] = None
    chunk_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.document_id is None) == (self.chunk_id is None):
            raise ValueError("Provide exactly one of document_id or chunk_id")
        return self


class AccessDecision(BaseModel):
    granted: bool
    reason: str
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    item_id: UUID
    item_type: str


class BatchAccessCheckRequest(BaseModel):
    document_ids: List[UUID] = Field(default_factory=list, max_length=1000)
    chunk_ids: List[UUID] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.document_ids and not self.chunk_ids:
            raise ValueError("Provide document_ids and/or chunk_ids")
        return self


class BatchAccessCheckResponse(BaseModel):
    results: Dict[str, bool]
    reason_by_item: Dict[str, str]
    granted_count: int
    denied_count: int


class FilterChunksRequest(BaseModel):
    chunk_ids: List[UUID] = Field(..., min_length=1, max_length=1000)


class FilterChunksResponse(BaseModel):
    """AGENTS.md 5.11 output contract."""
    authorized_chunk_ids: List[UUID]
    denied_chunk_ids: List[UUID]
    reason_by_chunk: Dict[str, str]
    total_requested: int
    total_authorized: int


class RetrievalFilterResponse(BaseModel):
    filter: Dict
    user_id: str
    tenant_id: str


class UserPermissionsResponse(BaseModel):
    user_id: str
    tenant_id: str
    department: Optional[str]
    groups: List[str]
    roles: List[str]
    clearance: str
    is_employee: bool
    accessible_classifications: List[str]
    region: Optional[str]
    country: Optional[str]


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str
    version: str
    checks: Dict
