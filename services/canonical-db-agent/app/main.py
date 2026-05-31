"""
Canonical DB Agent - FastAPI Application

Main application module for the Canonical DB Agent API.
Provides document and chunk metadata management for the Enterprise RAG System.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
# Prometheus disabled for Phase 1 MVP
# from prometheus_client import Counter, Histogram

from app.config import settings
from app.database import check_database_connection, check_redis_connection
from app.routers import chunks, documents, health

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
# Prometheus Metrics (Disabled for Phase 1 MVP)
# ============================================================================
# Metrics will be enabled in later phases when observability is implemented
# For now, we use None to disable metric collection

http_requests_total = None
http_request_duration_seconds = None
http_request_size_bytes = None

http_response_size_bytes = None
# Disabled for Phase 1 MVP - will be enabled in observability phase
# http_response_size_bytes = Histogram(
#     'http_response_size_bytes',
#     'HTTP response size in bytes',
#     ['method', 'endpoint']
# )


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
    logger.info("Starting Canonical DB Agent API")
    logger.info(f"Version: 0.1.0")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.database_url.split('@')[-1]}")  # Hide credentials
    logger.info(f"Redis: {settings.redis_url}")
    logger.info(f"RLS Enabled: {settings.rls_enabled}")
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
    
    logger.info("Canonical DB Agent API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Canonical DB Agent API")
    logger.info("Cleanup complete")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Canonical DB Agent API",
    description=(
        "Document and chunk metadata management for Enterprise RAG System. "
        "Provides CRUD operations for documents, chunks, and versions with "
        "multi-tenant support and Row-Level Security."
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
    
    # Record metrics (disabled for Phase 1 MVP)
    # Metrics will be enabled in later phases
    if http_requests_total is not None:
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
        
        if response_size > 0 and http_response_size_bytes is not None:
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
    documents.router,
    prefix="/api/v1",
    tags=["Documents"]
)

app.include_router(
    chunks.router,
    prefix="/api/v1",
    tags=["Chunks"]
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
        "service": "canonical-db-agent",
        "version": "0.1.0",
        "description": "Document and chunk metadata management for Enterprise RAG System",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
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
