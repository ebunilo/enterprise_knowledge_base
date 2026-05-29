# Canonical DB Agent

Document and chunk metadata management service for the Enterprise RAG System.

## Overview

The Canonical DB Agent is a FastAPI microservice that provides CRUD operations for documents, chunks, and versions with multi-tenant support and Row-Level Security (RLS). It serves as the source of truth for all document metadata in the Enterprise RAG System.

## Features

- **Document Management**: Create, read, update, delete, and archive documents
- **Chunk Management**: Create and retrieve document chunks with bulk operations
- **Version Control**: Track document versions and manage version history
- **Multi-Tenancy**: Tenant isolation using PostgreSQL Row-Level Security
- **Health Checks**: Kubernetes-ready health, readiness, and liveness probes
- **Metrics**: Prometheus metrics for monitoring
- **API Documentation**: Auto-generated OpenAPI/Swagger documentation

## Requirements

- Python 3.11+
- PostgreSQL 15+ with Row-Level Security enabled
- Redis 7+ (for caching)
- Docker (for containerized deployment)

## Installation

### Local Development

1. **Install dependencies:**

```bash
pip install -r requirements.txt
```

2. **Set environment variables:**

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/canonical_db"
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export REDIS_PASSWORD="your-redis-password"
export SECRET_KEY="your-secret-key"
```

3. **Run the service:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Deployment

1. **Build the image:**

```bash
docker build -t canonical-db-agent:latest .
```

2. **Run the container:**

```bash
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql://user:password@postgres:5432/canonical_db" \
  -e REDIS_HOST="redis" \
  -e REDIS_PORT="6379" \
  -e REDIS_PASSWORD="your-redis-password" \
  -e SECRET_KEY="your-secret-key" \
  --name canonical-db-agent \
  canonical-db-agent:latest
```

### Docker Compose

```bash
cd ../../infra/docker-compose
docker-compose up -d canonical-db-api
```

## Configuration

Configuration is managed through environment variables:

| Variable         | Description                  | Default       |
| ---------------- | ---------------------------- | ------------- |
| `DATABASE_URL`   | PostgreSQL connection string | Required      |
| `REDIS_HOST`     | Redis host                   | `localhost`   |
| `REDIS_PORT`     | Redis port                   | `6379`        |
| `REDIS_PASSWORD` | Redis password               | Required      |
| `SECRET_KEY`     | API secret key               | Required      |
| `ENVIRONMENT`    | Environment name             | `development` |
| `LOG_LEVEL`      | Logging level                | `INFO`        |
| `RLS_ENABLED`    | Enable Row-Level Security    | `true`        |
| `CORS_ORIGINS`   | Allowed CORS origins         | `*`           |

## API Documentation

Once the service is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## API Endpoints

### Health & Monitoring

- `GET /health` - Health check with dependency status
- `GET /ready` - Kubernetes readiness probe
- `GET /live` - Kubernetes liveness probe
- `GET /metrics` - Prometheus metrics
- `GET /version` - Service version information

### Documents

- `POST /api/v1/documents` - Create document
- `GET /api/v1/documents` - List documents (paginated)
- `GET /api/v1/documents/{id}` - Get document by ID
- `PUT /api/v1/documents/{id}` - Update document
- `DELETE /api/v1/documents/{id}` - Delete document (soft delete)
- `POST /api/v1/documents/{id}/archive` - Archive document
- `GET /api/v1/documents/{id}/version` - Get current version

### Chunks

- `POST /api/v1/chunks` - Create chunk
- `POST /api/v1/chunks/bulk` - Bulk create chunks
- `GET /api/v1/chunks/{id}` - Get chunk by ID
- `POST /api/v1/chunks/batch` - Get multiple chunks by IDs
- `GET /api/v1/documents/{id}/chunks` - Get document chunks (paginated)
- `GET /api/v1/documents/{id}/chunks/count` - Count document chunks

## Authentication

All API requests require two headers:

- `X-Tenant-ID`: Tenant identifier for multi-tenancy
- `X-API-Key`: API key for authentication (MVP implementation)

Example:

```bash
curl -X GET "http://localhost:8000/api/v1/documents" \
  -H "X-Tenant-ID: global-company" \
  -H "X-API-Key: your-secret-key"
```

## Testing

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_documents.py
```

### Test Structure

```
tests/
├── test_health.py          # Health check tests
├── test_documents.py       # Document CRUD tests
├── test_chunks.py          # Chunk CRUD tests
└── conftest.py            # Test fixtures
```

## Development

### Code Quality

```bash
# Format code
black app/

# Lint code
ruff check app/

# Type checking
mypy app/
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Monitoring

### Prometheus Metrics

The service exposes Prometheus metrics at `/metrics`:

- `http_requests_total` - Total HTTP requests by method, endpoint, and status
- `http_request_duration_seconds` - Request duration histogram
- `http_request_size_bytes` - Request size histogram
- `http_response_size_bytes` - Response size histogram
- `db_connections_active` - Active database connections
- `db_health_status` - Database health (1=healthy, 0=unhealthy)
- `redis_health_status` - Redis health (1=healthy, 0=unhealthy)

### Health Checks

- **Health**: `/health` - Comprehensive health check with dependency status
- **Readiness**: `/ready` - Returns 200 when ready to accept traffic
- **Liveness**: `/live` - Returns 200 when service is alive

## Troubleshooting

### Database Connection Issues

```bash
# Check database connectivity
psql -h localhost -U user -d canonical_db

# Verify RLS policies
SELECT * FROM pg_policies WHERE tablename = 'documents';
```

### Redis Connection Issues

```bash
# Check Redis connectivity
redis-cli -h localhost -p 6379 -a your-password ping
```

### Common Errors

**Error: "X-Tenant-ID header is required"**

- Solution: Include `X-Tenant-ID` header in all requests

**Error: "Invalid API key"**

- Solution: Verify `X-API-Key` matches `SECRET_KEY` environment variable

**Error: "Database connection failed"**

- Solution: Check `DATABASE_URL` and PostgreSQL service status

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Canonical DB Agent API                    │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Application                                         │
│  ├── Routers (health, documents, chunks)                    │
│  ├── Dependencies (tenant context, auth)                    │
│  ├── CRUD Operations                                         │
│  ├── Schemas (Pydantic models)                              │
│  └── Database (SQLAlchemy ORM)                              │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL 15+ (with RLS)                                   │
│  Redis 7+ (caching)                                          │
└─────────────────────────────────────────────────────────────┘
```

## Contributing

1. Follow PEP 8 style guide
2. Write tests for new features
3. Update documentation
4. Run code quality checks before committing

## License

Internal use only - Enterprise RAG System

## Support

For issues and questions, contact the Enterprise RAG Team.

---

**Version**: 0.1.0  
**Last Updated**: 2026-05-29
