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
- Sur l'hôte : le dossier `./instance/` (créé automatiquement par le bind-mount) est rendu à l'UID 1000 du conteneur au démarrage ; voir [§ permissions](#permissions-sur-le-volume) ci-dessous.
- Un fichier `.env` à la racine du projet (cf. [installation.md](installation.md#configuration-de-lenvironnement)).

---

## Premier démarrage

```bash
git clone <repo>
cd compta-asso

# Configurer les secrets — au minimum SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
cp .env .env.example   # gardez-en une copie
$EDITOR .env

# Build + run (local : port publié et données dans ./instance)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
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
| `APP_BASE_URL` | Adresse publique de Lyvre (`https://compta.seconde-nature.net`) : liens envoyés par e-mail (« Mot de passe oublié ? »). **Obligatoire en production** pour ces liens (sans elle, aucun lien n'est envoyé : jamais construit sur l'en-tête `Host` de la requête). |
| `SIRENE_API_KEY` (`SIRENE_API_URL`, par défaut `https://api.insee.fr/api-sirene/4`) | **Clé de l'API Sirene v4** de l'INSEE (portail-api.insee.fr), commune à toutes les instances : bouton « Compléter depuis Sirene » de la Structure (puis des tiers). Restée sur le serveur, jamais envoyée au navigateur. Vide : les fonctions Sirene sont masquées. Quota de l'INSEE : 30 requêtes par minute, 2 000 par heure, pour tout le serveur. |
| `LEXICON_API_KEY` (`LEXICON_URL`, par défaut `https://lexicon.osfarm.org`) | **Clé membre de Lexicon** (OSFarm), commune à toutes les instances : contrôle des aides d'une exploitation avec les montants PAC publiés par l'ASP (Compta › Aides et subventions), lus par SIREN et gardés en cache dans l'instance. Restée sur le serveur, envoyée en `Authorization: Bearer`. Vide : le contrôle est masqué. Limites du plan OSFarm (anonyme : 30 requêtes par minute). |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | **SMTP du serveur**, commun à toutes les instances : e-mails de la plateforme (lien « Mot de passe oublié »). Distinct de l'intégration SMTP de chaque instance (relances, reçus, factures). |

Les credentials externes (`STANCER_*`, `ODOO_*`, `HELLOASSO_*`, `QONTO_*`, et `MAIL_*` pour les intégrations) **ne servent pas de repli aux intégrations en production** (`FLASK_ENV=production`) : chaque instance saisit ses réglages et active ses intégrations dans **Configuration › Intégrations**. Avant de passer une instance existante sur cette version, lancer `scripts/integrations_report.py` dans le conteneur et saisir les réglages signalés (voir [integrations.md](integrations.md)). La table `integration_states` est créée par `flask db upgrade` (lancé par l'entrypoint) : **toute base tenant doit être migrée** (voir [multi_tenant.md](multi_tenant.md)). L'entrypoint s'en charge à chaque démarrage : `flask db upgrade` migre la base par défaut, puis `scripts/migrate_instances.py` migre la base de chaque instance déclarée dans la base méta (un échec est signalé dans les journaux, `[migrate_instances] … ÉCHEC`, sans bloquer les autres instances ni le démarrage).

---

## Build du front (SPA React)

Le `Dockerfile` est **multi-étapes** : l'étape `front` (`node:22-slim`) installe les dépendances
(`npm ci`, à partir de `frontend/package-lock.json`) et construit la SPA avec Vite ; l'image
finale ne reçoit que `app/static/dist/` (bundle + manifest lu par `vite_assets()`). Aucune action
manuelle : `docker compose build` (ou le build Dokploy) fait tout. `frontend/node_modules` et un
éventuel `app/static/dist/` local sont exclus du contexte (`.dockerignore`).

### Dokploy

Le déploiement est construit par **Dokploy** à partir du dépôt (service *Compose*, auto-déploiement
de `main` ; service actuel : **lyvre.seconde-nature.net** sur seconde-nature-kvm) : le build
multi-étapes s'exécute sur le serveur, sans CI. Le `docker-compose.yml` est fait pour cohabiter avec
d'autres services sur le même hôte :

- **ni `container_name` ni `image` nommée** (Dokploy nomme le conteneur et l'image par service) ;
- **aucun port publié** : onglet *Domains* du service, *Container Port* `5000`, HTTPS Let's Encrypt ;
- **données** dans `INSTANCE_DIR`, par défaut `../files/instance` (dossier persistant du service
  Dokploy) — **jamais** le dossier `instance/` d'un autre service : l'entrypoint migre les bases
  qu'il trouve (`flask db upgrade`) ;
- **variables** dans l'onglet *Environment* (équivalent du `.env`) : `SECRET_KEY`, `ADMIN_EMAIL`,
  `ADMIN_PASSWORD`, `APP_BASE_URL`, `MAIL_*`, `SIRENE_API_KEY`, `LEXICON_API_KEY` (voir ci-dessus).

Premier déploiement : Dokploy crée `../files/instance` en `root` ; l'entrypoint le rend
automatiquement à `appuser` avant de démarrer (voir [§ permissions](#permissions-sur-le-volume)).

---

## Version et nouveautés

Le numéro de version (calendaire `AAAA.MM.N`) et les nouveautés viennent de `data/changelog.yml` ;
`CHANGELOG.md`, la version de `frontend/package.json` et le badge du README en sont générés.

- Ajouter chaque changement sous `next` (`kind` : `new`, `improved`, `fixed` ou `action` pour une
  action requise à la mise à jour ; `structure` : `asso` ou `sci` ; `text` pour l'utilisateur,
  `tech` pour l'hébergeur).
- Publier : `python scripts/release.py publish --title "…"`, puis lancer les commandes `git commit` et
  `git tag v<version>` qu'il affiche (le script ne commite ni ne pousse rien).
- `python scripts/release.py check` (aussi lancé par la suite de tests) signale un fichier généré
  qui n'est plus à jour : `python scripts/release.py build` les régénère.
- Le commit construit s'affiche à côté de la version si l'image reçoit `SOURCE_COMMIT` (argument de
  construction, transmis par `docker-compose.yml`) ; sinon seule la version s'affiche.

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

Le conteneur démarre en `root` le temps de rendre `/app/instance` à `appuser` (UID/GID 1000 par
défaut, ou `APP_UID`/`APP_GID` au build) s'il ne lui appartient pas — cas d'un dossier créé par
Docker ou Dokploy, ou de bases restaurées par `root` —, puis abandonne ses privilèges (`setpriv`)
avant les migrations : l'application ne tourne jamais en `root`. Rien à faire côté hôte.

Conséquence en local : si votre utilisateur hôte n'est pas UID 1000, les fichiers de `./instance/`
passent à l'UID 1000. Pour les garder à votre nom, buildez avec votre UID :

```bash
APP_UID=$(id -u) APP_GID=$(id -g) docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

(ou `APP_UID=…` / `APP_GID=…` dans le `.env`). Symptôme d'un problème de droits malgré tout (volume
en lecture seule, système de fichiers sans `chown`) : `sqlite3.OperationalError: unable to open
database file` dans `flask db upgrade`.

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
docker inspect <conteneur> --format '{{.State.Health}}'
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
