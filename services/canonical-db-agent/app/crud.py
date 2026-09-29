"""
CRUD operations for canonical records.

Every function takes an explicit tenant_id and filters on it. RLS enforces the
same boundary in the database, but only when the service connects as the
non-superuser application role; the explicit filters keep isolation intact
either way (defence in depth, AGENTS.md section 1.5).

Versioning model: each document version is its own `documents` row. The
logical document is (tenant_id, source_uri). Exactly one version is current.
A new version is created non-current and only replaces the current one when
activated, so retrieval never has a gap or sees two versions at once.
"""

import hashlib
import logging
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    RetrievalAuditLog,
    Tenant,
    UserFeedback,
)
from app.schemas import ChunkCreate, DocumentCreate, DocumentUpdate, FeedbackCreate, RetrievalAuditCreate

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database errors."""


class NotFoundError(DatabaseError):
    """Entity not found (or not visible to this tenant)."""


class DuplicateError(DatabaseError):
    """Entity already exists."""


class ConflictError(DatabaseError):
    """Operation not valid for the entity's current state."""


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================================
# Tenants
# ============================================================================

def resolve_tenant(db: Session, tenant_ref: str) -> Optional[Tenant]:
    """Resolve a tenant by UUID or slug (Keycloak sends the slug)."""
    try:
        tenant_uuid = UUID(tenant_ref)
        condition = Tenant.tenant_id == tenant_uuid
    except ValueError:
        condition = Tenant.tenant_slug == tenant_ref.strip().lower()
    return db.execute(select(Tenant).where(condition)).scalar_one_or_none()


# ============================================================================
# Documents
# ============================================================================

def get_document(db: Session, tenant_id: UUID, document_id: UUID) -> Optional[Document]:
    return db.execute(
        select(Document).where(Document.tenant_id == tenant_id, Document.document_id == document_id)
    ).scalar_one_or_none()


def _require_document(db: Session, tenant_id: UUID, document_id: UUID, for_update: bool = False) -> Document:
    query = select(Document).where(Document.tenant_id == tenant_id, Document.document_id == document_id)
    if for_update:
        query = query.with_for_update()
    document = db.execute(query).scalar_one_or_none()
    if document is None:
        raise NotFoundError(f"Document {document_id} not found")
    return document


def get_current_document_version(db: Session, tenant_id: UUID, source_uri: str) -> Optional[Document]:
    return db.execute(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.source_uri == source_uri,
            Document.is_current_version.is_(True),
            Document.status != DocumentStatus.DELETED,
        )
    ).scalar_one_or_none()


def create_document(db: Session, tenant_id: UUID, data: DocumentCreate) -> Document:
    """
    Create the first version of a document, or a new pending version of an
    existing one. Identical content to the current version is rejected.
    """
    current = db.execute(
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.source_uri == data.source_uri,
            Document.is_current_version.is_(True),
            Document.status != DocumentStatus.DELETED,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if current is not None and current.checksum == data.checksum:
        raise DuplicateError("Document content is unchanged from the current version")

    fields = data.model_dump(exclude={"version", "status", "tags"})
    document = Document(tenant_id=tenant_id, tags=data.tags, **fields)

    if current is None:
        document.version_number = 1
        document.version = data.version or "v1"
        document.is_current_version = True
        document.status = data.status
    else:
        document.version_number = current.version_number + 1
        document.version = data.version or f"v{document.version_number}"
        document.parent_document_id = current.document_id
        # Stays non-current until activate_document() swaps it in.
        document.is_current_version = False
        document.status = DocumentStatus.PENDING if data.status == DocumentStatus.ACTIVE else data.status

    db.add(document)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise DuplicateError(f"Document conflicts with an existing record: {e.orig}") from e
    db.refresh(document)

    # A brand-new document may be created ACTIVE directly; a new version must
    # go through activation so the swap is atomic.
    if current is not None and data.status == DocumentStatus.ACTIVE:
        document = activate_document(db, tenant_id, document.document_id)

    logger.info("Created document %s v%s for tenant %s", document.document_id, document.version_number, tenant_id)
    return document


def activate_document(db: Session, tenant_id: UUID, document_id: UUID) -> Document:
    """Make a version ACTIVE and current, archiving the previous current version."""
    document = _require_document(db, tenant_id, document_id, for_update=True)
    if document.status == DocumentStatus.DELETED:
        raise ConflictError("Deleted documents cannot be activated")

    previous = db.execute(
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.source_uri == document.source_uri,
            Document.is_current_version.is_(True),
            Document.document_id != document.document_id,
        )
        .with_for_update()
    ).scalars().all()

    for old in previous:
        old.is_current_version = False
        if old.status != DocumentStatus.DELETED:
            old.status = DocumentStatus.ARCHIVED
    # Flush the demotion first so the one-current-version index never sees two.
    db.flush()

    document.is_current_version = True
    document.status = DocumentStatus.ACTIVE
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise DuplicateError(f"Activation conflicts with an existing record: {e.orig}") from e
    db.refresh(document)
    return document


def get_documents(
    db: Session,
    tenant_id: UUID,
    status: Optional[DocumentStatus] = DocumentStatus.ACTIVE,
    current_only: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Document], int]:
    conditions = [Document.tenant_id == tenant_id]
    if status is not None:
        conditions.append(Document.status == status)
    if current_only:
        conditions.append(Document.is_current_version.is_(True))

    query = db.query(Document).filter(and_(*conditions))
    total = query.count()
    documents = query.order_by(Document.created_at.desc()).limit(limit).offset(offset).all()
    return documents, total


def update_document(db: Session, tenant_id: UUID, document_id: UUID, updates: DocumentUpdate) -> Document:
    document = _require_document(db, tenant_id, document_id, for_update=True)
    changes = updates.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(document, field, value)

    # Chunks carry a copy of the access metadata for retrieval pre-filtering;
    # keep them in sync so a reclassification is never stale.
    inherited = {k: changes[k] for k in ("classification", "department", "region") if k in changes}
    if inherited:
        db.query(DocumentChunk).filter(
            DocumentChunk.tenant_id == tenant_id, DocumentChunk.document_id == document_id
        ).update(inherited, synchronize_session=False)

    db.commit()
    db.refresh(document)
    return document


def mark_document_archived(db: Session, tenant_id: UUID, document_id: UUID) -> Document:
    document = _require_document(db, tenant_id, document_id, for_update=True)
    if document.status == DocumentStatus.DELETED:
        raise ConflictError("Deleted documents cannot be archived")
    document.status = DocumentStatus.ARCHIVED
    db.commit()
    db.refresh(document)
    return document


def mark_document_deleted(db: Session, tenant_id: UUID, document_id: UUID) -> Document:
    """Soft delete: excluded from every retrieval path immediately."""
    document = _require_document(db, tenant_id, document_id, for_update=True)
    document.status = DocumentStatus.DELETED
    document.is_current_version = False
    db.commit()
    db.refresh(document)
    return document


def list_document_versions(db: Session, tenant_id: UUID, document_id: UUID) -> List[Document]:
    document = _require_document(db, tenant_id, document_id)
    return db.execute(
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.source_uri == document.source_uri)
        .order_by(Document.version_number.desc())
    ).scalars().all()


# ============================================================================
# Chunks
# ============================================================================

def _build_chunk(tenant_id: UUID, document: Document, data: ChunkCreate) -> DocumentChunk:
    checksum = sha256_hex(data.chunk_text)
    if data.checksum is not None and data.checksum.lower() != checksum:
        raise ConflictError(f"Checksum mismatch for chunk_index {data.chunk_index}")
    return DocumentChunk(
        tenant_id=tenant_id,
        document_id=document.document_id,
        chunk_text=data.chunk_text,
        chunk_index=data.chunk_index,
        token_count=data.token_count,
        checksum=checksum,
        page_start=data.page_start,
        page_end=data.page_end,
        section_title=data.section_title,
        heading_path=data.heading_path,
        chunk_type=data.chunk_type,
        # Access metadata always comes from the document, never the caller, so
        # a chunk can never cross a classification boundary.
        classification=document.classification,
        department=document.department,
        region=document.region,
        language=document.language,
    )


def create_chunk(db: Session, tenant_id: UUID, data: ChunkCreate) -> DocumentChunk:
    return bulk_create_chunks(db, tenant_id, [data])[0]


def bulk_create_chunks(db: Session, tenant_id: UUID, chunks: Sequence[ChunkCreate]) -> List[DocumentChunk]:
    """Create chunks for a single document atomically (all or nothing)."""
    if not chunks:
        return []
    document_ids = {chunk.document_id for chunk in chunks}
    if len(document_ids) > 1:
        raise ConflictError("All chunks in a batch must belong to the same document")

    document = _require_document(db, tenant_id, chunks[0].document_id)
    if document.status in (DocumentStatus.DELETED, DocumentStatus.ARCHIVED):
        raise ConflictError(f"Cannot add chunks to a {document.status.value} document")

    db_chunks = [_build_chunk(tenant_id, document, chunk) for chunk in chunks]
    db.add_all(db_chunks)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise DuplicateError(f"Chunk conflicts with an existing record: {e.orig}") from e
    for chunk in db_chunks:
        db.refresh(chunk)
    return db_chunks


def get_chunk(db: Session, tenant_id: UUID, chunk_id: UUID) -> Optional[DocumentChunk]:
    return db.execute(
        select(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.chunk_id == chunk_id)
    ).scalar_one_or_none()


def get_chunks_by_ids(
    db: Session,
    tenant_id: UUID,
    chunk_ids: Sequence[UUID],
    include_inactive: bool = False,
) -> Tuple[List[Tuple[DocumentChunk, Document]], List[UUID]]:
    """
    Resolve chunk IDs (e.g. from Qdrant/BM25/KG) to canonical records, in the
    order requested. By default only chunks of ACTIVE, current document
    versions are returned; everything else is reported as missing.
    """
    if not chunk_ids:
        return [], []

    conditions = [DocumentChunk.tenant_id == tenant_id, DocumentChunk.chunk_id.in_(list(chunk_ids))]
    if not include_inactive:
        conditions += [Document.status == DocumentStatus.ACTIVE, Document.is_current_version.is_(True)]

    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, and_(Document.document_id == DocumentChunk.document_id,
                             Document.tenant_id == DocumentChunk.tenant_id))
        .where(*conditions)
    ).all()

    by_id = {chunk.chunk_id: (chunk, document) for chunk, document in rows}
    ordered, missing, seen = [], [], set()
    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        if chunk_id in by_id:
            ordered.append(by_id[chunk_id])
        else:
            missing.append(chunk_id)
    return ordered, missing


def get_chunks_by_document(
    db: Session, tenant_id: UUID, document_id: UUID, limit: int = 1000, offset: int = 0
) -> Tuple[List[DocumentChunk], int]:
    _require_document(db, tenant_id, document_id)
    query = db.query(DocumentChunk).filter(
        DocumentChunk.tenant_id == tenant_id, DocumentChunk.document_id == document_id
    )
    total = query.count()
    chunks = query.order_by(DocumentChunk.chunk_index).limit(limit).offset(offset).all()
    return chunks, total


# ============================================================================
# Retrieval audit + feedback
# ============================================================================

def create_retrieval_audit(
    db: Session, tenant_id: UUID, data: RetrievalAuditCreate, store_query_text: bool
) -> RetrievalAuditLog:
    fields = data.model_dump(exclude={"query"})
    record = RetrievalAuditLog(
        tenant_id=tenant_id,
        query_hash=sha256_hex(data.query),
        query_text=data.query if store_query_text else None,
        **fields,
    )
    record.retrieval_sources = {str(k): v for k, v in data.retrieval_sources.items()}
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_retrieval_audit(db: Session, tenant_id: UUID, audit_id: UUID) -> Optional[RetrievalAuditLog]:
    return db.execute(
        select(RetrievalAuditLog).where(
            RetrievalAuditLog.tenant_id == tenant_id, RetrievalAuditLog.audit_id == audit_id
        )
    ).scalar_one_or_none()


def create_feedback(db: Session, tenant_id: UUID, data: FeedbackCreate) -> UserFeedback:
    audit = get_retrieval_audit(db, tenant_id, data.audit_id)
    if audit is None:
        raise NotFoundError(f"Answer {data.audit_id} not found")
    if audit.user_id != data.user_id:
        # Only the person who received the answer can rate it.
        raise ConflictError("Feedback must come from the user who received the answer")
    # Chunk-level feedback may only reference what the user was shown.
    shown = set(audit.context_chunk_ids or [])
    if not set(data.helpful_chunk_ids + data.unhelpful_chunk_ids) <= shown:
        raise ConflictError("Chunk feedback may only reference chunks that were in the answer context")

    feedback = UserFeedback(tenant_id=tenant_id, **data.model_dump())
    db.add(feedback)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise DuplicateError("Feedback already recorded for this answer") from e
    db.refresh(feedback)
    return feedback
