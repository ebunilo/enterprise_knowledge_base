"""
Canonical DB Agent - FastAPI Application

PostgreSQL is the source of truth for documents, chunks, versions and audit
references (AGENTS.md 5.1). Qdrant, BM25 and the knowledge graph resolve back
to these records by stable IDs.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import settings
from app.database import check_database_connection, check_redis_connection, ensure_audit_partitions
from app.dependencies import verify_api_key
from app.routers import chunks, documents, feedback, health

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Canonical DB Agent API %s (%s)", __version__, settings.environment)
    logger.info("Database: %s", settings.database_url.split("@")[-1])  # host/db only, no credentials

    if check_database_connection():
        logger.info("Database connection successful")
        ensure_audit_partitions()
    else:
        logger.error("Database connection failed")

    if not check_redis_connection():
        logger.warning("Redis connection failed (non-critical)")

    yield
    logger.info("Shutting down Canonical DB Agent API")


app = FastAPI(
    title="Canonical DB Agent API",
    description=(
        "Canonical store for documents, chunks, versions, retrieval audit "
        "records and feedback. Multi-tenant with PostgreSQL Row-Level Security."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Tenant-ID", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start_time:.4f}"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": "Request validation failed",
            "errors": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unexpected error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred"},
    )


app.include_router(health.router, tags=["Health"])

_secured = [Depends(verify_api_key)]
app.include_router(documents.router, prefix="/api/v1", dependencies=_secured)
app.include_router(chunks.router, prefix="/api/v1", dependencies=_secured)
app.include_router(feedback.router, prefix="/api/v1", dependencies=_secured)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "canonical-db-agent",
        "version": __version__,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }
