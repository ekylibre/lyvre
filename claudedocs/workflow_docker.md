# Workflow — Déploiement Docker (single service)

**Date :** 2026-05-21
**Auteur :** /sc:workflow
**Statut :** Plan d'implémentation — code non écrit, exécution réservée à `/sc:implement`

---

## 1. Contexte et objectifs

Aujourd'hui l'application tourne via `python run.py` (mode debug Flask) sur une machine ayant Python + virtualenv. Objectif : la conteneuriser pour :

- Déploiement reproductible (image identique en dev / staging / prod)
- Pas de dépendance à un Python local ni à `pip install`
- Persistence des données SQLite via un volume sur `instance/`
- **Un seul service** Docker (`web`) — pas de DB séparée, pas de reverse proxy, pas de Redis. La SQLite vit dans le volume monté.

Contraintes :

- L'app utilise SQLite avec un fichier par instance, plus une méta-base. Tout est dans `instance/` → un seul volume suffit.
- Threads daemon pour les syncs Stancer asynchrones → choix d'un worker WSGI multi-thread (pas multi-process).
- `app.run(debug=True)` reste pour le dev local. Docker bascule sur Gunicorn.
- Aucun secret dans l'image — uniquement injecté via `env_file: .env` dans compose.

---

## 2. Architecture du conteneur

```
┌──────────────────────────────────────────────────────┐
│ Image : python:3.12-slim-bookworm                    │
│                                                       │
│ /app                                                  │
│ ├── app/             ← code applicatif (COPY)        │
│ ├── data/            ← seeds JSON + YAML (COPY)      │
│ ├── migrations/      ← Alembic (COPY)                │
│ ├── seed_*.py, run.py, requirements.txt (COPY)       │
│ └── instance/        ← VOLUME → ./instance (hôte)    │
│                         └── meta.db                  │
│                         └── seconde-nature.db        │
│                         └── tenants/                 │
│                         └── backups/                 │
│                                                       │
│ User : appuser (uid 1000, gid 1000) — non-root       │
│ Port : 5000 (Gunicorn)                                │
│ CMD  : entrypoint.sh → gunicorn …                    │
└──────────────────────────────────────────────────────┘
```

### Choix du serveur WSGI

**Gunicorn** avec worker `gthread` :

```
gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:5000 --timeout 120 'app:create_app()'
```

Justifications :

- **1 worker** : SQLite sérialise les écritures via verrouillage de fichier. Plusieurs workers concurrents = `database is locked` sous charge. Pour une asso, 1 worker suffit largement.
- **gthread + 4 threads** : les syncs Stancer asynchrones lancent des `threading.Thread(daemon=True)` qui survivent à la requête HTTP qui les a démarrés. Sync worker bloquerait — gthread les autorise.
- **timeout 120 s** : les syncs Odoo / HelloAsso XML-RPC peuvent prendre du temps.

### Bootstrap au démarrage

L'entrypoint exécute en séquence (tout idempotent) :

1. `flask db upgrade` — applique les migrations sur `instance/seconde-nature.db` (création du fichier + schéma si vierge).
2. `python seed_accounts.py` — charge 783 comptes PCA + 6 journaux si absents.
3. `python seed_meta.py` — crée `instance/meta.db` + 1 user admin + 1 instance par défaut.
4. `python seed_rules.py` — importe les 20 règles depuis `data/rules.yml` si la table est vide.
5. `exec gunicorn …`

Le `exec` final remplace le processus shell par Gunicorn — propre pour la gestion des signaux Docker (SIGTERM gracieux).

---

## 3. Fichiers à créer

### 3.1 `Dockerfile`

```dockerfile
FROM python:3.12-slim-bookworm

# Minimal runtime deps (libsqlite already shipped with Python).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Non-root user matching the typical host UID/GID (overridable at build time).
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} appgrp \
 && useradd -m -u ${APP_UID} -g ${APP_GID} -s /bin/bash appuser

WORKDIR /app

# Cache pip layer: copy only requirements first.
COPY --chown=appuser:appgrp requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.*

# Copy the rest. .dockerignore excludes instance/, .venv/, etc.
COPY --chown=appuser:appgrp . /app

# instance/ lives in the volume — empty placeholder owned by appuser.
RUN mkdir -p /app/instance && chown -R appuser:appgrp /app/instance

USER appuser

ENV PYTHONUNBUFFERED=1 \
    FLASK_APP=run.py \
    FLASK_ENV=production

EXPOSE 5000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "4", \
     "-b", "0.0.0.0:5000", "--timeout", "120", "app:create_app()"]
```

Points d'attention :

- `python:3.12-slim-bookworm` — multi-arch (amd64 + arm64), ~50 Mo de base. Python 3.12 stable, compatible avec toutes les deps (3.13 incertain à cause de pandas, 3.14 inacceptable).
- `gunicorn` ajouté dynamiquement dans le `pip install` — **pas** dans `requirements.txt` (uniquement utile en Docker, le dev local utilise `flask run` ou `python run.py`).
- L'utilisateur non-root `appuser` avec UID/GID 1000 — match avec la plupart des installs Linux mono-user. Reconfigurable via `--build-arg APP_UID=…`.
- `EXPOSE 5000` est informatif uniquement ; le binding effectif est dans compose.

### 3.2 `docker/entrypoint.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /app

echo "[entrypoint] Applying database migrations…"
flask db upgrade

echo "[entrypoint] Seeding accounts (idempotent)…"
python seed_accounts.py || true

echo "[entrypoint] Seeding meta DB (idempotent)…"
python seed_meta.py

echo "[entrypoint] Seeding rules (idempotent)…"
python seed_rules.py

echo "[entrypoint] Starting: $*"
exec "$@"
```

Justifications :

- Le `set -euo pipefail` arrête immédiatement sur erreur (`flask db upgrade` ratée = bug bloquant).
- `seed_accounts.py || true` : ce script peut échouer si déjà lancé sur une DB qui a évolué (les comptes sont déjà là). Le `|| true` rend le script tolérant à un état partiel. Les autres seeds sont strictement idempotents.
- `exec "$@"` : remplace le shell par Gunicorn → signaux Docker (SIGTERM, SIGINT) propagés correctement.

### 3.3 `docker-compose.yml`

```yaml
services:
  web:
    build:
      context: .
      args:
        APP_UID: ${APP_UID:-1000}
        APP_GID: ${APP_GID:-1000}
    image: compta-asso:latest
    container_name: compta-asso
    restart: unless-stopped
    ports:
      - "${APP_PORT:-5000}:5000"
    volumes:
      - ./instance:/app/instance
    env_file:
      - .env
    environment:
      FLASK_ENV: production
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:5000/login"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
```

Points d'attention :

- **Volume bind-mount** `./instance:/app/instance` plutôt qu'un volume nommé : l'admin peut accéder aux fichiers depuis l'hôte (backup, debug). Plus pratique pour cette taille de déploiement.
- `env_file: .env` : injecte SECRET_KEY, ADMIN_EMAIL/PASSWORD, STANCER_*, ODOO_*, HELLOASSO_* — pas dans l'image.
- `${APP_PORT:-5000}` : permet de remapper si 5000 est pris localement (`APP_PORT=8000 docker-compose up`).
- `${APP_UID}` / `${APP_GID}` : par défaut 1000:1000, mais peuvent être surchargés au build pour matcher l'utilisateur hôte (utile sur des serveurs partagés).
- **Healthcheck** sur `/login` (route publique qui renvoie 200 sans auth). `start_period: 30s` couvre le bootstrap initial (migrations + seeds).

### 3.4 `.dockerignore`

```
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.git/
.gitignore
.env
.env.local
instance/
claudedocs/
doc/
tests/
*.md
README.md
LICENSE
Modele-document-Nouveau-Plan-comptable-Bilan-CDR.xls
.claude/
```

Justifications :

- `.env` exclu → secrets jamais copiés dans l'image, uniquement injectés à l'exécution.
- `instance/` exclu → la DB de dev locale ne contamine pas l'image (le volume Docker prend le relais).
- `tests/`, `claudedocs/`, `doc/`, `*.md` exclus → réduit la taille de l'image.
- `.git/` exclu → pas besoin de l'historique dans l'image.

> **NB** : `data/` (gabarits JSON+YAML) **doit** être copié — c'est utilisé au runtime par les seeds.

### 3.5 Mise à jour `requirements.txt`

Aucune. `gunicorn` est ajouté dans le `pip install` du Dockerfile uniquement (dev local n'en a pas besoin, et c'est un détail d'infra qui n'a rien à faire dans les deps applicatives).

> Alternative : ajouter `gunicorn==23.*` à requirements.txt. C'est OK aussi — plus simple, juste une dépendance Python en plus. Je préfère séparer (déploiement ≠ application) mais ça reste un détail de goût.

---

## 4. Migration / mise en route

### Première installation (machine propre)

```bash
git clone <repo>
cd compta-asso
cp .env .env.local  # éditer SECRET_KEY, ADMIN_EMAIL/PASSWORD, etc.
docker-compose up -d --build
docker-compose logs -f web
# → bootstrap visible :
# [entrypoint] Applying database migrations…
# [entrypoint] Seeding accounts (idempotent)…
# [entrypoint] Seeding meta DB (idempotent)…
# [entrypoint] Seeding rules (idempotent)…
# [entrypoint] Starting: gunicorn ...
# [INFO] Booting worker with pid: X
```

Ouvrir `http://localhost:5000` → login avec `ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`.

### Migration depuis une install existante (non-Docker)

```bash
# 1. Sauvegarder la DB actuelle
cp instance/seconde-nature.db instance/seconde-nature.db.bak

# 2. Construire et lancer
docker-compose up -d --build

# Le volume bind-mount partage le dossier instance/ ; l'app dans le conteneur voit
# directement la DB existante. Les seeds idempotents ne touchent à rien.
```

### Mise à jour de l'application

```bash
git pull
docker-compose up -d --build  # rebuild de l'image, restart du conteneur
# Les migrations Alembic s'appliquent automatiquement au démarrage.
```

---

## 5. Phases d'implémentation

### Phase 1 — Dockerfile + entrypoint

**Fichiers à créer :**
- `Dockerfile`
- `docker/entrypoint.sh` (avec `chmod +x`)

**Validation :**
- `docker build -t compta-asso:test .` réussit.
- L'image fait < 400 Mo (pandas pèse lourd, c'est attendu).
- `docker run --rm compta-asso:test python -c "from app import create_app; create_app()"` retourne sans erreur.

### Phase 2 — docker-compose + .dockerignore

**Fichiers à créer :**
- `docker-compose.yml`
- `.dockerignore`

**Validation :**
- `docker-compose config` valide la syntaxe.
- `docker-compose up -d` démarre le conteneur.
- `docker-compose logs web` affiche les étapes de bootstrap.
- `curl http://localhost:5000/login` renvoie 200.
- Le fichier `instance/meta.db` est créé sur l'hôte (preuve que le volume bind fonctionne).
- L'utilisateur peut se loguer avec `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

### Phase 3 — Documentation

**Fichiers à créer :**
- `doc/docker.md` — guide complet : prérequis, premier démarrage, mise à jour, logs, backup du volume, troubleshooting.

**Fichiers à modifier :**
- `doc/installation.md` — section « Déploiement Docker » qui pointe vers `doc/docker.md`.
- `doc/README.md` — ajout entrée « Déploiement Docker ».
- `.env` (le fichier exemple, pas le local) — ajouter commentaire « ces variables sont injectées dans le conteneur via `env_file:` dans docker-compose.yml ».

**Validation :**
- Doc complète et navigable.

---

## 6. Dépendances entre phases

```
Phase 1 (Dockerfile + entrypoint) ──▶ Phase 2 (compose + .dockerignore)
                                              │
                                              ▼
                                         Phase 3 (doc)
```

Phase 1 et 2 sont rapides (< 5 min de code) mais peuvent demander un peu d'itération sur le build (premiers builds Docker = découverte des manques dans `.dockerignore`, permissions, etc.). Phase 3 est de la rédaction pure.

---

## 7. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| **Permissions sur le volume `./instance`** | Si l'UID 1000 du conteneur ne match pas l'utilisateur hôte, l'app ne peut pas écrire dans `./instance`. Documenter : `chown -R 1000:1000 instance/` côté hôte, ou builder avec `--build-arg APP_UID=$(id -u)`. |
| **Concurrence SQLite sous charge** | 1 seul worker Gunicorn. Si trafic réel > 5 req/s soutenu, envisager un déplacement vers Postgres (l'app supporte déjà via `DATABASE_URL`). |
| **Seeds échouent au 1er run sur DB non-vide pré-existante** | `flask db upgrade` est idempotent (no-op si à jour). `seed_meta.py` et `seed_rules.py` aussi. `seed_accounts.py` également (skip si compte déjà présent). Pas de risque. |
| **`.env` absent en production** | `docker-compose up` échoue clairement avec « env_file not found ». À documenter. |
| **SECRET_KEY par défaut en prod** | Risque sécurité (sessions devinables). Documenter dans `doc/docker.md` qu'il **doit** être changé pour une valeur aléatoire forte. Idéalement, ajouter un check au démarrage qui refuse de booter si `SECRET_KEY == "dev-secret-key"` et `FLASK_ENV == "production"`. À discuter — peut-être hors périmètre. |
| **Threads Stancer asynchrones survivent au SIGTERM** | Lors d'un `docker-compose down`, Gunicorn reçoit SIGTERM, ferme les requêtes en cours. Les threads daemon sont killés brutalement. Acceptable — les `SyncJob` restent en état `running` mais l'idempotence du modèle fait que le prochain démarrage propose de relancer. Documenter. |
| **Image trop grosse à cause de pandas** | Pandas + numpy = ~250 Mo. C'est inévitable. L'utilisateur Mac sur lien lent peut souffrir au premier `docker pull` / `build`. Acceptable. |
| **Healthcheck pendant le bootstrap** | `start_period: 30s` couvre les migrations + seeds. Si le bootstrap prend plus de 30s (très gros DB pré-existante avec beaucoup de migrations), allonger. À documenter. |
| **Logs ne sortent pas du conteneur** | Gunicorn par défaut log sur stdout/stderr → capturé par Docker → `docker-compose logs web`. OK par construction. Mais : la sortie `print()` de l'app doit aussi sortir → `PYTHONUNBUFFERED=1` dans le Dockerfile la garantit. |

---

## 8. Hors-périmètre (v1)

- **Reverse proxy nginx/Caddy** devant Gunicorn — l'utilisateur peut l'ajouter lui-même via un service supplémentaire dans compose s'il veut TLS / mises en cache de static. Non couvert ici (« un seul service »).
- **Postgres** comme backend tenant — supporté par l'app (config par `database_url` de l'`Instance`), mais nécessite un 2e service compose. Hors périmètre v1.
- **Backups automatisés** vers S3 / etc. — out of scope. Le backup manuel via UI reste accessible.
- **CI/CD** (GitHub Actions, etc.) — non.
- **Multi-stage build** pour réduire la taille — pas nécessaire ici, l'image n'a pas de step de compilation cassable (les wheels pandas/numpy sont précompilés).
- **Tests dans le conteneur** (image dédiée `test` avec pytest) — utile si CI plus tard. Pas v1.

---

## 9. Checkpoints de validation

- [ ] **Phase 1** — `docker build` réussit ; l'entrypoint exécute les seeds sans erreur sur DB vide.
- [ ] **Phase 2** — `docker-compose up -d` rend l'app accessible sur `http://localhost:5000`, le volume `./instance` contient `meta.db` + `seconde-nature.db`.
- [ ] **Phase 3** — `doc/docker.md` couvre install / update / backup / troubleshooting ; `doc/installation.md` pointe vers ce nouveau doc.

---

## 10. Étape suivante

```
/sc:implement claudedocs/workflow_docker.md
```

Pas de phase parallélisable — les 3 phases sont courtes et séquentielles.
