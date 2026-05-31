"""
Auth ACL Agent - FastAPI Application

Main application module for the Auth ACL Agent API.
Provides authentication and access control for the Enterprise RAG System.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram

from app.config import settings
from app.database import check_database_connection, check_redis_connection
from app.oidc import oidc_config
from app.routers import acl, auth, health

# Configure logging
if settings.log_format.lower() == "json":
    # For JSON logging, use a standard format and let structured logging handle it
    # In production, you'd use python-json-logger or similar
    logging.basicConfig(
        level=settings.log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
else:
    # Use the provided format string
    logging.basicConfig(
        level=settings.log_level,
        format=settings.log_format
    )
logger = logging.getLogger(__name__)

# ============================================================================
# Prometheus Metrics
# ============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

http_request_size_bytes = Histogram(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint']
)

http_response_size_bytes = Histogram(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint']
)


# ============================================================================
# Lifespan Events
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 80)
    logger.info("Starting Auth ACL Agent API")
    logger.info(f"Version: 0.1.0")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.database_url.split('@')[-1]}")  # Hide credentials
    logger.info(f"Redis: {settings.redis_host}:{settings.redis_port}")
    logger.info(f"OIDC Provider: {settings.oidc_provider_url}")
    logger.info(f"CORS Origins: {settings.cors_origins}")
    logger.info("=" * 80)
    
    # Check database connection
    if check_database_connection():
        logger.info("✓ Database connection successful")
    else:
        logger.error("✗ Database connection failed")
    
    # Check Redis connection
    if check_redis_connection():
        logger.info("✓ Redis connection successful")
    else:
        logger.warning("✗ Redis connection failed (non-critical)")
    
    # Load OIDC configuration
    if await oidc_config.load_configuration():
        logger.info("✓ OIDC configuration loaded successfully")
        logger.info(f"  Issuer: {oidc_config.issuer}")
        logger.info(f"  JWKS URI: {oidc_config.jwks_uri}")
    else:
        logger.error("✗ OIDC configuration failed to load")
    
    logger.info("Auth ACL Agent API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Auth ACL Agent API")
    logger.info("Cleanup complete")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Auth ACL Agent API",
    description=(
        "Authentication and access control for Enterprise RAG System. "
        "Provides JWT token validation, user claims extraction, and "
        "access control logic with multi-tenant support."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)


# ============================================================================
# Middleware
# ============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"]
)

# GZip Compression
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000
)


# Request timing and metrics middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Add request processing time header and collect metrics.
    """
    start_time = time.time()
    
    # Get request size
    request_size = int(request.headers.get("content-length", 0))
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    process_time = time.time() - start_time
    
    # Add headers
    response.headers["X-Process-Time"] = str(process_time)
    
    # Get response size
    response_size = int(response.headers.get("content-length", 0))
    
    # Record metrics
    endpoint = request.url.path
    method = request.method
    status_code = response.status_code
    
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status=status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint
    ).observe(process_time)
    
    if request_size > 0:
        http_request_size_bytes.labels(
            method=method,
            endpoint=endpoint
        ).observe(request_size)
    
    if response_size > 0:
        http_response_size_bytes.labels(
            method=method,
            endpoint=endpoint
        ).observe(response_size)
    
    return response


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle request validation errors.
    """
    logger.warning(f"Validation error: {exc.errors()}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": "Request validation failed",
            "errors": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handle unexpected exceptions.
    """
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred"
        }
    )


# ============================================================================
# Routers
# ============================================================================

# Health check router (no prefix)
app.include_router(
    health.router,
    tags=["Health"]
)

# API v1 routers
app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    acl.router,
    prefix="/api/v1/acl",
    tags=["Access Control"]
)


# ============================================================================
# Root Endpoint
# ============================================================================

@app.get(
    "/",
    summary="Root endpoint",
    description="Get API information",
    tags=["Root"]
)
async def root():
    """
    Root endpoint - returns API information.
    """
    return {
        "service": "auth-acl-agent",
        "version": "0.1.0",
        "description": "Authentication and access control for Enterprise RAG System",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "oidc_provider": settings.oidc_provider_url
    }


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )

# Made with Bob
