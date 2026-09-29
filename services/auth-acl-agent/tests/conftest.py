import os

import pytest

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ADMIN_DATABASE_URL = os.environ.get("TEST_ADMIN_DATABASE_URL")

os.environ.setdefault("DATABASE_URL", DATABASE_URL or "postgresql://unused@localhost:1/unused")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "1")
os.environ.setdefault("REDIS_PASSWORD", "unused")
os.environ.setdefault("OIDC_PROVIDER_URL", "https://auth.example.test/realms/enterprise-rag")
os.environ.setdefault("OIDC_CLIENT_ID", "enterprise-rag")
os.environ.setdefault("OIDC_CLIENT_SECRET", "unused")
os.environ.setdefault("SECRET_KEY", "unused")

requires_db = pytest.mark.skipif(
    not (DATABASE_URL and ADMIN_DATABASE_URL),
    reason="TEST_DATABASE_URL and TEST_ADMIN_DATABASE_URL are required for integration tests",
)
