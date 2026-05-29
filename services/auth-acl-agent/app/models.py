"""
SQLAlchemy ORM models for Auth ACL Agent.

This module defines database models for access policies and related entities.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


# ============================================================================
# Access Policy Model
# ============================================================================

class AccessPolicy(Base):
    """
    Access policy for documents and chunks.
    
    Defines who can access a document based on classification,
    departments, groups, roles, users, and regions.
    """
    
    __tablename__ = "access_policies"
    
    # Primary key
    policy_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Tenant isolation
    tenant_id = Column(String(100), nullable=False, index=True)
    
    # Document reference (nullable for default policies)
    document_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    
    # Classification level
    classification = Column(String(50), nullable=False, index=True)
    # Values: PUBLIC, INTERNAL_GENERAL, DEPARTMENT_RESTRICTED, CONFIDENTIAL, REGULATED, EXECUTIVE_ONLY
    
    # Allowed access
    allowed_departments = Column(ARRAY(String), nullable=True)
    allowed_groups = Column(ARRAY(String), nullable=True)
    allowed_roles = Column(ARRAY(String), nullable=True)
    allowed_users = Column(ARRAY(String), nullable=True)
    allowed_regions = Column(ARRAY(String), nullable=True)
    
    # Denied access (overrides allowed)
    denied_users = Column(ARRAY(String), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Indexes
    __table_args__ = (
        {"schema": "public"}
    )
    
    def __repr__(self):
        return f"<AccessPolicy(policy_id={self.policy_id}, classification={self.classification})>"


# ============================================================================
# User Session Model (Optional - for session management)
# ============================================================================

class UserSession(Base):
    """
    User session tracking for audit and security.
    
    Tracks active user sessions and token usage.
    """
    
    __tablename__ = "user_sessions"
    
    # Primary key
    session_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # User identification
    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    
    # Session details
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # User agent and IP (for security)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    def __repr__(self):
        return f"<UserSession(session_id={self.session_id}, user_id={self.user_id})>"


# ============================================================================
# Access Denial Log Model (Optional - for security monitoring)
# ============================================================================

class AccessDenialLog(Base):
    """
    Log of access denials for security monitoring.
    
    Tracks when users are denied access to documents/chunks.
    """
    
    __tablename__ = "access_denial_logs"
    
    # Primary key
    log_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # User identification
    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    
    # Resource identification
    document_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    chunk_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    
    # Denial reason
    reason = Column(String(100), nullable=False)
    # Values: tenant_mismatch, explicit_deny, classification_mismatch, 
    #         department_mismatch, group_mismatch, role_mismatch, region_mismatch
    
    # Metadata
    denied_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<AccessDenialLog(log_id={self.log_id}, user_id={self.user_id}, reason={self.reason})>"

# Made with Bob
