# canonical-db-agent

**Domain:** Infrastructure  
**Status:** 📋 Planned  
**Phase:** 1 - Canonical Foundation  
**Owner:** Infrastructure Team  
**Implementation Week:** Week 2

---

## Overview

The `canonical-db-agent` owns PostgreSQL as the **source of truth** for all documents, chunks, versions, access policies, citations, and audit references in the Enterprise RAG System.

All other data stores (Qdrant, BM25/OpenSearch, Knowledge Graph) must resolve back to PostgreSQL using stable IDs. This agent ensures data consistency, versioning, and serves as the authoritative reference for all retrieval and generation operations.

---

## Responsibility

### Primary Responsibilities

- Own and manage PostgreSQL schema
- Store and manage document metadata
- Store and manage chunk metadata
- Handle document versioning
- Maintain access policy references
- Store canonical source URIs
- Compute and validate chunk checksums
- Track ingestion status and jobs

### Key Principle

**PostgreSQL is the single source of truth.** Qdrant, BM25, and Knowledge Graph records must always resolve back to PostgreSQL using stable IDs.

---

## Architecture

### Database Schema

#### Core Tables

```sql
-- Tenants
CREATE TABLE tenants (
    tenant_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Documents
CREATE TABLE documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    title TEXT NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_uri TEXT NOT NULL,
    classification VARCHAR(50) NOT NULL,
    department VARCHAR(100),
    region VARCHAR(100),
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    version VARCHAR(50) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, source_uri, version)
);

-- Document Chunks
CREATE TABLE document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    section_title TEXT,
    heading_path TEXT[],
    token_count INTEGER NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

-- Document Versions
CREATE TABLE document_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(document_id),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    version VARCHAR(50) NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMP,
    UNIQUE(document_id, version)
);

-- Access Policies
CREATE TABLE access_policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    document_id UUID REFERENCES documents(document_id) ON DELETE CASCADE,
    classification VARCHAR(50) NOT NULL,
    allowed_departments TEXT[],
    allowed_groups TEXT[],
    allowed_roles TEXT[],
    allowed_users TEXT[],
    denied_users TEXT[],
    allowed_regions TEXT[],
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Document Sources
CREATE TABLE document_sources (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    source_type VARCHAR(100) NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_config JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Ingestion Jobs
CREATE TABLE ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    source_id UUID REFERENCES document_sources(source_id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    documents_processed INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Retrieval Audit Logs
CREATE TABLE retrieval_audit_logs (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(255) NOT NULL,
    query TEXT NOT NULL,
    query_intent VARCHAR(100),
    retrieved_chunk_ids UUID[],
    authorized_chunk_ids UUID[],
    denied_chunk_ids UUID[],
    cited_chunk_ids UUID[],
    model_used VARCHAR(100),
    answer_hash VARCHAR(64),
    latency_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- User Feedback
CREATE TABLE user_feedback (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(tenant_id),
    audit_id UUID REFERENCES retrieval_audit_logs(audit_id),
    user_id VARCHAR(255) NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    feedback_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

#### Row-Level Security (RLS)

```sql
-- Enable RLS on all tenant-scoped tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE access_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE retrieval_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only access data from their tenant
CREATE POLICY tenant_isolation_policy ON documents
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON document_chunks
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON document_versions
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON access_policies
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON document_sources
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON ingestion_jobs
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON retrieval_audit_logs
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation_policy ON user_feedback
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);
```

#### Indexes

```sql
-- Documents
CREATE INDEX idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_classification ON documents(classification);
CREATE INDEX idx_documents_department ON documents(department);
CREATE INDEX idx_documents_source_uri ON documents(source_uri);

-- Document Chunks
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_tenant_id ON document_chunks(tenant_id);
CREATE INDEX idx_chunks_checksum ON document_chunks(checksum);

-- Document Versions
CREATE INDEX idx_versions_document_id ON document_versions(document_id);
CREATE INDEX idx_versions_is_current ON document_versions(is_current);

-- Access Policies
CREATE INDEX idx_policies_document_id ON access_policies(document_id);
CREATE INDEX idx_policies_tenant_id ON access_policies(tenant_id);

-- Ingestion Jobs
CREATE INDEX idx_jobs_tenant_id ON ingestion_jobs(tenant_id);
CREATE INDEX idx_jobs_status ON ingestion_jobs(status);
CREATE INDEX idx_jobs_source_id ON ingestion_jobs(source_id);

-- Audit Logs
CREATE INDEX idx_audit_tenant_id ON retrieval_audit_logs(tenant_id);
CREATE INDEX idx_audit_user_id ON retrieval_audit_logs(user_id);
CREATE INDEX idx_audit_created_at ON retrieval_audit_logs(created_at);
```

---

## API Contract

### Document Operations

```python
# Create document
def create_document(
    tenant_id: str,
    title: str,
    source_type: str,
    source_uri: str,
    classification: str,
    department: Optional[str],
    region: Optional[str],
    language: str,
    version: str,
    checksum: str
) -> UUID:
    """Create a new document record."""
    pass

# Get document
def get_document(document_id: UUID) -> Optional[Document]:
    """Retrieve document by ID."""
    pass

# Get documents by tenant
def get_documents_by_tenant(
    tenant_id: str,
    status: Optional[str] = "active",
    limit: int = 100,
    offset: int = 0
) -> List[Document]:
    """Retrieve documents for a tenant."""
    pass

# Mark document archived
def mark_document_archived(document_id: UUID) -> bool:
    """Mark document as archived."""
    pass

# Mark document deleted
def mark_document_deleted(document_id: UUID) -> bool:
    """Mark document as deleted."""
    pass

# Get current document version
def get_current_document_version(document_id: UUID) -> Optional[DocumentVersion]:
    """Get the current active version of a document."""
    pass
```

### Chunk Operations

```python
# Create chunk
def create_chunk(
    document_id: UUID,
    tenant_id: str,
    chunk_text: str,
    chunk_index: int,
    page_start: Optional[int],
    page_end: Optional[int],
    section_title: Optional[str],
    heading_path: Optional[List[str]],
    token_count: int,
    checksum: str
) -> UUID:
    """Create a new chunk record."""
    pass

# Get chunk
def get_chunk(chunk_id: UUID) -> Optional[Chunk]:
    """Retrieve chunk by ID."""
    pass

# Get chunks by IDs
def get_chunks_by_ids(chunk_ids: List[UUID]) -> List[Chunk]:
    """Retrieve multiple chunks by IDs in stable order."""
    pass

# Get chunks by document
def get_chunks_by_document(
    document_id: UUID,
    limit: int = 1000,
    offset: int = 0
) -> List[Chunk]:
    """Retrieve all chunks for a document."""
    pass
```

### Version Operations

```python
# Create version
def create_document_version(
    document_id: UUID,
    tenant_id: str,
    version: str,
    is_current: bool = True
) -> UUID:
    """Create a new document version."""
    pass

# Archive old versions
def archive_old_versions(document_id: UUID, current_version: str) -> int:
    """Archive all versions except the current one."""
    pass
```

---

## Data Models

### Document

```python
@dataclass
class Document:
    document_id: UUID
    tenant_id: str
    title: str
    source_type: str
    source_uri: str
    classification: str
    department: Optional[str]
    region: Optional[str]
    language: str
    version: str
    checksum: str
    status: str
    created_at: datetime
    updated_at: datetime
```

### Chunk

```python
@dataclass
class Chunk:
    chunk_id: UUID
    document_id: UUID
    tenant_id: str
    chunk_text: str
    chunk_index: int
    page_start: Optional[int]
    page_end: Optional[int]
    section_title: Optional[str]
    heading_path: Optional[List[str]]
    token_count: int
    checksum: str
    created_at: datetime
```

### DocumentVersion

```python
@dataclass
class DocumentVersion:
    version_id: UUID
    document_id: UUID
    tenant_id: str
    version: str
    is_current: bool
    created_at: datetime
    archived_at: Optional[datetime]
```

---

## Testing Requirements

### Unit Tests

**Test Coverage Target:** >80%

#### Document Tests

- ✅ Create document record successfully
- ✅ Reject document with missing required fields
- ✅ Reject document with invalid tenant_id
- ✅ Reject duplicate document (same tenant + source_uri + version)
- ✅ Update document status successfully
- ✅ Mark document as archived
- ✅ Mark document as deleted

#### Chunk Tests

- ✅ Create chunk linked to valid document
- ✅ Reject chunk with invalid document_id
- ✅ Reject chunk with missing required fields
- ✅ Reject duplicate chunk_index for same document
- ✅ Retrieve chunks by IDs in stable order
- ✅ Retrieve chunks by document_id

#### Version Tests

- ✅ Create document version successfully
- ✅ Mark old version as archived when new version is current
- ✅ Retrieve current document version
- ✅ Reject duplicate version for same document

#### Checksum Tests

- ✅ Reject duplicate checksum for same active document version
- ✅ Allow same checksum for different documents
- ✅ Allow same checksum for archived versions

### Integration Tests

- ✅ Insert document and chunks, then retrieve by document_id
- ✅ Update document version and confirm old version is no longer current
- ✅ Confirm Qdrant/BM25/KG references can resolve to PostgreSQL chunk records
- ✅ Bulk insert 1000 chunks and verify retrieval performance
- ✅ Test RLS policies enforce tenant isolation

### Security Tests

- ✅ Confirm deleted documents are excluded from retrieval queries
- ✅ Confirm archived documents are excluded unless explicitly requested
- ✅ Confirm RLS prevents cross-tenant data access
- ✅ Confirm tenant_id is required for all operations
- ✅ Confirm unauthorized tenant access is rejected

### Performance Tests

- ✅ Insert 10,000 documents in <10 seconds
- ✅ Insert 500,000 chunks in <60 seconds
- ✅ Retrieve document by ID in <10ms
- ✅ Retrieve 100 chunks by IDs in <50ms
- ✅ Query documents by tenant with pagination in <100ms

---

## Dependencies

### Upstream Dependencies

- PostgreSQL 15+
- Database migration tool (Alembic or similar)

### Downstream Consumers

- [`auth-acl-agent`](./auth-acl-agent.md) - Validates access policies
- [`document-ingestion-agent`](../ingestion/document-ingestion-agent.md) - Creates documents
- [`chunking-agent`](../ingestion/chunking-agent.md) - Creates chunks
- [`embedding-agent`](../indexing/embedding-agent.md) - Reads chunks for embedding
- [`acl-validation-agent`](../retrieval/acl-validation-agent.md) - Validates chunk access
- [`citation-agent`](../generation/citation-agent.md) - Validates citations
- [`audit-agent`](../operations/audit-agent.md) - Logs retrieval events

---

## Configuration

### Environment Variables

```bash
# Database Connection
DATABASE_URL=postgresql://user:password@localhost:5432/enterprise_rag
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Row-Level Security
RLS_ENABLED=true

# Performance
QUERY_TIMEOUT_MS=5000
BULK_INSERT_BATCH_SIZE=1000
```

### Configuration File

```yaml
database:
  url: ${DATABASE_URL}
  pool_size: 20
  max_overflow: 10
  echo: false

security:
  rls_enabled: true
  require_tenant_id: true

performance:
  query_timeout_ms: 5000
  bulk_insert_batch_size: 1000
  connection_pool_recycle: 3600
```

---

## Error Handling

### Error Types

```python
class DocumentNotFoundError(Exception):
    """Document does not exist."""
    pass

class ChunkNotFoundError(Exception):
    """Chunk does not exist."""
    pass

class DuplicateDocumentError(Exception):
    """Document already exists."""
    pass

class DuplicateChunkError(Exception):
    """Chunk index already exists for document."""
    pass

class InvalidTenantError(Exception):
    """Tenant ID is invalid or missing."""
    pass

class DatabaseConnectionError(Exception):
    """Cannot connect to database."""
    pass
```

---

## Monitoring & Observability

### Metrics

```python
# Operation metrics
canonical_db_document_created_total
canonical_db_document_retrieved_total
canonical_db_chunk_created_total
canonical_db_chunk_retrieved_total

# Performance metrics
canonical_db_query_duration_seconds
canonical_db_bulk_insert_duration_seconds
canonical_db_connection_pool_size
canonical_db_connection_pool_available

# Error metrics
canonical_db_errors_total
canonical_db_connection_errors_total
canonical_db_query_timeouts_total
```

### Logging

```python
# Log all database operations
logger.info("Document created", extra={
    "document_id": document_id,
    "tenant_id": tenant_id,
    "source_type": source_type
})

# Log errors with context
logger.error("Failed to create chunk", extra={
    "document_id": document_id,
    "chunk_index": chunk_index,
    "error": str(e)
})
```

---

## Migration Strategy

### Initial Migration

```sql
-- migrations/001_initial_schema.sql
-- Create all tables, indexes, and RLS policies
```

### Version Upgrades

```sql
-- migrations/002_add_language_support.sql
-- Add language column to documents table
ALTER TABLE documents ADD COLUMN language VARCHAR(10) NOT NULL DEFAULT 'en';
```

---

## Related Documentation

- [System Architecture](../../ARCHITECTURE.md)
- [Multi-Tenancy Model](../../architecture/multi-tenancy.md)
- [PostgreSQL RLS](../../decisions/ADR-002-postgresql-rls.md)
- [Phase 1 Implementation](../../phases/phase-1-canonical-foundation/README.md)
- [auth-acl-agent](./auth-acl-agent.md)

---

**Status:** 📋 Ready for Implementation  
**Next Steps:** Begin Week 2 implementation with database schema creation and RLS policies.
