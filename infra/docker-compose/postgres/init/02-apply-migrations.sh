#!/usr/bin/env bash
# Runs on first boot (empty volume) right after 01-init-database.sql so fresh
# installs end up with the same schema as upgraded ones.
set -euo pipefail
bash /migrations/migrate.sh
