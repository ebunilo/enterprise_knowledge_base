"""
CRUD operations for database entities.

This module provides all database CRUD operations with tenant isolation,
error handling, and transaction management.
"""

import hashlib
import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    Tenant,
)
from app.schemas import (
    ChunkCreate,
    DocumentCreate,
    DocumentUpdate,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================

class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class NotFoundError(DatabaseError):
    """Exception raised when entity is not found."""
    pass


class DuplicateError(DatabaseError):
    """Exception raised when duplicate entity is created."""
    pass


class TenantMismatchError(DatabaseError):
    """Exception raised when tenant context doesn't match."""
    pass


# ============================================================================
# Tenant Operations
# ============================================================================

def get_tenant(db: Session, tenant_id: str) -> Optional[Tenant]:
    """Get tenant by ID."""
    try:
        return db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting tenant {tenant_id}: {e}")
        raise DatabaseError(f"Failed to get tenant: {e}")


def verify_tenant_exists(db: Session, tenant_id: str) -> None:
    """Verify tenant exists, raise error if not."""
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        raise NotFoundError(f"Tenant {tenant_id} not found")
    if not tenant.is_active:
        raise DatabaseError(f"Tenant {tenant_id} is not active")


# ============================================================================
# Document Operations
# ============================================================================

def create_document(db: Session, document: DocumentCreate) -> Document:
    """
    Create a new document.
    
    Args:
        db: Database session
        document: Document creation data
        
    Returns:
        Created document
        
    Raises:
        NotFoundError: If tenant doesn't exist
        DuplicateError: If document with same checksum exists
        DatabaseError: On other database errors
    """
    try:
        # Verify tenant exists
        verify_tenant_exists(db, document.tenant_id)
        
        # Check for duplicate checksum in active documents
        existing = db.query(Document).filter(
            and_(
                Document.tenant_id == document.tenant_id,
                Document.checksum == document.checksum,
                Document.status == 'active'
            )
        ).first()
        
        if existing:
            raise DuplicateError(
                f"Active document with checksum {document.checksum} already exists"
            )
        
        # Create document
        db_document = Document(**document.model_dump())
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        
        logger.info(f"Created document {db_document.document_id} for tenant {document.tenant_id}")
        return db_document
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating document: {e}")
        raise DuplicateError(f"Document creation failed: {e}")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating document: {e}")
        raise DatabaseError(f"Failed to create document: {e}")


def get_document(db: Session, document_id: UUID) -> Optional[Document]:
    """
    Get document by ID.
    
    Args:
        db: Database session
        document_id: Document UUID
        
    Returns:
        Document if found, None otherwise
    """
    try:
        return db.query(Document).filter(
            Document.document_id == document_id
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting document {document_id}: {e}")
        raise DatabaseError(f"Failed to get document: {e}")


def get_documents(
    db: Session,
    tenant_id: str,
    status: str = "active",
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Document], int]:
    """
    Get documents with pagination.
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        status: Document status filter
        limit: Maximum number of documents to return
        offset: Number of documents to skip
        
    Returns:
        Tuple of (documents list, total count)
    """
    try:
        # Build query
        query = db.query(Document).filter(
            and_(
                Document.tenant_id == tenant_id,
                Document.status == status
            )
        )
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        documents = query.order_by(
            Document.created_at.desc()
        ).limit(limit).offset(offset).all()
        
        return documents, total
        
    except SQLAlchemyError as e:
        logger.error(f"Error getting documents: {e}")
        raise DatabaseError(f"Failed to get documents: {e}")


def update_document(
    db: Session,
    document_id: UUID,
    updates: DocumentUpdate
) -> Document:
    """
    Update document.
    
    Args:
        db: Database session
        document_id: Document UUID
        updates: Update data
        
    Returns:
        Updated document
        
    Raises:
        NotFoundError: If document doesn't exist
        DatabaseError: On database errors
    """
    try:
        document = get_document(db, document_id)
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Apply updates
        update_data = updates.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)
        
        db.commit()
        db.refresh(document)
        
        logger.info(f"Updated document {document_id}")
        return document
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating document {document_id}: {e}")
        raise DatabaseError(f"Failed to update document: {e}")


def delete_document(db: Session, document_id: UUID) -> bool:
    """
    Delete document (soft delete by setting status).
    
    Args:
        db: Database session
        document_id: Document UUID
        
    Returns:
        True if deleted, False if not found
    """
    try:
        document = get_document(db, document_id)
        if not document:
            return False
        
        document.status = 'deleted'
        db.commit()
        
        logger.info(f"Deleted document {document_id}")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting document {document_id}: {e}")
        raise DatabaseError(f"Failed to delete document: {e}")


def mark_document_archived(db: Session, document_id: UUID) -> bool:
    """
    Archive document.
    
    Args:
        db: Database session
        document_id: Document UUID
        
    Returns:
        True if archived, False if not found
    """
    try:
        document = get_document(db, document_id)
        if not document:
            return False
        
        document.status = 'archived'
        db.commit()
        
        logger.info(f"Archived document {document_id}")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error archiving document {document_id}: {e}")
        raise DatabaseError(f"Failed to archive document: {e}")


# ============================================================================
# Chunk Operations
# ============================================================================

def create_chunk(db: Session, chunk: ChunkCreate) -> DocumentChunk:
    """
    Create a new chunk.
    
    Args:
        db: Database session
        chunk: Chunk creation data
        
    Returns:
        Created chunk
        
    Raises:
        NotFoundError: If document doesn't exist
        DatabaseError: On database errors
    """
    try:
        # Verify document exists
        document = get_document(db, chunk.document_id)
        if not document:
            raise NotFoundError(f"Document {chunk.document_id} not found")
        
        # Verify tenant matches
        if document.tenant_id != chunk.tenant_id:
            raise TenantMismatchError(
                f"Chunk tenant {chunk.tenant_id} doesn't match document tenant {document.tenant_id}"
            )
        
        # Create chunk
        db_chunk = DocumentChunk(**chunk.model_dump())
        db.add(db_chunk)
        db.commit()
        db.refresh(db_chunk)
        
        logger.info(f"Created chunk {db_chunk.chunk_id} for document {chunk.document_id}")
        return db_chunk
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating chunk: {e}")
        raise DuplicateError(f"Chunk creation failed: {e}")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating chunk: {e}")
        raise DatabaseError(f"Failed to create chunk: {e}")


def bulk_create_chunks(
    db: Session,
    chunks: List[ChunkCreate],
    batch_size: int = 1000
) -> List[DocumentChunk]:
    """
    Bulk create chunks with batching.
    
    Args:
        db: Database session
        chunks: List of chunk creation data
        batch_size: Number of chunks per batch
        
    Returns:
        List of created chunks
        
    Raises:
        NotFoundError: If document doesn't exist
        DatabaseError: On database errors
    """
    try:
        if not chunks:
            return []
        
        # Verify all chunks belong to same document
        document_ids = set(chunk.document_id for chunk in chunks)
        if len(document_ids) > 1:
            raise DatabaseError("All chunks must belong to the same document")
        
        document_id = chunks[0].document_id
        tenant_id = chunks[0].tenant_id
        
        # Verify document exists
        document = get_document(db, document_id)
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Verify tenant matches
        if document.tenant_id != tenant_id:
            raise TenantMismatchError(
                f"Chunk tenant {tenant_id} doesn't match document tenant {document.tenant_id}"
            )
        
        created_chunks = []
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            db_chunks = [DocumentChunk(**chunk.model_dump()) for chunk in batch]
            db.bulk_save_objects(db_chunks, return_defaults=True)
            db.commit()
            created_chunks.extend(db_chunks)
            
            logger.info(f"Created batch of {len(db_chunks)} chunks for document {document_id}")
        
        return created_chunks
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error bulk creating chunks: {e}")
        raise DatabaseError(f"Failed to bulk create chunks: {e}")


def get_chunk(db: Session, chunk_id: UUID) -> Optional[DocumentChunk]:
    """
    Get chunk by ID.
    
    Args:
        db: Database session
        chunk_id: Chunk UUID
        
    Returns:
        Chunk if found, None otherwise
    """
    try:
        return db.query(DocumentChunk).filter(
            DocumentChunk.chunk_id == chunk_id
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting chunk {chunk_id}: {e}")
        raise DatabaseError(f"Failed to get chunk: {e}")


def get_chunks_by_ids(
    db: Session,
    chunk_ids: List[UUID]
) -> List[DocumentChunk]:
    """
    Get multiple chunks by IDs.
    
    Args:
        db: Database session
        chunk_ids: List of chunk UUIDs
        
    Returns:
        List of chunks (may be fewer than requested if some not found)
    """
    try:
        if not chunk_ids:
            return []
        
        return db.query(DocumentChunk).filter(
            DocumentChunk.chunk_id.in_(chunk_ids)
        ).all()
        
    except SQLAlchemyError as e:
        logger.error(f"Error getting chunks by IDs: {e}")
        raise DatabaseError(f"Failed to get chunks: {e}")


def get_chunks_by_document(
    db: Session,
    document_id: UUID,
    limit: int = 1000,
    offset: int = 0
) -> Tuple[List[DocumentChunk], int]:
    """
    Get chunks for a document with pagination.
    
    Args:
        db: Database session
        document_id: Document UUID
        limit: Maximum number of chunks to return
        offset: Number of chunks to skip
        
    Returns:
        Tuple of (chunks list, total count)
    """
    try:
        # Build query
        query = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        )
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        chunks = query.order_by(
            DocumentChunk.chunk_index
        ).limit(limit).offset(offset).all()
        
        return chunks, total
        
    except SQLAlchemyError as e:
        logger.error(f"Error getting chunks for document {document_id}: {e}")
        raise DatabaseError(f"Failed to get chunks: {e}")


# ============================================================================
# Version Operations
# ============================================================================

def create_document_version(
    db: Session,
    document_id: UUID,
    tenant_id: str,
    version: str
) -> DocumentVersion:
    """
    Create a new document version.
    
    Args:
        db: Database session
        document_id: Document UUID
        tenant_id: Tenant ID
        version: Version string
        
    Returns:
        Created version
        
    Raises:
        NotFoundError: If document doesn't exist
        DatabaseError: On database errors
    """
    try:
        # Verify document exists
        document = get_document(db, document_id)
        if not document:
            raise NotFoundError(f"Document {document_id} not found")
        
        # Verify tenant matches
        if document.tenant_id != tenant_id:
            raise TenantMismatchError(
                f"Version tenant {tenant_id} doesn't match document tenant {document.tenant_id}"
            )
        
        # Mark all existing versions as not current
        db.query(DocumentVersion).filter(
            and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_current == True
            )
        ).update({"is_current": False})
        
        # Create new version
        db_version = DocumentVersion(
            document_id=document_id,
            tenant_id=tenant_id,
            version=version,
            is_current=True
        )
        db.add(db_version)
        db.commit()
        db.refresh(db_version)
        
        logger.info(f"Created version {version} for document {document_id}")
        return db_version
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating document version: {e}")
        raise DatabaseError(f"Failed to create version: {e}")


def get_current_version(
    db: Session,
    document_id: UUID
) -> Optional[DocumentVersion]:
    """
    Get current version of a document.
    
    Args:
        db: Database session
        document_id: Document UUID
        
    Returns:
        Current version if found, None otherwise
    """
    try:
        return db.query(DocumentVersion).filter(
            and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_current == True
            )
        ).first()
    except SQLAlchemyError as e:
        logger.error(f"Error getting current version for document {document_id}: {e}")
        raise DatabaseError(f"Failed to get current version: {e}")


def archive_old_versions(
    db: Session,
    document_id: UUID,
    current_version: str
) -> int:
    """
    Archive old versions of a document.
    
    Args:
        db: Database session
        document_id: Document UUID
        current_version: Current version string
        
    Returns:
        Number of versions archived
    """
    try:
        result = db.query(DocumentVersion).filter(
            and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version != current_version,
                DocumentVersion.is_current == True
            )
        ).update({"is_current": False})
        
        db.commit()
        
        logger.info(f"Archived {result} old versions for document {document_id}")
        return result
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error archiving old versions: {e}")
        raise DatabaseError(f"Failed to archive versions: {e}")

# Made with Bob
