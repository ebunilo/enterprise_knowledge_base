"""
Health check and monitoring endpoints.

This module provides health check, readiness, liveness, and metrics endpoints
for monitoring and orchestration systems.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Response, status
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from app.database import check_database_connection, check_redis_connection
from app.schemas import HealthCheckResponse

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# ============================================================================
# Prometheus Metrics
# ============================================================================

# Request metrics
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

# Database metrics
db_connections_active = Gauge(
    'db_connections_active',
    'Number of active database connections'
)

db_health_status = Gauge(
    'db_health_status',
    'Database health status (1=healthy, 0=unhealthy)'
)

# Redis metrics
redis_health_status = Gauge(
    'redis_health_status',
    'Redis health status (1=healthy, 0=unhealthy)'
)

# Application metrics
app_info = Gauge(
    'app_info',
    'Application information',
    ['version', 'service']
)

# Set application info
app_info.labels(version='0.1.0', service='canonical-db-agent').set(1)


# ============================================================================
# Health Check Endpoints
# ============================================================================

@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check",
    description="Check the health status of the service and its dependencies",
    tags=["Health"]
)
async def health_check():
    """
    Comprehensive health check endpoint.
    
    Checks:
    - Database connectivity
    - Redis connectivity
    - Overall service status
    
    Returns:
        HealthCheckResponse with status and component checks
    """
    try:
        # Check database
        db_healthy = check_database_connection()
        db_health_status.set(1 if db_healthy else 0)
        
        # Check Redis
        redis_healthy = check_redis_connection()
        redis_health_status.set(1 if redis_healthy else 0)
        
        # Determine overall status
        overall_healthy = db_healthy and redis_healthy
        
        response = HealthCheckResponse(
            status="healthy" if overall_healthy else "unhealthy",
            timestamp=datetime.utcnow(),
            service="canonical-db-agent",
            version="0.1.0",
            checks={
                "database": "ok" if db_healthy else "error",
                "redis": "ok" if redis_healthy else "error"
            }
        )
        
        logger.debug(f"Health check: {response.status}")
        return response
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            service="canonical-db-agent",
            version="0.1.0",
            checks={
                "database": "error",
                "redis": "error",
                "error": str(e)
            }
        )


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Kubernetes readiness probe - checks if service is ready to accept traffic",
    tags=["Health"]
)
async def readiness_check():
    """
    Kubernetes readiness probe.
    
    Returns 200 if service is ready to accept traffic,
    503 if service is not ready.
    
    Checks:
    - Database connectivity
    - Redis connectivity
    """
    try:
        db_healthy = check_database_connection()
        redis_healthy = check_redis_connection()
        
        if db_healthy and redis_healthy:
            return {
                "status": "ready",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return Response(
                content='{"status": "not ready"}',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="application/json"
            )
            
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return Response(
            content=f'{{"status": "not ready", "error": "{str(e)}"}}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )


@router.get(
    "/live",
    summary="Liveness probe",
    description="Kubernetes liveness probe - checks if service is alive",
    tags=["Health"]
)
async def liveness_check():
    """
    Kubernetes liveness probe.
    
    Returns 200 if service is alive and running.
    This is a simple check that doesn't verify dependencies.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "canonical-db-agent",
        "version": "0.1.0"
    }


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Prometheus-formatted metrics for monitoring",
    tags=["Monitoring"]
)
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format for scraping.
    """
    try:
        # Generate Prometheus metrics
        metrics_output = generate_latest()
        
        return Response(
            content=metrics_output,
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )
        
    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        return Response(
            content=f"# Error generating metrics: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="text/plain"
        )


@router.get(
    "/version",
    summary="Service version",
    description="Get service version information",
    tags=["Health"]
)
async def version_info():
    """
    Get service version and build information.
    """
    return {
        "service": "canonical-db-agent",
        "version": "0.1.0",
        "description": "Document and chunk metadata management for Enterprise RAG System",
        "api_version": "v1",
        "timestamp": datetime.utcnow().isoformat()
    }

# Made with Bob
