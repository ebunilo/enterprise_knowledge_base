"""
Database connection and session management.

This module provides database connectivity, session management,
and Redis client setup for the Auth ACL Agent.
"""

import logging
from contextlib import contextmanager
from typing import Generator

import redis
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# Database Engine
# ============================================================================

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,
    echo=False
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# ============================================================================
# Redis Client
# ============================================================================

redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5
)


# ============================================================================
# Database Session Dependencies
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Health Check Functions
# ============================================================================

def check_database_connection() -> bool:
    """
    Check if database connection is healthy.
    
    Returns:
        True if connection is healthy, False otherwise
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
    
    Returns:
        True if connection is healthy, False otherwise
    """
    try:
        redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


# ============================================================================
# Event Listeners
# ============================================================================

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set connection parameters on connect."""
    logger.debug("Database connection established")


@event.listens_for(Engine, "close")
def receive_close(dbapi_conn, connection_record):
    """Log connection close."""
    logger.debug("Database connection closed")


# ============================================================================
# Cache Helper Functions
# ============================================================================

def cache_set(key: str, value: str, ttl: int = None) -> bool:
    """
    Set a value in Redis cache.
    
    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds (default: settings.cache_ttl)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if ttl is None:
            ttl = settings.cache_ttl
        redis_client.setex(key, ttl, value)
        return True
    except Exception as e:
        logger.error(f"Cache set failed for key {key}: {e}")
        return False


def cache_get(key: str) -> str | None:
    """
    Get a value from Redis cache.
    
    Args:
        key: Cache key
        
    Returns:
        Cached value or None if not found
    """
    try:
        return redis_client.get(key)
    except Exception as e:
        logger.error(f"Cache get failed for key {key}: {e}")
        return None


def cache_delete(key: str) -> bool:
    """
    Delete a value from Redis cache.
    
    Args:
        key: Cache key
        
    Returns:
        True if successful, False otherwise
    """
    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Cache delete failed for key {key}: {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.
    
    Args:
        pattern: Key pattern (e.g., "acl:user_123:*")
        
    Returns:
        Number of keys deleted
    """
    try:
        keys = redis_client.keys(pattern)
        if keys:
            return redis_client.delete(*keys)
        return 0
    except Exception as e:
        logger.error(f"Cache delete pattern failed for {pattern}: {e}")
        return 0

# Made with Bob
