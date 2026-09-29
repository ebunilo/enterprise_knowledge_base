"""
Database connectivity, tenant (RLS) context, and the Redis cache.

Redis caches OIDC discovery, JWKS and validated token claims only. Access
decisions are never cached: they are re-evaluated against PostgreSQL on every
request (AGENTS.md 1.5 "Triple ACL Enforcement", 14.6).
"""

import logging
from typing import Generator
from uuid import UUID

import redis
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
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
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5,
)


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction, connection) -> None:
    """SET LOCAL lasts one transaction; re-apply it for every transaction."""
    tenant_id = session.info.get(TENANT_INFO_KEY)
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )


def set_tenant_context(db: Session, tenant_id: UUID) -> None:
    db.info[TENANT_INFO_KEY] = str(tenant_id)
    if db.in_transaction():
        db.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def check_redis_connection() -> bool:
    try:
        redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


def cache_set(key: str, value: str, ttl: int | None = None) -> bool:
    try:
        redis_client.setex(key, ttl or settings.cache_ttl, value)
        return True
    except Exception as e:
        logger.warning(f"Cache set failed for {key.split(':')[0]}: {e}")
        return False


def cache_get(key: str) -> str | None:
    try:
        return redis_client.get(key)
    except Exception as e:
        logger.warning(f"Cache get failed for {key.split(':')[0]}: {e}")
        return None
