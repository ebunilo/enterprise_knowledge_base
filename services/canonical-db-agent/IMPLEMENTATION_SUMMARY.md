# Canonical DB Agent - Implementation Summary

**Status:** In Progress  
**Date:** 2026-05-29  
**Completion:** 5/15 files (33%)

---

## Completed Files ✅

### 1. requirements.txt (40 lines)

**Purpose:** Python dependencies  
**Key Dependencies:**

- FastAPI 0.109.0 + Uvicorn
- SQLAlchemy 2.0.25 + psycopg2
- Redis 5.0.1
- Pydantic 2.5.3
- Prometheus client
- Development tools (pytest, black, ruff, mypy)

### 2. Dockerfile (57 lines)

**Purpose:** Multi-stage Docker build  
**Features:**

- Python 3.11-slim base
- Non-root user (appuser)
- Health check on /health endpoint
- Exposes port 8000
- 4 workers by default

### 3. app/config.py (68 lines)

**Purpose:** Configuration management with pydantic-settings  
**Key Settings:**

- Database connection (pool size, timeout)
- Redis connection
- Security (secret_key, CORS)
- Logging (level, format)
- RLS (Row-Level Security) flags
- Performance tuning

### 4. app/database.py (137 lines)

**Purpose:** Database connection and session management  
**Features:**

- SQLAlchemy engine with connection pooling
- Session factory with context managers
- Redis client setup
- RLS tenant context support
- Health check functions
- Connection lifecycle event listeners

### 5. app/models.py (248 lines)

**Purpose:** SQLAlchemy ORM models  
**Models Implemented:**

- Tenant (multi-tenancy)
- Document (metadata)
- DocumentChunk (chunk data)
- DocumentVersion (versioning)
- AccessPolicy (ACL rules)
- DocumentSource (ingestion config)
- IngestionJob (job tracking)
- RetrievalAuditLog (query audit)
- UserFeedback (quality tracking)

---

## Remaining Files 📋

### 6. app/schemas.py (~200 lines)

**Purpose:** Pydantic models for request/response validation

**Required Schemas:**

#### Document Schemas

```python
class DocumentBase(BaseModel):
    title: str
    source_type: str
    source_uri: str
    classification: str
    department: Optional[str]
    region: Optional[str]
    language: str = "en"
    version: str
    checksum: str

class DocumentCreate(DocumentBase):
    tenant_id: str

class DocumentUpdate(BaseModel):
    title: Optional[str]
    status: Optional[str]
    classification: Optional[str]

class DocumentResponse(DocumentBase):
    document_id: UUID
    tenant_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

#### Chunk Schemas

```python
class ChunkBase(BaseModel):
    chunk_text: str
    chunk_index: int
    page_start: Optional[int]
    page_end: Optional[int]
    section_title: Optional[str]
    heading_path: Optional[List[str]]
    token_count: int
    checksum: str

class ChunkCreate(ChunkBase):
    document_id: UUID
    tenant_id: str

class ChunkResponse(ChunkBase):
    chunk_id: UUID
    document_id: UUID
    tenant_id: str
    created_at: datetime

    class Config:
        from_attributes = True
```

#### Pagination Schemas

```python
class PaginationParams(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool
```

---

### 7. app/crud.py (~300 lines)

**Purpose:** Database CRUD operations

**Required Functions:**

#### Document Operations

```python
def create_document(db: Session, document: DocumentCreate) -> Document
def get_document(db: Session, document_id: UUID) -> Optional[Document]
def get_documents(
    db: Session,
    tenant_id: str,
    status: str = "active",
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Document], int]
def update_document(db: Session, document_id: UUID, updates: DocumentUpdate) -> Document
def delete_document(db: Session, document_id: UUID) -> bool
def mark_document_archived(db: Session, document_id: UUID) -> bool
```

#### Chunk Operations

```python
def create_chunk(db: Session, chunk: ChunkCreate) -> DocumentChunk
def get_chunk(db: Session, chunk_id: UUID) -> Optional[DocumentChunk]
def get_chunks_by_ids(db: Session, chunk_ids: List[UUID]) -> List[DocumentChunk]
def get_chunks_by_document(
    db: Session,
    document_id: UUID,
    limit: int = 1000,
    offset: int = 0
) -> Tuple[List[DocumentChunk], int]
def bulk_create_chunks(db: Session, chunks: List[ChunkCreate]) -> List[DocumentChunk]
```

#### Version Operations

```python
def create_document_version(
    db: Session,
    document_id: UUID,
    tenant_id: str,
    version: str
) -> DocumentVersion
def get_current_version(db: Session, document_id: UUID) -> Optional[DocumentVersion]
def archive_old_versions(db: Session, document_id: UUID, current_version: str) -> int
```

**Features:**

- Tenant context enforcement
- Error handling with custom exceptions
- Bulk operations with batching
- Efficient queries with joins
- Transaction management

---

### 8. app/dependencies.py (~50 lines)

**Purpose:** FastAPI dependency injection

**Required Dependencies:**

```python
def get_tenant_id(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID")
) -> str:
    """Extract tenant ID from request header."""
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return x_tenant_id

def get_db_with_tenant_context(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
) -> Session:
    """Get database session with tenant context set."""
    set_tenant_context(db, tenant_id)
    return db

def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key")
) -> str:
    """Verify API key for service-to-service calls."""
    # Simple API key validation
    if x_api_key != settings.secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
```

---

### 9. app/routers/health.py (~80 lines)

**Purpose:** Health check and metrics endpoints

**Endpoints:**

```python
@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns: {"status": "healthy", "timestamp": "...", "checks": {...}}
    """
    db_healthy = check_database_connection()
    redis_healthy = check_redis_connection()

    return {
        "status": "healthy" if (db_healthy and redis_healthy) else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "canonical-db-agent",
        "version": "0.1.0",
        "checks": {
            "database": "ok" if db_healthy else "error",
            "redis": "ok" if redis_healthy else "error"
        }
    }

@router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Returns: Prometheus-formatted metrics
    """
    # Return Prometheus metrics
    pass

@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe."""
    pass

@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    pass
```

---

### 10. app/routers/documents.py (~250 lines)

**Purpose:** Document CRUD API endpoints

**Endpoints:**

```python
@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def create_document(
    document: DocumentCreate,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Create a new document."""
    pass

@router.get("/documents", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    status: str = "active",
    pagination: PaginationParams = Depends(),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db_with_tenant_context)
):
    """List documents with pagination."""
    pass

@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Get document by ID."""
    pass

@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    updates: DocumentUpdate,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Update document."""
    pass

@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Delete document."""
    pass

@router.post("/documents/{document_id}/archive", status_code=200)
async def archive_document(
    document_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Archive document."""
    pass
```

**Features:**

- Request validation with Pydantic
- Tenant isolation via dependencies
- Error handling with HTTP exceptions
- Pagination support
- OpenAPI documentation

---

### 11. app/routers/chunks.py (~200 lines)

**Purpose:** Chunk CRUD API endpoints

**Endpoints:**

```python
@router.post("/chunks", response_model=ChunkResponse, status_code=201)
async def create_chunk(
    chunk: ChunkCreate,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Create a new chunk."""
    pass

@router.post("/chunks/bulk", response_model=List[ChunkResponse], status_code=201)
async def bulk_create_chunks(
    chunks: List[ChunkCreate],
    db: Session = Depends(get_db_with_tenant_context)
):
    """Bulk create chunks."""
    pass

@router.get("/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(
    chunk_id: UUID,
    db: Session = Depends(get_db_with_tenant_context)
):
    """Get chunk by ID."""
    pass

@router.post("/chunks/batch", response_model=List[ChunkResponse])
async def get_chunks_batch(
    chunk_ids: List[UUID],
    db: Session = Depends(get_db_with_tenant_context)
):
    """Get multiple chunks by IDs."""
    pass

@router.get("/documents/{document_id}/chunks", response_model=PaginatedResponse[ChunkResponse])
async def get_document_chunks(
    document_id: UUID,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_with_tenant_context)
):
    """Get all chunks for a document."""
    pass
```

---

### 12. app/main.py (~150 lines)

**Purpose:** FastAPI application setup and configuration

**Structure:**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import make_asgi_app
import logging

from app.config import settings
from app.routers import health, documents, chunks

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create FastAPI app
app = FastAPI(
    title="Canonical DB Agent API",
    description="Document and chunk metadata management for Enterprise RAG System",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])
app.include_router(chunks.router, prefix="/api/v1", tags=["Chunks"])

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Canonical DB Agent API")
    # Initialize connections, etc.

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Canonical DB Agent API")
    # Cleanup connections, etc.

# Root endpoint
@app.get("/")
async def root():
    return {
        "service": "canonical-db-agent",
        "version": "0.1.0",
        "status": "running"
    }
```

---

### 13. app/**init**.py (minimal)

**Purpose:** Package initialization

```python
"""Canonical DB Agent - Document and chunk metadata management."""
__version__ = "0.1.0"
```

---

### 14. README.md (~100 lines)

**Purpose:** Service documentation

**Sections:**

- Overview
- Features
- Requirements
- Installation
- Configuration
- Running locally
- Running with Docker
- API Documentation
- Testing
- Deployment
- Troubleshooting

---

### 15. .dockerignore (~20 lines)

**Purpose:** Exclude files from Docker build

```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
.pytest_cache/
.coverage
htmlcov/
.git/
.gitignore
*.md
tests/
.env
.env.*
```

---

## Implementation Approach

### Phase 1: Core Files (Next)

1. app/schemas.py - Request/response models
2. app/crud.py - Database operations
3. app/dependencies.py - FastAPI dependencies

### Phase 2: API Endpoints

4. app/routers/health.py - Health checks
5. app/routers/documents.py - Document CRUD
6. app/routers/chunks.py - Chunk CRUD

### Phase 3: Application Setup

7. app/main.py - FastAPI app
8. app/**init**.py - Package init
9. README.md - Documentation
10. .dockerignore - Docker exclusions

---

## Testing Strategy

### Unit Tests (After Implementation)

- Test CRUD operations
- Test schema validation
- Test error handling
- Test tenant isolation

### Integration Tests

- Test with real PostgreSQL
- Test with real Redis
- Test API endpoints
- Test Docker build

---

## Estimated Completion Time

- **Remaining files:** 10 files, ~1,350 lines
- **Estimated time:** 2-3 hours with systematic implementation
- **Messages required:** ~15-20 messages (one file at a time)

---

## Next Steps

**Option A: Continue Implementation**

- I'll create all remaining files systematically
- One file per message for review
- You can stop me at any point

**Option B: Batch Implementation**

- I'll create multiple related files together
- Faster but less granular review

**Option C: Pause and Review**

- Review current implementation
- Provide feedback
- Continue after confirmation

**Which option do you prefer?**

---

**Status:** Awaiting confirmation to proceed  
**Current Progress:** 33% complete (5/15 files)  
**Next File:** app/schemas.py (Pydantic models)
