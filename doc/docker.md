# Déploiement Docker

L'application est packagée dans une image unique. Toutes les données persistantes vivent dans un volume bind-mount sur `./instance/`.

```
┌─────────────────────────────────────┐
│ Étape « front » : node:22-slim      │
│  npm ci + npm run build (Vite)      │──┐ app/static/dist/
└─────────────────────────────────────┘  │ (seul le résultat est copié)
┌─────────────────────────────────────┐  │
│ Image compta-asso:latest            │◀─┘
│  - Python 3.12-slim (sans Node)     │
│  - Tesseract OCR (fra), WeasyPrint  │
│  - Gunicorn (1 worker, 4 threads)   │
│  - User non-root (UID/GID 1000)     │
│  - Port 5000                        │
└─────────────────────────────────────┘
            │
            │ volume bind
            ▼
   ./instance/   ◀── méta DB + tenant DBs + sauvegardes + pièces jointes (uploads/)
```

---

## Prérequis

- Docker Engine ≥ 24 et le plugin Compose v2.
- Sur l'hôte : le dossier `./instance/` (créé automatiquement par le bind-mount) doit être **inscriptible par UID 1000**. Si votre utilisateur hôte n'est pas UID 1000, voir [§ permissions](#permissions-sur-le-volume) ci-dessous.
- Un fichier `.env` à la racine du projet (cf. [installation.md](installation.md#configuration-de-lenvironnement)).

---

## Premier démarrage

```bash
git clone <repo>
cd compta-asso

# Configurer les secrets — au minimum SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
cp .env .env.example   # gardez-en une copie
$EDITOR .env

# Build + run
docker compose up -d --build
docker compose logs -f web
```

Sortie attendue :

```
[entrypoint] Applying database migrations…
[entrypoint] Seeding accounts (idempotent)…
[entrypoint] Seeding meta DB (idempotent)…
[entrypoint] Seeding rules (idempotent)…
[entrypoint] Starting: gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:5000 --timeout 120 app:create_app()
[INFO] Booting worker with pid: 71
```

Aller sur **http://localhost:5000**, se connecter avec l'`ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`.

---

## Variables d'environnement

Le `.env` est injecté dans le conteneur via `env_file:` dans `docker-compose.yml`. Variables clés :

| Variable | Rôle |
|----------|------|
| `SECRET_KEY` | **À changer impérativement** — clé de signature des sessions Flask. Générer via `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Compte admin créé au premier démarrage par `seed_meta.py`. Lus une fois ; les modifications ultérieures se font via `/users/`. |
| `DEFAULT_INSTANCE_CHART` | Plan comptable (`asso` ou `sci`) chargé dans la base tenant par défaut **si elle est vide** (défaut `asso`). Une base existante garde son plan : `seed_accounts.py` le détecte et le complète, sans jamais y mélanger l'autre. |
| `DATABASE_URL` | URL de la base tenant par défaut. Pour Docker, garder `sqlite:///seconde-nature.db` (résolu dans `instance/`). |
| `META_DATABASE_URL` | URL SQLAlchemy de la méta-base. **À laisser non définie** (le fallback `config.py` calcule un chemin absolu correct), ou écrire `sqlite:///meta.db` (sans `instance/`) — voir [le piège SQLite relatif](installation.md#3-configurer-lenvironnement) dans la doc installation. |
| `APP_PORT` | Port hôte → conteneur (défaut `5000`). Utile si 5000 est pris : `APP_PORT=8000 docker compose up -d`. |
| `APP_UID` / `APP_GID` | UID/GID au sein du conteneur (défaut `1000:1000`). À builder avec `--build-arg APP_UID=$(id -u)` pour matcher un hôte différent. |

Les credentials externes (`STANCER_*`, `ODOO_*`, `HELLOASSO_*`, `QONTO_*`) restent pris en charge via `.env` comme **repli global** — à éviter pour Qonto, dont les identifiants désignent une organisation précise. Pour les surcharger par instance, utiliser **Configuration › Intégrations** dans l'UI ; on peut aussi y **désactiver** une intégration configurée par `.env` (l'interrupteur prime). La table `integration_states` est créée par `flask db upgrade` (lancé par l'entrypoint) : **toute base tenant doit être migrée** (voir [multi_tenant.md](multi_tenant.md)).

---

## Build du front (îlots React)

Le `Dockerfile` est **multi-étapes** : l'étape `front` (`node:22-slim`) installe les dépendances
(`npm ci`, à partir de `frontend/package-lock.json`) et construit les îlots avec Vite ; l'image
finale ne reçoit que `app/static/dist/` (bundle + manifest lu par `vite_assets()`). Aucune action
manuelle : `docker compose build` (ou le build Dokploy) fait tout. `frontend/node_modules` et un
éventuel `app/static/dist/` local sont exclus du contexte (`.dockerignore`).

### Dokploy

Le déploiement est construit par **Dokploy** à partir du dépôt, en service *Dockerfile* ou
*Compose* (le `docker-compose.yml` garde `build: .`) : le build multi-étapes s'exécute sur le
serveur, sans CI. Adapter dans Dokploy le volume persistant de `instance/` et les variables
d'environnement (équivalent du `.env`).

---

## Mise à jour de l'application

```bash
git pull
docker compose up -d --build
```

L'entrypoint applique les migrations Alembic automatiquement au démarrage. **Aucune commande manuelle n'est nécessaire** côté DB.

---

## Mise à jour depuis une install non-Docker

Si vous aviez déjà l'application en `python run.py` :

```bash
# Sauvegarde de précaution
cp -a instance instance.bak

# Lancement
docker compose up -d --build
```

Le volume bind-mount partage `./instance/` ; l'app dans le conteneur voit la DB existante. Les seeds sont strictement idempotents (rien n'est ré-écrit). Login : email/mot de passe **inchangés** — les utilisateurs en méta-base restent valides.

---

## Sauvegardes

Les fichiers `instance/seconde-nature.db`, `instance/meta.db` et `instance/tenants/*.db` sont **directement accessibles depuis l'hôte** :

```bash
# Backup ad-hoc d'une instance tenant
cp instance/seconde-nature.db /backup/$(date +%Y%m%d)-seconde-nature.db

# Backup complet (méta + tenants + pièces jointes + sauvegardes UI déjà faites)
tar czf compta-asso-$(date +%Y%m%d).tar.gz instance/
```

L'UI **Instances → Détail → Sauvegardes** reste disponible : archives `.zip` (base de l'instance +
ses pièces jointes `instance/uploads/<slug>/`) dans `instance/backups/`, visibles depuis l'hôte. Une
copie `cp` de la seule base ne contient pas les pièces des factures d'achat.

---

## Permissions sur le volume

L'utilisateur dans le conteneur est `appuser` (UID/GID 1000 par défaut). Si l'utilisateur hôte qui fait `docker compose up` n'est pas UID 1000, le conteneur n'aura pas les droits d'écriture sur `./instance/`.

**Option A — Builder avec l'UID hôte (recommandé)** :

```bash
APP_UID=$(id -u) APP_GID=$(id -g) docker compose up -d --build
```

Ou en persistant via `.env` (lu par compose pour les `${VARS}`) :

```
APP_UID=1001
APP_GID=1001
```

**Option B — Aligner le owner du dossier existant** :

```bash
sudo chown -R 1000:1000 instance/
```

**Option C — Déploiement Dokploy (ou autre PaaS qui provisionne le volume)** :

Dokploy crée typiquement le volume avec `root:root`, ce qui empêche l'`appuser` (UID 1000) du conteneur d'écrire dedans — symptôme : `sqlite3.OperationalError: unable to open database file` au démarrage, dans `flask db upgrade`.

Fix manuel côté hôte Dokploy (à refaire après chaque recréation du volume) :

```bash
# 1. Identifier le chemin du volume
docker volume inspect <nom_du_volume>
# → cherche "Mountpoint" dans la sortie JSON

# 2. Aligner le propriétaire
sudo chown -R 1000:1000 <Mountpoint>

# 3. Redémarrer le conteneur
docker restart <container_id>
```

Pour un bind-mount déclaré dans le `docker-compose.yml` Dokploy :

```bash
sudo chown -R 1000:1000 /chemin/hôte/vers/instance
docker restart <container_id>
```

Alternative permanente : adapter le Dockerfile + l'entrypoint pour démarrer en `root`, chown le volume au boot, puis dropper les privilèges vers `appuser` via `gosu`. Voir `/sc:troubleshoot "container Dokploy"` pour le détail du correctif.

---

## Troubleshooting

### Le conteneur démarre puis s'arrête immédiatement

```bash
docker compose logs web
```

Causes fréquentes :

- `.env` absent → message clair de compose au démarrage.
- Permission denied sur `instance/` → cf. § permissions ci-dessus.
- Migration Alembic échouée (rare) → la sortie des logs indique le revision concerné.
- `sqlalchemy.exc.OperationalError: unable to open database file` au `flask db upgrade` → souvent une URL SQLite **relative avec `instance/` dans le path** (`DATABASE_URL=sqlite:///instance/...`). Flask-SQLAlchemy double-préfixe — voir [le piège SQLite relatif](installation.md#3-configurer-lenvironnement). Corriger en retirant `instance/` ou en passant un chemin absolu à 4 slashes.

### Healthcheck en `unhealthy`

```bash
docker compose ps
docker inspect compta-asso --format '{{.State.Health}}'
```

Le bootstrap (migrations + seeds) peut prendre > 30 s sur une grosse DB. Allonger `start_period` dans `docker-compose.yml` si nécessaire.

### Logs trop verbeux ou absents

- `print()` côté Python sort grâce à `PYTHONUNBUFFERED=1` (déjà posé dans le Dockerfile).
- Gunicorn log access + erreurs sur stdout/stderr → `docker compose logs -f web`.
- Pour filtrer : `docker compose logs --tail=100 web | grep -i error`.

### Threads de sync Stancer interrompus par un restart

Lors d'un `docker compose down` ou d'un déploiement, Gunicorn reçoit SIGTERM et ferme proprement les requêtes en cours. **Les threads daemon Stancer sont tués brutalement** — les `SyncJob` correspondants restent en état `running` en DB. Au prochain démarrage, l'utilisateur peut relancer la synchro depuis `/payouts/` (idempotent grâce au modèle SyncJob).

### Build trop lent (pandas)

Pandas + numpy = ~250 Mo. Sur lien lent, le premier `docker compose build` peut prendre plusieurs minutes. Une fois l'image construite, les builds suivants ne refont pas cette étape (layer caché par `requirements.txt` inchangé).

### SECRET_KEY par défaut détectée en prod

Aucune alerte automatique en v1. **Vérifier manuellement** avant déploiement que `SECRET_KEY` n'est pas la valeur par défaut `change-me-in-production`. Une session sous cette clé peut être forgée par n'importe qui ayant accès au code public.

---

## Limitations connues

- **1 seul worker Gunicorn** — SQLite verrouille en écriture. Si la charge dépasse quelques requêtes/seconde soutenues, basculer vers Postgres (l'app supporte déjà via `database_url` de l'`Instance`). Hors périmètre du compose actuel.
- **Pas de reverse proxy** intégré — pas de TLS, pas de cache statique. Pour la prod publique, mettre nginx / Caddy devant.
- **Pas de service Postgres** dans le compose — si vous voulez Postgres pour une instance, créer un 2ᵉ service `db:` à part et configurer l'URL d'instance via l'UI Instances.
- **Pas de backup auto** — l'admin gère manuellement (UI ou tar côté hôte).

---

## Référence rapide

| Action | Commande |
|--------|----------|
| Démarrer | `docker compose up -d --build` |
| Stopper | `docker compose down` |
| Logs en direct | `docker compose logs -f web` |
| Shell dans le conteneur | `docker compose exec web bash` |
| Re-jouer le bootstrap | `docker compose restart web` |
| Détruire (mais garder `./instance/`) | `docker compose down` |
| Reset complet (⚠ supprime les DBs) | `docker compose down && rm -rf instance/` |
