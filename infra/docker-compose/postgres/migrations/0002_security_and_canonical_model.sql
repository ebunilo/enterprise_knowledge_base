-- 0002: Security hardening and completion of the canonical data model
--
-- * Row-Level Security now FAILS CLOSED. The original policies used
--   COALESCE(current_setting(...), tenant_id), which matched every row when the
--   tenant context was not set.
-- * Adds a non-superuser application role (rag_app). Superusers and table
--   owners bypass RLS, so services must connect as rag_app for RLS to apply.
-- * Revokes the blanket GRANT ... TO PUBLIC from the baseline script.
-- * Keeps audit_logs writable after the last pre-created partition
--   (2026-08) via a DEFAULT partition and ensure_audit_partitions().
-- * Adds tables required by AGENTS.md 5.1 that were missing:
--   document_versions (view), retrieval_audit_logs, user_feedback.

-- ============================================================================
-- APPLICATION ROLE
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_app') THEN
        CREATE ROLE rag_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END $$;

REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO rag_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rag_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO rag_app;

-- Tenants are resolved (slug -> id) before a tenant context exists; the app
-- only needs to read them.
REVOKE INSERT, UPDATE, DELETE ON tenants FROM rag_app;

-- ============================================================================
-- FAIL-CLOSED ROW-LEVEL SECURITY
-- ============================================================================

CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS UUID
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::UUID
$$;

DROP POLICY IF EXISTS users_tenant_isolation ON users;
DROP POLICY IF EXISTS sources_tenant_isolation ON document_sources;
DROP POLICY IF EXISTS documents_tenant_isolation ON documents;
DROP POLICY IF EXISTS chunks_tenant_isolation ON document_chunks;
DROP POLICY IF EXISTS policies_tenant_isolation ON access_policies;
DROP POLICY IF EXISTS jobs_tenant_isolation ON ingestion_jobs;
DROP POLICY IF EXISTS audit_logs_tenant_isolation ON audit_logs;

CREATE POLICY users_tenant_isolation ON users
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY sources_tenant_isolation ON document_sources
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY documents_tenant_isolation ON documents
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY chunks_tenant_isolation ON document_chunks
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY policies_tenant_isolation ON access_policies
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY jobs_tenant_isolation ON ingestion_jobs
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
CREATE POLICY audit_logs_tenant_isolation ON audit_logs
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());

-- ============================================================================
-- AUDIT LOG PARTITIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs_default PARTITION OF audit_logs DEFAULT;

-- Creates monthly partitions from the current month up to `months_ahead`
-- months in the future. SECURITY DEFINER so the app role can call it at
-- startup without owning the table.
CREATE OR REPLACE FUNCTION ensure_audit_partitions(months_ahead INTEGER DEFAULT 3)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    -- Bounds are pinned to UTC to line up with the baseline partitions, which
    -- were created with `SET timezone = 'UTC'`.
    month_start DATE := date_trunc('month', now() AT TIME ZONE 'UTC')::DATE;
    part_start DATE;
    part_name TEXT;
    created INTEGER := 0;
BEGIN
    FOR i IN 0..months_ahead LOOP
        part_start := (month_start + make_interval(months => i))::DATE;
        part_name := format('audit_logs_%s', to_char(part_start, 'YYYY_MM'));
        IF to_regclass(part_name) IS NULL THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF audit_logs FOR VALUES FROM (%L) TO (%L)',
                    part_name,
                    part_start::TEXT || ' 00:00:00+00',
                    (part_start + INTERVAL '1 month')::DATE::TEXT || ' 00:00:00+00'
                );
                created := created + 1;
            EXCEPTION WHEN others THEN
                -- Rows for this month already landed in the default partition;
                -- leave them there rather than failing the caller.
                RAISE WARNING 'could not create %: %', part_name, SQLERRM;
            END;
        END IF;
    END LOOP;
    RETURN created;
END $$;

REVOKE ALL ON FUNCTION ensure_audit_partitions(INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ensure_audit_partitions(INTEGER) TO rag_app;

-- ============================================================================
-- ACCESS POLICIES: roles and users as free text
-- ============================================================================
-- allowed_roles/denied_roles were typed user_role[] (the six platform admin
-- roles), which cannot express business roles such as `finance_manager`
-- coming from Keycloak. allowed_users/denied_users were UUID[], but Keycloak
-- subjects of federated users are not UUIDs. Values are matched
-- case-insensitively by auth-acl-agent.

ALTER TABLE access_policies
    ALTER COLUMN allowed_roles DROP DEFAULT,
    ALTER COLUMN allowed_roles TYPE TEXT[] USING allowed_roles::TEXT[],
    ALTER COLUMN allowed_roles SET DEFAULT ARRAY[]::TEXT[],
    ALTER COLUMN denied_roles DROP DEFAULT,
    ALTER COLUMN denied_roles TYPE TEXT[] USING denied_roles::TEXT[],
    ALTER COLUMN denied_roles SET DEFAULT ARRAY[]::TEXT[],
    ALTER COLUMN allowed_users DROP DEFAULT,
    ALTER COLUMN allowed_users TYPE TEXT[] USING allowed_users::TEXT[],
    ALTER COLUMN allowed_users SET DEFAULT ARRAY[]::TEXT[],
    ALTER COLUMN denied_users DROP DEFAULT,
    ALTER COLUMN denied_users TYPE TEXT[] USING denied_users::TEXT[],
    ALTER COLUMN denied_users SET DEFAULT ARRAY[]::TEXT[];

-- ============================================================================
-- DOCUMENTS: source type + one current version per logical document
-- ============================================================================

ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type document_source_type;

-- A logical document is (tenant_id, source_uri); each version is its own row
-- and chunks attach to the version row, so chunks never cross versions.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_one_current_version
    ON documents (tenant_id, source_uri)
    WHERE is_current_version = true AND status <> 'DELETED';

CREATE INDEX IF NOT EXISTS idx_documents_source_uri ON documents (tenant_id, source_uri);

-- Version history as a view over documents so there is a single source of
-- truth. security_invoker makes RLS on documents apply to view readers.
CREATE OR REPLACE VIEW document_versions WITH (security_invoker = true) AS
SELECT
    d.document_id AS document_version_id,
    d.document_id,
    d.tenant_id,
    d.source_uri,
    d.version,
    d.version_number,
    d.parent_document_id,
    d.checksum,
    d.is_current_version AS is_current,
    d.status,
    d.effective_date,
    d.created_at
FROM documents d;

GRANT SELECT ON document_versions TO rag_app;

-- ============================================================================
-- RETRIEVAL AUDIT LOGS (AGENTS.md 5.16 / 14.5)
-- ============================================================================

CREATE TABLE IF NOT EXISTS retrieval_audit_logs (
    audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,              -- OIDC subject

    -- Query (full text is optional; hash always stored)
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT,
    query_language VARCHAR(10),
    query_intent VARCHAR(50),

    -- Retrieval path
    retrieved_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    authorized_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    denied_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    denied_reasons JSONB NOT NULL DEFAULT '{}'::JSONB,
    context_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    cited_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    retrieval_sources JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Generation
    model_used VARCHAR(100),
    provider VARCHAR(100),
    processing_region VARCHAR(50),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    answer_hash VARCHAR(64),
    insufficient_context BOOLEAN,
    citation_validation_passed BOOLEAN,

    -- Performance
    latency_ms INTEGER,
    stage_latency_ms JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Self-improvement attribution: which parameter values / experiment arms
    -- produced this answer (see migration 0003).
    parameter_snapshot JSONB NOT NULL DEFAULT '{}'::JSONB,
    experiment_assignments JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_retrieval_audit_tenant_time
    ON retrieval_audit_logs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retrieval_audit_user
    ON retrieval_audit_logs (tenant_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retrieval_audit_experiments
    ON retrieval_audit_logs USING GIN (experiment_assignments);

ALTER TABLE retrieval_audit_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS retrieval_audit_tenant_isolation ON retrieval_audit_logs;
CREATE POLICY retrieval_audit_tenant_isolation ON retrieval_audit_logs
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());

-- ============================================================================
-- USER FEEDBACK (explicit quality signal for self-improvement)
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_feedback (
    feedback_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    audit_id UUID NOT NULL REFERENCES retrieval_audit_logs(audit_id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,

    rating SMALLINT CHECK (rating BETWEEN 1 AND 5),
    thumbs SMALLINT CHECK (thumbs IN (-1, 1)),
    -- e.g. wrong_answer, incomplete, outdated_source, not_relevant,
    --      bad_citation, missing_source, too_slow
    reason_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    helpful_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    unhelpful_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    comment TEXT,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT feedback_has_signal CHECK (
        rating IS NOT NULL OR thumbs IS NOT NULL OR cardinality(reason_codes) > 0
    ),
    CONSTRAINT feedback_one_per_user_answer UNIQUE (audit_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_tenant_time ON user_feedback (tenant_id, created_at DESC);

ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS feedback_tenant_isolation ON user_feedback;
CREATE POLICY feedback_tenant_isolation ON user_feedback
    USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());

-- Tables above were created after the GRANT ... ON ALL TABLES; default
-- privileges cover them, but be explicit for upgraded databases.
GRANT SELECT, INSERT, UPDATE, DELETE ON retrieval_audit_logs, user_feedback TO rag_app;
