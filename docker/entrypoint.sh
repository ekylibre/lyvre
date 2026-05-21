#!/usr/bin/env bash
# Bootstrap a fresh or existing instance, then exec the CMD (gunicorn).
# All steps are idempotent — safe to run on every container start.

set -euo pipefail

cd /app

echo "[entrypoint] Applying database migrations…"
flask db upgrade

echo "[entrypoint] Seeding accounts (idempotent)…"
# seed_accounts.py iterates with INSERT-if-absent; failure is non-fatal once
# the chart of accounts already exists (e.g. mid-migration).
python seed_accounts.py || echo "[entrypoint] seed_accounts.py reported issues — continuing."

echo "[entrypoint] Seeding meta DB (idempotent)…"
python seed_meta.py

echo "[entrypoint] Seeding rules (idempotent)…"
python seed_rules.py

echo "[entrypoint] Starting: $*"
exec "$@"
