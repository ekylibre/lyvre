# Workflow — Connexions externes en base + Sauvegardes/restauration d'instances

**Date :** 2026-05-21
**Auteur :** /sc:workflow
**Statut :** Plan d'implémentation — code non écrit, exécution réservée à `/sc:implement`

---

## 1. Contexte et objectifs

Deux évolutions indépendantes regroupées dans le même workflow car elles touchent toutes deux à la **configuration au niveau instance** :

1. **Connexions externes en base** — Sortir les credentials Stancer / Odoo / HelloAsso du `.env` pour les stocker dans une table de **la base tenant** (chaque association a ses propres clés API). Une nouvelle page `Configuration → Connexions externes` permet à l'admin d'éditer ces credentials sans toucher au fichier `.env` du serveur.

2. **Sauvegardes/restauration d'instances** — Permettre à un admin de créer une sauvegarde du fichier SQLite d'une instance, de le télécharger, et d'en restaurer une depuis l'interface `/instances/<id>`. Le tout sans accès SSH au serveur.

Décisions confirmées :

- **Stockage credentials** : table générique clé-valeur (`external_connections(service, key, value)`), une ligne par credential, dans la base tenant.
- **Chiffrement** : non, stockage en clair (le fichier DB est protégé au même niveau que le `.env`).
- **Backup** : copie SQLite atomique locale (`instance/backups/<slug>-<timestamp>.db`) + bouton de téléchargement HTTP.
- **Restauration** : remplace la DB de l'instance courante après création d'un backup de sécurité.
- **Postgres** : non supporté pour la sauvegarde/restauration (message d'erreur explicite).
- **Menu** : nouveau dropdown top-level **« Configuration »** dans la nav principale.

---

## 2. Modèle de données

### 2.1 Table `external_connections` (base **tenant**)

| Colonne | Type | Description |
|---|---|---|
| `id` | Integer PK | |
| `service` | String(30) NOT NULL | `stancer`, `odoo`, `helloasso` |
| `key` | String(50) NOT NULL | Voir tableau ci-dessous |
| `value` | Text nullable | Valeur (token, URL, slug…). NULL = non configuré. |
| `updated_at` | DateTime default=utcnow onupdate=utcnow | Pour l'audit visuel |

**Contrainte unique** : `(service, key)`. Index sur `service`.

**Clés attendues par service** :

| `service` | `key`s | Origine `.env` |
|-----------|--------|----------------|
| `stancer` | `secret_key`, `mode` | `STANCER_SECRET_KEY`, `STANCER_MODE` |
| `odoo` | `url`, `db`, `username`, `api_key` | `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY` |
| `helloasso` | `client_id`, `client_secret`, `org_slug`, `api_base` | `HELLOASSO_*` |

> Le schéma reste **agnostique** : l'application définit les clés attendues côté Python (dans un dict de constantes), pas dans une table. Ajouter un service plus tard = ajouter une entrée au dict + un formulaire UI.

### 2.2 Pas de modification de schéma méta

La méta-base reste inchangée. Les backups d'instances sont des fichiers sur disque, pas des lignes en DB. Les credentials sont par-instance et donc dans le tenant.

---

## 3. Architecture technique

### 3.1 Accès aux credentials — helper `external_config`

Nouveau module `app/services/external_config.py` :

```python
from app.extensions import db
from app.models import ExternalConnection
from flask import current_app, g

SERVICE_KEYS = {
    "stancer":   ["secret_key", "mode"],
    "odoo":      ["url", "db", "username", "api_key"],
    "helloasso": ["client_id", "client_secret", "org_slug", "api_base"],
}

ENV_FALLBACK = {
    ("stancer",   "secret_key"):     "STANCER_SECRET_KEY",
    ("stancer",   "mode"):           "STANCER_MODE",
    ("odoo",      "url"):            "ODOO_URL",
    ...
}

def get(service: str, key: str) -> str | None:
    """Lit la valeur en DB ; fallback sur le .env si vide ; cache par requête."""
    cache = getattr(g, "_ext_config_cache", None)
    if cache is None:
        cache = g._ext_config_cache = {}
    if (service, key) in cache:
        return cache[(service, key)]
    row = db.session.query(ExternalConnection).filter_by(
        service=service, key=key
    ).first()
    value = row.value if row and row.value else None
    if value is None:
        env_name = ENV_FALLBACK.get((service, key))
        if env_name:
            value = current_app.config.get(env_name) or None
    cache[(service, key)] = value
    return value


def get_all(service: str) -> dict[str, str | None]:
    return {k: get(service, k) for k in SERVICE_KEYS[service]}


def set_many(service: str, values: dict[str, str | None]) -> None:
    """Upsert pour ce service. Une value vide → row supprimée pour redéclencher le fallback."""
    for key in SERVICE_KEYS[service]:
        new_val = (values.get(key) or "").strip() or None
        row = db.session.query(ExternalConnection).filter_by(
            service=service, key=key
        ).first()
        if new_val is None:
            if row is not None:
                db.session.delete(row)
        else:
            if row is None:
                row = ExternalConnection(service=service, key=key, value=new_val)
                db.session.add(row)
            else:
                row.value = new_val
    db.session.commit()
```

Le cache par-requête évite N requêtes SQL si plusieurs appels au même service dans une vue.

### 3.2 Migration des services existants

| Service | Avant | Après |
|---------|-------|-------|
| `stancer_sync.py` | `current_app.config["STANCER_SECRET_KEY"]` | `external_config.get("stancer", "secret_key")` |
| `odoo_client.from_app_config()` | lit `ODOO_*` de `current_app.config` | lit `external_config.get_all("odoo")` |
| `helloasso_client.from_app_config()` | lit `HELLOASSO_*` | lit `external_config.get_all("helloasso")` |

Pour chaque check « la configuration est-elle suffisante ? » (dans les vues `payouts.py`, `orders.py`, etc.), remplacer la lecture directe par un appel à un helper `is_configured(service)` qui renvoie `True` si toutes les clés requises ont une valeur.

### 3.3 Backup/restore — couche fichier

Nouveau module `app/services/instance_backup.py` :

```python
BACKUPS_DIR = "instance/backups"

def list_backups(instance) -> list[BackupFile]:
    """Liste les fichiers <slug>-*.db dans BACKUPS_DIR, triés par date décroissante."""

def create_backup(instance) -> Path:
    """Crée un backup atomique de la DB tenant. SQLite uniquement.

    1. Détermine le chemin source via _resolve_database_url (déjà dans app/tenant.py).
    2. Refuse si l'instance n'est pas SQLite (RuntimeError).
    3. Ouvre la source en lecture, ouvre la target en écriture, appelle
       source.backup(target). Atomique, non-bloquant pour les lecteurs.
    4. Retourne le Path créé.
    """

def restore_backup(instance, uploaded_file) -> Path:
    """Restaure le fichier uploadé comme nouvelle DB de l'instance.

    1. Refuse si l'instance n'est pas SQLite.
    2. Lit les premiers 16 octets du fichier — doit commencer par 'SQLite format 3\0'.
    3. Tente d'ouvrir avec sqlite3 + PRAGMA integrity_check (rapide).
    4. Crée un backup de sécurité de la DB actuelle (préfixe 'pre-restore-').
    5. Écrit le fichier uploadé à la place de la DB actuelle (rename atomique).
    6. Purge le cache d'engines (app.tenant.clear_engine_cache(instance.id)).
    7. Retourne le Path du backup de sécurité.
    """

def delete_backup(instance, filename) -> None:
    """Supprime un fichier de backup (avec validation que le nom appartient à l'instance)."""
```

Sécurité :
- Le nom de fichier de backup doit **commencer par `<slug>-`** pour éviter le path traversal (`../../etc/passwd`).
- Limite de taille upload : 500 Mo (configurable via `MAX_BACKUP_UPLOAD_MB`).
- Vérification du magic header SQLite avant toute écriture.

---

## 4. Phases d'implémentation

### Phase 1 — Modèle ExternalConnection + migration

**Fichiers à créer :**
- `app/models/external_connection.py` — modèle SQLAlchemy (bind par défaut = tenant)
- `app/services/external_config.py` — helpers `get`, `get_all`, `set_many`, `is_configured`
- Nouvelle migration Alembic : `flask db migrate -m "add external_connections table"`

**Fichiers à modifier :**
- `app/models/__init__.py` — export `ExternalConnection`
- `app/services/stancer_sync.py` — utiliser `external_config.get("stancer", "secret_key")`
- `app/services/stancer_async.py` — idem
- `app/services/odoo_client.py` — réécrire `from_app_config()` pour utiliser `external_config.get_all("odoo")`
- `app/services/helloasso_client.py` — idem pour `helloasso`
- `app/views/payouts.py`, `app/views/orders.py`, `app/views/customer_invoices.py`, `app/views/entities.py` — remplacer les vérifications de configuration par `external_config.is_configured(...)`.

**Validation :**
- `flask db upgrade` applique la nouvelle migration sur les bases tenant existantes.
- Les boutons de sync Stancer/Odoo/HelloAsso continuent de fonctionner avec les credentials du `.env` (fallback intact).
- Tests existants restent verts.

> Les tenants existants n'ont pas de lignes dans `external_connections` — c'est ok, le fallback `.env` couvre. Les nouveaux tenants partent avec une table vide et l'admin remplit via l'UI.

### Phase 2 — UI Connexions externes

**Fichiers à créer :**
- `app/views/external_connections.py` — blueprint `external_connections` (admin uniquement) :
  - `GET /configuration/external-connections` — page avec 3 formulaires (un par service)
  - `POST /configuration/external-connections/<service>` — sauvegarde les credentials du service
- `app/templates/external_connections/index.html` — page unique avec 3 cartes (`<div class="card">`) Stancer / Odoo / HelloAsso.

**Fichiers à modifier :**
- `app/__init__.py` — enregistrer le blueprint.

**UX détails :**
- Pour chaque champ : afficher la valeur actuelle (uniquement les non-secrètes en clair ; les secrets affichés masqués `••••••••` avec lien « modifier »).
- Section de statut au-dessus de chaque carte : badge vert « Configuré » si `is_configured(service)`, gris « À configurer » sinon. Indication de la source (DB ou .env fallback).
- Un seul bouton « Enregistrer » par carte qui POST vers `/configuration/external-connections/<service>`.

**Validation :**
- Saisie des credentials Stancer via UI → flash succès → liste des payouts continue de fonctionner.
- Vider un champ (laisser blanc) → la value est supprimée de la DB → fallback `.env` re-prend si défini.

### Phase 3 — Backup création + listing + download

**Fichiers à créer :**
- `app/services/instance_backup.py` — implémentation des helpers (cf. §3.3).
- `app/templates/instances/detail.html` — vue détail enrichie : listing des backups + boutons.

**Fichiers à modifier :**
- `app/views/instances.py` — ajout :
  - `GET /instances/<id>` — vue détail (affiche les infos + la liste des backups)
  - `POST /instances/<id>/backup` — crée un backup
  - `GET /instances/<id>/backups/<filename>/download` — envoie le fichier
  - `POST /instances/<id>/backups/<filename>/delete` — supprime un backup
- `app/templates/instances/index.html` — chaque ligne pointe désormais vers `/instances/<id>` (au lieu d'`/edit`).

**Validation :**
- Cliquer « Créer une sauvegarde » → fichier `instance/backups/<slug>-YYYYMMDD-HHMMSS.db` apparaît.
- Cliquer « Télécharger » → le navigateur reçoit le fichier en `application/octet-stream`.
- Cliquer « Supprimer » → fichier disparaît avec confirmation JS.
- Tentative de backup sur instance Postgres → message d'erreur explicite, pas de fichier créé.

### Phase 4 — Restauration

**Fichiers à modifier :**
- `app/views/instances.py` — ajout :
  - `GET /instances/<id>/restore` — formulaire upload
  - `POST /instances/<id>/restore` — applique
- `app/templates/instances/restore.html` — formulaire avec confirmation JS double.

**Validation :**
- Upload d'un fichier non-SQLite → erreur, rien n'est modifié.
- Upload d'un fichier SQLite valide → backup de sécurité créé (`pre-restore-...`), DB courante remplacée, cache d'engines purgé.
- Après restore : reload de la page d'accueil affiche les données du backup.
- Backup de sécurité reste accessible dans la liste pour rollback.

### Phase 5 — Menu Configuration

**Fichiers à modifier :**
- `app/templates/base.html` — ajouter un nouveau dropdown top-level :

```html
<li class="nav-item dropdown">
  <a class="nav-link dropdown-toggle {% if request.blueprint == 'external_connections' %}active{% endif %}"
     href="#" data-bs-toggle="dropdown">Configuration</a>
  <ul class="dropdown-menu">
    {% if current_user.is_admin %}
      <li>
        <a class="dropdown-item" href="{{ url_for('external_connections.index') }}">
          Connexions externes
        </a>
      </li>
    {% endif %}
  </ul>
</li>
```

- Le dropdown apparaît dans tous les cas (utilisateur authentifié sur une instance), mais le contenu est vide (juste un message « rien à configurer ») pour les non-admins.

**Décision UX** : le dropdown peut être masqué entièrement pour les non-admins en v1 (rien d'autre dedans). À ré-ouvrir si on ajoute des préférences user-level plus tard.

### Phase 6 — Documentation

**Fichiers à modifier :**
- `doc/routes.md` — ajouter les sections `/configuration/external-connections/*` et `/instances/<id>/backup*`.
- `doc/models.md` — ajouter `ExternalConnection`.
- `doc/architecture.md` — section « Credentials externes » + section « Sauvegardes ».
- `doc/installation.md` — préciser que les variables `STANCER_*`, `ODOO_*`, `HELLOASSO_*` deviennent **optionnelles** (fallback uniquement) et que la configuration se fait désormais en UI.
- `doc/multi_tenant.md` — note sur le fait que les credentials externes sont per-instance.

**Fichiers à créer :**
- `doc/backups.md` — guide utilisateur : créer un backup, télécharger, restaurer, troubleshooting.

---

## 5. Dépendances entre phases

```
Phase 1 (modèle + helper) ──┬──▶ Phase 2 (UI connexions)
                            │
                            └──▶ (services consomment external_config)

Phase 3 (backup) ──▶ Phase 4 (restore)

Phase 5 (menu)  ── parallèle à tout, mais doit attendre que les blueprints existent
Phase 6 (doc)   ── final
```

Phase 1 ↔ Phase 3 sont indépendantes (peuvent être faites en parallèle).
Phase 2 dépend de Phase 1.
Phase 4 dépend de Phase 3.
Phase 5 dépend de Phase 2 (référence `external_connections.index`).
Phase 6 dépend de tout.

---

## 6. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| **Migration sur les bases tenant existantes** | La migration ajoute une table neuve, no-op sur les données existantes. Exécutable via `flask db upgrade` sur chaque DB tenant (cf. boucle dans `installation.md`). |
| **Credentials oubliés du .env** | Le fallback `.env` reste actif tant que la table est vide. Pas de big-bang : transition douce. |
| **Restore d'un mauvais fichier** | Validation magic header + `PRAGMA integrity_check` avant d'écraser. Backup de sécurité créé systématiquement. |
| **Path traversal sur les noms de backups** | Nom validé : doit matcher `<slug>-[0-9-]+\.db`. Pas de `..`, pas de séparateur de chemin. |
| **Backup d'une DB Postgres** | Détection via URL : si non-SQLite, retourne `RuntimeError` avant toute action. Bouton masqué côté UI pour les instances non-SQLite. |
| **Engine cache obsolète après restore** | `clear_engine_cache(instance.id)` appelé en fin de restore. Les futures requêtes sur cette instance recréent l'engine sur le nouveau fichier. |
| **Concurrence pendant restore** | SQLite ne bloque pas les lecteurs pendant un rename, mais une requête en cours peut voir la transition incohérente. Acceptable v1 (faible fréquence, admin manuel). Envisager un mode maintenance dans le futur. |
| **Taille des fichiers téléchargés** | Pas de streaming particulier : Flask `send_file` gère. Limite `MAX_CONTENT_LENGTH` configurée à 500 Mo. |
| **Credentials en clair dans backup** | Les backups contiennent la table `external_connections`. Si on télécharge un backup et qu'on le laisse traîner, les credentials sont compromis. À documenter dans `doc/backups.md`. |

---

## 7. Hors-périmètre (v1)

- **Backup/restore Postgres** — uniquement SQLite. Pour Postgres, l'admin utilise `pg_dump`/`pg_restore` côté serveur.
- **Sauvegardes planifiées (cron)** — manuelles uniquement. Une routine cron côté système peut appeler `python scripts/backup_all.py` (à créer plus tard).
- **Rétention automatique** — pas de purge des vieux backups. L'admin gère manuellement.
- **Chiffrement au repos** — refusé en discussion préalable. À reconsidérer si exigence de conformité.
- **Audit log des modifs credentials** — pas en v1. À ajouter avec une table générique d'audit plus tard.
- **Validation des credentials (« tester la connexion »)** — pas de bouton « tester » dans les formulaires. À ajouter en v2 (appel API léger côté serveur).
- **Restauration vers une nouvelle instance** — restauration ne crée pas de nouvelle instance, elle remplace l'existante. La création d'instance avec un backup en seed est laissée pour plus tard.
- **Diff/comparaison entre backups** — non.

---

## 8. Checkpoints de validation

- [ ] **Phase 1** — Migration appliquée sur les bases tenant ; les boutons de sync Stancer/Odoo/HelloAsso fonctionnent avec uniquement les credentials du `.env` (fallback OK).
- [ ] **Phase 2** — Configurer Stancer via UI puis vider le `.env` : la sync continue de fonctionner. Le badge « Configuré » s'affiche.
- [ ] **Phase 3** — Création d'un backup → fichier visible dans la liste + téléchargeable.
- [ ] **Phase 4** — Restauration depuis un backup → données restaurées, backup de sécurité conservé.
- [ ] **Phase 5** — Menu « Configuration » présent dans la nav avec entrée « Connexions externes ».
- [ ] **Phase 6** — Doc à jour, `doc/backups.md` rédigé.

---

## 9. Étape suivante

Le code de ce workflow n'est **pas** écrit. Pour démarrer l'implémentation :

```
/sc:implement claudedocs/workflow_connections_backups.md
```

Les phases peuvent être appliquées séparément :
- Phases 1-2 (connexions externes) sont autonomes.
- Phases 3-4 (backups) sont autonomes.
- Phases 5-6 (UI + doc) viennent en finalisation.
