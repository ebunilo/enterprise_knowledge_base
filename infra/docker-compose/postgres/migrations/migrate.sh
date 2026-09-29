#!/usr/bin/env bash
# Enterprise RAG System - Schema migration runner
#
# docker-entrypoint-initdb.d scripts only run against an EMPTY data volume, so
# schema changes after the first deploy never reach an existing database. This
# runner applies every NNNN_*.sql file in this directory exactly once, each in
# its own transaction, and records it in schema_migrations.
#
# Usage (inside the postgres container):
#   bash /migrations/migrate.sh
# It is also invoked automatically on first boot by init/02-apply-migrations.sh.
#
# Environment:
#   POSTGRES_USER / POSTGRES_DB  - connection (set by the postgres image)
#   APP_DB_PASSWORD              - if set, enables LOGIN for the non-superuser
#                                  application role `rag_app` (RLS applies to it)
#   MIGRATIONS_DIR               - override migration directory

set -euo pipefail

DIR="${MIGRATIONS_DIR:-$(cd "$(dirname "$0")" && pwd)}"
DB="${POSTGRES_DB:-enterprise_rag}"
DB_USER="${POSTGRES_USER:-rag_admin}"
PSQL=(psql -X -q -v ON_ERROR_STOP=1 --username "$DB_USER" --dbname "$DB")
export PGOPTIONS="${PGOPTIONS:-} -c client_min_messages=warning"

"${PSQL[@]}" -c "CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"

shopt -s nullglob
for file in "$DIR"/[0-9][0-9][0-9][0-9]_*.sql; do
    version="$(basename "$file" .sql)"
    applied="$("${PSQL[@]}" -tA -c "SELECT 1 FROM schema_migrations WHERE version = '${version}'")"
    if [ "$applied" = "1" ]; then
        continue
    fi
    echo "[migrate] applying ${version}"
    "${PSQL[@]}" --single-transaction \
        -f "$file" \
        -c "INSERT INTO schema_migrations (version) VALUES ('${version}')"
done

if [ -n "${APP_DB_PASSWORD:-}" ]; then
    echo "[migrate] enabling login for application role rag_app"
    # postgresql.conf has log_statement = 'ddl'; keep the password out of the logs.
    "${PSQL[@]}" -v pw="$APP_DB_PASSWORD" <<'SQL'
SET log_statement = 'none';
ALTER ROLE rag_app WITH LOGIN PASSWORD :'pw';
SQL
fi

"${PSQL[@]}" -tA -c "SELECT ensure_audit_partitions(3)" >/dev/null
echo "[migrate] schema is up to date"
