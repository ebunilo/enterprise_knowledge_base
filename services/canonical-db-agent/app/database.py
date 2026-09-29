"""
Database connection and session management.
Implements connection pooling and Row-Level Security (RLS) support.

RLS policies read `app.current_tenant_id`. It is set with SET LOCAL, which
only lasts for the current transaction, so it is re-applied at the start of
every transaction a session opens (including after each commit). Queries in a
session without a tenant see no tenant-owned rows when connected as the
non-superuser application role.
"""

import logging
from typing import Generator
from uuid import UUID

import redis
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app.config import settings

logger = logging.getLogger(__name__)

TENANT_INFO_KEY = "tenant_id"

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,
    echo=settings.db_echo,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction, connection) -> None:
    """Re-apply the tenant RLS context at the start of every transaction."""
    tenant_id = session.info.get(TENANT_INFO_KEY)
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )


def set_tenant_context(db: Session, tenant_id: UUID) -> None:
    """Bind a session to a tenant for the rest of its lifetime."""
    db.info[TENANT_INFO_KEY] = str(tenant_id)
    if db.in_transaction():
        # A transaction is already open, so after_begin has fired; apply now.
        db.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: database session closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    return redis_client


def check_database_connection() -> bool:
    """Check if database connection is healthy."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def check_redis_connection() -> bool:
    """Check if Redis connection is healthy."""
    try:
        redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


def ensure_audit_partitions(months_ahead: int = 3) -> None:
    """Create upcoming audit_logs partitions (best effort, run at startup)."""
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT ensure_audit_partitions(:m)"), {"m": months_ahead})
    except Exception as e:
        logger.warning(f"Could not ensure audit partitions: {e}")
