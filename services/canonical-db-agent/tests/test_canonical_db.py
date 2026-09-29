"""
canonical-db-agent tests (AGENTS.md 5.1: unit, integration and security cases).
"""

import hashlib
import uuid

from sqlalchemy import create_engine, text

from tests.conftest import API_KEY, DATABASE_URL, chunk_payload, document_payload, requires_db

pytestmark = requires_db


def _create_doc(client, headers, **overrides) -> dict:
    response = client.post("/api/v1/documents", json=document_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Authentication and tenancy
# ---------------------------------------------------------------------------

def test_requires_api_key(client, tenant):
    response = client.get("/api/v1/documents", headers={"X-Tenant-ID": tenant["tenant_id"]})
    assert response.status_code == 401


def test_rejects_wrong_api_key(client, tenant):
    response = client.get("/api/v1/documents", headers={"X-API-Key": "nope", "X-Tenant-ID": tenant["tenant_id"]})
    assert response.status_code == 401


def test_unknown_tenant_is_404(client):
    response = client.get("/api/v1/documents", headers={"X-API-Key": API_KEY, "X-Tenant-ID": str(uuid.uuid4())})
    assert response.status_code == 404


def test_tenant_resolves_by_slug(client, tenant):
    doc = _create_doc(client, {"X-API-Key": API_KEY, "X-Tenant-ID": tenant["slug"]})
    assert doc["tenant_id"] == tenant["tenant_id"]


def test_cross_tenant_read_is_denied(client, make_tenant):
    tenant_a, tenant_b = make_tenant(), make_tenant()
    doc = _create_doc(client, {"X-API-Key": API_KEY, "X-Tenant-ID": tenant_a["tenant_id"]})
    headers_b = {"X-API-Key": API_KEY, "X-Tenant-ID": tenant_b["tenant_id"]}

    assert client.get(f"/api/v1/documents/{doc['document_id']}", headers=headers_b).status_code == 404
    batch = client.post("/api/v1/chunks/batch", json={"chunk_ids": [str(uuid.uuid4())]}, headers=headers_b)
    assert batch.status_code == 200


def test_rls_hides_rows_without_tenant_context(client, headers):
    _create_doc(client, headers)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            visible = conn.execute(text("SELECT count(*) FROM documents")).scalar_one()
    finally:
        engine.dispose()
    assert visible == 0


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def test_create_document(client, headers, tenant):
    doc = _create_doc(client, headers)
    assert doc["tenant_id"] == tenant["tenant_id"]
    assert doc["classification"] == "INTERNAL_GENERAL"
    assert doc["source_type"] == "SHAREPOINT"
    assert doc["status"] == "ACTIVE"
    assert doc["is_current_version"] is True
    assert doc["version_number"] == 1
    assert doc["document_version_id"] == doc["document_id"]


def test_rejects_invalid_classification(client, headers):
    response = client.post("/api/v1/documents", json=document_payload(classification="TOP_SECRET"), headers=headers)
    assert response.status_code == 422


def test_rejects_duplicate_checksum_for_active_version(client, headers):
    checksum = uuid.uuid4().hex
    first = _create_doc(client, headers, checksum=checksum)
    same_source = client.post(
        "/api/v1/documents",
        json=document_payload(checksum=checksum, source_uri=first["source_uri"]),
        headers=headers,
    )
    other_source = client.post("/api/v1/documents", json=document_payload(checksum=checksum), headers=headers)
    assert same_source.status_code == 409
    assert other_source.status_code == 409


def test_new_version_supersedes_old_only_on_activation(client, headers):
    v1 = _create_doc(client, headers)
    v2 = client.post(
        "/api/v1/documents", json=document_payload(source_uri=v1["source_uri"], status="PENDING"), headers=headers
    ).json()

    assert v2["version_number"] == 2
    assert v2["parent_document_id"] == v1["document_id"]
    assert v2["is_current_version"] is False

    current = client.get(f"/api/v1/documents/{v2['document_id']}/version", headers=headers).json()
    assert current["document_id"] == v1["document_id"]

    activated = client.post(f"/api/v1/documents/{v2['document_id']}/activate", headers=headers).json()
    assert activated["is_current_version"] is True
    assert activated["status"] == "ACTIVE"

    old = client.get(f"/api/v1/documents/{v1['document_id']}", headers=headers).json()
    assert old["is_current_version"] is False
    assert old["status"] == "ARCHIVED"

    versions = client.get(f"/api/v1/documents/{v1['document_id']}/versions", headers=headers).json()
    assert [v["version_number"] for v in versions] == [2, 1]


def test_list_excludes_archived_and_deleted(client, headers):
    kept = _create_doc(client, headers)
    archived = _create_doc(client, headers)
    deleted = _create_doc(client, headers)
    client.post(f"/api/v1/documents/{archived['document_id']}/archive", headers=headers)
    client.delete(f"/api/v1/documents/{deleted['document_id']}", headers=headers)

    listed = client.get("/api/v1/documents", headers=headers).json()
    ids = {item["document_id"] for item in listed["items"]}
    assert ids == {kept["document_id"]}


def test_reclassification_propagates_to_chunks(client, headers):
    doc = _create_doc(client, headers)
    chunk = client.post("/api/v1/chunks", json=chunk_payload(doc["document_id"]), headers=headers).json()
    client.put(f"/api/v1/documents/{doc['document_id']}", json={"classification": "CONFIDENTIAL"}, headers=headers)
    refreshed = client.get(f"/api/v1/chunks/{chunk['chunk_id']}", headers=headers).json()
    assert refreshed["classification"] == "CONFIDENTIAL"


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------

def test_create_chunk_inherits_access_metadata(client, headers):
    doc = _create_doc(client, headers, classification="DEPARTMENT_RESTRICTED", department="HR", region="emea")
    payload = chunk_payload(doc["document_id"])
    response = client.post("/api/v1/chunks", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    chunk = response.json()
    assert chunk["classification"] == "DEPARTMENT_RESTRICTED"
    assert chunk["department"] == "HR"
    assert chunk["region"] == "emea"
    assert chunk["checksum"] == hashlib.sha256(payload["chunk_text"].encode()).hexdigest()
    assert chunk["heading_path"] == ["Finance Policy", "Travel", "Expense Claims"]


def test_reject_chunk_with_invalid_document(client, headers):
    response = client.post("/api/v1/chunks", json=chunk_payload(str(uuid.uuid4())), headers=headers)
    assert response.status_code == 404


def test_reject_chunk_checksum_mismatch(client, headers):
    doc = _create_doc(client, headers)
    payload = chunk_payload(doc["document_id"]) | {"checksum": "0" * 64}
    assert client.post("/api/v1/chunks", json=payload, headers=headers).status_code == 409


def test_bulk_create_is_atomic(client, headers):
    doc = _create_doc(client, headers)
    payload = [chunk_payload(doc["document_id"], 0), chunk_payload(doc["document_id"], 0, "duplicate index")]
    assert client.post("/api/v1/chunks/bulk", json=payload, headers=headers).status_code == 409
    listed = client.get(f"/api/v1/documents/{doc['document_id']}/chunks", headers=headers).json()
    assert listed["total"] == 0


def test_batch_returns_chunks_in_stable_order_with_citation_metadata(client, headers):
    doc = _create_doc(client, headers)
    payload = [chunk_payload(doc["document_id"], i, f"clause {i}") for i in range(3)]
    created = client.post("/api/v1/chunks/bulk", json=payload, headers=headers).json()
    missing = str(uuid.uuid4())
    requested = [created[2]["chunk_id"], missing, created[0]["chunk_id"], created[1]["chunk_id"]]

    result = client.post("/api/v1/chunks/batch", json={"chunk_ids": requested}, headers=headers).json()
    assert [c["chunk_id"] for c in result["chunks"]] == [requested[0], requested[2], requested[3]]
    assert result["missing_chunk_ids"] == [missing]
    assert result["chunks"][0]["title"] == doc["title"]
    assert result["chunks"][0]["source_uri"] == doc["source_uri"]


def test_batch_excludes_deleted_and_archived_unless_requested(client, headers):
    deleted = _create_doc(client, headers)
    archived = _create_doc(client, headers)
    ids = []
    for doc in (deleted, archived):
        ids.append(client.post("/api/v1/chunks", json=chunk_payload(doc["document_id"]), headers=headers).json()["chunk_id"])
    client.delete(f"/api/v1/documents/{deleted['document_id']}", headers=headers)
    client.post(f"/api/v1/documents/{archived['document_id']}/archive", headers=headers)

    normal = client.post("/api/v1/chunks/batch", json={"chunk_ids": ids}, headers=headers).json()
    assert normal["chunks"] == []
    assert set(normal["missing_chunk_ids"]) == set(ids)

    admin = client.post("/api/v1/chunks/batch", json={"chunk_ids": ids, "include_inactive": True}, headers=headers).json()
    assert {c["chunk_id"] for c in admin["chunks"]} == set(ids)


def test_cannot_add_chunks_to_deleted_document(client, headers):
    doc = _create_doc(client, headers)
    client.delete(f"/api/v1/documents/{doc['document_id']}", headers=headers)
    assert client.post("/api/v1/chunks", json=chunk_payload(doc["document_id"]), headers=headers).status_code == 409


# ---------------------------------------------------------------------------
# Retrieval audit + feedback (self-improvement signals)
# ---------------------------------------------------------------------------

def _audit(client, headers, **overrides):
    ids = [str(uuid.uuid4()) for _ in range(3)]
    payload = {
        "user_id": "user-1",
        "query": "How many days do I have to submit expenses?",
        "retrieved_chunk_ids": ids,
        "authorized_chunk_ids": ids[:2],
        "denied_chunk_ids": ids[2:],
        "denied_reasons": {ids[2]: "department_mismatch"},
        "context_chunk_ids": ids[:2],
        "cited_chunk_ids": ids[:1],
        "parameter_snapshot": {"retrieval.vector.top_k": 30},
        "experiment_assignments": {"exp-1": "candidate_1"},
    }
    payload.update(overrides)
    return client.post("/api/v1/retrieval-audit", json=payload, headers=headers), ids


def test_audit_stores_hash_not_query_text(client, headers):
    response, _ = _audit(client, headers)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["query_hash"] == hashlib.sha256(b"How many days do I have to submit expenses?").hexdigest()
    assert record["experiment_assignments"] == {"exp-1": "candidate_1"}


def test_audit_rejects_unauthorized_context(client, headers):
    ids = [str(uuid.uuid4()) for _ in range(2)]
    response, _ = _audit(client, headers, authorized_chunk_ids=ids[:1], context_chunk_ids=ids)
    assert response.status_code == 422


def test_audit_rejects_citation_outside_context(client, headers):
    ids = [str(uuid.uuid4()) for _ in range(2)]
    response, _ = _audit(client, headers, authorized_chunk_ids=ids, context_chunk_ids=ids[:1], cited_chunk_ids=ids)
    assert response.status_code == 422


def test_feedback_lifecycle(client, headers):
    audit, ids = _audit(client, headers)
    audit_id = audit.json()["audit_id"]

    ok = client.post("/api/v1/feedback", json={
        "audit_id": audit_id, "user_id": "user-1", "rating": 4, "reason_codes": ["incomplete"],
        "helpful_chunk_ids": [ids[0]],
    }, headers=headers)
    assert ok.status_code == 201, ok.text

    duplicate = client.post("/api/v1/feedback", json={"audit_id": audit_id, "user_id": "user-1", "thumbs": 1},
                            headers=headers)
    assert duplicate.status_code == 409

    other_user = client.post("/api/v1/feedback", json={"audit_id": audit_id, "user_id": "user-2", "thumbs": -1},
                             headers=headers)
    assert other_user.status_code == 409


def test_feedback_cannot_reference_chunks_not_shown(client, headers):
    audit, ids = _audit(client, headers)
    response = client.post("/api/v1/feedback", json={
        "audit_id": audit.json()["audit_id"], "user_id": "user-1", "thumbs": -1,
        "unhelpful_chunk_ids": [ids[2]],  # denied chunk, never shown
    }, headers=headers)
    assert response.status_code == 409


def test_feedback_requires_a_signal(client, headers):
    audit, _ = _audit(client, headers)
    response = client.post("/api/v1/feedback", json={"audit_id": audit.json()["audit_id"], "user_id": "user-1"},
                           headers=headers)
    assert response.status_code == 422
