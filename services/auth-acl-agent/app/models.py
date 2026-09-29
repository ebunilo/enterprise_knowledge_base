"""
Read models for the ACL engine. The tables are owned by the canonical schema
(infra/docker-compose/postgres); this service only reads them, apart from
appending ACL decision events to audit_logs.
"""

from uuid import uuid4

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_slug = Column(String(100), nullable=False)
    is_active = Column(Boolean)


class Document(Base):
    __tablename__ = "documents"

    document_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    classification = Column(String(50), nullable=False)
    department = Column(String(100))
    region = Column(String(100))
    tags = Column(ARRAY(Text))
    status = Column(String(20), nullable=False)
    is_current_version = Column(Boolean, nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.document_id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)


class AccessPolicy(Base):
    """
    A policy applies to a document when every selector it sets matches
    (document_id, classification, department, region, tags). Deny lists on
    any applicable policy override every allow.
    """

    __tablename__ = "access_policies"

    policy_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    policy_name = Column(String(255), nullable=False)
    priority = Column(Integer, nullable=False)

    # Selectors
    document_id = Column(UUID(as_uuid=True))
    classification = Column(String(50))
    department = Column(String(100))
    region = Column(String(100))
    tags = Column(ARRAY(Text))

    # Rules
    allowed_users = Column(ARRAY(Text))
    denied_users = Column(ARRAY(Text))
    allowed_groups = Column(ARRAY(Text))
    denied_groups = Column(ARRAY(Text))
    allowed_departments = Column(ARRAY(Text))
    denied_departments = Column(ARRAY(Text))
    allowed_roles = Column(ARRAY(Text))
    denied_roles = Column(ARRAY(Text))
    allowed_regions = Column(ARRAY(Text))
    denied_regions = Column(ARRAY(Text))

    is_active = Column(Boolean, nullable=False)
    effective_from = Column(TIMESTAMP(timezone=True))
    effective_until = Column(TIMESTAMP(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(TIMESTAMP(timezone=True), primary_key=True, server_default=func.now())
    event_type = Column(String(100), nullable=False)
    event_category = Column(String(50), nullable=False)
    user_email = Column(String(255))
    resource_type = Column(String(100))
    action = Column(String(100), nullable=False)
    result = Column(String(50), nullable=False)
    details = Column(JSONB, nullable=False, default=dict)
    ip_address = Column(INET)
    user_agent = Column(Text)
