-- Enterprise RAG System - Database Initialization Script
-- Phase 1: Core Infrastructure (canonical-db-agent + auth-acl-agent)
-- PostgreSQL 15+ with Row-Level Security (RLS)

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Set timezone to UTC
SET timezone = 'UTC';

-- ============================================================================
-- ENUMS AND TYPES
-- ============================================================================

-- Document classification levels
CREATE TYPE document_classification AS ENUM (
    'PUBLIC',
    'INTERNAL_GENERAL',
    'DEPARTMENT_RESTRICTED',
    'CONFIDENTIAL',
    'REGULATED',
    'EXECUTIVE_ONLY'
);

-- Document status
CREATE TYPE document_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'ACTIVE',
    'ARCHIVED',
    'DELETED',
    'FAILED'
);

-- Document source types
CREATE TYPE document_source_type AS ENUM (
    'SHAREPOINT',
    'GOOGLE_DRIVE',
    'CONFLUENCE',
    'NOTION',
    'S3',
    'AZURE_BLOB',
    'GIT',
    'LOCAL_UPLOAD',
    'INTERNAL_WIKI',
    'OTHER'
);

-- Ingestion job status
CREATE TYPE ingestion_job_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'CANCELLED'
);

-- User roles
CREATE TYPE user_role AS ENUM (
    'SUPER_ADMIN',
    'TENANT_ADMIN',
    'DEPARTMENT_ADMIN',
    'SOURCE_ADMIN',
    'POLICY_ADMIN',
    'USER'
);

-- Access decision
CREATE TYPE access_decision AS ENUM (
    'ALLOW',
    'DENY'
);

-- ============================================================================
-- TENANTS TABLE
-- ============================================================================

CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_name VARCHAR(255) NOT NULL UNIQUE,
    tenant_slug VARCHAR(100) NOT NULL UNIQUE,
    
    -- Configuration
    default_language VARCHAR(10) DEFAULT 'en',
    allowed_languages TEXT[] DEFAULT ARRAY['en'],
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Limits and quotas
    max_documents INTEGER DEFAULT 10000,
    max_users INTEGER DEFAULT 1000,
    max_storage_gb INTEGER DEFAULT 100,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID,
    updated_by UUID,
    
    -- Constraints
    CONSTRAINT tenant_name_length CHECK (char_length(tenant_name) >= 2),
    CONSTRAINT tenant_slug_format CHECK (tenant_slug ~ '^[a-z0-9-]+$')
);

-- Indexes
CREATE INDEX idx_tenants_slug ON tenants(tenant_slug);
CREATE INDEX idx_tenants_active ON tenants(is_active) WHERE is_active = true;

-- ============================================================================
-- USERS TABLE
-- ============================================================================

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    
    -- Identity
    email VARCHAR(255) NOT NULL,
    username VARCHAR(100),
    full_name VARCHAR(255),
    
    -- Authentication (OAuth/OIDC)
    oidc_sub VARCHAR(255) UNIQUE,
    oidc_provider VARCHAR(100),
    
    -- Organization
    department VARCHAR(100),
    job_title VARCHAR(255),
    manager_id UUID REFERENCES users(user_id),
    
    -- Location
    region VARCHAR(100),
    country VARCHAR(100),
    office_location VARCHAR(255),
    
    -- Role and permissions
    role user_role DEFAULT 'USER',
    groups TEXT[] DEFAULT ARRAY[]::TEXT[],
    clearance_level document_classification DEFAULT 'INTERNAL_GENERAL',
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    last_login_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT users_tenant_email_unique UNIQUE (tenant_id, email),
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- Indexes
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_oidc_sub ON users(oidc_sub);
CREATE INDEX idx_users_department ON users(tenant_id, department);
CREATE INDEX idx_users_groups ON users USING GIN(groups);
CREATE INDEX idx_users_active ON users(tenant_id, is_active) WHERE is_active = true;

-- Row-Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_tenant_isolation ON users
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- DOCUMENT SOURCES TABLE
-- ============================================================================

CREATE TABLE document_sources (
    source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    
    -- Source details
    source_name VARCHAR(255) NOT NULL,
    source_type document_source_type NOT NULL,
    source_uri TEXT NOT NULL,
    
    -- Configuration
    config JSONB DEFAULT '{}'::JSONB,
    credentials_encrypted TEXT,
    
    -- Sync settings
    sync_enabled BOOLEAN DEFAULT true,
    sync_schedule VARCHAR(100) DEFAULT '0 */6 * * *', -- Every 6 hours
    last_sync_at TIMESTAMP WITH TIME ZONE,
    next_sync_at TIMESTAMP WITH TIME ZONE,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(user_id),
    updated_by UUID REFERENCES users(user_id),
    
    -- Constraints
    CONSTRAINT source_tenant_name_unique UNIQUE (tenant_id, source_name)
);

-- Indexes
CREATE INDEX idx_sources_tenant ON document_sources(tenant_id);
CREATE INDEX idx_sources_type ON document_sources(tenant_id, source_type);
CREATE INDEX idx_sources_active ON document_sources(tenant_id, is_active) WHERE is_active = true;
CREATE INDEX idx_sources_sync ON document_sources(next_sync_at) WHERE sync_enabled = true;

-- Row-Level Security
ALTER TABLE document_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY sources_tenant_isolation ON document_sources
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- DOCUMENTS TABLE
-- ============================================================================

CREATE TABLE documents (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    source_id UUID REFERENCES document_sources(source_id) ON DELETE SET NULL,
    
    -- Document identity
    title VARCHAR(500) NOT NULL,
    source_uri TEXT NOT NULL,
    external_id VARCHAR(255),
    
    -- Content
    file_name VARCHAR(500),
    file_extension VARCHAR(20),
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    checksum VARCHAR(64) NOT NULL,
    
    -- Storage
    storage_path TEXT,
    storage_bucket VARCHAR(255),
    
    -- Classification and access
    classification document_classification DEFAULT 'INTERNAL_GENERAL',
    department VARCHAR(100),
    region VARCHAR(100),
    language VARCHAR(10) DEFAULT 'en',
    
    -- Versioning
    version VARCHAR(50) DEFAULT 'v1.0',
    version_number INTEGER DEFAULT 1,
    parent_document_id UUID REFERENCES documents(document_id),
    is_current_version BOOLEAN DEFAULT true,
    
    -- Status
    status document_status DEFAULT 'PENDING',
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::JSONB,
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    
    -- Timestamps
    effective_date DATE,
    expiration_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP WITH TIME ZONE,
    
    -- Audit
    created_by UUID REFERENCES users(user_id),
    updated_by UUID REFERENCES users(user_id),
    
    -- Constraints
    CONSTRAINT document_tenant_checksum_unique UNIQUE (tenant_id, checksum, is_current_version) WHERE is_current_version = true,
    CONSTRAINT file_size_positive CHECK (file_size_bytes >= 0)
);

-- Indexes
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_source ON documents(source_id);
CREATE INDEX idx_documents_status ON documents(tenant_id, status);
CREATE INDEX idx_documents_classification ON documents(tenant_id, classification);
CREATE INDEX idx_documents_department ON documents(tenant_id, department);
CREATE INDEX idx_documents_region ON documents(tenant_id, region);
CREATE INDEX idx_documents_checksum ON documents(checksum);
CREATE INDEX idx_documents_current_version ON documents(tenant_id, is_current_version) WHERE is_current_version = true;
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);
CREATE INDEX idx_documents_title_trgm ON documents USING GIN(title gin_trgm_ops);
CREATE INDEX idx_documents_created_at ON documents(tenant_id, created_at DESC);

-- Row-Level Security
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_isolation ON documents
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- DOCUMENT CHUNKS TABLE
-- ============================================================================

CREATE TABLE document_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    
    -- Chunk content
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    
    -- Position in document
    page_start INTEGER,
    page_end INTEGER,
    section_title VARCHAR(500),
    heading_path TEXT[] DEFAULT ARRAY[]::TEXT[],
    
    -- Chunk type
    chunk_type VARCHAR(50) DEFAULT 'paragraph',
    
    -- Inherited from document
    classification document_classification NOT NULL,
    department VARCHAR(100),
    region VARCHAR(100),
    language VARCHAR(10) DEFAULT 'en',
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::JSONB,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chunk_document_index_unique UNIQUE (document_id, chunk_index),
    CONSTRAINT chunk_token_count_positive CHECK (token_count > 0),
    CONSTRAINT chunk_page_order CHECK (page_start IS NULL OR page_end IS NULL OR page_start <= page_end)
);

-- Indexes
CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_tenant ON document_chunks(tenant_id);
CREATE INDEX idx_chunks_classification ON document_chunks(tenant_id, classification);
CREATE INDEX idx_chunks_department ON document_chunks(tenant_id, department);
CREATE INDEX idx_chunks_checksum ON document_chunks(checksum);
CREATE INDEX idx_chunks_text_trgm ON document_chunks USING GIN(chunk_text gin_trgm_ops);
CREATE INDEX idx_chunks_metadata ON document_chunks USING GIN(metadata);

-- Row-Level Security
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY chunks_tenant_isolation ON document_chunks
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- ACCESS POLICIES TABLE
-- ============================================================================

CREATE TABLE access_policies (
    policy_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    
    -- Policy details
    policy_name VARCHAR(255) NOT NULL,
    policy_description TEXT,
    priority INTEGER DEFAULT 100,
    
    -- Target resources
    document_id UUID REFERENCES documents(document_id) ON DELETE CASCADE,
    classification document_classification,
    department VARCHAR(100),
    region VARCHAR(100),
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    
    -- Access rules
    allowed_users UUID[] DEFAULT ARRAY[]::UUID[],
    denied_users UUID[] DEFAULT ARRAY[]::UUID[],
    allowed_groups TEXT[] DEFAULT ARRAY[]::TEXT[],
    denied_groups TEXT[] DEFAULT ARRAY[]::TEXT[],
    allowed_departments TEXT[] DEFAULT ARRAY[]::TEXT[],
    denied_departments TEXT[] DEFAULT ARRAY[]::TEXT[],
    allowed_roles user_role[] DEFAULT ARRAY[]::user_role[],
    denied_roles user_role[] DEFAULT ARRAY[]::user_role[],
    allowed_regions TEXT[] DEFAULT ARRAY[]::TEXT[],
    denied_regions TEXT[] DEFAULT ARRAY[]::TEXT[],
    
    -- Default decision
    default_decision access_decision DEFAULT 'DENY',
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Effective period
    effective_from TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    effective_until TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(user_id),
    updated_by UUID REFERENCES users(user_id),
    
    -- Constraints
    CONSTRAINT policy_tenant_name_unique UNIQUE (tenant_id, policy_name),
    CONSTRAINT policy_priority_positive CHECK (priority > 0)
);

-- Indexes
CREATE INDEX idx_policies_tenant ON access_policies(tenant_id);
CREATE INDEX idx_policies_document ON access_policies(document_id);
CREATE INDEX idx_policies_classification ON access_policies(tenant_id, classification);
CREATE INDEX idx_policies_department ON access_policies(tenant_id, department);
CREATE INDEX idx_policies_priority ON access_policies(tenant_id, priority DESC);
CREATE INDEX idx_policies_active ON access_policies(tenant_id, is_active) WHERE is_active = true;
CREATE INDEX idx_policies_effective ON access_policies(effective_from, effective_until);

-- Row-Level Security
ALTER TABLE access_policies ENABLE ROW LEVEL SECURITY;

CREATE POLICY policies_tenant_isolation ON access_policies
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- INGESTION JOBS TABLE
-- ============================================================================

CREATE TABLE ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    source_id UUID REFERENCES document_sources(source_id) ON DELETE SET NULL,
    
    -- Job details
    job_type VARCHAR(50) DEFAULT 'FULL_SYNC',
    status ingestion_job_status DEFAULT 'PENDING',
    
    -- Progress
    total_documents INTEGER DEFAULT 0,
    processed_documents INTEGER DEFAULT 0,
    failed_documents INTEGER DEFAULT 0,
    
    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    
    -- Error handling
    error_message TEXT,
    error_details JSONB,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(user_id)
);

-- Indexes
CREATE INDEX idx_jobs_tenant ON ingestion_jobs(tenant_id);
CREATE INDEX idx_jobs_source ON ingestion_jobs(source_id);
CREATE INDEX idx_jobs_status ON ingestion_jobs(tenant_id, status);
CREATE INDEX idx_jobs_created_at ON ingestion_jobs(tenant_id, created_at DESC);

-- Row-Level Security
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY jobs_tenant_isolation ON ingestion_jobs
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- AUDIT LOGS TABLE (Partitioned by month)
-- ============================================================================

CREATE TABLE audit_logs (
    log_id UUID DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    
    -- Event details
    event_type VARCHAR(100) NOT NULL,
    event_category VARCHAR(50) NOT NULL,
    
    -- User context
    user_id UUID REFERENCES users(user_id),
    user_email VARCHAR(255),
    user_role user_role,
    
    -- Resource
    resource_type VARCHAR(100),
    resource_id UUID,
    
    -- Action
    action VARCHAR(100) NOT NULL,
    result VARCHAR(50) NOT NULL,
    
    -- Details
    details JSONB DEFAULT '{}'::JSONB,
    
    -- Network
    ip_address INET,
    user_agent TEXT,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    PRIMARY KEY (tenant_id, created_at, log_id)
) PARTITION BY RANGE (created_at);

-- Create initial partitions (current month + next 3 months)
CREATE TABLE audit_logs_2026_05 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE audit_logs_2026_06 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE audit_logs_2026_07 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE audit_logs_2026_08 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

-- Indexes on partitioned table
CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(tenant_id, event_type, created_at DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(tenant_id, resource_type, resource_id);

-- Row-Level Security
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_logs_tenant_isolation ON audit_logs
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.current_tenant_id', true), '')::UUID,
            tenant_id
        )
    );

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to all relevant tables
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sources_updated_at BEFORE UPDATE ON document_sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chunks_updated_at BEFORE UPDATE ON document_chunks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_policies_updated_at BEFORE UPDATE ON access_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON ingestion_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Create default tenant for development
INSERT INTO tenants (tenant_id, tenant_name, tenant_slug, default_language, timezone)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Default Tenant',
    'default',
    'en',
    'UTC'
) ON CONFLICT DO NOTHING;

-- Create system admin user
INSERT INTO users (
    user_id,
    tenant_id,
    email,
    username,
    full_name,
    role,
    clearance_level,
    is_active,
    is_verified
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'admin@enterprise-rag.local',
    'admin',
    'System Administrator',
    'SUPER_ADMIN',
    'EXECUTIVE_ONLY',
    true,
    true
) ON CONFLICT DO NOTHING;

-- ============================================================================
-- GRANTS
-- ============================================================================

-- Grant necessary permissions to application user
-- Note: In production, create a dedicated application user with limited privileges
GRANT USAGE ON SCHEMA public TO PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO PUBLIC;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO PUBLIC;

-- ============================================================================
-- COMPLETION
-- ============================================================================

-- Log initialization completion
DO $$
BEGIN
    RAISE NOTICE 'Enterprise RAG database initialization completed successfully';
    RAISE NOTICE 'Database version: PostgreSQL %', version();
    RAISE NOTICE 'Row-Level Security: ENABLED on all tenant-scoped tables';
    RAISE NOTICE 'Default tenant created: default (00000000-0000-0000-0000-000000000001)';
    RAISE NOTICE 'System admin created: admin@enterprise-rag.local';
END $$;

-- Made with Bob
