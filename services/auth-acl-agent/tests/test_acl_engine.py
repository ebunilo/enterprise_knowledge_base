"""
Unit tests for the pure ACL decision function (AGENTS.md 5.2 and 5.11).
"""

import uuid
from dataclasses import replace

from app.acl import Policy, Resource, Subject, build_retrieval_filter, evaluate
from app.claims import CLEARANCE_RANK
from app.schemas import UserClaims

TENANT = str(uuid.uuid4())


def subject(**overrides) -> Subject:
    base = dict(
        user_id="user-1",
        tenant_id=TENANT,
        department="engineering",
        groups=frozenset({"engineering", "internal-users"}),
        roles=frozenset({"senior_engineer"}),
        locations=frozenset({"emea", "germany"}),
        clearance_rank=CLEARANCE_RANK["DEPARTMENT_RESTRICTED"],
        is_employee=True,
    )
    base.update(overrides)
    return Subject(**base)


def resource(classification="INTERNAL_GENERAL", **overrides) -> Resource:
    base = dict(
        document_id=uuid.uuid4(),
        tenant_id=TENANT,
        classification=classification,
        status="ACTIVE",
        is_current_version=True,
        department=None,
        region="global",
    )
    base.update(overrides)
    return Resource(**base)


FINANCE_USER = subject(department="finance", groups=frozenset({"finance", "internal-users"}),
                       roles=frozenset({"finance_manager"}), clearance_rank=CLEARANCE_RANK["CONFIDENTIAL"])
EXTERNAL_USER = subject(department="external", groups=frozenset({"external-users"}), roles=frozenset(),
                        clearance_rank=CLEARANCE_RANK["PUBLIC"], is_employee=False)


# --- Classification defaults ------------------------------------------------

def test_public_document_accessible_to_all_users():
    doc = resource("PUBLIC")
    for user in (FINANCE_USER, EXTERNAL_USER, subject()):
        assert evaluate(user, doc, []) == (True, "public_access")


def test_internal_document_only_for_employees():
    doc = resource("INTERNAL_GENERAL")
    assert evaluate(subject(), doc, [])[0] is True
    assert evaluate(EXTERNAL_USER, doc, []) == (False, "not_employee")


def test_finance_document_accessible_to_finance_users():
    doc = resource("DEPARTMENT_RESTRICTED", department="finance")
    assert evaluate(FINANCE_USER, doc, []) == (True, "department_access")


def test_finance_document_denied_to_engineering_users():
    doc = resource("DEPARTMENT_RESTRICTED", department="finance")
    assert evaluate(subject(), doc, []) == (False, "department_mismatch")


def test_confidential_requires_explicit_grant_even_within_department():
    doc = resource("CONFIDENTIAL", department="finance")
    assert evaluate(FINANCE_USER, doc, []) == (False, "no_matching_grant")


# --- Policies ------------------------------------------------------------------

def test_group_grant():
    doc = resource("CONFIDENTIAL", department="finance")
    policy = Policy(name="payroll", document_id=doc.document_id, allowed_groups=frozenset({"finance"}))
    assert evaluate(FINANCE_USER, doc, [policy]) == (True, "policy_grant:payroll")


def test_role_and_user_grants():
    doc = resource("DEPARTMENT_RESTRICTED", department="hr")
    by_role = Policy(name="r", classification="DEPARTMENT_RESTRICTED", allowed_roles=frozenset({"finance_manager"}))
    by_user = Policy(name="u", document_id=doc.document_id, allowed_users=frozenset({"user-1"}))
    assert evaluate(FINANCE_USER, doc, [by_role])[0] is True
    assert evaluate(subject(), doc, [by_user])[0] is True


def test_explicit_deny_overrides_explicit_allow():
    doc = resource("PUBLIC")
    allow = Policy(name="allow", document_id=doc.document_id, allowed_users=frozenset({"user-1"}), priority=500)
    deny = Policy(name="deny", document_id=doc.document_id, denied_users=frozenset({"user-1"}), priority=1)
    assert evaluate(subject(), doc, [allow, deny]) == (False, "explicit_deny")


def test_denied_group_overrides_department_default():
    doc = resource("DEPARTMENT_RESTRICTED", department="finance")
    deny = Policy(name="no-contractors", department="finance", denied_groups=frozenset({"contractors"}))
    contractor = replace(FINANCE_USER, groups=FINANCE_USER.groups | {"contractors"})
    assert evaluate(contractor, doc, [deny]) == (False, "explicit_deny")


def test_region_restricted_document_inaccessible_outside_region():
    doc = resource("INTERNAL_GENERAL", region="germany")
    policy = Policy(name="de-only", document_id=doc.document_id, allowed_regions=frozenset({"germany"}))
    us_user = subject(locations=frozenset({"americas", "united states"}))
    assert evaluate(subject(), doc, [policy])[0] is True
    assert evaluate(us_user, doc, [policy]) == (False, "region_mismatch")


def test_policy_selectors_limit_scope():
    hr_doc = resource("DEPARTMENT_RESTRICTED", department="hr")
    finance_only = Policy(name="f", department="finance", allowed_groups=frozenset({"engineering"}))
    assert evaluate(subject(), hr_doc, [finance_only]) == (False, "department_mismatch")

    tagged = replace(hr_doc, tags=frozenset({"onboarding"}))
    by_tag = Policy(name="t", tags=frozenset({"onboarding"}), allowed_groups=frozenset({"engineering"}))
    assert evaluate(subject(), tagged, [by_tag])[0] is True
    assert evaluate(subject(), hr_doc, [by_tag])[0] is False


# --- Clearance ---------------------------------------------------------------------

def test_clearance_blocks_grants_above_user_level():
    doc = resource("EXECUTIVE_ONLY")
    policy = Policy(name="board", document_id=doc.document_id, allowed_groups=frozenset({"finance"}))
    assert evaluate(FINANCE_USER, doc, [policy]) == (False, "clearance_insufficient")
    assert evaluate(FINANCE_USER, doc, [policy], enforce_clearance=False)[0] is True


# --- Tenant and lifecycle ------------------------------------------------------------

def test_tenant_mismatch_always_denies():
    doc = resource("PUBLIC", tenant_id=str(uuid.uuid4()))
    assert evaluate(subject(), doc, []) == (False, "tenant_mismatch")


def test_inactive_deleted_and_archived_documents_denied():
    for status in ("DELETED", "ARCHIVED", "PENDING", "FAILED"):
        assert evaluate(subject(), resource("PUBLIC", status=status), []) == (False, f"document_{status.lower()}")


def test_non_current_version_denied():
    assert evaluate(subject(), resource("PUBLIC", is_current_version=False), []) == (False, "document_not_current")


def test_unknown_classification_denied():
    assert evaluate(subject(), resource("TOP_SECRET"), []) == (False, "unknown_classification")


# --- Retrieval pre-filter ------------------------------------------------------------

def test_retrieval_filter_scopes_tenant_status_and_clearance():
    claims = UserClaims(user_id="u1", tenant_id=TENANT, department="engineering", groups=["engineering"],
                        roles=["senior_engineer"], clearance="DEPARTMENT_RESTRICTED", is_employee=True)
    flt = build_retrieval_filter(claims)
    assert {"key": "tenant_id", "match": {"value": TENANT}} in flt["must"]
    assert {"key": "status", "match": {"value": "ACTIVE"}} in flt["must"]
    assert {"key": "is_current_version", "match": {"value": True}} in flt["must"]
    blocked = next(c for c in flt["must_not"] if c["key"] == "classification")
    assert blocked["match"]["any"] == ["CONFIDENTIAL", "REGULATED", "EXECUTIVE_ONLY"]


def test_retrieval_filter_excludes_internal_for_external_users():
    claims = UserClaims(user_id="x", tenant_id=TENANT, clearance="PUBLIC", is_employee=False)
    classifications = [c["match"].get("value") for c in build_retrieval_filter(claims)["should"]
                       if c.get("key") == "classification"]
    assert classifications == ["PUBLIC"]
