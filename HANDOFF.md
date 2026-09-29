# Handoff: Milestone 1 Hardening, Self-Improvement, Keycloak Realm

**Last updated:** 2026-09-29
**Branch:** `refactor/milestone1-hardening-self-improvement`
**PR:** https://github.com/ebunilo/enterprise_knowledge_base/pull/1 (open, CI green, not merged)
**Spec:** `AGENTS.md` (system design). Self-improvement design: `SELF_IMPROVEMENT.md`.

> Merging to `main` deploys to production (144.91.105.160). Finish the "Before merging" items below first.

---

## 1. Where things stand

| Area | State |
|---|---|
| canonical-db-agent | Rewritten against the real schema; 25 integration tests passing |
| auth-acl-agent | Fail-closed ACL engine + Keycloak normalisation; 45 tests passing |
| packages/adaptive-tuning | Self-improvement library; 20 tests passing |
| DB migrations | 0002, 0003, 0004 + runner; applied in CI and verified idempotent |
| CI (`.github/workflows/deploy-phase1.yml`) | `Tests` + `Build and Smoke Test` green on the PR |
| Keycloak realm `enterprise-rag` | Script written and tested against a mock. **Not run yet** (needs admin password) |
| Production | Still running the old code (v0.1.0) until the PR is merged |

Commits on the branch:
1. `9b31c56` Harden Milestone 1 services and add self-improvement foundation
2. `1e8906f` Replace removed minio/minio image for fresh installs; keep cached image on servers
3. `cb580d4` Add enterprise-rag Keycloak realm setup and global-company tenant

---

## 2. Problems found in the original code (all fixed on the branch)

**Security**
- `auth-acl-agent` `filter_authorized_chunks` / `batch_check_access` authorized every chunk not found in the Redis cache. The mandatory ACL boundary was a no-op.
- `/acl/authorize` hard-coded `INTERNAL_GENERAL` / `active` and never looked up the document.
- The RLS policies used `COALESCE(current_setting(...), tenant_id)`, so every row matched whenever no tenant was set. On top of that, the services connect as the superuser `rag_admin`, and superusers bypass RLS entirely.
- `GRANT ... ON ALL TABLES ... TO PUBLIC` in the init script.
- canonical-db API had no authentication and was publicly routed via nginx (`/api/canonical-db/`, `api.igwilo.com/canonical-db/`).
- Any user could invalidate any user's or document's ACL cache.
- Postgres, Redis and MinIO ports were published on `0.0.0.0` (Docker bypasses ufw).
- `infra/docker-compose/secrets/production_secrets_20260528_114327.txt` was committed. It is now untracked, **but still in git history**.
- canonical-db logged `REDIS_URL` including the password at startup.
- python-jose 3.3.0 (CVE-2024-33663, CVE-2024-33664).

**Correctness**
- canonical-db ORM models didn't match the SQL. They used `Tenant.name/status`, `documents.source_type`, lowercase statuses, string tenant IDs, and tables that didn't exist (`document_versions`, `retrieval_audit_logs`, `user_feedback`). Inserts would fail.
- `SET LOCAL app.current_tenant_id` was lost after every `commit()`.
- `access_policies.allowed_roles` was typed `user_role[]` (6 admin roles), which can't hold Keycloak roles like `finance_manager`. `allowed_users` was `UUID[]`, but federated Keycloak subjects aren't UUIDs.
- Keycloak mismatches:
  - `tenant_id` arrives as a slug (`global-company`), but the DB uses UUIDs.
  - Clearance arrives in lowercase.
  - Access tokens lack `aud=<client>` unless an Audience mapper is configured.
  - Groups arrive as `/path`.
  - `is_employee` defaulted to `true`.
- `audit_logs` partitions only ran to 2026-08.
- Init scripts only run on an empty volume, so schema changes never reached production.
- Blocking SQLAlchemy calls ran inside `async def` endpoints.
- Compose build contexts only worked in the server layout. Local `docker compose up` was broken.

**CI/CD**
- No tests existed, and none ran.
- `rsync --delete` wiped the `backups/` directory that the backup step had just written.
- A failed production deploy ran `docker compose down`, turning any failure into a full outage.
- The CI `.env` was uploaded as an artifact.
- `minio/minio` has been **removed from Docker Hub**. Any pull fails, and the next production deploy would have failed.

---

## 3. What was built

### Database (`infra/docker-compose/postgres/`)
- `migrations/migrate.sh`: applies `NNNN_*.sql` once each, in a transaction, recorded in `schema_migrations`. It also enables login for `rag_app` when `APP_DB_PASSWORD` is set (with `log_statement` suppressed so the password isn't logged), and calls `ensure_audit_partitions(3)`.
  - Fresh installs run it via `init/02-apply-migrations.sh`.
  - Deploys run `docker compose exec -T postgres bash /migrations/migrate.sh`.
- `0002_security_and_canonical_model.sql`:
  - Fail-closed RLS via `current_tenant_id()`, plus the `rag_app` role; PUBLIC grants revoked.
  - Audit default partition and `ensure_audit_partitions()` (UTC bounds).
  - Role and user columns converted to `TEXT[]`.
  - `documents.source_type`, and a single current version per `(tenant_id, source_uri)`.
  - `document_versions` view (`security_invoker`), `retrieval_audit_logs`, `user_feedback`.
- `0003_self_improvement.sql`: `tuning_parameters`, `tuning_experiments`, `tuning_change_log` (append-only for the app), `evaluation_cases`, `evaluation_runs`. All tenant-scoped with RLS.
- `0004_seed_global_company_tenant.sql`: tenant `global-company`.

### canonical-db-agent (v0.2.0)
- Every `/api/v1` route requires `X-API-Key` (`SERVICE_API_KEYS`, falling back to `SECRET_KEY`).
- `X-Tenant-ID` accepts a UUID or a slug.
- Explicit tenant filters on every query, and tenant context applied per transaction (`after_begin`).
- Versioning: re-posting a `source_uri` creates version N+1 as non-current. `POST /documents/{id}/activate` swaps it in atomically and archives the old version. `GET /documents/{id}/versions` lists them.
- Chunks inherit classification, department, region and language from their document. The checksum is computed server-side, and reclassifying a document propagates to its chunks.
- `POST /chunks/batch`: returns chunks in request order, only from ACTIVE and current versions, with citation metadata.
- New endpoints `POST/GET /retrieval-audit` and `POST /feedback`, which capture the self-improvement signals. They enforce context ⊆ authorized and citations ⊆ context. Feedback can only come from the answer's user.

### auth-acl-agent (v0.2.0)
- `app/acl.py`: a pure `evaluate()` decision function plus PostgreSQL loaders. It fails closed and returns `reason_by_chunk`.
  - Decision order: tenant → status and current version → explicit deny → clearance (CONFIDENTIAL and above) → region → grant.
  - Denials are written to `audit_logs` (`ACL_DECISION`).
  - Decisions are never cached.
- `app/claims.py`: Keycloak normalisation of tenant slug, groups, roles (from `role`, `realm_access` and `resource_access`), clearance and is_employee. It fails closed: an unknown clearance is treated as PUBLIC and the user as a non-employee.
- `app/oidc.py`:
  - Issuer from discovery; accepts `aud` or `azp`.
  - Rejects ID tokens.
  - Refreshes the JWKS when a token has an unknown key ID.
  - Blocks algorithm confusion.
- Tenant always comes from the token, never a header.
- Removed the placeholder `/auth/callback`, `/auth/logout` and `/cache/invalidate/*` endpoints.

### Self-improvement (`packages/adaptive-tuning`, `SELF_IMPROVEMENT.md`)
- `registry.py`: every tunable parameter, with bounds and a safety class.
  - **AUTO:** retrieval top_k, fusion method and weights, rerank weights and top_n, context budget, temperature, cache TTL, query expansion.
  - **REVIEW:** LLM tier, prompt template, chunking (needs re-index), external reranker.
  - **LOCKED:** ACL validation, clearance, archived-in-retrieval, citation required, citation validity = 1.0, documents-untrusted, sensitive answer caching.
- `resolver.py`: default < global < tenant < experiment arm. Returns a snapshot and assignments for the audit log.
- `experiments.py`: deterministic enrollment, Thompson sampling, `propose_arms()`.
- `rewards.py`: reward in [0,1]. A leak or an invalid citation scores 0.
- `guardrails.py`:
  - A leak rolls back every arm.
  - A worse citation-failure rate or a p95 latency regression rolls back that candidate.
  - Otherwise it promotes when P(better) ≥ 0.95 and lift ≥ 1 point. REVIEW parameters go to `AWAIT_REVIEW` instead.
- `evaluation.py`: golden-set metrics (recall@k, MRR, nDCG, leaks, citation validity, abstention, p95) and `compare_to_baseline()`.

### Infra and CI
- Compose:
  - Ports bound to `${BIND_ADDRESS:-127.0.0.1}`.
  - `SERVICES_DIR` for build contexts.
  - Services connect as `rag_app` when `APP_DB_PASSWORD` is set, otherwise as admin.
  - Postgres healthcheck over TCP, to avoid the init race.
  - MinIO image `${MINIO_IMAGE:-cgr.dev/chainguard/minio:latest}` with `pull_policy: missing` and `user: 0:0`. Servers pin `MINIO_IMAGE=minio/minio:latest`, which is cached locally.
- Workflow:
  - `test` job (PostgreSQL service, migrations run twice, 3 test suites) and a compose smoke test (migrations, RLS and 401 checks).
  - Deploy order: backup (`pg_dump -Fc`), rsync (excluding `backups/`, `.env*`, `secrets/`), migrate, build, up.
  - A failed deploy no longer stops the stack.
  - PRs run CI but never deploy.
- nginx: fixed the `minio_console` upstream. The server configs are tracked as `infra/nginx/api.igwilo.com.conf` and `infra/nginx/qdrant.igwilo.com.conf`. Qdrant enforces an API key (verified: 401 without one).
- `.env.example` documents `APP_DB_*`, `BIND_ADDRESS`, `SERVICE_API_KEYS`, `OIDC_AUDIENCES`, `EXTERNAL_GROUPS`, `ENFORCE_CLEARANCE`, and the realm-URL format.

### Keycloak (`infra/keycloak/setup_realm.py`)
An idempotent admin REST script, stdlib only, that prompts for the password. It creates:
- **Realm `enterprise-rag`:**
  - `sslRequired=external`, brute-force protection on, registration off.
  - Access token lifetime 15 min.
- **Clients:**
  - `enterprise-rag-web`: public, PKCE S256, redirect `https://rag.igwilo.com/*`, with an audience mapper adding `enterprise-rag-api`.
  - `enterprise-rag-api`: confidential; the backend's `OIDC_CLIENT_ID`.
- **Client scope `enterprise-rag-claims`:**
  - Hard-coded claim `tenant_id=global-company`.
  - `groups` mapper using full group paths.
  - Attribute mappers for department, role, region, country, clearance, is_employee.
- **Groups:** internal-users, external-users, finance, hr, engineering, legal, security.
- **User profile attributes:** admin-editable only.
- **Options:** `--set-github-secrets` writes `PRODUCTION_OIDC_PROVIDER_URL`, `_CLIENT_ID` and `_CLIENT_SECRET` via `gh` (the secret is never printed). `--dry-run` makes no changes.

Verified facts, 2026-09-29:
- `https://auth.igwilo.com/.well-known/openid-configuration` returns 404.
- `/realms/master` returns 200.
- `/realms/enterprise-rag` returns 404 (not created yet).
- Production auth-acl `/health` reports `oidc: ok`, so the current secret probably points at `/realms/master`.

---

## 4. To-do

### Before merging PR #1 (user actions)
- [ ] **Rotate every credential** that was in `production_secrets_20260528_114327.txt` (it's still in git history). Consider purging the history.
- [ ] **Revert `infra/docker-compose/.env.example` line `APP_DB_PASSWORD=`** to the placeholder. A real-looking value was typed there (uncommitted). If it equals `PRODUCTION_APP_DB_PASSWORD`, set a new secret value.
- [x] `PRODUCTION_APP_DB_PASSWORD` set by the user.
- [ ] Run the realm setup in your own terminal (it prompts for the Keycloak admin password):
  ```bash
  python3 infra/keycloak/setup_realm.py --url https://auth.igwilo.com --admin-user <admin> \
      --origin https://rag.igwilo.com --dry-run          # preview
  python3 infra/keycloak/setup_realm.py --url https://auth.igwilo.com --admin-user <admin> \
      --origin https://rag.igwilo.com --set-github-secrets
  ```
- [ ] Check with `curl https://auth.igwilo.com/realms/enterprise-rag/.well-known/openid-configuration` (expect 200).
- [ ] Create users in the **enterprise-rag** realm (not master): assign groups and set attributes (`department`, `role`, `region`, `country`, `clearance` = public|internal_general|department_restricted|confidential|regulated|executive_only, `is_employee`).
- [ ] Ensure `PRODUCTION_ALLOWED_ORIGINS` includes `https://rag.igwilo.com`.
- [ ] Optional secrets:
  - `PRODUCTION_SERVICE_API_KEYS` (dedicated canonical-db key; otherwise it falls back to SECRET_KEY)
  - `PRODUCTION_OIDC_AUDIENCES`
  - `PRODUCTION_MINIO_IMAGE`
- [ ] Merge PR #1. The deploy backs up the DB, runs migrations 0002–0004, and rebuilds.
- [ ] After the deploy:
  - `https://api.igwilo.com/canonical-db/health` and `/auth-acl/health` are healthy.
  - An unauthenticated `GET https://api.igwilo.com/canonical-db/api/v1/documents` returns 401.
  - `docker compose exec postgres psql -U rag_admin -d enterprise_rag -c "select * from schema_migrations"` shows 0002–0004.

### Follow-ups (engineering)
- [ ] Remove the old client in the `master` realm once nothing uses it.
- [ ] Staging: no `STAGING_*` secrets exist. Add them before using `develop`. Set `STAGING_MINIO_IMAGE` (e.g. `cgr.dev/chainguard/minio:latest`) on fresh servers.
- [ ] Choose a long-term maintained object store (MinIO community images are discontinued).
- [ ] `.gitignore` ignores itself and `docs/`, so the new ignore rules (secrets/, backups/, Python caches) exist only locally. Decide whether to track `.gitignore` and `docs/`.
- [ ] Health endpoints still report version `"0.1.0"` (hard-coded in `routers/health.py`). Use `app.__version__`.
- [ ] `infra/nginx/nginx.conf` (older, includes `storage.igwilo.com`) versus the tracked server configs: keep one source of truth.
- [ ] Right-to-deletion (AGENTS.md §14.5): deletion is soft only. Add purge and propagation once Qdrant, BM25 and the KG exist.
- [ ] `retrieval_audit_logs` isn't partitioned. Add partitioning or retention before volume grows.
- [ ] Bump GitHub Actions versions (Node 20 deprecation warnings on checkout@v4 and setup-python@v5).

### Next milestones (AGENTS.md §12)
- [ ] **Milestone 2:** document-ingestion, document-parser and chunking agents (use `chunking.*` defaults from the registry: 512/768/64).
- [ ] **Milestone 3:** embedding-agent + Qdrant. Collection per tenant: `enterprise_chunks_{tenant_id}_{model_version}`. The payload must use the values `build_retrieval_filter()` expects:
  - uppercase `classification` and `status`, plus `is_current_version`
  - lowercase `department`, `allowed_departments`, `allowed_groups`, `allowed_roles`, `allowed_users`, `denied_users`
- [ ] **Milestones 4–5:** BM25 (OpenSearch), knowledge graph.
- [ ] **Milestones 6–7:** query-understanding, hybrid retrieval, reranker, context builder, LLM answer, citation agent, plus the orchestrator. The orchestrator must:
  - call auth-acl `/api/v1/acl/filter` with the user's bearer token on every candidate set
  - call `adaptive_tuning.resolve()` and write `parameter_snapshot` and `experiment_assignments` to `/api/v1/retrieval-audit`
- [ ] **Milestone 8:**
  - hourly reward/decide job (`compute_reward` → `ArmStats.update` → `decide`), plus an offline golden-set gate (`evaluate` / `compare_to_baseline`)
  - admin approval UI for REVIEW parameters
  - feedback-mined evaluation cases
  - "unanswered questions" view

---

## 5. Working on this locally

```bash
# Throwaway PostgreSQL 15 (Postgres.app); use TCP, the scratch socket path is too long
initdb -D /tmp/pg -U rag_admin --auth=trust
pg_ctl -D /tmp/pg -o "-p 55432 -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" start
export PGHOST=127.0.0.1 PGPORT=55432
createdb -U rag_admin enterprise_rag
psql -U rag_admin -d enterprise_rag -v ON_ERROR_STOP=1 -f infra/docker-compose/postgres/init/01-init-database.sql
POSTGRES_USER=rag_admin POSTGRES_DB=enterprise_rag APP_DB_PASSWORD=apppw \
  bash infra/docker-compose/postgres/migrations/migrate.sh

export TEST_DATABASE_URL=postgresql://rag_app:apppw@127.0.0.1:55432/enterprise_rag
export TEST_ADMIN_DATABASE_URL=postgresql://rag_admin@127.0.0.1:55432/enterprise_rag
# Python 3.11 (e.g. `uv venv -p 3.11`); pin cryptography==44.0.3 (in requirements) on macOS
(cd services/canonical-db-agent && pip install -r requirements-dev.txt && pytest -q)
(cd services/auth-acl-agent && pip install -r requirements-dev.txt && pytest -q)
(cd packages/adaptive-tuning && PYTHONPATH=. pytest -q)
```

Notes:
- Integration tests connect as `rag_app` on purpose, so RLS is exercised.
- The unit tests run without a database; the integration tests are skipped when the env vars are missing.
- `docker compose --env-file .env.example config` validates compose without a Docker daemon.
- The Ansible `inventory` file (untracked) points at the production server; it was never used.
