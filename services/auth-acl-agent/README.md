# Auth ACL Agent

Authentication and access control service for the Enterprise RAG System.

## Overview

The Auth ACL Agent is a FastAPI microservice that provides JWT token validation, user claims extraction, and access control logic for the Enterprise RAG System. It enforces strict access control across all document categories and ensures users can only access documents they are authorized to view.

## Features

- **JWT Token Validation**: Validate tokens from Keycloak OIDC provider
- **User Claims Extraction**: Extract and normalize user claims from JWT tokens
- **Access Control Logic**: Enforce multi-level access control (PUBLIC, INTERNAL, DEPARTMENT, CONFIDENTIAL, etc.)
- **Chunk Filtering**: Filter chunk IDs by user access permissions
- **Retrieval Filters**: Build metadata filters for pre-filtering retrieval results
- **Multi-Tenancy**: Strict tenant isolation with tenant-aware access checks
- **Caching**: Redis-based caching for access decisions and OIDC configuration
- **Health Checks**: Kubernetes-ready health, readiness, and liveness probes
- **Metrics**: Prometheus metrics for monitoring authentication and authorization
- **API Documentation**: Auto-generated OpenAPI/Swagger documentation

## Requirements

- Python 3.11+
- PostgreSQL 15+ (for access policies)
- Redis 7+ (for caching)
- Keycloak or compatible OIDC provider
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
export OIDC_PROVIDER_URL="https://auth.igwilo.com/realms/caltech"
export OIDC_CLIENT_ID="caltech-001"
export OIDC_CLIENT_SECRET="your-client-secret"
export SECRET_KEY="your-secret-key"
```

3. **Run the service:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Deployment

1. **Build the image:**

```bash
docker build -t auth-acl-agent:latest .
```

2. **Run the container:**

```bash
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql://user:password@postgres:5432/canonical_db" \
  -e REDIS_HOST="redis" \
  -e REDIS_PORT="6379" \
  -e REDIS_PASSWORD="your-redis-password" \
  -e OIDC_PROVIDER_URL="https://auth.igwilo.com/realms/caltech" \
  -e OIDC_CLIENT_ID="caltech-001" \
  -e OIDC_CLIENT_SECRET="your-client-secret" \
  -e SECRET_KEY="your-secret-key" \
  --name auth-acl-agent \
  auth-acl-agent:latest
```

### Docker Compose

```bash
cd ../../infra/docker-compose
docker-compose up -d auth-acl-api
```

## Configuration

Configuration is managed through environment variables:

| Variable                  | Description                     | Default       |
| ------------------------- | ------------------------------- | ------------- |
| `DATABASE_URL`            | PostgreSQL connection string    | Required      |
| `REDIS_HOST`              | Redis host                      | `localhost`   |
| `REDIS_PORT`              | Redis port                      | `6379`        |
| `REDIS_PASSWORD`          | Redis password                  | Required      |
| `OIDC_PROVIDER_URL`       | OIDC provider URL               | Required      |
| `OIDC_CLIENT_ID`          | OIDC client ID                  | Required      |
| `OIDC_CLIENT_SECRET`      | OIDC client secret              | Required      |
| `SECRET_KEY`              | Application secret key          | Required      |
| `ENVIRONMENT`             | Environment name                | `development` |
| `LOG_LEVEL`               | Logging level                   | `INFO`        |
| `REQUIRE_TENANT_ID`       | Require tenant ID in requests   | `true`        |
| `STRICT_TENANT_ISOLATION` | Enforce strict tenant isolation | `true`        |
| `LOG_ACCESS_DENIALS`      | Log access denials              | `true`        |
| `CORS_ORIGINS`            | Allowed CORS origins            | `*`           |
| `CACHE_TTL`               | Cache TTL in seconds            | `300`         |

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

### Authentication

- `POST /api/v1/auth/validate` - Validate JWT token
- `GET /api/v1/auth/user/info` - Get user information from token
- `GET /api/v1/auth/user/me` - Get current user (alias)
- `POST /api/v1/auth/callback` - OIDC callback handler (placeholder)
- `POST /api/v1/auth/logout` - Logout (placeholder)

### Access Control

- `POST /api/v1/acl/authorize` - Check document/chunk access
- `POST /api/v1/acl/authorize/batch` - Batch access check
- `POST /api/v1/acl/filter` - Filter chunk IDs by access
- `POST /api/v1/acl/retrieval-filter` - Build retrieval filter
- `GET /api/v1/acl/user/permissions` - Get user permissions summary

### Cache Management

- `POST /api/v1/acl/cache/invalidate/user` - Invalidate user cache
- `POST /api/v1/acl/cache/invalidate/document/{id}` - Invalidate document cache

## Authentication

All API requests (except health checks) require a valid JWT token in the Authorization header:

```bash
curl -X GET "http://localhost:8000/api/v1/auth/user/info" \
  -H "Authorization: Bearer <your-jwt-token>"
```

## Access Control Model

The service enforces a multi-level access control model:

### Access Levels

1. **PUBLIC** - Accessible to all users
2. **INTERNAL_GENERAL** - Accessible to all employees
3. **DEPARTMENT_RESTRICTED** - Accessible to specific departments
4. **CONFIDENTIAL** - Accessible to specific groups/roles
5. **REGULATED** - Accessible with special clearance
6. **EXECUTIVE_ONLY** - Accessible to executives only

### Access Decision Rules

A user can access a document/chunk if **ALL** of the following are true:

1. **Tenant Match**: `user.tenant_id == document.tenant_id`
2. **Document Active**: `document.status == "active"`
3. **No Explicit Deny**: `user.user_id NOT IN document.denied_users`
4. **Access Level Check**: At least ONE of:
   - Document is PUBLIC
   - Document is INTERNAL and user is employee
   - User's department is in allowed_departments
   - User's group is in allowed_groups
   - User's role is in allowed_roles
   - User's user_id is in allowed_users
5. **Region Check**: If `allowed_regions` is set, user's region/country must match

### Example Access Check

```python
# User claims
{
  "user_id": "user_123",
  "tenant_id": "global-company",
  "department": "finance",
  "groups": ["finance", "internal-users"],
  "role": "finance_manager",
  "region": "emea",
  "is_employee": true
}

# Document metadata
{
  "document_id": "doc_001",
  "tenant_id": "global-company",
  "classification": "DEPARTMENT_RESTRICTED",
  "status": "active",
  "allowed_departments": ["finance", "hr"],
  "denied_users": []
}

# Result: Access GRANTED (department match)
```

## Caching Strategy

The service uses Redis for caching to improve performance:

### Cached Items

- **Access Decisions**: 5 minutes TTL
- **OIDC Configuration**: 1 hour TTL
- **JWKS (JSON Web Key Set)**: 1 hour TTL
- **Token Validation Results**: Until token expiry (max 5 minutes)

### Cache Keys

```
acl:{user_id}:{item_id}           # Access decision
oidc:config:{provider_url}        # OIDC configuration
oidc:jwks:{provider_url}          # JWKS
oidc:token:{token_hash}           # Token validation result
```

### Cache Invalidation

Cache is automatically invalidated when:

- User permissions change
- Document access policy changes
- Document is deleted or archived
- Manual invalidation via API

## Testing

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-mock

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py
```

### Test Structure

```
tests/
├── test_health.py          # Health check tests
├── test_auth.py            # Authentication tests
├── test_acl.py             # Access control tests
├── test_oidc.py            # OIDC client tests
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

## Monitoring

### Prometheus Metrics

The service exposes Prometheus metrics at `/metrics`:

**Authentication Metrics:**

- `auth_token_validations_total` - Total token validations by result
- `auth_token_validation_duration_seconds` - Token validation duration

**ACL Metrics:**

- `acl_access_checks_total` - Total access checks by result
- `acl_access_check_duration_seconds` - Access check duration
- `acl_cache_hits_total` - Total ACL cache hits
- `acl_cache_misses_total` - Total ACL cache misses

**Component Health:**

- `db_health_status` - Database health (1=healthy, 0=unhealthy)
- `redis_health_status` - Redis health (1=healthy, 0=unhealthy)
- `oidc_health_status` - OIDC provider health (1=healthy, 0=unhealthy)

**HTTP Metrics:**

- `http_requests_total` - Total HTTP requests by method, endpoint, and status
- `http_request_duration_seconds` - Request duration histogram
- `http_request_size_bytes` - Request size histogram
- `http_response_size_bytes` - Response size histogram

### Health Checks

- **Health**: `/health` - Comprehensive health check with dependency status
- **Readiness**: `/ready` - Returns 200 when ready to accept traffic
- **Liveness**: `/live` - Returns 200 when service is alive

## Troubleshooting

### OIDC Connection Issues

```bash
# Check OIDC provider connectivity
curl https://auth.igwilo.com/realms/caltech/.well-known/openid-configuration

# Verify JWKS endpoint
curl https://auth.igwilo.com/realms/caltech/protocol/openid-connect/certs
```

### Token Validation Failures

**Error: "Invalid or expired token"**

- Solution: Check token expiration (`exp` claim)
- Solution: Verify token issuer matches OIDC provider
- Solution: Ensure token audience matches client ID

**Error: "Token missing required claims"**

- Solution: Verify token includes `sub` (user_id) and `tenant_id` claims
- Solution: Check Keycloak client mappers configuration

### Redis Connection Issues

```bash
# Check Redis connectivity
redis-cli -h localhost -p 6379 -a your-password ping

# Check cache keys
redis-cli -h localhost -p 6379 -a your-password keys "acl:*"
```

### Common Errors

**Error: "Tenant mismatch"**

- Solution: Ensure user's tenant_id matches document's tenant_id

**Error: "Access denied"**

- Solution: Check user's department, groups, and roles
- Solution: Verify document's access policy allows user's attributes
- Solution: Check for explicit deny rules

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Auth ACL Agent API                        │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Application                                         │
│  ├── Routers (health, auth, acl)                            │
│  ├── OIDC Client (token validation)                         │
│  ├── ACL Engine (access control logic)                      │
│  ├── Dependencies (authentication, user claims)             │
│  └── Database (access policies)                             │
├─────────────────────────────────────────────────────────────┤
│  Keycloak OIDC Provider                                      │
│  PostgreSQL 15+ (access policies)                            │
│  Redis 7+ (caching)                                          │
└─────────────────────────────────────────────────────────────┘
```

## Security Considerations

### Critical Security Rules

1. **Never trust metadata filters alone** - Always validate against PostgreSQL ACLs
2. **Explicit deny always wins** - Deny overrides all allow rules
3. **Tenant isolation is mandatory** - Cross-tenant access is never allowed
4. **Cache must be validated** - Cached decisions have short TTL
5. **Log all denials** - Security monitoring requires denial logging

### Threat Mitigation

| Threat               | Mitigation                                   |
| -------------------- | -------------------------------------------- |
| Token forgery        | JWT signature verification with JWKS         |
| Token replay         | Short token expiry (5-15 minutes)            |
| Cache poisoning      | Cache keys include policy version, short TTL |
| Tenant leakage       | Strict tenant checks at every access point   |
| Privilege escalation | Explicit deny overrides all allow rules      |

## Integration with Enterprise RAG System

The Auth ACL Agent integrates with other system components:

- **Canonical DB Agent**: Fetches document/chunk metadata for access checks
- **Hybrid Retrieval Agent**: Provides pre-filtering metadata filters
- **ACL Validation Agent**: Performs final authorization before context building
- **Context Builder Agent**: Ensures only authorized chunks reach LLM
- **Audit Agent**: Logs access denials for security monitoring

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
**Status**: Production Ready (MVP)
