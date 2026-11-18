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

# Démonstration publique (LYVRE_DEMO=1, docker-compose.demo.yml) : données remises à zéro à chaque démarrage. Le
# dossier n'est vidé que s'il est vide ou marqué par une remise à zéro précédente (.lyvre-demo) : un LYVRE_DEMO posé par
# erreur sur une vraie instance arrête le conteneur au lieu d'effacer ses données.
is_demo() { case "${LYVRE_DEMO:-}" in 1|true|yes|on) return 0;; *) return 1;; esac; }
if is_demo && [ "${DEMO_RESET_ON_START:-1}" = "1" ]; then
  if [ -n "$(find /app/instance -mindepth 1 -maxdepth 1 -print -quit)" ] && [ ! -f /app/instance/.lyvre-demo ]; then
    echo "[entrypoint] LYVRE_DEMO=1 sur un dossier d'instance qui n'est pas celui d'une démo : arrêt." >&2
    exit 1
  fi
  echo "[entrypoint] Démonstration : remise à zéro des données…"
  find /app/instance -mindepth 1 -delete
  touch /app/instance/.lyvre-demo
fi
# Administrateur de seed_meta.py en démonstration : mot de passe aléatoire jamais affiché (demo_seed.py le désactive).
if is_demo; then
  ADMIN_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
  export ADMIN_PASSWORD
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

if is_demo; then
  echo "[entrypoint] Démonstration : données fabriquées…"
  python scripts/demo_seed.py || echo "[entrypoint] demo_seed.py reported issues — continuing."
  # Remise à zéro chaque nuit (DEMO_RESET_AT, heure UTC) : arrêt du processus principal, que la politique
  # `restart: unless-stopped` relance ; le démarrage vide alors le dossier et recrée les données.
  (
    at="${DEMO_RESET_AT:-02:00}"
    while true; do
      now=$(date -u +%s); target=$(date -u -d "today ${at}" +%s)
      [ "$target" -gt "$now" ] || target=$(date -u -d "tomorrow ${at}" +%s)
      sleep $((target - now))
      echo "[entrypoint] Démonstration : remise à zéro de la nuit."
      kill -TERM 1
      sleep 120
    done
  ) &
fi

echo "[entrypoint] Starting: $*"
exec "$@"
