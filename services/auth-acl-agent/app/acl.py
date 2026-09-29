"""
Access Control engine (AGENTS.md 5.2 / 5.11).

This is the mandatory security boundary before any text reaches the LLM. It
fails closed: anything that cannot be positively authorized against the
current PostgreSQL state (unknown chunk, other tenant, inactive or
non-current version, missing grant, lookup error) is denied.

Decision order for one document:
  1. tenant matches                             else tenant_mismatch
  2. status ACTIVE and current version          else document_<status> / document_not_current
  3. no applicable policy denies the user       else explicit_deny
  4. clearance >= classification (CONFIDENTIAL+) else clearance_insufficient
  5. region restrictions of applicable policies else region_mismatch
  6. a grant exists:
       PUBLIC
       INTERNAL_GENERAL and the user is an employee
       DEPARTMENT_RESTRICTED and document.department == user.department
       an applicable policy allows the user's department / group / role / id
                                                else not_employee / department_mismatch / no_matching_grant

A policy applies to a document when every selector it sets matches
(document_id, classification, department, region, tags). All string
comparisons are case-insensitive.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.claims import CLEARANCE_LEVELS, CLEARANCE_RANK
from app.models import AccessPolicy, AuditLog, Document, DocumentChunk
from app.schemas import UserClaims

logger = logging.getLogger(__name__)

HIGH_CLEARANCE_RANK = CLEARANCE_RANK["CONFIDENTIAL"]


# ============================================================================
# Plain data used by the pure decision function
# ============================================================================

def _lower_set(values: Optional[Iterable]) -> frozenset:
    return frozenset(str(v).strip().lower() for v in (values or []) if v is not None and str(v).strip())


@dataclass(frozen=True)
class Resource:
    document_id: UUID
    tenant_id: str
    classification: str
    status: str
    is_current_version: bool
    department: Optional[str] = None
    region: Optional[str] = None
    tags: frozenset = frozenset()

    @classmethod
    def from_row(cls, doc: Document) -> "Resource":
        return cls(
            document_id=doc.document_id,
            tenant_id=str(doc.tenant_id),
            classification=str(doc.classification).upper(),
            status=str(doc.status).upper(),
            is_current_version=bool(doc.is_current_version),
            department=(doc.department or "").strip().lower() or None,
            region=(doc.region or "").strip().lower() or None,
            tags=_lower_set(doc.tags),
        )


@dataclass(frozen=True)
class Policy:
    name: str
    priority: int = 100
    document_id: Optional[UUID] = None
    classification: Optional[str] = None
    department: Optional[str] = None
    region: Optional[str] = None
    tags: frozenset = frozenset()
    allowed_users: frozenset = frozenset()
    denied_users: frozenset = frozenset()
    allowed_groups: frozenset = frozenset()
    denied_groups: frozenset = frozenset()
    allowed_departments: frozenset = frozenset()
    denied_departments: frozenset = frozenset()
    allowed_roles: frozenset = frozenset()
    denied_roles: frozenset = frozenset()
    allowed_regions: frozenset = frozenset()
    denied_regions: frozenset = frozenset()

    @classmethod
    def from_row(cls, row: AccessPolicy) -> "Policy":
        return cls(
            name=row.policy_name,
            priority=row.priority or 100,
            document_id=row.document_id,
            classification=str(row.classification).upper() if row.classification else None,
            department=(row.department or "").strip().lower() or None,
            region=(row.region or "").strip().lower() or None,
            tags=_lower_set(row.tags),
            allowed_users=_lower_set(row.allowed_users),
            denied_users=_lower_set(row.denied_users),
            allowed_groups=_lower_set(g.lstrip("/") for g in (row.allowed_groups or [])),
            denied_groups=_lower_set(g.lstrip("/") for g in (row.denied_groups or [])),
            allowed_departments=_lower_set(row.allowed_departments),
            denied_departments=_lower_set(row.denied_departments),
            allowed_roles=_lower_set(row.allowed_roles),
            denied_roles=_lower_set(row.denied_roles),
            allowed_regions=_lower_set(row.allowed_regions),
            denied_regions=_lower_set(row.denied_regions),
        )

    def applies_to(self, resource: Resource) -> bool:
        if self.document_id is not None and self.document_id != resource.document_id:
            return False
        if self.classification and self.classification != resource.classification:
            return False
        if self.department and self.department != resource.department:
            return False
        if self.region and self.region != resource.region:
            return False
        if self.tags and not (self.tags & resource.tags):
            return False
        return True


@dataclass(frozen=True)
class Subject:
    """User claims prepared for set comparisons."""
    user_id: str
    tenant_id: str
    department: Optional[str]
    groups: frozenset
    roles: frozenset
    locations: frozenset  # region and country
    clearance_rank: int
    is_employee: bool

    @classmethod
    def from_claims(cls, claims: UserClaims) -> "Subject":
        return cls(
            user_id=claims.user_id.strip().lower(),
            tenant_id=str(claims.tenant_id),
            department=(claims.department or "").strip().lower() or None,
            groups=_lower_set(claims.groups),
            roles=_lower_set(claims.roles),
            locations=_lower_set([claims.region, claims.country]),
            clearance_rank=CLEARANCE_RANK.get(claims.clearance, 0),
            is_employee=claims.is_employee,
        )


@dataclass
class FilterResult:
    authorized: List[UUID] = field(default_factory=list)
    denied: List[UUID] = field(default_factory=list)
    reasons: Dict[str, str] = field(default_factory=dict)


# ============================================================================
# Pure decision function
# ============================================================================

def _denied_by(policy: Policy, subject: Subject) -> bool:
    return bool(
        subject.user_id in policy.denied_users
        or subject.groups & policy.denied_groups
        or (subject.department and subject.department in policy.denied_departments)
        or subject.roles & policy.denied_roles
        or subject.locations & policy.denied_regions
    )


def _granted_by(policy: Policy, subject: Subject) -> bool:
    return bool(
        subject.user_id in policy.allowed_users
        or subject.groups & policy.allowed_groups
        or (subject.department and subject.department in policy.allowed_departments)
        or subject.roles & policy.allowed_roles
    )


def evaluate(
    subject: Subject,
    resource: Resource,
    policies: Sequence[Policy],
    enforce_clearance: bool = True,
) -> Tuple[bool, str]:
    """Return (granted, reason) for one document. Pure; no I/O."""
    if subject.tenant_id != resource.tenant_id:
        return False, "tenant_mismatch"
    if resource.status != "ACTIVE":
        return False, f"document_{resource.status.lower()}"
    if not resource.is_current_version:
        return False, "document_not_current"

    applicable = sorted((p for p in policies if p.applies_to(resource)), key=lambda p: -p.priority)

    # Deny always overrides allow.
    if any(_denied_by(p, subject) for p in applicable):
        return False, "explicit_deny"

    classification_rank = CLEARANCE_RANK.get(resource.classification)
    if classification_rank is None:
        return False, "unknown_classification"
    if enforce_clearance and classification_rank >= HIGH_CLEARANCE_RANK and subject.clearance_rank < classification_rank:
        return False, "clearance_insufficient"

    for policy in applicable:
        if policy.allowed_regions and not (subject.locations & policy.allowed_regions):
            return False, "region_mismatch"

    if resource.classification == "PUBLIC":
        return True, "public_access"
    if resource.classification == "INTERNAL_GENERAL" and subject.is_employee:
        return True, "internal_access"
    if (
        resource.classification == "DEPARTMENT_RESTRICTED"
        and resource.department
        and subject.department == resource.department
    ):
        return True, "department_access"
    for policy in applicable:
        if _granted_by(policy, subject):
            return True, f"policy_grant:{policy.name}"

    if resource.classification == "INTERNAL_GENERAL":
        return False, "not_employee"
    if resource.classification == "DEPARTMENT_RESTRICTED":
        return False, "department_mismatch"
    return False, "no_matching_grant"


# ============================================================================
# PostgreSQL loaders
# ============================================================================

def _load_policies(db: Session, tenant_id: str, document_ids: Iterable[UUID]) -> List[Policy]:
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(AccessPolicy).where(
            AccessPolicy.tenant_id == tenant_id,
            AccessPolicy.is_active.is_(True),
            or_(AccessPolicy.effective_from.is_(None), AccessPolicy.effective_from <= now),
            or_(AccessPolicy.effective_until.is_(None), AccessPolicy.effective_until > now),
            or_(AccessPolicy.document_id.is_(None), AccessPolicy.document_id.in_(list(document_ids))),
        )
    ).scalars().all()
    return [Policy.from_row(row) for row in rows]


def _decide_many(
    subject: Subject,
    resources: Dict[UUID, Resource],
    policies: Sequence[Policy],
    enforce_clearance: bool,
) -> Dict[UUID, Tuple[bool, str]]:
    return {doc_id: evaluate(subject, res, policies, enforce_clearance) for doc_id, res in resources.items()}


def filter_authorized_chunks(
    db: Session,
    claims: UserClaims,
    chunk_ids: Sequence[UUID],
    enforce_clearance: bool = True,
) -> FilterResult:
    """Partition chunk IDs into authorized and denied, with a reason per denial."""
    result = FilterResult()
    unique_ids = list(dict.fromkeys(chunk_ids))
    if not unique_ids:
        return result

    subject = Subject.from_claims(claims)
    rows = db.execute(
        select(DocumentChunk.chunk_id, Document)
        .join(Document, and_(Document.document_id == DocumentChunk.document_id,
                             Document.tenant_id == DocumentChunk.tenant_id))
        .where(DocumentChunk.tenant_id == claims.tenant_id, DocumentChunk.chunk_id.in_(unique_ids))
    ).all()

    chunk_to_doc = {chunk_id: doc.document_id for chunk_id, doc in rows}
    resources = {doc.document_id: Resource.from_row(doc) for _, doc in rows}
    policies = _load_policies(db, claims.tenant_id, resources.keys())
    decisions = _decide_many(subject, resources, policies, enforce_clearance)

    for chunk_id in unique_ids:
        doc_id = chunk_to_doc.get(chunk_id)
        # Unknown IDs and other tenants' IDs look identical to the caller.
        granted, reason = decisions[doc_id] if doc_id else (False, "not_found")
        if granted:
            result.authorized.append(chunk_id)
        else:
            result.denied.append(chunk_id)
            result.reasons[str(chunk_id)] = reason
    return result


def check_documents(
    db: Session,
    claims: UserClaims,
    document_ids: Sequence[UUID],
    enforce_clearance: bool = True,
) -> Dict[UUID, Tuple[bool, str]]:
    unique_ids = list(dict.fromkeys(document_ids))
    if not unique_ids:
        return {}
    subject = Subject.from_claims(claims)
    docs = db.execute(
        select(Document).where(Document.tenant_id == claims.tenant_id, Document.document_id.in_(unique_ids))
    ).scalars().all()
    resources = {doc.document_id: Resource.from_row(doc) for doc in docs}
    policies = _load_policies(db, claims.tenant_id, resources.keys())
    decisions = _decide_many(subject, resources, policies, enforce_clearance)
    return {doc_id: decisions.get(doc_id, (False, "not_found")) for doc_id in unique_ids}


def record_decision(db: Session, claims: UserClaims, action: str, result: FilterResult) -> None:
    """Append the access decision to audit_logs (AGENTS.md 5.11 'log denied chunks')."""
    outcome = "DENY" if not result.authorized else ("PARTIAL" if result.denied else "ALLOW")
    db.add(AuditLog(
        tenant_id=claims.tenant_id,
        event_type="ACL_DECISION",
        event_category="SECURITY",
        user_email=claims.email,
        resource_type="chunk",
        action=action,
        result=outcome,
        details={
            "subject": claims.user_id,
            "authorized_count": len(result.authorized),
            "denied_chunk_ids": [str(c) for c in result.denied],
            "reason_by_chunk": result.reasons,
        },
    ))
    db.commit()


# ============================================================================
# Retrieval pre-filter
# ============================================================================

def build_retrieval_filter(claims: UserClaims, enforce_clearance: bool = True) -> Dict:
    """
    Qdrant-style payload filter for retrieval PRE-filtering (Qdrant, BM25, KG).

    This only narrows candidates; it is never an authorization decision.
    Every candidate must still pass filter_authorized_chunks. Indexers must
    write lowercase values for allowed_departments / allowed_groups /
    allowed_roles / allowed_users / denied_users and department, and
    uppercase classification / status.
    """
    subject = Subject.from_claims(claims)
    should: List[Dict] = [{"key": "classification", "match": {"value": "PUBLIC"}}]
    if subject.is_employee:
        should.append({"key": "classification", "match": {"value": "INTERNAL_GENERAL"}})
    if subject.department:
        should.append({"must": [
            {"key": "classification", "match": {"value": "DEPARTMENT_RESTRICTED"}},
            {"key": "department", "match": {"value": subject.department}},
        ]})
        should.append({"key": "allowed_departments", "match": {"any": [subject.department]}})
    if subject.groups:
        should.append({"key": "allowed_groups", "match": {"any": sorted(subject.groups)}})
    if subject.roles:
        should.append({"key": "allowed_roles", "match": {"any": sorted(subject.roles)}})
    should.append({"key": "allowed_users", "match": {"any": [subject.user_id]}})

    must_not: List[Dict] = [{"key": "denied_users", "match": {"any": [subject.user_id]}}]
    if enforce_clearance:
        above = [c for c in CLEARANCE_LEVELS
                 if CLEARANCE_RANK[c] >= HIGH_CLEARANCE_RANK and CLEARANCE_RANK[c] > subject.clearance_rank]
        if above:
            must_not.append({"key": "classification", "match": {"any": above}})

    return {
        "must": [
            {"key": "tenant_id", "match": {"value": subject.tenant_id}},
            {"key": "status", "match": {"value": "ACTIVE"}},
            {"key": "is_current_version", "match": {"value": True}},
        ],
        "should": should,
        "must_not": must_not,
    }


def get_user_permissions_summary(claims: UserClaims, enforce_clearance: bool = True) -> Dict:
    subject = Subject.from_claims(claims)
    accessible = ["PUBLIC"]
    if subject.is_employee:
        accessible.append("INTERNAL_GENERAL")
    if subject.department:
        accessible.append("DEPARTMENT_RESTRICTED")
    for level in ("CONFIDENTIAL", "REGULATED", "EXECUTIVE_ONLY"):
        if not enforce_clearance or subject.clearance_rank >= CLEARANCE_RANK[level]:
            accessible.append(f"{level} (with policy grant)")
    return {
        "user_id": claims.user_id,
        "tenant_id": claims.tenant_id,
        "department": claims.department,
        "groups": claims.groups,
        "roles": claims.roles,
        "clearance": claims.clearance,
        "is_employee": claims.is_employee,
        "accessible_classifications": accessible,
        "region": claims.region,
        "country": claims.country,
    }
