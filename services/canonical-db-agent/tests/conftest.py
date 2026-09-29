"""
Integration test fixtures.

Requires a PostgreSQL database with 01-init-database.sql and all migrations
applied (see .github/workflows/deploy-phase1.yml, job `test`):

    TEST_DATABASE_URL        connection as the application role (rag_app),
                             so Row-Level Security is actually enforced
    TEST_ADMIN_DATABASE_URL  connection as the owner, used only to create
                             and remove test tenants
"""

import os
import uuid

import pytest

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ADMIN_DATABASE_URL = os.environ.get("TEST_ADMIN_DATABASE_URL")

os.environ.setdefault("DATABASE_URL", DATABASE_URL or "postgresql://unused@localhost:1/unused")
os.environ.setdefault("REDIS_URL", "redis://localhost:1/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SERVICE_API_KEYS", "test-api-key")

API_KEY = "test-api-key"

requires_db = pytest.mark.skipif(
    not (DATABASE_URL and ADMIN_DATABASE_URL),
    reason="TEST_DATABASE_URL and TEST_ADMIN_DATABASE_URL are required for integration tests",
)


@pytest.fixture(scope="session")
def admin_engine():
    from sqlalchemy import create_engine

    engine = create_engine(ADMIN_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def make_tenant(admin_engine):
    from sqlalchemy import text

    created = []

    def _make() -> dict:
        tenant_id = uuid.uuid4()
        slug = f"test-{tenant_id.hex[:12]}"
        with admin_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tenants (tenant_id, tenant_name, tenant_slug) VALUES (:id, :name, :slug)"),
                {"id": tenant_id, "name": slug, "slug": slug},
            )
        created.append(tenant_id)
        return {"tenant_id": str(tenant_id), "slug": slug}

    yield _make

    with admin_engine.begin() as conn:
        for tenant_id in created:
            conn.execute(text("DELETE FROM tenants WHERE tenant_id = :id"), {"id": tenant_id})


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def tenant(make_tenant):
    return make_tenant()


@pytest.fixture
def headers(tenant):
    return {"X-API-Key": API_KEY, "X-Tenant-ID": tenant["tenant_id"]}


def document_payload(**overrides) -> dict:
    payload = {
        "title": "Travel Expense Policy",
        "source_type": "sharepoint",
        "source_uri": f"s3://bucket/docs/{uuid.uuid4()}.pdf",
        "classification": "internal_general",
        "department": "Finance",
        "region": "global",
        "checksum": uuid.uuid4().hex,
        "status": "ACTIVE",
    }
    payload.update(overrides)
    return payload


def chunk_payload(document_id: str, index: int = 0, text: str = "Employees must submit expenses within 14 days.") -> dict:
    return {
        "document_id": document_id,
        "chunk_index": index,
        "chunk_text": text,
        "token_count": 12,
        "page_start": 8,
        "page_end": 8,
        "section_title": "Expense Claims",
        "heading_path": ["Finance Policy", "Travel", "Expense Claims"],
    }
