# Workflow — Gestion d'instances multi-tenant + Gestion d'utilisateurs basique

**Date :** 2026-05-21
**Auteur :** /sc:workflow
**Statut :** Plan d'implémentation — code non écrit, exécution réservée à `/sc:implement`

---

## 1. Contexte et objectifs

L'application est aujourd'hui mono-tenant (une seule base `instance/seconde-nature.db`) avec un seul mot de passe partagé (`ADMIN_PASSWORD`). Deux évolutions sont demandées :

1. **Multi-tenant par instance** — 1 instance = 1 association = 1 base de données. Au login, l'utilisateur choisit l'instance ; toutes les requêtes comptables (écritures, comptes, payouts…) sont routées vers la base de cette instance.
2. **Gestion d'utilisateurs basique** — comptes individuels (email + mot de passe hashé), CRUD admin, remplaçant le mot de passe unique actuel. Pas de rôles fins : seulement `is_admin` / `is_active`.

Décisions confirmées :
- Les **utilisateurs sont globaux** (vivent dans une méta-DB séparée), pas liés à une instance dans cette première version.
- Tout utilisateur authentifié peut accéder à **n'importe quelle instance** (pas de table de jointure user × instance pour l'instant — extension prévue plus tard).
- Les utilisateurs ne sont pas dupliqués par instance ; ils sont partagés.

---

## 2. Modèle de données cible

### 2.1 Méta-DB (`instance/meta.db`)

Nouvelle base SQLite globale, distincte des données comptables. Versionnée par un répertoire `migrations_meta/` Alembic propre.

#### Table `instances`

| Colonne | Type | Description |
|---|---|---|
| `id` | Integer PK | |
| `slug` | String(50) UNIQUE NOT NULL | Identifiant URL-safe (ex : `asso-dupont`). Sert aussi de nom de fichier SQLite. |
| `label` | String(200) NOT NULL | Nom affiché (ex : `Association Dupont — 2024-2025`) |
| `database_url` | String(500) NOT NULL | URL SQLAlchemy. Pour SQLite local : `sqlite:///instance/tenants/<slug>.db`. Postgres accepté : `postgresql://…`. |
| `is_active` | Boolean default=True | Si False, n'apparaît pas dans la liste de sélection au login |
| `created_at` | DateTime default=utcnow | |

Index : `slug` (UNIQUE).

#### Table `users`

| Colonne | Type | Description |
|---|---|---|
| `id` | Integer PK | |
| `email` | String(200) UNIQUE NOT NULL | Login |
| `password_hash` | String(255) NOT NULL | `werkzeug.security.generate_password_hash(method='pbkdf2:sha256')` |
| `full_name` | String(200) | Nom affiché |
| `is_admin` | Boolean default=False | Accès au CRUD utilisateurs et au CRUD instances |
| `is_active` | Boolean default=True | Compte désactivé = login refusé sans suppression |
| `last_login_at` | DateTime nullable | Dernière connexion réussie (utile pour audit) |
| `created_at` | DateTime default=utcnow | |

Index : `email` (UNIQUE, case-insensitive lookup via `func.lower`).

> **Note** : aucune liaison `user × instance` dans cette version. Tout utilisateur actif voit toutes les instances actives.

### 2.2 DB tenant (existante, schéma inchangé)

Les bases tenant conservent **exactement** le schéma actuel (`accounts`, `journals`, `journal_entries`, `bank_accounts`, etc.). Aucun changement de modèle métier. Le fichier `instance/seconde-nature.db` actuel est conservé tel quel et devient la base de la **première instance** (slug `default` ou nom choisi par l'admin lors de la migration — voir §5).

---

## 3. Architecture technique

### 3.1 Séparation des deux extensions SQLAlchemy

Flask-SQLAlchemy ne permet pas nativement de basculer le moteur principal par requête de manière propre. Solution retenue : **deux instances SQLAlchemy distinctes**.

```python
# app/extensions.py
meta_db = SQLAlchemy()      # Users, Instances — toujours connectée à meta.db
tenant_db = SQLAlchemy()    # Tous les modèles comptables — moteur changé par requête
```

- `meta_db` est initialisée avec `SQLALCHEMY_DATABASE_URI` pointant vers `instance/meta.db`.
- `tenant_db` est initialisée avec une URL « bidon » au démarrage, puis son `session` est rebindée par requête via un registre d'engines mémoïsé.

### 3.2 Routage par requête

```python
# app/tenant.py (nouveau module)
_ENGINE_CACHE: dict[int, Engine] = {}      # instance_id → SQLAlchemy Engine
_SESSION_CACHE: dict[int, scoped_session] = {}

def get_tenant_engine(instance: Instance) -> Engine:
    if instance.id not in _ENGINE_CACHE:
        _ENGINE_CACHE[instance.id] = create_engine(instance.database_url, future=True)
    return _ENGINE_CACHE[instance.id]

def bind_tenant_session(instance: Instance) -> None:
    """Appelé en before_request : configure tenant_db.session pour pointer vers la bonne DB."""
    engine = get_tenant_engine(instance)
    tenant_db.session.remove()
    tenant_db.session.configure(bind=engine)
```

Hook Flask :
```python
@app.before_request
def _select_tenant():
    if not current_user.is_authenticated:
        return  # login_required redirigera
    instance_id = session.get("instance_id")
    if instance_id is None:
        if request.endpoint not in ("auth.login", "auth.select_instance", "auth.logout", "static"):
            return redirect(url_for("auth.select_instance"))
        return
    inst = meta_db.session.get(Instance, instance_id)
    if inst is None or not inst.is_active:
        session.pop("instance_id", None)
        return redirect(url_for("auth.select_instance"))
    g.current_instance = inst
    bind_tenant_session(inst)
```

### 3.3 Migration des modèles existants vers `tenant_db`

Tous les modèles dans `app/models/*.py` qui font aujourd'hui `from app.extensions import db` doivent passer à `from app.extensions import tenant_db as db`. Le nom local `db` est conservé pour limiter la diff.

**Impact** : ~17 fichiers de modèles + tous les services qui font `db.session.add/commit/query` continuent de fonctionner sans changement, à condition que `tenant_db.session` soit bien bindée au moteur courant avant d'exécuter la vue.

### 3.4 Migrations Alembic — deux pipelines

- **`migrations/`** (existant) → pilote `tenant_db.metadata`. Renommé symboliquement « migrations tenant ».
- **`migrations_meta/`** (nouveau) → pilote `meta_db.metadata` (users + instances).

Commandes :
```bash
# Méta
FLASK_APP=run.py flask --directory=migrations_meta db upgrade

# Tenant — appliqué sur CHAQUE base tenant
for db_path in instance/tenants/*.db; do
    DATABASE_URL=sqlite:///$db_path FLASK_APP=run.py flask db upgrade
done
```

Un script `scripts/migrate_all_tenants.py` est créé pour automatiser la boucle.

### 3.5 CSRF, Flask-Login

- `Flask-Login` charge l'utilisateur depuis `meta_db` :
  ```python
  @login_manager.user_loader
  def load_user(user_id):
      return meta_db.session.get(User, int(user_id))
  ```
- `User` hérite de `UserMixin`.
- CSRF inchangé.

---

## 4. Flux utilisateur

### 4.1 Premier démarrage (bootstrap)

1. `flask db upgrade` (tenant) sur `instance/seconde-nature.db` — déjà fait, inchangé.
2. `flask --directory=migrations_meta db upgrade` — crée `instance/meta.db`.
3. Script `seed_meta.py` :
   - Crée la première `Instance` (`slug='seconde-nature'`, `label='Seconde Nature'`, `database_url='sqlite:///seconde-nature.db'`).
   - Crée le premier `User` admin (email + password lus depuis `.env` ou prompts CLI).

### 4.2 Login → sélection d'instance → tableau de bord

1. `GET /login` — formulaire email + mot de passe.
2. `POST /login` — vérifie credentials sur `meta_db.users`, redirige vers `/select-instance`.
3. `GET /select-instance` — liste les instances actives. Si une seule instance → auto-sélection et redirection vers `/`.
4. `POST /select-instance` — pose `session["instance_id"]`, redirige vers `?next=` ou `/`.
5. Toutes les pages métier suivantes utilisent `g.current_instance` (badge dans la nav).
6. Bouton « Changer d'instance » dans la nav → `GET /select-instance` (pop `session["instance_id"]`).

### 4.3 CRUD utilisateurs (admin uniquement)

- `GET /users/` — liste paginée.
- `GET /users/new`, `POST /users/new` — création (génère hash mot de passe).
- `GET /users/<id>/edit`, `POST /users/<id>/edit` — édition. Modification du mot de passe optionnelle (champ vide = inchangé).
- `POST /users/<id>/delete` — suppression. L'admin ne peut pas se supprimer lui-même.
- `POST /users/<id>/toggle-active` — bascule `is_active`.

Décorateur `@admin_required` qui vérifie `current_user.is_admin`, renvoie 403 sinon.

### 4.4 CRUD instances (admin uniquement)

- `GET /instances/` — liste.
- `GET /instances/new`, `POST /instances/new` — création. Si SQLite, créé automatiquement le fichier `instance/tenants/<slug>.db` et applique les migrations tenant.
- `GET /instances/<id>/edit`, `POST /instances/<id>/edit` — édition (label, is_active). `database_url` et `slug` sont en lecture seule après création pour éviter de casser le cache d'engines.
- Pas de suppression d'instance dans la première version (le fichier DB tenant ne doit pas être supprimé sans confirmation explicite).

---

## 5. Migration depuis l'état actuel

L'application existante a déjà des données dans `instance/seconde-nature.db` et un utilisateur unique géré par `ADMIN_PASSWORD`. Procédure de migration **manuelle, non destructive** :

1. Sauvegarder `instance/seconde-nature.db`.
2. Appliquer la migration méta : crée `instance/meta.db` vide.
3. Lancer `seed_meta.py` :
   - Lit `ADMIN_PASSWORD` du `.env` (et un nouvel `ADMIN_EMAIL`).
   - Crée 1 `Instance` `slug='seconde-nature'` pointant vers `sqlite:///seconde-nature.db`.
   - Crée 1 `User` admin avec ces credentials.
4. Démarrer l'app. Login avec `ADMIN_EMAIL` + `ADMIN_PASSWORD` → sélection auto de l'instance `default` (la seule) → application normale.
5. Optionnel : créer d'autres instances via `/instances/new`. Chaque nouvelle instance crée un fichier `instance/tenants/<slug>.db` et y applique le schéma comptable + les seeds (783 comptes PCA + 6 journaux).

Les variables `.env` `ADMIN_PASSWORD` et `ADMIN_EMAIL` ne sont lues que par `seed_meta.py` ; elles ne participent plus à l'auth applicative après le seed.

---

## 6. Phases d'implémentation

### Phase 1 — Méta-DB et modèles (fondations)

**Fichiers à créer :**
- `app/models/user.py` — modèle `User` sur `meta_db`.
- `app/models/instance.py` — modèle `Instance` sur `meta_db`.
- `migrations_meta/` — répertoire Alembic indépendant, généré par `flask --directory=migrations_meta db init` puis `migrate -m "init meta schema"`.

**Fichiers à modifier :**
- `app/extensions.py` — ajouter `meta_db = SQLAlchemy()` (renommer `db` en `tenant_db`).
- `app/__init__.py` — initialiser les deux extensions ; deux instances `Migrate(app, meta_db, directory='migrations_meta')` et `Migrate(app, tenant_db, directory='migrations')`.
- Les 17 fichiers `app/models/*.py` existants — remplacer `from app.extensions import db` par `from app.extensions import tenant_db as db`.

**Validation :**
- `flask db upgrade` (tenant) toujours fonctionnel sur `seconde-nature.db`.
- `flask --directory=migrations_meta db upgrade` crée `meta.db` avec deux tables.
- Tests existants (`pytest`) passent toujours sur `tenant_db`.

### Phase 2 — Routing tenant par requête

**Fichiers à créer :**
- `app/tenant.py` — registre `_ENGINE_CACHE`, helpers `get_tenant_engine`, `bind_tenant_session`, hook `before_request`.

**Fichiers à modifier :**
- `app/__init__.py` — enregistrer `before_request` global qui appelle `bind_tenant_session(g.current_instance)`.

**Validation :**
- Au démarrage, sans utilisateur connecté, l'app sert `/login`.
- Une fois connecté + instance choisie en session, `tenant_db.session` est bindée à la bonne DB ; un test de bout-en-bout (création d'une écriture) ne touche que la DB cible.

### Phase 3 — Auth utilisateurs (remplace `ADMIN_PASSWORD`)

**Fichiers à modifier :**
- `app/views/auth.py` — réécriture complète :
  - `user_loader` lit `meta_db.User`.
  - `POST /login` : vérifie email + password contre `meta_db.users`, met à jour `last_login_at`, `login_user(user)`.
  - `GET/POST /select-instance` (nouveau).
  - `GET /logout` inchangé.
- `app/templates/auth/login.html` — ajouter champ email + libellés.
- `app/templates/auth/select_instance.html` (nouveau).

**Fichiers à créer :**
- `seed_meta.py` — bootstrap user admin + 1ère instance pointant vers `instance/seconde-nature.db`.

**Validation :**
- Login avec email/mot de passe seed.
- Logout → redirection `/login`.
- Sélection d'instance posée en `session["instance_id"]`.

### Phase 4 — CRUD utilisateurs

**Fichiers à créer :**
- `app/views/users.py` — blueprint `users` avec `index`, `new`, `edit`, `delete`, `toggle_active`.
- `app/templates/users/index.html`, `new.html`, `edit.html`.
- `app/decorators.py` — `@admin_required`.

**Fichiers à modifier :**
- `app/__init__.py` — enregistrer le blueprint `users`.
- `app/templates/base.html` — entrée nav « Utilisateurs » conditionnée à `current_user.is_admin`.

**Validation :**
- Un admin peut créer, éditer, désactiver un autre utilisateur.
- Un non-admin reçoit 403 sur ces routes.
- Suppression de soi-même refusée.

### Phase 5 — CRUD instances

**Fichiers à créer :**
- `app/views/instances.py` — blueprint `instances` avec `index`, `new`, `edit`.
- `app/templates/instances/index.html`, `new.html`, `edit.html`.
- `app/services/instance_provisioning.py` — `create_instance(slug, label, database_url)` : crée le fichier SQLite si besoin, applique les migrations tenant sur cette DB, exécute `seed_accounts.py` sur cette DB.

**Fichiers à modifier :**
- `app/__init__.py` — enregistrer le blueprint `instances`.
- `app/templates/base.html` — entrée nav « Instances » conditionnée à `is_admin` + badge d'instance courante.

**Validation :**
- Création d'une nouvelle instance via UI : le fichier `instance/tenants/<slug>.db` apparaît, contient 783 comptes + 6 journaux.
- Bascule entre instances : les écritures de l'une ne sont jamais visibles depuis l'autre.

### Phase 6 — Polish & migration

**Tâches :**
- Mettre à jour `doc/installation.md` (nouveau bootstrap : `flask db upgrade --directory=migrations_meta` + `python seed_meta.py`).
- Mettre à jour `doc/architecture.md` (section « Multi-tenant et auth »).
- Mettre à jour `doc/routes.md` (nouvelles routes `/users/*`, `/instances/*`, `/select-instance`).
- Ajouter `doc/multi_tenant.md` (modèle d'architecture, schéma des deux DBs, procédure de provisioning).
- Tests :
  - `tests/test_meta_auth.py` — login, logout, sélection instance, CRUD users.
  - `tests/test_tenant_isolation.py` — créer 2 instances, vérifier qu'une écriture créée dans l'une n'est pas visible dans l'autre.
  - `tests/conftest.py` — fixtures pour méta-DB + DB tenant temporaires (deux fichiers tmp).

---

## 7. Dépendances entre phases

```
Phase 1 (méta-DB)
    │
    ▼
Phase 2 (routing) ──┬──▶ Phase 3 (auth) ──▶ Phase 4 (CRUD users)
                    │                            │
                    └──▶ Phase 5 (CRUD instances)│
                                                 │
                                                 ▼
                                              Phase 6 (doc + tests)
```

Phase 1 et 2 sont strictement séquentielles. Phases 3 et 5 peuvent être parallélisées une fois 2 terminée, mais 3 doit précéder 4 (besoin du modèle `User` côté flux).

---

## 8. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| **Pollution d'engine cache si la DB d'une instance change** | `database_url` rendu immuable après création (seule `label` + `is_active` éditables). |
| **Migrations tenant non appliquées sur une nouvelle instance** | Le service `instance_provisioning.create_instance` applique systématiquement `alembic upgrade head` après création du fichier SQLite. |
| **Mauvaise instance bindée pendant un long traitement (sync Stancer)** | Les threads de `stancer_async.py` doivent capturer **l'engine tenant courant** au démarrage du thread et le passer explicitement à `tenant_db.session.configure(bind=engine)` à l'intérieur du `app_context()`. À documenter dans le helper. |
| **Test runner partagés** | `conftest.py` doit purger `_ENGINE_CACHE` entre tests pour éviter les fuites. |
| **Suppression accidentelle d'une DB tenant** | Pas de route DELETE sur les instances dans la v1. La désactivation (`is_active=False`) suffit. |
| **Login conservé après désactivation** | Vérification `is_active` à chaque `before_request` sur l'utilisateur en session ; sinon `logout_user()`. |
| **Fuite de session entre instances** | `g.current_instance` recalculé à chaque requête ; jamais mémoïsé hors `g`. |

---

## 9. Hors-périmètre (explicitement non traité)

- **Liaison fine `user × instance`** (autorisations par instance) — extension future.
- **Rôles fins** (comptable / lecture seule) — extension future, table `users` déjà prête à recevoir un champ `role`.
- **SSO / OAuth** — non, login email/password classique uniquement.
- **2FA** — non.
- **Audit log** des actions utilisateur — non.
- **Reset mot de passe par email** — non (admin reset depuis le CRUD users).
- **Switch d'instance sans logout** — supporté via `/select-instance` (pas besoin de logout).
- **Provisioning d'instances Postgres** — supporté par config (`database_url` accepte n'importe quel DSN SQLAlchemy) mais le service de provisioning n'auto-crée pas la base Postgres ; l'admin doit la créer manuellement et fournir un DSN sur une DB déjà existante et vide.

---

## 10. Checkpoints de validation

À cocher manuellement après chaque phase via `/sc:implement` :

- [ ] **Phase 1** — `flask db upgrade` (tenant) et `flask --directory=migrations_meta db upgrade` passent ; `tests/` existants verts.
- [ ] **Phase 2** — au démarrage, accès à `/` redirige vers `/login` puis `/select-instance` puis tableau de bord.
- [ ] **Phase 3** — login email/password depuis `meta.db` ; `last_login_at` mis à jour.
- [ ] **Phase 4** — création/édition/désactivation d'utilisateurs en UI ; 403 pour non-admins.
- [ ] **Phase 5** — création d'une 2e instance via UI ; isolation totale entre les deux DBs vérifiée par test.
- [ ] **Phase 6** — doc à jour, suite de tests verte (`pytest`), `doc/multi_tenant.md` rédigé.

---

## 11. Étape suivante

Le code de ce workflow n'est **pas** écrit. Pour démarrer l'implémentation :

```
/sc:implement claudedocs/workflow_instances_users.md
```

L'implémentation suivra l'ordre des phases ci-dessus. Chaque phase peut être validée indépendamment avant de passer à la suivante.
