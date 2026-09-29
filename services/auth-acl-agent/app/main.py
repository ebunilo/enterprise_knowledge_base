"""
Auth ACL Agent - FastAPI Application

Validates Keycloak access tokens and evaluates access to documents and chunks
against PostgreSQL (AGENTS.md 5.2 and 5.11).
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import settings
from app.database import check_database_connection, check_redis_connection
from app.oidc import oidc_config
from app.routers import acl, auth, health

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Auth ACL Agent API %s (%s)", __version__, settings.environment)
    logger.info("Database: %s", settings.database_url.split("@")[-1])
    logger.info("OIDC provider: %s, accepted audiences: %s",
                settings.oidc_provider_url, settings.accepted_audiences)

    if not check_database_connection():
        logger.error("Database connection failed")
    if not check_redis_connection():
        logger.warning("Redis connection failed (non-critical)")
    if await oidc_config.load_configuration():
        logger.info("OIDC issuer: %s", oidc_config.issuer)
    else:
        logger.error("OIDC configuration failed to load; all tokens will be rejected until it does")

    yield
    logger.info("Shutting down Auth ACL Agent API")


app = FastAPI(
    title="Auth ACL Agent API",
    description="Keycloak token validation and PostgreSQL-backed access control for the Enterprise RAG System.",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
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
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(acl.router, prefix="/api/v1/acl")


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "auth-acl-agent",
        "version": __version__,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }
