"""
ACL validation against PostgreSQL through the HTTP API (AGENTS.md 5.2 / 5.11
integration and security tests). Token signature checks are covered in
test_oidc.py; here the validated claims are injected directly.
"""

import uuid

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import ADMIN_DATABASE_URL, requires_db

pytestmark = requires_db


@pytest.fixture(scope="module")
def admin():
    engine = create_engine(ADMIN_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def world(admin):
    """Two tenants with documents of each classification and one chunk each."""
    tenant_id, other_tenant_id = uuid.uuid4(), uuid.uuid4()
    slug = f"acl-{tenant_id.hex[:10]}"
    chunks = {}

    def doc(conn, tenant, name, classification, department=None, status="ACTIVE", current=True):
        document_id = uuid.uuid4()
        conn.execute(text("""
            INSERT INTO documents (document_id, tenant_id, title, source_uri, checksum, classification,
                                   department, status, is_current_version)
            VALUES (:id, :t, :title, :uri, :sum, :c, :d, :s, :cur)
        """), {"id": document_id, "t": tenant, "title": name, "uri": f"s3://{name}", "sum": uuid.uuid4().hex,
               "c": classification, "d": department, "s": status, "cur": current})
        chunk_id = uuid.uuid4()
        conn.execute(text("""
            INSERT INTO document_chunks (chunk_id, document_id, tenant_id, chunk_text, chunk_index,
                                         token_count, checksum, classification, department)
            VALUES (:id, :doc, :t, :txt, 0, 5, :sum, :c, :d)
        """), {"id": chunk_id, "doc": document_id, "t": tenant, "txt": f"{name} text", "sum": uuid.uuid4().hex,
               "c": classification, "d": department})
        chunks[name] = chunk_id
        return document_id

    with admin.begin() as conn:
        conn.execute(text("INSERT INTO tenants (tenant_id, tenant_name, tenant_slug) VALUES (:id, :n, :s)"),
                     {"id": tenant_id, "n": slug, "s": slug})
        conn.execute(text("INSERT INTO tenants (tenant_id, tenant_name, tenant_slug) VALUES (:id, :n, :s)"),
                     {"id": other_tenant_id, "n": slug + "-b", "s": slug + "-b"})
        doc(conn, tenant_id, "sustainability", "PUBLIC")
        doc(conn, tenant_id, "travel-policy", "INTERNAL_GENERAL")
        doc(conn, tenant_id, "eng-runbook", "DEPARTMENT_RESTRICTED", "Engineering")
        payroll = doc(conn, tenant_id, "payroll", "CONFIDENTIAL", "Finance")
        legal = doc(conn, tenant_id, "legal-hold", "CONFIDENTIAL", "Legal")
        doc(conn, tenant_id, "old-travel-policy", "INTERNAL_GENERAL", status="ARCHIVED", current=False)
        doc(conn, tenant_id, "deleted-memo", "PUBLIC", status="DELETED", current=False)
        doc(conn, other_tenant_id, "other-tenant-public", "PUBLIC")
        conn.execute(text("""
            INSERT INTO access_policies (tenant_id, policy_name, document_id, allowed_groups, allowed_roles)
            VALUES (:t, 'payroll-finance', :doc, ARRAY['finance'], ARRAY['finance_manager'])
        """), {"t": tenant_id, "doc": payroll})
        conn.execute(text("""
            INSERT INTO access_policies (tenant_id, policy_name, document_id, allowed_departments)
            VALUES (:t, 'legal-only', :doc, ARRAY['Legal'])
        """), {"t": tenant_id, "doc": legal})

    yield {"tenant_id": tenant_id, "slug": slug, "chunks": chunks}

    with admin.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE tenant_id IN (:a, :b)"), {"a": tenant_id, "b": other_tenant_id})


def token_claims(world, **overrides) -> dict:
    claims = {
        "sub": f"user-{uuid.uuid4().hex[:8]}", "email": "ada@igwilo.com", "tenant_id": world["slug"],
        "department": "Engineering", "groups": ["/engineering", "internal-users"], "role": "senior_engineer",
        "region": "emea", "country": "Germany", "clearance": "department_restricted",
    }
    claims.update(overrides)
    return claims


@pytest.fixture
def call_filter(world):
    from fastapi.testclient import TestClient

    from app.dependencies import get_token_claims
    from app.main import app

    def _call(claims: dict, names: list[str], extra_ids: list = ()):
        app.dependency_overrides[get_token_claims] = lambda: claims
        try:
            with TestClient(app) as client:
                ids = [str(world["chunks"][n]) for n in names] + [str(i) for i in extra_ids]
                response = client.post("/api/v1/acl/filter", json={"chunk_ids": ids},
                                       headers={"Authorization": "Bearer test"})
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 200, response.text
        body = response.json()
        by_id = {str(v): k for k, v in world["chunks"].items()}
        return (
            {by_id.get(c, c) for c in body["authorized_chunk_ids"]},
            {by_id.get(c, c): r for c, r in body["reason_by_chunk"].items()},
        )

    return _call


ALL = ["sustainability", "travel-policy", "eng-runbook", "payroll", "legal-hold",
       "old-travel-policy", "deleted-memo", "other-tenant-public"]


def test_engineering_user_mixed_candidates_from_all_retrievers(call_filter, world):
    """Simulated Qdrant + BM25 + KG candidates: only authorized chunks survive."""
    allowed, reasons = call_filter(token_claims(world), ALL)
    assert allowed == {"sustainability", "travel-policy", "eng-runbook"}
    assert reasons["payroll"] == "clearance_insufficient"
    assert reasons["old-travel-policy"] == "document_archived"
    assert reasons["deleted-memo"] == "document_deleted"
    assert reasons["other-tenant-public"] == "not_found"


def test_payroll_chunk_denied_to_engineering_even_with_high_clearance(call_filter, world):
    allowed, reasons = call_filter(token_claims(world, clearance="confidential"), ["payroll"])
    assert allowed == set()
    assert reasons["payroll"] == "no_matching_grant"


def test_finance_manager_reads_payroll(call_filter, world):
    finance = token_claims(world, department="Finance", groups=["/finance"], role="finance_manager",
                           clearance="confidential")
    allowed, _ = call_filter(finance, ["payroll", "eng-runbook"])
    assert allowed == {"payroll"}


def test_graph_traversal_to_confidential_legal_policy_denied(call_filter, world):
    allowed, reasons = call_filter(token_claims(world, clearance="confidential"), ["legal-hold"])
    assert allowed == set()
    assert reasons["legal-hold"] == "no_matching_grant"


def test_external_user_only_sees_public(call_filter, world):
    external = token_claims(world, department="External", groups=["external-users"], role="external_user",
                            clearance="public")
    allowed, reasons = call_filter(external, ALL)
    assert allowed == {"sustainability"}
    assert reasons["travel-policy"] == "not_employee"


def test_unknown_chunk_ids_fail_closed(call_filter, world):
    unknown = uuid.uuid4()
    allowed, reasons = call_filter(token_claims(world), [], [unknown])
    assert allowed == set()
    assert reasons[str(unknown)] == "not_found"


def test_denials_are_audited(call_filter, world, admin):
    claims = token_claims(world)
    call_filter(claims, ["payroll"])
    with admin.connect() as conn:
        row = conn.execute(text("""
            SELECT result, details FROM audit_logs
            WHERE tenant_id = :t AND event_type = 'ACL_DECISION' AND details->>'subject' = :s
        """), {"t": world["tenant_id"], "s": claims["sub"]}).one()
    assert row.result == "DENY"
    assert row.details["reason_by_chunk"] == {str(world["chunks"]["payroll"]): "clearance_insufficient"}


def test_unknown_tenant_in_token_is_forbidden(world):
    from fastapi.testclient import TestClient

    from app.dependencies import get_token_claims
    from app.main import app

    app.dependency_overrides[get_token_claims] = lambda: token_claims(world, tenant_id="no-such-tenant")
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/acl/filter", json={"chunk_ids": [str(uuid.uuid4())]},
                                   headers={"Authorization": "Bearer test"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
