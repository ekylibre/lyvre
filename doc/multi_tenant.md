# Multi-tenant et gestion des utilisateurs

L'application sépare les **données globales** (utilisateurs, déclaration des
instances) des **données comptables** (écritures, comptes, payouts, etc.).
Chaque association = une base SQLite (ou Postgres) distincte ; un même
utilisateur peut basculer entre les instances auxquelles il a accès.

---

## Deux bases de données

| Base | Tables | Configurée par | Schéma |
|------|--------|----------------|--------|
| **Méta** (`instance/meta.db`) | `users`, `instances` | `META_DATABASE_URL` | Créée par `seed_meta.py` via `db.create_all(bind_key=['meta'])` |
| **Tenant** (`instance/<slug>.db`) | Toutes les tables comptables (accounts, journals, journal_entries, …) | `database_url` dans `instances` | Géré par Alembic (`migrations/`) |

La méta-base est unique et stable. Il y a **autant de bases tenant que d'instances** déclarées.

---

## Routage par requête

Un seul objet `SQLAlchemy` (`app.extensions.db`) est partagé. La sélection de
l'engine se fait dans une classe `Session` custom :

```python
# app/extensions.py
class MultiTenantSession(FSASession):
    def get_bind(self, mapper=None, ...):
        # 1. Modèle avec __bind_key__='meta' → engine méta
        # 2. Sinon, si g.tenant_engine est posé → engine tenant
        # 3. Sinon → engine par défaut (DATABASE_URL)
```

Les modèles `User` et `Instance` portent `__bind_key__ = "meta"` et tapent
toujours dans `instance/meta.db`. Tous les autres modèles n'ont pas de
`__bind_key__` et tapent dans l'engine tenant rebindé par requête.

Le `before_request` hook (`app/tenant.py`) :

1. Vérifie que l'utilisateur est authentifié.
2. Charge l'instance sélectionnée depuis `session["instance_id"]`.
3. Récupère/crée un `Engine` en cache (`_ENGINE_CACHE[instance.id]`).
4. Pose `g.tenant_engine` + `g.current_instance`.

Le cache d'engines est purgé via `clear_engine_cache(instance.id)` quand
l'admin modifie une instance.

---

## Flux utilisateur

```
GET /                       → 302 /login
POST /login                 → 302 /select-instance
GET /select-instance        → si 1 instance active → 302 /
                              sinon → page avec liste radio
POST /select-instance       → pose session["instance_id"], 302 /
GET / (any tenant page)     → before_request bind l'engine, rend la page
GET /logout                 → vide session + logout, 302 /login
```

Le menu utilisateur (en haut à droite) propose :

- **Changer d'instance** (toujours visible)
- **Utilisateurs** (admin uniquement)
- **Instances** (admin uniquement)
- **Déconnexion**

Le badge bleu dans la nav affiche le libellé de l'instance courante.

---

## CRUD utilisateurs (`/users/`)

Réservé aux admins (`@admin_required` qui retourne 403 sinon).

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/users/` | Liste tous les utilisateurs |
| GET | `/users/new` | Formulaire de création |
| POST | `/users/new` | Crée l'utilisateur (email unique, mot de passe hashé pbkdf2) |
| GET | `/users/<id>/edit` | Formulaire de modification |
| POST | `/users/<id>/edit` | Met à jour. Champ password vide = inchangé. |
| POST | `/users/<id>/delete` | Supprime (interdit sur soi-même) |
| POST | `/users/<id>/toggle-active` | Bascule `is_active` (interdit sur soi-même) |

**Garde-fous** :
- Un admin ne peut pas se retirer son propre statut admin, se désactiver ou se supprimer.
- Les comptes désactivés sont déconnectés au prochain `before_request`.
- L'unicité de l'email est case-insensitive (`func.lower(User.email)`).

---

## CRUD instances (`/instances/`)

Réservé aux admins.

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/instances/` | Liste toutes les instances |
| GET | `/instances/new` | Formulaire de création |
| POST | `/instances/new` | Crée l'instance + provisionne la DB selon le mode choisi |
| GET | `/instances/<id>/edit` | Modifier libellé + statut |
| POST | `/instances/<id>/edit` | Met à jour. `slug` et `database_url` sont en lecture seule. |

### Mode "Automatique" (SQLite local)

Le service `app/services/instance_provisioning.py` :

1. Valide le slug (`^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$`).
2. Construit l'URL `sqlite:///tenants/<slug>.db`.
3. Crée `instance/tenants/` si besoin.
4. Refuse de continuer si le fichier existe déjà avec du contenu.
5. Lance `flask db upgrade` dans un subprocess avec `DATABASE_URL` surchargé.
6. Lance `python seed_accounts.py <chart>` dans un subprocess (plan comptable choisi dans le formulaire).

Coût : ~3-5 secondes pour 1 instance neuve. Subprocess isolé pour ne pas
perturber l'état Flask-Migrate de l'app principale.

### Plan comptable de l'instance

Le formulaire de création propose un **plan comptable** (`chart`), mémorisé dans
`instances.chart` et non modifiable ensuite :

| Valeur | Référentiel | Usage |
|--------|-------------|-------|
| `asso` (défaut) | `data/plan_comptable_asso.json` — 783 comptes | Association loi 1901 |
| `sci` | `data/plan_comptable_sci.json` — 576 comptes | Société civile immobilière |
| `societe` | `data/plan_comptable_societe.json` — 837 comptes (PCG 2026) | Société commerciale (SAS, SASU) |

Le plan comptable de l'instance courante (`app.tenant.current_chart()`) pilote :

- **le référentiel chargé** au provisioning automatique (`seed_accounts.py <chart>`) ;
- **les menus** : `app/menu_config.py` déclare tous les menus et sous-menus avec la liste des
  plans pour lesquels ils apparaissent (`charts`). Les fonctionnalités propres aux associations
  (Adhérents, Temps de travaux, Versements Stancer, menus Odoo et Indicateurs, Import de
  tonnages) sont masquées pour une SCI ou une société. `build_nav(chart, is_admin)` filtre aussi par droits
  admin et masque les menus déroulants vides ; le résultat est injecté dans `base.html`
  (variable `nav_menus`) ;
- **le Bilan et le Compte de résultat** (voir [reports.md](reports.md)) ;
- **les fonctions réservées aux associations** (`app.tenant.is_association()`, `useIsAssociation()`
  côté client) : reçus fiscaux, adhérents et bénévolat, temps de travaux, comptabilité simplifiée,
  indicateurs et rapport d'activité, fonds dédiés de la clôture, tuile « Adhésions » du tableau de
  bord, RNA et signataire des reçus (Structure). Le menu les masque, et `app/association_only.py`
  refuse aussi une adresse saisie à la main : 403 `association_only` pour l'API, 404 pour les pages.
  Les champs d'association envoyés pour une autre structure sont ignorés, et ceux déjà en base sont
  seulement masqués. À l'inverse, le bloc Associés de la Structure n'existe pas pour une association.

En mode manuel, le plan est mémorisé mais aucun compte n'est chargé : l'admin lance
lui-même `seed_accounts.py <chart>` sur la base.

### Mode "Manuel"

L'admin fournit une `database_url` arbitraire (SQLite préexistant, Postgres, …).
Le service ne fait que la mémoriser. À l'admin de provisionner le schéma
côté DB (Postgres : `createdb`, puis `flask db upgrade` avec `DATABASE_URL` pointant
sur cette base).

---

## Migrations

### Tenant

Le pipeline Alembic existant (`migrations/`) cible **uniquement les tables du
bind par défaut** grâce à `target_db.metadatas[None]` dans `env.py`. Les modèles
`User` et `Instance` (bind `meta`) sont automatiquement exclus.

Pour appliquer une nouvelle migration à **toutes** les instances tenant :

```bash
# Sur la 1ère instance (DATABASE_URL pointe dessus par défaut)
FLASK_APP=run.py flask db upgrade

# Sur les autres instances
for db_path in instance/tenants/*.db; do
    DATABASE_URL="sqlite:///$(realpath $db_path)" FLASK_APP=run.py flask db upgrade
done
```

### Méta

Le schéma des tables `users` / `instances` est créé par `db.create_all(bind_key=['meta'])`
dans `seed_meta.py`. Pas d'Alembic à ce jour.

Si une évolution du schéma méta est nécessaire (ex : ajouter `User.role`), procéder
manuellement :

1. Ajouter la colonne dans le modèle.
2. Ouvrir `instance/meta.db` avec `sqlite3` et exécuter l'`ALTER TABLE`.
3. Documenter le changement ici.

À terme, un pipeline Alembic dédié (`migrations_meta/`) pourra être ajouté.

---

## Points d'attention

| Sujet | Comportement |
|-------|--------------|
| **Cache d'engines** | Mémoïsé par `instance_id`. Reconstruit après `clear_engine_cache`, lui-même appelé sur edit d'instance. Le `database_url` est intentionnellement en lecture seule en UI pour éviter d'oublier le purge. |
| **Threads asynchrones (Stancer, Qonto : transactions et factures d'achat)** | Toujours passer par `services/sync_jobs.start` : il capture l'instance courante avant de rendre la main, puis, dans le thread, crée un `app.app_context()` et **pose `g.current_instance` / `g.tenant_engine`** pour que les requêtes SQLAlchemy tapent dans la base de l'instance (sans cela, elles retomberaient sur la base par défaut — anomalie corrigée en octobre 2026). |
| **Désactivation d'utilisateur** | Vérifiée à chaque `before_request`. Un user désactivé pendant qu'il est connecté est déconnecté de force au prochain hit. |
| **Désactivation d'instance** | Une instance désactivée disparaît du `/select-instance`. Si elle était sélectionnée, le `before_request` vide la session et redirige. |
| **Suppression d'instance** | **Pas exposée en UI.** Désactiver suffit pour la 1ère version. Une suppression nécessiterait de purger le cache + supprimer le fichier ; à ajouter plus tard avec une vraie confirmation. |
| **Isolation entre instances** | Validée par construction : l'engine est rebindé par requête, et `__bind_key__` route les modèles méta. Aucun risque qu'une requête écriture sur `JournalEntry` n'atteigne la mauvaise base tant que `g.tenant_engine` est correctement posé. |

---

## Credentials externes per-instance

Depuis mai 2026, les credentials Stancer / Odoo / HelloAsso ne vivent plus dans le `.env` global mais dans la table `external_connections` **de chaque base tenant**. Chaque association a donc ses propres clés API.

Qonto suit la même règle : ses identifiants identifient **une** organisation, ils doivent donc être saisis dans l'instance concernée, pas dans le `.env` (repli commun à toutes les instances).

L'UI **Configuration › Intégrations** (admin uniquement) permet de saisir / vider ces valeurs, d'**activer ou désactiver** chaque intégration et de **tester** son fonctionnement. L'interrupteur est enregistré sur l'instance dans la méta-base (`instances.integrations`) ; une intégration est désactivée par défaut et n'existe que pour certaines structures (HelloAsso, GA4, Facebook : associations). Le `.env` n'est un repli qu'en développement (`INTEGRATIONS_ENV_FALLBACK`) : en production, seuls les réglages de l'instance comptent. Voir [integrations.md](integrations.md), dont la mise en place sur une instance existante (`scripts/integrations_report.py`).

Voir [models.md](models.md#externalconnection--credentials-services-externes-tenant) pour le schéma et [routes.md](routes.md#intégrations-configurationintegrations--admin-uniquement) pour les endpoints.

## Règles de catégorisation per-instance

Depuis mai 2026, les règles de catégorisation automatique vivent dans la table `rules` **de chaque base tenant**. Une instance vierge au plan comptable associatif reçoit les règles par défaut via `seed_rules.py` (appelé automatiquement par le provisioning) ; une instance SCI démarre sans règle, celles de `data/rules.yml` étant propres à une association. La gestion (CRUD + réordonnancement + aide REGEX) se fait depuis l'UI `/rules/`.

Voir [models.md](models.md#rule--règle-de-catégorisation-tenant) pour le schéma et [routes.md](routes.md#moteur-de-règles-rules) pour les endpoints.

## Sauvegardes per-instance

Les bases tenant SQLite peuvent être sauvegardées et restaurées depuis l'UI `/instances/<id>`. Les archives vivent dans `instance/backups/<slug>-YYYYMMDD-HHMMSS.zip` (base + pièces jointes de `instance/uploads/<slug>/`). Voir [backups.md](backups.md) pour le workflow utilisateur et les limitations connues.

## Accès par instance et rôles

Table méta `instance_memberships(user_id, instance_id, role)` (`app/access.py`) :

| Rôle | Droits |
|------|--------|
| **Administrateur global** (`users.is_admin`) | Utilisateurs, instances ; administrateur de **toutes** les instances (sans ligne d'accès) |
| `admin` | Tout sur l'instance, dont **Configuration › Accès** et **Intégrations** (`instance_admin_required`) |
| `treasurer` | Saisie, rapprochement, imports, synchronisations ; pas d'administration de l'instance |
| `accountant` (expert-comptable) | **Lecture seule** : tout consulter (écritures, états, pièces, exports) ; toute écriture de l'API est refusée (403 `read_only`) sauf préférences, notifications lues et session |

- Le hook tenant vérifie l'accès **à chaque requête** (`g.instance_role`) : un accès retiré prend
  effet immédiatement (409 `no_instance` → choix d'instance).
- `GET /api/v1/session` ne liste que les instances accessibles et renvoie `role` et `permissions`
  (`write`, `instance_admin`) ; la SPA masque les actions (`useCan`, `<Can>`, `writeOnly`, colonne
  `actions` des tableaux), le serveur fait foi (test : toute route d'écriture de l'API refusée à
  l'expert-comptable).
- Une instance garde au moins un administrateur (hors administrateurs globaux).
- **Reprise** (`seed_meta`, une seule fois, à la création de la table) : chaque utilisateur reçoit
  l'accès à chaque instance existante, `admin` s'il est administrateur global, `treasurer` sinon ;
  un accès retiré ensuite n'est jamais recréé.

## Hors-périmètre (v1)

- ~~Reset de mot de passe par email~~ : fait (« Mot de passe oublié ? » sur la page de connexion ; voir `doc/routes.md`).
- 2FA / SSO.
- Provisioning automatique de bases Postgres (le mode "Manuel" suffit).
- Suppression d'instance.
- Audit log des actions utilisateur.
