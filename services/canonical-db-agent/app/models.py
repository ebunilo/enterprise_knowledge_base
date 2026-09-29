"""
SQLAlchemy ORM models for Canonical DB Agent.

These map 1:1 onto the tables created by
infra/docker-compose/postgres/init/01-init-database.sql and the migrations in
infra/docker-compose/postgres/migrations/. The SQL files are the source of
truth; keep these models in sync with them.
"""

import enum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Classification(str, enum.Enum):
    PUBLIC = "PUBLIC"
    INTERNAL_GENERAL = "INTERNAL_GENERAL"
    DEPARTMENT_RESTRICTED = "DEPARTMENT_RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    REGULATED = "REGULATED"
    EXECUTIVE_ONLY = "EXECUTIVE_ONLY"


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    FAILED = "FAILED"


class SourceType(str, enum.Enum):
    SHAREPOINT = "SHAREPOINT"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"
    CONFLUENCE = "CONFLUENCE"
    NOTION = "NOTION"
    S3 = "S3"
    AZURE_BLOB = "AZURE_BLOB"
    GIT = "GIT"
    LOCAL_UPLOAD = "LOCAL_UPLOAD"
    INTERNAL_WIKI = "INTERNAL_WIKI"
    OTHER = "OTHER"


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> ENUM:
    return ENUM(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda members: [member.value for member in members],
    )


ClassificationType = _pg_enum(Classification, "document_classification")
DocumentStatusType = _pg_enum(DocumentStatus, "document_status")
SourceTypeType = _pg_enum(SourceType, "document_source_type")


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_name = Column(String(255), nullable=False, unique=True)
    tenant_slug = Column(String(100), nullable=False, unique=True)
    default_language = Column(String(10), default="en")
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Document(Base):
    """One row per document *version*; (tenant_id, source_uri) is the logical document."""

    __tablename__ = "documents"

    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)

    title = Column(String(500), nullable=False)
    source_type = Column(SourceTypeType, nullable=True)
    source_uri = Column(Text, nullable=False)
    external_id = Column(String(255))

    file_name = Column(String(500))
    file_extension = Column(String(20))
    file_size_bytes = Column(BigInteger)
    mime_type = Column(String(100))
    checksum = Column(String(64), nullable=False)

    storage_path = Column(Text)
    storage_bucket = Column(String(255))

    classification = Column(ClassificationType, nullable=False, default=Classification.INTERNAL_GENERAL)
    department = Column(String(100))
    region = Column(String(100))
    language = Column(String(10), nullable=False, default="en")

    version = Column(String(50), nullable=False, default="v1.0")
    version_number = Column(Integer, nullable=False, default=1)
    parent_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.document_id"))
    is_current_version = Column(Boolean, nullable=False, default=True)

    status = Column(DocumentStatusType, nullable=False, default=DocumentStatus.PENDING)

    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    tags = Column(ARRAY(Text), nullable=False, default=list)

    effective_date = Column(Date)
    expiration_date = Column(Date)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    indexed_at = Column(TIMESTAMP(timezone=True))

    chunks = relationship("DocumentChunk", back_populates="document", passive_deletes=True)

    @property
    def document_version_id(self):
        return self.document_id


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)

    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False)

    page_start = Column(Integer)
    page_end = Column(Integer)
    section_title = Column(String(500))
    heading_path = Column(ARRAY(Text), nullable=False, default=list)
    chunk_type = Column(String(50), nullable=False, default="paragraph")

    # Inherited from the document at creation; never supplied by the caller.
    classification = Column(ClassificationType, nullable=False)
    department = Column(String(100))
    region = Column(String(100))
    language = Column(String(10), nullable=False, default="en")

    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    document = relationship("Document", back_populates="chunks")

    @property
    def document_version_id(self):
        return self.document_id


class RetrievalAuditLog(Base):
    __tablename__ = "retrieval_audit_logs"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id = Column(String(255), nullable=False)

    query_hash = Column(String(64), nullable=False)
    query_text = Column(Text)
    query_language = Column(String(10))
    query_intent = Column(String(50))

    retrieved_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    authorized_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    denied_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    denied_reasons = Column(JSONB, nullable=False, default=dict)
    context_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    cited_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    retrieval_sources = Column(JSONB, nullable=False, default=dict)

    model_used = Column(String(100))
    provider = Column(String(100))
    processing_region = Column(String(50))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    answer_hash = Column(String(64))
    insufficient_context = Column(Boolean)
    citation_validation_passed = Column(Boolean)

    latency_ms = Column(Integer)
    stage_latency_ms = Column(JSONB, nullable=False, default=dict)

    parameter_snapshot = Column(JSONB, nullable=False, default=dict)
    experiment_assignments = Column(JSONB, nullable=False, default=dict)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    audit_id = Column(
        UUID(as_uuid=True), ForeignKey("retrieval_audit_logs.audit_id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String(255), nullable=False)

    rating = Column(SmallInteger)
    thumbs = Column(SmallInteger)
    reason_codes = Column(ARRAY(Text), nullable=False, default=list)
    helpful_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    unhelpful_chunk_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    comment = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
