"""Document endpoints (AGENTS.md 5.1 output contract)."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud
from app.dependencies import get_db_with_tenant_context, get_pagination_params, get_tenant_id
from app.models import DocumentStatus
from app.routers.errors import crud_errors
from app.schemas import DocumentCreate, DocumentResponse, DocumentUpdate, PaginatedResponse

router = APIRouter(tags=["Documents"])


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a document or a new version of one")
def create_document(
    document: DocumentCreate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.create_document(db, tenant_id, document)


@router.get("/documents", response_model=PaginatedResponse[DocumentResponse], summary="List documents")
def list_documents(
    status_filter: Optional[DocumentStatus] = Query(DocumentStatus.ACTIVE, alias="status"),
    current_only: bool = Query(True, description="Only the current version of each document"),
    tenant_id: UUID = Depends(get_tenant_id),
    pagination: dict = Depends(get_pagination_params),
    db: Session = Depends(get_db_with_tenant_context),
):
    documents, total = crud.get_documents(
        db, tenant_id, status=status_filter, current_only=current_only,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse.create(items=documents, total=total, **pagination)


@router.get("/documents/{document_id}", response_model=DocumentResponse, summary="Get document")
def get_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    document = crud.get_document(db, tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")
    return document


@router.put("/documents/{document_id}", response_model=DocumentResponse, summary="Update document metadata")
def update_document(
    document_id: UUID,
    updates: DocumentUpdate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.update_document(db, tenant_id, document_id, updates)


@router.post("/documents/{document_id}/activate", response_model=DocumentResponse,
             summary="Activate a version (archives the previous current version)")
def activate_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.activate_document(db, tenant_id, document_id)


@router.post("/documents/{document_id}/archive", response_model=DocumentResponse, summary="Archive document")
def archive_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.mark_document_archived(db, tenant_id, document_id)


@router.delete("/documents/{document_id}", response_model=DocumentResponse, summary="Delete document (soft)")
def delete_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.mark_document_deleted(db, tenant_id, document_id)


@router.get("/documents/{document_id}/versions", response_model=List[DocumentResponse],
            summary="All versions of the logical document, newest first")
def list_document_versions(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.list_document_versions(db, tenant_id, document_id)


@router.get("/documents/{document_id}/version", response_model=DocumentResponse,
            summary="Current version of the logical document this version belongs to")
def get_current_document_version(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    document = crud.get_document(db, tenant_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")
    current = crud.get_current_document_version(db, tenant_id, document.source_uri)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document has no current version")
    return current
