"""Chunk endpoints (AGENTS.md 5.1 output contract)."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.dependencies import get_db_with_tenant_context, get_pagination_params, get_tenant_id
from app.routers.errors import crud_errors
from app.schemas import (
    ChunkBatchRequest,
    ChunkBatchResponse,
    ChunkCreate,
    ChunkResponse,
    ChunkWithSource,
    PaginatedResponse,
)

router = APIRouter(tags=["Chunks"])


@router.post("/chunks", response_model=ChunkResponse, status_code=status.HTTP_201_CREATED,
             summary="Create chunk")
def create_chunk(
    chunk: ChunkCreate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.create_chunk(db, tenant_id, chunk)


@router.post("/chunks/bulk", response_model=List[ChunkResponse], status_code=status.HTTP_201_CREATED,
             summary="Create chunks for one document atomically")
def bulk_create_chunks(
    chunks: List[ChunkCreate] = Body(..., min_length=1, max_length=5000),
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.bulk_create_chunks(db, tenant_id, chunks)


@router.get("/chunks/{chunk_id}", response_model=ChunkResponse, summary="Get chunk")
def get_chunk(
    chunk_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    chunk = crud.get_chunk(db, tenant_id, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chunk {chunk_id} not found")
    return chunk


@router.post("/chunks/batch", response_model=ChunkBatchResponse,
             summary="Resolve chunk IDs to canonical records, in request order")
def get_chunks_batch(
    request: ChunkBatchRequest,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    """
    Resolves retriever output back to PostgreSQL. Chunks of archived, deleted
    or non-current versions are returned in `missing_chunk_ids` unless
    `include_inactive` is set (admin workflows). This is not an authorization
    check; callers must still validate with auth-acl-agent `/acl/filter`.
    """
    rows, missing = crud.get_chunks_by_ids(db, tenant_id, request.chunk_ids, request.include_inactive)
    chunks = [
        ChunkWithSource(
            **ChunkResponse.model_validate(chunk).model_dump(),
            title=document.title,
            version=document.version,
            source_uri=document.source_uri,
            document_status=document.status,
            is_current_version=document.is_current_version,
        )
        for chunk, document in rows
    ]
    return ChunkBatchResponse(chunks=chunks, missing_chunk_ids=missing)


@router.get("/documents/{document_id}/chunks", response_model=PaginatedResponse[ChunkResponse],
            summary="List chunks of a document version")
def get_document_chunks(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    pagination: dict = Depends(get_pagination_params),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        chunks, total = crud.get_chunks_by_document(db, tenant_id, document_id, **pagination)
    return PaginatedResponse.create(items=chunks, total=total, **pagination)
