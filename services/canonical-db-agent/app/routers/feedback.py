"""
Retrieval audit records and user feedback.

These are the raw signals of the self-improvement loop (SELF_IMPROVEMENT.md):
the orchestrator records what was retrieved, denied, shown and cited together
with the parameter values / experiment arms in effect, and users rate the
answer against that record.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.dependencies import get_db_with_tenant_context, get_tenant_id
from app.routers.errors import crud_errors
from app.schemas import FeedbackCreate, FeedbackResponse, RetrievalAuditCreate, RetrievalAuditResponse

router = APIRouter(tags=["Audit & Feedback"])


@router.post("/retrieval-audit", response_model=RetrievalAuditResponse, status_code=status.HTTP_201_CREATED,
             summary="Record a query's retrieval and generation path")
def create_retrieval_audit(
    record: RetrievalAuditCreate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    return crud.create_retrieval_audit(db, tenant_id, record, settings.audit_store_query_text)


@router.get("/retrieval-audit/{audit_id}", response_model=RetrievalAuditResponse,
            summary="Get a retrieval audit record")
def get_retrieval_audit(
    audit_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    record = crud.get_retrieval_audit(db, tenant_id, audit_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit record {audit_id} not found")
    return record


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED,
             summary="Record user feedback on an answer")
def create_feedback(
    feedback: FeedbackCreate,
    tenant_id: UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context),
):
    with crud_errors():
        return crud.create_feedback(db, tenant_id, feedback)
