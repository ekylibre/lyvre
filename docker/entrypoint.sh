#!/usr/bin/env bash
# Bootstrap a fresh or existing instance, then exec the CMD (gunicorn).
# All steps are idempotent — safe to run on every container start.

set -euo pipefail

cd /app

# Démarré en root (image standard) : /app/instance est rendu à appuser — le dossier monté est créé
# en root par Dokploy / Docker au premier déploiement — puis le script se relance sans privilèges.
# Rien d'autre ne tourne en root.
if [ "$(id -u)" = "0" ]; then
  owner="$(id -u appuser):$(id -g appuser)"
  if [ "$(stat -c '%u:%g' /app/instance)" != "$owner" ] || [ -n "$(find /app/instance ! -user appuser -print -quit)" ]; then
    echo "[entrypoint] /app/instance rendu à appuser (${owner})…"
    chown -R appuser:appgrp /app/instance
  fi
  exec setpriv --reuid=appuser --regid=appgrp --init-groups "$0" "$@"
fi

echo "[entrypoint] Applying database migrations…"
flask db upgrade

echo "[entrypoint] Seeding accounts (idempotent)…"
# No argument: seed_accounts.py completes the chart already in the database
# (asso or sci); an empty database gets DEFAULT_INSTANCE_CHART (default asso).
# Failure is non-fatal once the chart of accounts already exists.
python seed_accounts.py || echo "[entrypoint] seed_accounts.py reported issues — continuing."

echo "[entrypoint] Seeding meta DB (idempotent)…"
python seed_meta.py

# `flask db upgrade` ci-dessus ne migre que la base par défaut : chaque autre instance déclarée
# dans la base méta est migrée ici (un échec est signalé sans bloquer le démarrage).
echo "[entrypoint] Applying migrations to every instance database…"
python scripts/migrate_instances.py

echo "[entrypoint] Seeding rules (idempotent)…"
python seed_rules.py

echo "[entrypoint] Starting: $*"
exec "$@"
