"""
Access Control endpoints.

`/filter` is the endpoint the RAG orchestrator must call with the end user's
bearer token for every candidate set from Qdrant, BM25 and the knowledge
graph, before context building (AGENTS.md 5.11, section 14).
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import acl
from app.config import settings
from app.dependencies import get_current_user, get_tenant_db
from app.schemas import (
    AccessCheckRequest,
    AccessDecision,
    BatchAccessCheckRequest,
    BatchAccessCheckResponse,
    FilterChunksRequest,
    FilterChunksResponse,
    RetrievalFilterResponse,
    UserClaims,
    UserPermissionsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Access Control"])


@router.post("/filter", response_model=FilterChunksResponse,
             summary="Partition candidate chunk IDs into authorized and denied")
def filter_chunks(
    request: FilterChunksRequest,
    user: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    result = acl.filter_authorized_chunks(db, user, request.chunk_ids, settings.enforce_clearance)
    if settings.log_access_denials and result.denied:
        try:
            acl.record_decision(db, user, "filter_chunks", result)
        except Exception as e:
            db.rollback()
            logger.error("Failed to record ACL decision: %s", e)
    return FilterChunksResponse(
        authorized_chunk_ids=result.authorized,
        denied_chunk_ids=result.denied,
        reason_by_chunk=result.reasons,
        total_requested=len(request.chunk_ids),
        total_authorized=len(result.authorized),
    )


@router.post("/authorize", response_model=AccessDecision, summary="Check access to one document or chunk")
def authorize_access(
    request: AccessCheckRequest,
    user: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    if request.chunk_id is not None:
        result = acl.filter_authorized_chunks(db, user, [request.chunk_id], settings.enforce_clearance)
        granted = bool(result.authorized)
        reason = "access_granted" if granted else result.reasons[str(request.chunk_id)]
        item_id, item_type = request.chunk_id, "chunk"
    else:
        granted, reason = acl.check_documents(db, user, [request.document_id], settings.enforce_clearance)[
            request.document_id
        ]
        item_id, item_type = request.document_id, "document"
    return AccessDecision(granted=granted, reason=reason, user_id=user.user_id, item_id=item_id, item_type=item_type)


@router.post("/authorize/batch", response_model=BatchAccessCheckResponse,
             summary="Check access to many documents and/or chunks")
def authorize_batch(
    request: BatchAccessCheckRequest,
    user: UserClaims = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    results, reasons = {}, {}
    for doc_id, (granted, reason) in acl.check_documents(
        db, user, request.document_ids, settings.enforce_clearance
    ).items():
        results[str(doc_id)] = granted
        reasons[str(doc_id)] = reason
    chunk_result = acl.filter_authorized_chunks(db, user, request.chunk_ids, settings.enforce_clearance)
    for chunk_id in chunk_result.authorized:
        results[str(chunk_id)] = True
        reasons[str(chunk_id)] = "access_granted"
    for chunk_id in chunk_result.denied:
        results[str(chunk_id)] = False
        reasons[str(chunk_id)] = chunk_result.reasons[str(chunk_id)]

    granted_count = sum(results.values())
    return BatchAccessCheckResponse(
        results=results, reason_by_item=reasons,
        granted_count=granted_count, denied_count=len(results) - granted_count,
    )


@router.post("/retrieval-filter", response_model=RetrievalFilterResponse,
             summary="Metadata pre-filter for retrievers (not an authorization decision)")
def build_retrieval_filter(user: UserClaims = Depends(get_current_user)):
    return RetrievalFilterResponse(
        filter=acl.build_retrieval_filter(user, settings.enforce_clearance),
        user_id=user.user_id,
        tenant_id=user.tenant_id,
    )


@router.get("/user/permissions", response_model=UserPermissionsResponse, summary="Caller's permission summary")
def get_user_permissions(user: UserClaims = Depends(get_current_user)):
    return UserPermissionsResponse(**acl.get_user_permissions_summary(user, settings.enforce_clearance))
