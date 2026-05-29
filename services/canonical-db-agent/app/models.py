"""
SQLAlchemy ORM models for Canonical DB Agent.
Maps to PostgreSQL tables with Row-Level Security.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import (
    Column, String, Integer, Text, Boolean, TIMESTAMP,
    ForeignKey, CheckConstraint, UniqueConstraint, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Tenant(Base):
    """Tenant model for multi-tenancy support."""
    
    __tablename__ = "tenants"
    
    tenant_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Tenant(tenant_id='{self.tenant_id}', name='{self.name}')>"


class Document(Base):
    """Document model storing document metadata."""
    
    __tablename__ = "documents"
    
    document_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    title = Column(Text, nullable=False)
    source_type = Column(String(100), nullable=False)
    source_uri = Column(Text, nullable=False)
    classification = Column(String(50), nullable=False)
    department = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    language = Column(String(10), nullable=False, default="en")
    version = Column(String(50), nullable=False)
    checksum = Column(String(64), nullable=False)
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    access_policies = relationship("AccessPolicy", back_populates="document", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_uri", "version", name="uq_document_tenant_source_version"),
    )
    
    def __repr__(self):
        return f"<Document(document_id='{self.document_id}', title='{self.title}')>"


class DocumentChunk(Base):
    """Document chunk model storing chunk metadata and text."""
    
    __tablename__ = "document_chunks"
    
    chunk_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    section_title = Column(Text, nullable=True)
    heading_path = Column(ARRAY(Text), nullable=True)
    token_count = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )
    
    def __repr__(self):
        return f"<DocumentChunk(chunk_id='{self.chunk_id}', document_id='{self.document_id}', index={self.chunk_index})>"


class DocumentVersion(Base):
    """Document version model for version tracking."""
    
    __tablename__ = "document_versions"
    
    version_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.document_id"), nullable=False)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    version = Column(String(50), nullable=False)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    archived_at = Column(TIMESTAMP, nullable=True)
    
    # Relationships
    document = relationship("Document", back_populates="versions")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_version_document_version"),
    )
    
    def __repr__(self):
        return f"<DocumentVersion(version_id='{self.version_id}', version='{self.version}', is_current={self.is_current})>"


class AccessPolicy(Base):
    """Access policy model for document-level access control."""
    
    __tablename__ = "access_policies"
    
    policy_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=True)
    classification = Column(String(50), nullable=False)
    allowed_departments = Column(ARRAY(Text), nullable=True)
    allowed_groups = Column(ARRAY(Text), nullable=True)
    allowed_roles = Column(ARRAY(Text), nullable=True)
    allowed_users = Column(ARRAY(Text), nullable=True)
    denied_users = Column(ARRAY(Text), nullable=True)
    allowed_regions = Column(ARRAY(Text), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="access_policies")
    
    def __repr__(self):
        return f"<AccessPolicy(policy_id='{self.policy_id}', classification='{self.classification}')>"


class DocumentSource(Base):
    """Document source model for ingestion configuration."""
    
    __tablename__ = "document_sources"
    
    source_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    source_type = Column(String(100), nullable=False)
    source_name = Column(String(255), nullable=False)
    source_config = Column(Text, nullable=False)  # JSON stored as text
    status = Column(String(50), nullable=False, default="active")
    last_sync_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    ingestion_jobs = relationship("IngestionJob", back_populates="source", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<DocumentSource(source_id='{self.source_id}', name='{self.source_name}')>"


class IngestionJob(Base):
    """Ingestion job model for tracking document ingestion."""
    
    __tablename__ = "ingestion_jobs"
    
    job_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    source_id = Column(PG_UUID(as_uuid=True), ForeignKey("document_sources.source_id"), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    documents_processed = Column(Integer, default=0)
    documents_failed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    source = relationship("DocumentSource", back_populates="ingestion_jobs")
    
    def __repr__(self):
        return f"<IngestionJob(job_id='{self.job_id}', status='{self.status}')>"


class RetrievalAuditLog(Base):
    """Retrieval audit log model for query tracking."""
    
    __tablename__ = "retrieval_audit_logs"
    
    audit_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id = Column(String(255), nullable=False)
    query = Column(Text, nullable=False)
    query_intent = Column(String(100), nullable=True)
    retrieved_chunk_ids = Column(ARRAY(PG_UUID(as_uuid=True)), nullable=True)
    authorized_chunk_ids = Column(ARRAY(PG_UUID(as_uuid=True)), nullable=True)
    denied_chunk_ids = Column(ARRAY(PG_UUID(as_uuid=True)), nullable=True)
    cited_chunk_ids = Column(ARRAY(PG_UUID(as_uuid=True)), nullable=True)
    model_used = Column(String(100), nullable=True)
    answer_hash = Column(String(64), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    feedback = relationship("UserFeedback", back_populates="audit_log", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<RetrievalAuditLog(audit_id='{self.audit_id}', user_id='{self.user_id}')>"


class UserFeedback(Base):
    """User feedback model for query quality tracking."""
    
    __tablename__ = "user_feedback"
    
    feedback_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=False)
    audit_id = Column(PG_UUID(as_uuid=True), ForeignKey("retrieval_audit_logs.audit_id"), nullable=True)
    user_id = Column(String(255), nullable=False)
    rating = Column(Integer, nullable=True)
    feedback_text = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    audit_log = relationship("RetrievalAuditLog", back_populates="feedback")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating_range"),
    )
    
    def __repr__(self):
        return f"<UserFeedback(feedback_id='{self.feedback_id}', rating={self.rating})>"

# Made with Bob
