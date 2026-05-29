"""
Document CRUD API endpoints.

This module provides REST API endpoints for document management including
creation, retrieval, update, deletion, and archival operations.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.dependencies import get_db_with_tenant_context, get_pagination_params, get_tenant_id
from app.schemas import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# Document Endpoints
# ============================================================================

@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create document",
    description="Create a new document with metadata",
    tags=["Documents"]
)
async def create_document(
    document: DocumentCreate,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Create a new document.
    
    Args:
        document: Document creation data
        db: Database session with tenant context
        
    Returns:
        Created document
        
    Raises:
        400: Invalid input data
        404: Tenant not found
        409: Duplicate document (same checksum)
        500: Database error
    """
    try:
        logger.info(f"Creating document: {document.title}")
        db_document = crud.create_document(db, document)
        return db_document
        
    except crud.NotFoundError as e:
        logger.warning(f"Tenant not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except crud.DuplicateError as e:
        logger.warning(f"Duplicate document: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except crud.DatabaseError as e:
        logger.error(f"Database error creating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document"
        )


@router.get(
    "/documents",
    response_model=PaginatedResponse[DocumentResponse],
    summary="List documents",
    description="List documents with pagination and filtering",
    tags=["Documents"]
)
async def list_documents(
    status_filter: str = Query(
        default="active",
        alias="status",
        description="Filter by document status"
    ),
    tenant_id: str = Depends(get_tenant_id),
    pagination: dict = Depends(get_pagination_params),
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    List documents with pagination.
    
    Args:
        status_filter: Document status filter (active, archived, deleted)
        tenant_id: Tenant ID from header
        pagination: Pagination parameters (limit, offset)
        db: Database session with tenant context
        
    Returns:
        Paginated list of documents
        
    Raises:
        400: Invalid pagination parameters
        500: Database error
    """
    try:
        logger.debug(f"Listing documents for tenant {tenant_id}, status={status_filter}")
        
        documents, total = crud.get_documents(
            db,
            tenant_id=tenant_id,
            status=status_filter,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
        return PaginatedResponse.create(
            items=documents,
            total=total,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
    except crud.DatabaseError as e:
        logger.error(f"Database error listing documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents"
        )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document",
    description="Get document by ID",
    tags=["Documents"]
)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Get document by ID.
    
    Args:
        document_id: Document UUID
        db: Database session with tenant context
        
    Returns:
        Document details
        
    Raises:
        404: Document not found
        500: Database error
    """
    try:
        logger.debug(f"Getting document {document_id}")
        
        document = crud.get_document(db, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        return document
        
    except crud.DatabaseError as e:
        logger.error(f"Database error getting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document"
        )


@router.put(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Update document",
    description="Update document metadata",
    tags=["Documents"]
)
async def update_document(
    document_id: UUID,
    updates: DocumentUpdate,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Update document metadata.
    
    Args:
        document_id: Document UUID
        updates: Update data
        db: Database session with tenant context
        
    Returns:
        Updated document
        
    Raises:
        404: Document not found
        500: Database error
    """
    try:
        logger.info(f"Updating document {document_id}")
        
        document = crud.update_document(db, document_id, updates)
        return document
        
    except crud.NotFoundError as e:
        logger.warning(f"Document not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except crud.DatabaseError as e:
        logger.error(f"Database error updating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update document"
        )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document",
    description="Delete document (soft delete)",
    tags=["Documents"]
)
async def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Delete document (soft delete by setting status to 'deleted').
    
    Args:
        document_id: Document UUID
        db: Database session with tenant context
        
    Returns:
        No content (204)
        
    Raises:
        404: Document not found
        500: Database error
    """
    try:
        logger.info(f"Deleting document {document_id}")
        
        deleted = crud.delete_document(db, document_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        return None
        
    except crud.DatabaseError as e:
        logger.error(f"Database error deleting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )


@router.post(
    "/documents/{document_id}/archive",
    response_model=DocumentResponse,
    summary="Archive document",
    description="Archive document by setting status to 'archived'",
    tags=["Documents"]
)
async def archive_document(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Archive document.
    
    Args:
        document_id: Document UUID
        db: Database session with tenant context
        
    Returns:
        Archived document
        
    Raises:
        404: Document not found
        500: Database error
    """
    try:
        logger.info(f"Archiving document {document_id}")
        
        archived = crud.mark_document_archived(db, document_id)
        if not archived:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        # Get and return the archived document
        document = crud.get_document(db, document_id)
        return document
        
    except crud.DatabaseError as e:
        logger.error(f"Database error archiving document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to archive document"
        )


@router.get(
    "/documents/{document_id}/version",
    summary="Get current version",
    description="Get current version of a document",
    tags=["Documents"]
)
async def get_document_version(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Get current version of a document.
    
    Args:
        document_id: Document UUID
        db: Database session with tenant context
        
    Returns:
        Current document version
        
    Raises:
        404: Document or version not found
        500: Database error
    """
    try:
        logger.debug(f"Getting current version for document {document_id}")
        
        # Verify document exists
        document = crud.get_document(db, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        # Get current version
        version = crud.get_current_version(db, document_id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No version found for document {document_id}"
            )
        
        return version
        
    except crud.DatabaseError as e:
        logger.error(f"Database error getting document version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document version"
        )

# Made with Bob
