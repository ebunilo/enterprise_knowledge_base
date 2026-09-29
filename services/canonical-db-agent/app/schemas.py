"""
Pydantic schemas for request/response validation.

Enum-like inputs are accepted case-insensitively (the original API used
lowercase values) and normalised to the uppercase values stored in PostgreSQL.
"""

from datetime import date, datetime
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Classification, DocumentStatus, SourceType

# Legacy lowercase source types from the v0.1 API.
_SOURCE_TYPE_ALIASES = {"MINIO": "S3", "WIKI": "INTERNAL_WIKI"}

FEEDBACK_REASON_CODES = {
    "wrong_answer",
    "incomplete",
    "outdated_source",
    "not_relevant",
    "bad_citation",
    "missing_source",
    "too_slow",
    "other",
}


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    source_type: SourceType
    source_uri: str = Field(..., min_length=1, max_length=2000)
    classification: Classification
    department: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    language: str = Field(default="en", min_length=2, max_length=10)
    checksum: str = Field(..., min_length=1, max_length=64)
    mime_type: Optional[str] = Field(None, max_length=100)
    file_name: Optional[str] = Field(None, max_length=500)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    storage_bucket: Optional[str] = Field(None, max_length=255)
    storage_path: Optional[str] = None
    effective_date: Optional[date] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator("classification", mode="before")
    @classmethod
    def _normalise_classification(cls, v):
        return _upper(v)

    @field_validator("source_type", mode="before")
    @classmethod
    def _normalise_source_type(cls, v):
        v = _upper(v)
        return _SOURCE_TYPE_ALIASES.get(v, v)


class DocumentCreate(DocumentBase):
    """Create a document, or a new version of an existing (tenant, source_uri)."""
    version: Optional[str] = Field(None, min_length=1, max_length=50)
    status: DocumentStatus = DocumentStatus.PENDING

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_status(cls, v):
        return _upper(v)

    @field_validator("status")
    @classmethod
    def _creatable_status(cls, v: DocumentStatus) -> DocumentStatus:
        if v not in (DocumentStatus.PENDING, DocumentStatus.PROCESSING, DocumentStatus.ACTIVE):
            raise ValueError("New documents must be PENDING, PROCESSING or ACTIVE")
        return v


class DocumentUpdate(BaseModel):
    """Metadata update. Status changes go through the dedicated endpoints."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    classification: Optional[Classification] = None
    department: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    status: Optional[DocumentStatus] = None
    tags: Optional[List[str]] = None

    @field_validator("classification", "status", mode="before")
    @classmethod
    def _normalise(cls, v):
        return _upper(v)

    @field_validator("status")
    @classmethod
    def _updatable_status(cls, v: Optional[DocumentStatus]) -> Optional[DocumentStatus]:
        if v in (DocumentStatus.ARCHIVED, DocumentStatus.DELETED, DocumentStatus.ACTIVE):
            raise ValueError("Use /activate, /archive or DELETE to change to this status")
        return v


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    document_version_id: UUID
    tenant_id: UUID
    title: str
    source_type: Optional[SourceType]
    source_uri: str
    classification: Classification
    department: Optional[str]
    region: Optional[str]
    language: str
    version: str
    version_number: int
    parent_document_id: Optional[UUID]
    is_current_version: bool
    checksum: str
    status: DocumentStatus
    tags: List[str]
    effective_date: Optional[date]
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Chunk Schemas
# ============================================================================

class ChunkBase(BaseModel):
    chunk_text: str = Field(..., min_length=1)
    chunk_index: int = Field(..., ge=0)
    page_start: Optional[int] = Field(None, ge=1)
    page_end: Optional[int] = Field(None, ge=1)
    section_title: Optional[str] = Field(None, max_length=500)
    heading_path: List[str] = Field(default_factory=list)
    chunk_type: str = Field(default="paragraph", max_length=50)
    token_count: int = Field(..., ge=1)

    @model_validator(mode="after")
    def _page_range(self):
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        return self


class ChunkCreate(ChunkBase):
    """Classification/department/region/language are inherited from the document."""
    document_id: UUID
    # Optional client-computed SHA-256 of chunk_text; verified if present.
    checksum: Optional[str] = Field(None, min_length=64, max_length=64)


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    tenant_id: UUID
    chunk_text: str
    chunk_index: int
    page_start: Optional[int]
    page_end: Optional[int]
    section_title: Optional[str]
    heading_path: List[str]
    chunk_type: str
    token_count: int
    checksum: str
    classification: Classification
    department: Optional[str]
    region: Optional[str]
    language: str
    created_at: datetime


class ChunkWithSource(ChunkResponse):
    """Chunk plus the document metadata needed for citations (AGENTS.md section 8)."""
    title: str
    version: str
    source_uri: str
    document_status: DocumentStatus
    is_current_version: bool


class ChunkBatchRequest(BaseModel):
    chunk_ids: List[UUID] = Field(..., min_length=1, max_length=1000)
    # Admin workflows only; normal retrieval never sees archived versions.
    include_inactive: bool = False


class ChunkBatchResponse(BaseModel):
    chunks: List[ChunkWithSource]
    missing_chunk_ids: List[UUID]


# ============================================================================
# Retrieval audit and feedback (self-improvement signals)
# ============================================================================

class RetrievalAuditCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    query: str = Field(..., min_length=1)
    query_language: Optional[str] = Field(None, max_length=10)
    query_intent: Optional[str] = Field(None, max_length=50)
    retrieved_chunk_ids: List[UUID] = Field(default_factory=list)
    authorized_chunk_ids: List[UUID] = Field(default_factory=list)
    denied_chunk_ids: List[UUID] = Field(default_factory=list)
    denied_reasons: dict[str, str] = Field(default_factory=dict)
    context_chunk_ids: List[UUID] = Field(default_factory=list)
    cited_chunk_ids: List[UUID] = Field(default_factory=list)
    retrieval_sources: dict[str, List[str]] = Field(default_factory=dict)
    model_used: Optional[str] = Field(None, max_length=100)
    provider: Optional[str] = Field(None, max_length=100)
    processing_region: Optional[str] = Field(None, max_length=50)
    prompt_tokens: Optional[int] = Field(None, ge=0)
    completion_tokens: Optional[int] = Field(None, ge=0)
    answer_hash: Optional[str] = Field(None, max_length=64)
    insufficient_context: Optional[bool] = None
    citation_validation_passed: Optional[bool] = None
    latency_ms: Optional[int] = Field(None, ge=0)
    stage_latency_ms: dict[str, int] = Field(default_factory=dict)
    parameter_snapshot: dict[str, Any] = Field(default_factory=dict)
    experiment_assignments: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _context_is_authorized(self):
        # Mirrors the non-negotiable rules: nothing unauthorized may be in the
        # context, and nothing outside the context may be cited.
        authorized = set(self.authorized_chunk_ids)
        if not set(self.context_chunk_ids) <= authorized:
            raise ValueError("context_chunk_ids must be a subset of authorized_chunk_ids")
        if not set(self.cited_chunk_ids) <= set(self.context_chunk_ids):
            raise ValueError("cited_chunk_ids must be a subset of context_chunk_ids")
        return self


class RetrievalAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: UUID
    tenant_id: UUID
    user_id: str
    query_hash: str
    query_intent: Optional[str]
    retrieved_chunk_ids: List[UUID]
    authorized_chunk_ids: List[UUID]
    denied_chunk_ids: List[UUID]
    denied_reasons: dict
    context_chunk_ids: List[UUID]
    cited_chunk_ids: List[UUID]
    model_used: Optional[str]
    answer_hash: Optional[str]
    latency_ms: Optional[int]
    parameter_snapshot: dict
    experiment_assignments: dict
    created_at: datetime


class FeedbackCreate(BaseModel):
    audit_id: UUID
    user_id: str = Field(..., min_length=1, max_length=255)
    rating: Optional[int] = Field(None, ge=1, le=5)
    thumbs: Optional[int] = None
    reason_codes: List[str] = Field(default_factory=list)
    helpful_chunk_ids: List[UUID] = Field(default_factory=list)
    unhelpful_chunk_ids: List[UUID] = Field(default_factory=list)
    comment: Optional[str] = Field(None, max_length=4000)

    @field_validator("thumbs")
    @classmethod
    def _thumbs(cls, v):
        if v is not None and v not in (-1, 1):
            raise ValueError("thumbs must be -1 or 1")
        return v

    @field_validator("reason_codes")
    @classmethod
    def _reasons(cls, v: List[str]) -> List[str]:
        unknown = set(v) - FEEDBACK_REASON_CODES
        if unknown:
            raise ValueError(f"Unknown reason codes: {sorted(unknown)}")
        return v

    @model_validator(mode="after")
    def _has_signal(self):
        if self.rating is None and self.thumbs is None and not self.reason_codes:
            raise ValueError("Feedback needs a rating, thumbs or at least one reason code")
        return self


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_id: UUID
    audit_id: UUID
    tenant_id: UUID
    user_id: str
    rating: Optional[int]
    thumbs: Optional[int]
    reason_codes: List[str]
    created_at: datetime


# ============================================================================
# Pagination / errors / health
# ============================================================================

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    has_more: bool

    @classmethod
    def create(cls, items: List[T], total: int, limit: int, offset: int) -> "PaginatedResponse[T]":
        return cls(items=items, total=total, limit=limit, offset=offset,
                   has_more=(offset + len(items)) < total)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str
    version: str
    checks: dict
