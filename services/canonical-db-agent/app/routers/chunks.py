"""
Chunk CRUD API endpoints.

This module provides REST API endpoints for document chunk management including
creation, retrieval, and batch operations.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.dependencies import get_db_with_tenant_context, get_pagination_params
from app.schemas import (
    ChunkBatchRequest,
    ChunkCreate,
    ChunkResponse,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# Chunk Endpoints
# ============================================================================

@router.post(
    "/chunks",
    response_model=ChunkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create chunk",
    description="Create a new document chunk",
    tags=["Chunks"]
)
async def create_chunk(
    chunk: ChunkCreate,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Create a new chunk.
    
    Args:
        chunk: Chunk creation data
        db: Database session with tenant context
        
    Returns:
        Created chunk
        
    Raises:
        400: Invalid input data
        404: Document not found
        409: Duplicate chunk
        500: Database error
    """
    try:
        logger.info(f"Creating chunk for document {chunk.document_id}")
        db_chunk = crud.create_chunk(db, chunk)
        return db_chunk
        
    except crud.NotFoundError as e:
        logger.warning(f"Document not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except crud.TenantMismatchError as e:
        logger.warning(f"Tenant mismatch: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except crud.DuplicateError as e:
        logger.warning(f"Duplicate chunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except crud.DatabaseError as e:
        logger.error(f"Database error creating chunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chunk"
        )


@router.post(
    "/chunks/bulk",
    response_model=List[ChunkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk create chunks",
    description="Create multiple chunks in a single request",
    tags=["Chunks"]
)
async def bulk_create_chunks(
    chunks: List[ChunkCreate],
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Bulk create chunks.
    
    All chunks must belong to the same document.
    
    Args:
        chunks: List of chunk creation data
        db: Database session with tenant context
        
    Returns:
        List of created chunks
        
    Raises:
        400: Invalid input data or chunks from different documents
        404: Document not found
        500: Database error
    """
    try:
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chunks list cannot be empty"
            )
        
        if len(chunks) > 10000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create more than 10,000 chunks in a single request"
            )
        
        logger.info(f"Bulk creating {len(chunks)} chunks")
        db_chunks = crud.bulk_create_chunks(db, chunks)
        return db_chunks
        
    except crud.NotFoundError as e:
        logger.warning(f"Document not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except crud.TenantMismatchError as e:
        logger.warning(f"Tenant mismatch: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except crud.DatabaseError as e:
        logger.error(f"Database error bulk creating chunks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk create chunks"
        )


@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkResponse,
    summary="Get chunk",
    description="Get chunk by ID",
    tags=["Chunks"]
)
async def get_chunk(
    chunk_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Get chunk by ID.
    
    Args:
        chunk_id: Chunk UUID
        db: Database session with tenant context
        
    Returns:
        Chunk details
        
    Raises:
        404: Chunk not found
        500: Database error
    """
    try:
        logger.debug(f"Getting chunk {chunk_id}")
        
        chunk = crud.get_chunk(db, chunk_id)
        if not chunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk {chunk_id} not found"
            )
        
        return chunk
        
    except crud.DatabaseError as e:
        logger.error(f"Database error getting chunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get chunk"
        )


@router.post(
    "/chunks/batch",
    response_model=List[ChunkResponse],
    summary="Get chunks batch",
    description="Get multiple chunks by IDs",
    tags=["Chunks"]
)
async def get_chunks_batch(
    request: ChunkBatchRequest,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Get multiple chunks by IDs.
    
    Args:
        request: Batch request with chunk IDs
        db: Database session with tenant context
        
    Returns:
        List of chunks (may be fewer than requested if some not found)
        
    Raises:
        400: Invalid request (empty list or too many IDs)
        500: Database error
    """
    try:
        if not request.chunk_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chunk IDs list cannot be empty"
            )
        
        logger.debug(f"Getting batch of {len(request.chunk_ids)} chunks")
        
        chunks = crud.get_chunks_by_ids(db, request.chunk_ids)
        return chunks
        
    except crud.DatabaseError as e:
        logger.error(f"Database error getting chunks batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get chunks"
        )


@router.get(
    "/documents/{document_id}/chunks",
    response_model=PaginatedResponse[ChunkResponse],
    summary="Get document chunks",
    description="Get all chunks for a document with pagination",
    tags=["Chunks"]
)
async def get_document_chunks(
    document_id: UUID,
    pagination: dict = Depends(get_pagination_params),
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Get all chunks for a document with pagination.
    
    Args:
        document_id: Document UUID
        pagination: Pagination parameters (limit, offset)
        db: Database session with tenant context
        
    Returns:
        Paginated list of chunks
        
    Raises:
        404: Document not found
        500: Database error
    """
    try:
        logger.debug(f"Getting chunks for document {document_id}")
        
        # Verify document exists
        document = crud.get_document(db, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        # Get chunks
        chunks, total = crud.get_chunks_by_document(
            db,
            document_id=document_id,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
        return PaginatedResponse.create(
            items=chunks,
            total=total,
            limit=pagination["limit"],
            offset=pagination["offset"]
        )
        
    except crud.DatabaseError as e:
        logger.error(f"Database error getting document chunks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document chunks"
        )


@router.get(
    "/documents/{document_id}/chunks/count",
    summary="Count document chunks",
    description="Get total count of chunks for a document",
    tags=["Chunks"]
)
async def count_document_chunks(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """
    Get total count of chunks for a document.
    
    Args:
        document_id: Document UUID
        db: Database session with tenant context
        
    Returns:
        Chunk count
        
    Raises:
        404: Document not found
        500: Database error
    """
    try:
        logger.debug(f"Counting chunks for document {document_id}")
        
        # Verify document exists
        document = crud.get_document(db, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        # Get count
        _, total = crud.get_chunks_by_document(
            db,
            document_id=document_id,
            limit=1,
            offset=0
        )
        
        return {
            "document_id": document_id,
            "chunk_count": total
        }
        
    except crud.DatabaseError as e:
        logger.error(f"Database error counting chunks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to count chunks"
        )

# Made with Bob
