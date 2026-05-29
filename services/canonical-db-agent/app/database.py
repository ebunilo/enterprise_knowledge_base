"""
Database connection and session management.
Implements connection pooling and Row-Level Security (RLS) support.
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import redis
import logging

from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.db_echo,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Create declarative base for models
Base = declarative_base()

# Redis connection
redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session.
    Automatically closes session after request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_tenant_context(db: Session, tenant_id: str) -> None:
    """
    Set tenant context for Row-Level Security (RLS).
    Must be called before any queries when RLS is enabled.
    """
    if settings.rls_enabled:
        db.execute(
            text("SET LOCAL app.current_tenant_id = :tenant_id"),
            {"tenant_id": tenant_id}
        )
        logger.debug(f"Set tenant context: {tenant_id}")


@contextmanager
def get_db_with_tenant(tenant_id: str) -> Generator[Session, None, None]:
    """
    Context manager for database session with tenant context.
    Automatically sets RLS tenant context and closes session.
    """
    db = SessionLocal()
    try:
        set_tenant_context(db, tenant_id)
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    return redis_client


def check_database_connection() -> bool:
    """
    Check if database connection is healthy.
    Used for health checks.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def check_redis_connection() -> bool:
    """
    Check if Redis connection is healthy.
    Used for health checks.
    """
    try:
        redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


# Event listeners for connection lifecycle
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log new database connections."""
    logger.debug("New database connection established")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log connection checkout from pool."""
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """Log connection return to pool."""
    logger.debug("Connection returned to pool")

# Made with Bob
