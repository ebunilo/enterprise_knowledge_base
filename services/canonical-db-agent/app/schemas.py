"""
Pydantic schemas for request/response validation.

This module defines all Pydantic models used for API request validation
and response serialization in the Canonical DB Agent.
"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Base Schemas
# ============================================================================

class TenantBase(BaseModel):
    """Base schema for tenant."""
    tenant_name: str = Field(..., min_length=1, max_length=255)
    tenant_slug: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True


class TenantCreate(TenantBase):
    """Schema for creating a tenant."""
    pass


class TenantResponse(TenantBase):
    """Schema for tenant response."""
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentBase(BaseModel):
    """Base schema for document."""
    title: str = Field(..., min_length=1, max_length=500)
    source_type: str = Field(..., min_length=1, max_length=50)
    source_uri: str = Field(..., min_length=1, max_length=1000)
    classification: str = Field(..., min_length=1, max_length=50)
    department: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    language: str = Field(default="en", max_length=10)
    version: str = Field(..., min_length=1, max_length=50)
    checksum: str = Field(..., min_length=1, max_length=64)

    @field_validator('classification')
    @classmethod
    def validate_classification(cls, v: str) -> str:
        """Validate classification level."""
        valid_classifications = [
            'PUBLIC',
            'INTERNAL_GENERAL',
            'DEPARTMENT_RESTRICTED',
            'CONFIDENTIAL',
            'REGULATED',
            'EXECUTIVE_ONLY'
        ]
        if v not in valid_classifications:
            raise ValueError(f'Classification must be one of: {", ".join(valid_classifications)}')
        return v

    @field_validator('source_type')
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        """Validate source type."""
        valid_types = [
            'sharepoint',
            'google_drive',
            'confluence',
            'notion',
            's3',
            'minio',
            'azure_blob',
            'git',
            'wiki',
            'local_upload'
        ]
        if v not in valid_types:
            raise ValueError(f'Source type must be one of: {", ".join(valid_types)}')
        return v


class DocumentCreate(DocumentBase):
    """Schema for creating a document."""
    tenant_id: str = Field(..., min_length=1, max_length=100)


class DocumentUpdate(BaseModel):
    """Schema for updating a document."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[str] = Field(None, max_length=20)
    classification: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate document status."""
        if v is not None:
            valid_statuses = ['active', 'archived', 'deleted']
            if v not in valid_statuses:
                raise ValueError(f'Status must be one of: {", ".join(valid_statuses)}')
        return v


class DocumentResponse(DocumentBase):
    """Schema for document response."""
    document_id: UUID
    tenant_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Chunk Schemas
# ============================================================================

class ChunkBase(BaseModel):
    """Base schema for document chunk."""
    chunk_text: str = Field(..., min_length=1)
    chunk_index: int = Field(..., ge=0)
    page_start: Optional[int] = Field(None, ge=1)
    page_end: Optional[int] = Field(None, ge=1)
    section_title: Optional[str] = Field(None, max_length=500)
    heading_path: Optional[List[str]] = None
    token_count: int = Field(..., ge=0)
    checksum: str = Field(..., min_length=1, max_length=64)

    @field_validator('page_end')
    @classmethod
    def validate_page_range(cls, v: Optional[int], info) -> Optional[int]:
        """Validate that page_end >= page_start."""
        if v is not None and 'page_start' in info.data:
            page_start = info.data.get('page_start')
            if page_start is not None and v < page_start:
                raise ValueError('page_end must be >= page_start')
        return v


class ChunkCreate(ChunkBase):
    """Schema for creating a chunk."""
    document_id: UUID
    tenant_id: str = Field(..., min_length=1, max_length=100)


class ChunkResponse(ChunkBase):
    """Schema for chunk response."""
    chunk_id: UUID
    document_id: UUID
    tenant_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChunkBatchRequest(BaseModel):
    """Schema for batch chunk retrieval."""
    chunk_ids: List[UUID] = Field(..., min_items=1, max_items=1000)


# ============================================================================
# Version Schemas
# ============================================================================

class DocumentVersionBase(BaseModel):
    """Base schema for document version."""
    version: str = Field(..., min_length=1, max_length=50)
    is_current: bool = True


class DocumentVersionCreate(DocumentVersionBase):
    """Schema for creating a document version."""
    document_id: UUID
    tenant_id: str = Field(..., min_length=1, max_length=100)


class DocumentVersionResponse(DocumentVersionBase):
    """Schema for document version response."""
    version_id: UUID
    document_id: UUID
    tenant_id: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Pagination Schemas
# ============================================================================

class PaginationParams(BaseModel):
    """Schema for pagination parameters."""
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic schema for paginated responses."""
    items: List[T]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    has_more: bool

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        limit: int,
        offset: int
    ) -> "PaginatedResponse[T]":
        """Create a paginated response."""
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + len(items)) < total
        )


# ============================================================================
# Error Schemas
# ============================================================================

class ErrorDetail(BaseModel):
    """Schema for error detail."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Schema for error response."""
    error: str
    detail: Optional[str] = None
    errors: Optional[List[ErrorDetail]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Health Check Schemas
# ============================================================================

class HealthCheckResponse(BaseModel):
    """Schema for health check response."""
    status: str
    timestamp: datetime
    service: str
    version: str
    checks: dict


class MetricsResponse(BaseModel):
    """Schema for metrics response."""
    metrics: str

# Made with Bob
