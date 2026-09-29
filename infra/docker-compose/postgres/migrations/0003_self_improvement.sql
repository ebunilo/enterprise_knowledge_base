-- 0003: Storage for the self-improvement loop (see SELF_IMPROVEMENT.md)
--
--   tuning_parameters   current value of each tunable parameter
--                       (tenant_id NULL = global default)
--   tuning_experiments  A/B or bandit experiments over one parameter
--   tuning_change_log   append-only history of every parameter change
--   evaluation_cases    golden queries, incl. security "must not retrieve" sets
--   evaluation_runs     offline evaluation results that gate promotions
--
-- Security-critical behaviour (ACL, citation enforcement, tenant isolation) is
-- deliberately NOT stored here; it is not tunable.

CREATE TABLE IF NOT EXISTS tuning_parameters (
    param_key VARCHAR(120) NOT NULL,
    tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    value JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_by VARCHAR(255) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tuning_parameters_key_tenant_unique UNIQUE NULLS NOT DISTINCT (param_key, tenant_id)
);

CREATE TABLE IF NOT EXISTS tuning_experiments (
    experiment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    param_key VARCHAR(120) NOT NULL,
    -- [{"arm_id": "control", "value": 30}, {"arm_id": "candidate_1", "value": 40}]
    arms JSONB NOT NULL,
    control_arm_id VARCHAR(50) NOT NULL DEFAULT 'control',
    allocation VARCHAR(20) NOT NULL DEFAULT 'thompson'
        CHECK (allocation IN ('thompson', 'fixed_split')),
    traffic_fraction NUMERIC(4, 3) NOT NULL DEFAULT 0.100
        CHECK (traffic_fraction > 0 AND traffic_fraction <= 0.5),
    -- Beta posterior per arm: {"control": {"alpha": 1, "beta": 1, "n": 0}}
    arm_stats JSONB NOT NULL DEFAULT '{}'::JSONB,
    min_samples_per_arm INTEGER NOT NULL DEFAULT 200,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'RUNNING', 'PROMOTED', 'ROLLED_BACK', 'ABORTED')),
    decision JSONB,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE
);

-- At most one running experiment per parameter per scope, so outcomes can be
-- attributed to a single change.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tuning_one_running_experiment
    ON tuning_experiments (param_key, COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::UUID))
    WHERE status = 'RUNNING';

CREATE TABLE IF NOT EXISTS tuning_change_log (
    change_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    param_key VARCHAR(120) NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    change_source VARCHAR(30) NOT NULL
        CHECK (change_source IN ('manual', 'experiment_promotion', 'auto_rollback', 'seed')),
    experiment_id UUID REFERENCES tuning_experiments(experiment_id),
    reason TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    changed_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tuning_change_log_param
    ON tuning_change_log (param_key, created_at DESC);

-- The change log is evidence for auditors: the app may append but never edit.
REVOKE UPDATE, DELETE ON tuning_change_log FROM rag_app;

CREATE TABLE IF NOT EXISTS evaluation_cases (
    case_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    query_language VARCHAR(10) NOT NULL DEFAULT 'en',
    -- Claims to evaluate as, so ACL behaviour is part of every evaluation.
    user_claims JSONB NOT NULL,
    expected_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    expected_document_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    expected_answer_points TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Security cases: any of these in the context is a leak and fails the run.
    must_not_retrieve_chunk_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    expect_insufficient_context BOOLEAN NOT NULL DEFAULT false,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    origin VARCHAR(30) NOT NULL DEFAULT 'curated'
        CHECK (origin IN ('curated', 'feedback_mined', 'security_suite')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evaluation_cases_tenant
    ON evaluation_cases (tenant_id) WHERE is_active = true;

CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    experiment_id UUID REFERENCES tuning_experiments(experiment_id),
    parameter_snapshot JSONB NOT NULL,
    case_count INTEGER NOT NULL,
    -- recall_at_k, mrr, ndcg_at_k, leak_count, citation_validity, p95_latency_ms ...
    metrics JSONB NOT NULL,
    passed BOOLEAN NOT NULL,
    failure_reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_tenant_time
    ON evaluation_runs (tenant_id, created_at DESC);

-- Row-Level Security: global rows (tenant_id IS NULL) are readable by every
-- tenant but only writable by the owner/admin role, never by the app role.
ALTER TABLE tuning_parameters ENABLE ROW LEVEL SECURITY;
ALTER TABLE tuning_experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE tuning_change_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_runs ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['tuning_parameters', 'tuning_experiments', 'tuning_change_log'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_read', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_write', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR SELECT USING (tenant_id IS NULL OR tenant_id = current_tenant_id())',
            t || '_read', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I FOR ALL USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())',
            t || '_write', t);
    END LOOP;

    FOREACH t IN ARRAY ARRAY['evaluation_cases', 'evaluation_runs'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_tenant_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())',
            t || '_tenant_isolation', t);
    END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON tuning_parameters, tuning_experiments,
    evaluation_cases, evaluation_runs TO rag_app;
GRANT SELECT, INSERT ON tuning_change_log TO rag_app;
