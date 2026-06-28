# Référence des routes

Toutes les routes nécessitent d'être authentifié (redirection vers `/login` sinon).  
Les formulaires POST sont protégés par un token CSRF (Flask-WTF).

---

## Paramètres communs des listes datées

Les 8 listes datées de l'application (`/entries/`, `/bank-accounts/<id>/transactions`, `/payouts/`, `/payouts/<id>`, `/orders/`, `/customer-invoices/`, `/reconciliation/`, `/imports/odoo/batch/<name>`) acceptent en plus de leurs filtres spécifiques :

| Paramètre | Valeur | Description |
|-----------|--------|-------------|
| `sort` | `asc` ou `desc` (défaut `desc`) | Sens de tri de la colonne date principale |
| `month` | `YYYY-MM` (ex : `2026-03`) | Filtre `WHERE date >= 1er du mois AND date < 1er du mois suivant` |

Le dropdown de mois est alimenté par les **12 mois de l'exercice comptable courant** (`FiscalYear.closed=False` le plus récent). Le clic sur l'en-tête de date bascule `asc ↔ desc` et conserve tous les autres filtres GET en cours (cf. macros `sortable_date_header` / `month_filter_select` dans `templates/_list_helpers.html`).

---

## Authentification et sélection d'instance

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/login` | Formulaire de connexion (email + mot de passe) |
| POST | `/login` | Vérifie les credentials, crée la session, redirige vers `/select-instance` |
| GET | `/select-instance` | Liste les instances actives. Si une seule, auto-sélection et redirection. |
| POST | `/select-instance` | Pose `session["instance_id"]`, redirige vers `?next=` ou `/` |
| GET | `/logout` | Détruit la session (login + instance), redirige vers `/login` |

**Paramètres POST `/login` :**

| Champ | Type | Description |
|-------|------|-------------|
| `email` | string | Email de l'utilisateur (case-insensitive) |
| `password` | string | Mot de passe (vérifié contre `User.password_hash`) |
| `csrf_token` | string | Token CSRF fourni par le formulaire |

**Paramètres POST `/select-instance` :**

| Champ | Type | Description |
|-------|------|-------------|
| `instance_id` | int | ID de l'instance choisie (parmi celles actives) |
| `csrf_token` | string | Token CSRF |

> Toutes les routes ci-dessous nécessitent d'avoir choisi une instance. Sinon, redirection vers `/select-instance`. Les routes `/users/*` et `/instances/*` font exception : elles ne tapent que dans la méta-base et restent accessibles sans instance sélectionnée.

---

## Utilisateurs (`/users/`) — admin uniquement

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/users/` | Liste tous les utilisateurs |
| GET | `/users/new` | Formulaire de création |
| POST | `/users/new` | Crée l'utilisateur (email unique, mot de passe hashé) |
| GET | `/users/<id>/edit` | Formulaire de modification |
| POST | `/users/<id>/edit` | Met à jour. Champ `password` vide = inchangé. |
| POST | `/users/<id>/delete` | Supprime (interdit sur soi-même) |
| POST | `/users/<id>/toggle-active` | Bascule `is_active` (interdit sur soi-même) |

**Paramètres POST `/users/new` et `/users/<id>/edit` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `email` | oui | Email unique (case-insensitive) |
| `password` | oui (création) / non (édition) | Mot de passe en clair, hashé via `pbkdf2:sha256` |
| `full_name` | non | Nom affiché |
| `is_admin` | non (checkbox) | Donne accès aux CRUD users + instances |
| `is_active` | non (checkbox) | Permet la connexion ; faux = login refusé |

Un admin ne peut pas retirer son propre `is_admin`, se désactiver, ni se supprimer.

---

## Instances (`/instances/`) — admin uniquement

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/instances/` | Liste toutes les instances |
| GET | `/instances/<id>` | Vue détail : infos + liste des sauvegardes |
| GET | `/instances/new` | Formulaire de création |
| POST | `/instances/new` | Crée l'instance + provisionne la DB (mode auto) ou enregistre l'URL (mode manuel) |
| GET | `/instances/import` | Formulaire d'upload (.db / .backup SQLite) |
| POST | `/instances/import` | Si le slug du fichier matche une instance → **restauration** ; sinon → **création** d'une nouvelle instance utilisant le fichier comme seed |
| GET | `/instances/<id>/edit` | Formulaire de modification (slug + URL non modifiables) |
| POST | `/instances/<id>/edit` | Met à jour `label` et `is_active`. Vide le cache d'engine de cette instance. |
| POST | `/instances/<id>/backup` | Crée une sauvegarde atomique SQLite. Refus en non-SQLite. |
| GET | `/instances/<id>/backups/<filename>/download` | Télécharge un fichier de sauvegarde |
| POST | `/instances/<id>/backups/<filename>/delete` | Supprime un fichier de sauvegarde |
| GET | `/instances/<id>/restore` | Formulaire d'upload de sauvegarde |
| POST | `/instances/<id>/restore` | Restaure la DB depuis l'upload (snapshot de sécurité créé avant) |

Le nom de fichier (`<filename>`) doit matcher `(pre-restore-)?<slug>-\d{8}-\d{6}\.db` pour éviter le path traversal.

Voir [doc/backups.md](backups.md) pour le workflow utilisateur détaillé.

## Configuration (`/configuration/external-connections/`) — admin uniquement

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/configuration/external-connections/` | Affiche 4 cartes (Stancer / Odoo / HelloAsso / SMTP) avec les credentials de l'instance courante |
| POST | `/configuration/external-connections/<service>` | Upsert les credentials d'un service. Champ vide = ligne DB supprimée → repli `.env` actif. |
| POST | `/configuration/external-connections/smtp/test` | Teste la connexion au serveur SMTP configuré (NOOP) et affiche le résultat en flash |

Les valeurs sont stockées dans `external_connections` de la base **tenant** (donc per-instance). Les variables d'environnement `STANCER_*`, `ODOO_*`, `HELLOASSO_*`, `MAIL_*` servent de **repli global** quand la table est vide. Service `smtp` : clés `host`, `port`, `use_tls`, `username`, `password`, `sender` (repli `MAIL_SERVER`/`MAIL_PORT`/`MAIL_USE_TLS`/`MAIL_USERNAME`/`MAIL_PASSWORD`/`MAIL_DEFAULT_SENDER`).

---

**Paramètres POST `/instances/new` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `slug` | oui | `^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$`. Sert de nom de fichier SQLite. |
| `label` | oui | Libellé affiché |
| `provisioning_mode` | oui | `auto` (crée le SQLite local + migrations + seed) ou `manual` (URL fournie) |
| `database_url` | oui en mode manuel | URL SQLAlchemy (SQLite ou Postgres) pointant sur une base **déjà** prête |

En mode `auto`, le service `instance_provisioning.provision_sqlite_database` exécute :

1. Validation du slug
2. Refus si `instance/tenants/<slug>.db` existe déjà avec du contenu
3. `flask db upgrade` (subprocess, `DATABASE_URL` surchargé)
4. `python seed_accounts.py` (subprocess) — charge les 783 comptes PCA + 6 journaux

Voir [doc/multi_tenant.md](multi_tenant.md) pour le détail de l'architecture.

---

## Tableau de bord

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/` | Affiche les statistiques de l'exercice courant et les 10 dernières écritures |

---

## Plan comptable (`/accounts/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/accounts/` | Liste tous les comptes. Paramètre `?q=` pour filtrer par code ou libellé |
| GET | `/accounts/new` | Formulaire de création d'un compte |
| POST | `/accounts/new` | Crée le compte |
| GET | `/accounts/<id>/edit` | Formulaire de modification |
| POST | `/accounts/<id>/edit` | Enregistre les modifications |
| GET | `/accounts/search` | **HTMX** — Retourne des `<option>` filtrés (param `?q=`). Utilisé dans les formulaires d'écriture |

**Paramètres POST `/accounts/new` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `code` | oui | Code unique (ex : `512001`) |
| `label` | oui | Libellé |
| `account_type` | oui | Type parmi : `ASSET`, `LIABILITY`, `EQUITY`, `EXPENSE`, `REVENUE`, `TIERS`, `OFFBALANCE`, `OTHER` |
| `parent_code` | non | Code du compte parent |

---

## Exercices comptables (`/fiscal-years/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/fiscal-years/` | Liste tous les exercices |
| GET | `/fiscal-years/new` | Formulaire de création |
| POST | `/fiscal-years/new` | Crée l'exercice |
| POST | `/fiscal-years/<id>/close` | Clôture l'exercice (irréversible) |

> La clôture positionne `FiscalYear.closed = True`. Les écritures de cet exercice ne peuvent plus être supprimées.

---

## Journaux (`/journals/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/journals/` | Liste tous les journaux |
| GET | `/journals/new` | Formulaire de création |
| POST | `/journals/new` | Crée le journal |

---

## Écritures comptables (`/entries/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/entries/` | Liste les écritures avec actions Modifier / Supprimer. Filtres : `?fy_id=` et `?journal_id=` |
| GET | `/entries/new` | Formulaire de saisie multi-lignes. Paramètre optionnel `?bt_id=<bank_transaction_id>` pour pré-remplir depuis une transaction bancaire (date, journal `BQ`, exercice englobant la date, ligne 5121 au débit ou crédit selon le signe du montant). |
| POST | `/entries/new` | Valide et enregistre l'écriture. Si `bt_id` est présent, rapproche automatiquement la transaction bancaire à la ligne d'écriture côté banque et redirige vers `/reconciliation/`. |
| GET | `/entries/<id>` | Détail d'une écriture avec toutes ses lignes |
| GET | `/entries/<id>/edit` | Formulaire pré-rempli pour modifier l'écriture (interdit si FY clôturé ou si une ligne est rapprochée à une transaction bancaire) |
| POST | `/entries/<id>/edit` | Remplace les lignes existantes par les nouvelles, met à jour l'en-tête (date, journal, exercice, description). La référence d'origine est conservée. |
| POST | `/entries/<id>/delete` | Supprime l'écriture (interdit si FY clôturé) |
| GET | `/entries/new-line` | **HTMX** — Retourne une ligne HTML vide à ajouter au formulaire. Paramètre `?index=` |

**Paramètres POST `/entries/new` (formulaire multi-valeurs) :**

| Champ | Description |
|-------|-------------|
| `fiscal_year_id` | ID de l'exercice |
| `journal_id` | ID du journal |
| `entry_date` | Date au format `YYYY-MM-DD` |
| `description` | Libellé libre |
| `account_id[]` | IDs des comptes (tableau) |
| `line_label[]` | Libellés des lignes (tableau) |
| `debit[]` | Montants débit en euros avec décimales (tableau) |
| `credit[]` | Montants crédit en euros avec décimales (tableau) |

L'écriture est refusée si Σ débit ≠ Σ crédit (message flash d'erreur).

---

## Comptes bancaires (`/bank-accounts/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/bank-accounts/` | Liste tous les comptes bancaires avec statistiques (total transactions, non rapprochées) |
| GET | `/bank-accounts/new` | Formulaire de création |
| POST | `/bank-accounts/new` | Crée le compte bancaire |
| GET | `/bank-accounts/<id>/edit` | Formulaire de modification |
| POST | `/bank-accounts/<id>/edit` | Enregistre les modifications |
| POST | `/bank-accounts/<id>/delete` | Supprime le compte (interdit s'il a des transactions) |
| GET | `/bank-accounts/<id>/transactions` | Liste les transactions importées. Paramètre `?unreconciled=1` pour filtrer les non rapprochées |

**Paramètres POST `/bank-accounts/new` et `/bank-accounts/<id>/edit` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `label` | oui | Nom affiché (ex : `CIC Compte courant`) |
| `iban` | non | IBAN — les espaces sont supprimés automatiquement |
| `account_id` | oui | ID du compte GL 512x associé |

> Le formulaire ne propose que les comptes dont le code commence par `51` et qui ne sont pas des comptes d'en-tête (`is_header = False`).

---

## Imports (`/imports/`)

### Import OFX

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/imports/ofx` | Formulaire d'import OFX avec liste des comptes bancaires |
| POST | `/imports/ofx` | Upload du fichier, parse et insère les transactions non-dupliquées |

**Paramètres POST :**

| Champ | Description |
|-------|-------------|
| `bank_account_id` | ID du compte bancaire cible |
| `ofx_file` | Fichier OFX (`.ofx` ou `.qfx`) |

**Réponse :** message flash avec le nombre de transactions importées, doublons et erreurs.

### Import Odoo

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/imports/odoo` | Formulaire d'import CSV avec liste des lots existants |
| POST | `/imports/odoo` | Upload du fichier CSV, staging dans `odoo_import_lines` |
| GET | `/imports/odoo/batch/<batch_name>` | Détail de toutes les lignes d'un lot |

**Paramètres POST :**

| Champ | Description |
|-------|-------------|
| `csv_file` | Fichier CSV (export Odoo) |
| `batch_name` | Nom du lot (optionnel, généré automatiquement si vide) |

---

## Rapprochement bancaire (`/reconciliation/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/reconciliation/` | Liste les transactions non rapprochées. Filtre : `?bank_account_id=` |
| GET | `/reconciliation/suggest/<bt_id>` | **HTMX** — Retourne les lignes d'écriture candidates pour une transaction |
| POST | `/reconciliation/link` | Lie une transaction à une ligne d'écriture |
| POST | `/reconciliation/unlink/<bt_id>` | Supprime le lien de rapprochement |
| POST | `/reconciliation/auto` | Rapprochement automatique (correspondances exactes date + montant) |

**Paramètres POST `/reconciliation/link` :**

| Champ | Description |
|-------|-------------|
| `bank_transaction_id` | ID de la transaction bancaire |
| `journal_line_id` | ID de la ligne d'écriture à lier |

---

## Entités (`/entities/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/entities/` | Liste toutes les entités (hors `ADHERENT`) avec dates de dernière adhésion HelloAsso et POS |
| GET | `/entities/members` | Liste des adhérents (`entity_type='ADHERENT'`). Colonnes calculées **Date anniversaire** et **Statut** (pilule de couleur). Paramètres : `?q=`, `?date_from=`, `?date_to=`, `?sort_by=name\|birthday\|status`, `?sort=asc\|desc` |
| GET | `/entities/members/export` | Export des adhérents — `?format=csv\|xlsx` (alias `xls`→`xlsx`), mêmes filtres + tri que `/members`. Colonnes : Nom, Email, Adhérent, Dernière adh. HA, Dernière adh. POS, Date anniversaire, Statut, Couleur, Notes |
| GET | `/entities/members.csv` | Compat : redirige (302) vers `/members/export?format=csv` |
| GET/POST | `/entities/members/reminders` | GET = preview des adhérents expirés (statut rouge + email) ; POST = envoie les relances par email (Flask-Mail) |
| GET/POST | `/entities/members/reminder-template` | Édition du gabarit d'email de relance (modèle `EmailTemplate`, clé `membership_reminder`) |
| GET | `/entities/<id>` | Vue détail : commandes POS Odoo + factures clients + (si adhérent) commandes/articles/paiements HelloAsso |
| GET | `/entities/new` | Formulaire de création |
| POST | `/entities/new` | Crée l'entité |
| GET | `/entities/<id>/edit` | Formulaire de modification |
| POST | `/entities/<id>/edit` | Enregistre les modifications |
| POST | `/entities/<id>/delete` | Supprime l'entité (interdit si des transactions y sont liées) |
| POST | `/entities/sync-helloasso` | Lance la synchronisation HelloAsso (synchrone, voir [services.md](services.md#helloasso_syncpy--synchronisation-helloasso)) |
| GET | `/entities/create-helloasso-memberships` | Preview des tiers ayant une adhésion POS sans adhésion HelloAsso |
| POST | `/entities/create-helloasso-memberships` | Crée les adhésions manquantes côté HelloAsso via l'API |

**Paramètres POST `/entities/new` et `/entities/<id>/edit` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `name` | oui | Nom unique (max 200 caractères) |
| `entity_type` | non | `CLIENT`, `FOURNISSEUR`, `SALARIE`, `ADHERENT`, `ORGANISME` ou `AUTRE` (défaut) |
| `account_code` | non | Code compte GL associé |
| `email` | non | Email — clé de rattachement HelloAsso/Odoo |
| `is_member` | non (checkbox) | Marque le tiers comme adhérent |
| `notes` | non | Notes libres |

---

## Moteur de règles (`/rules/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/rules/` | Liste toutes les règles (table `rules` de l'instance courante) avec actions Modifier / Activer-Désactiver / ↑↓ / Supprimer |
| GET | `/rules/new` | Formulaire de création (inclut l'aide REGEX + testeur live) |
| POST | `/rules/new` | Crée la règle (position = max+1) |
| GET | `/rules/<id>/edit` | Formulaire de modification |
| POST | `/rules/<id>/edit` | Met à jour la règle |
| POST | `/rules/<id>/delete` | Supprime la règle |
| POST | `/rules/<id>/toggle-active` | Bascule `is_active` |
| POST | `/rules/<id>/move-up` | Échange position avec la règle au-dessus |
| POST | `/rules/<id>/move-down` | Échange position avec la règle au-dessous |
| POST | `/rules/apply` | Applique les règles aux transactions non catégorisées et génère les écritures pour celles avec `account_code` |

**Paramètres POST `/rules/new` et `/rules/<id>/edit` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `name` | oui | Libellé court |
| `label_contains` | non | Sous-chaîne (case-insensitive) |
| `label_regex` | non | Regex Python (validée serveur via `re.compile`) |
| `amount_min` / `amount_max` | non | En euros, convertis en centimes |
| `raw_type` | non | Filtre type OFX |
| `entity_name` / `entity_type` | non | Tiers à rattacher (créé si nécessaire) |
| `category` | non | Étiquette libre |
| `account_code` | non | Code 6xx/7xx du plan comptable — déclenche la génération d'écriture |
| `is_active` | non (checkbox) | Activer la règle |

Au moins une condition (`label_contains`, `label_regex`, `amount_min`, `amount_max`, `raw_type`) est obligatoire — sinon le formulaire est refusé.

**Paramètres POST `/rules/apply` :**

| Champ | Description |
|-------|-------------|
| `overwrite` | `1` pour ré-appliquer les règles sur les transactions déjà catégorisées |

**Effet sur les écritures :** pour chaque règle qui définit `account`, une écriture est créée dans le journal `BQ` :
- compte commençant par `6` (charge) → débit du compte 6xx, crédit du compte bancaire
- compte commençant par `7` (produit) → débit du compte bancaire, crédit du compte 7xx

La transaction bancaire est automatiquement rapprochée à la ligne d'écriture côté banque. La page affiche également la syntaxe YAML de référence pour créer ou modifier les règles.

---

## Versements Stancer (`/payouts/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/payouts/` | Liste des versements importés (triés par `date_payout` descendante). Affiche montant net, frais, nombre de paiements, badge « rapprochée » si `bank_transaction_id` est renseigné, statut. Affiche aussi l'état du dernier `SyncJob` (zone `#sync-status-zone`). Indique si la clé API est configurée. |
| GET | `/payouts/<id>` | Vue détail : en-tête du payout (dates, montant, frais, opération bancaire rattachée si présente) + tableau des paiements liés (date, méthode, client, montant, statut). Affiche l'état du dernier job concernant ce payout (sync globale ou sync ciblée). |
| POST | `/payouts/sync` | **Lancement asynchrone** d'un job `kind='payouts'` via `stancer_async.start_sync_payouts(app)`. Retourne immédiatement (le thread tourne en arrière-plan) : en HTMX, renvoie le fragment `_sync_status.html` ; en non-HTMX, redirige vers `/payouts/`. Idempotent : un re-clic pendant qu'un job tourne ne crée pas de doublon. |
| POST | `/payouts/<id>/sync-payments` | **Lancement asynchrone** d'un job `kind='payout_payments'` ciblé. Même contrat : fragment HTMX si possible, sinon redirection. |
| GET | `/payouts/sync/status/<job_id>` | **Polling HTMX** : retourne le fragment `_sync_status.html` du job. Tant que `status='running'`, le fragment se ré-interroge automatiquement toutes les 2 s (`hx-trigger="every 2s"`). 404 si l'`id` est inconnu. |

**Workflow utilisateur :**

1. L'utilisateur clique sur « Récupérer les versements via l'API ».
2. Le formulaire `hx-post="/payouts/sync"` cible la zone `#sync-status-zone`. La réponse est le fragment `_sync_status.html` du nouveau `SyncJob`.
3. Le fragment porte `hx-get="/payouts/sync/status/<id>" hx-trigger="every 2s"`. Toutes les 2 s, il se rafraîchit en place.
4. Le thread de sync met à jour `progress_done` / `message` au fil du traitement (throttle = 1 écriture sur 5).
5. Quand le job passe à `done` ou `failed`, l'attribut `hx-trigger` disparaît du fragment → le polling s'arrête. Un lien « Recharger la page » apparaît pour rafraîchir la liste avec les nouvelles données.

**Configuration requise** : variables d'environnement `STANCER_SECRET_KEY` (clé secrète de l'espace Stancer, format `sk_xxx`) et facultativement `STANCER_MODE` (`live` ou `test`).

Le bouton de synchronisation est désactivé tant que `STANCER_SECRET_KEY` n'est pas définie.

**Auth Stancer** : HTTP Basic, login = `STANCER_SECRET_KEY`, password vide.

---

## Commandes POS Odoo (`/orders/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/orders/` | Liste des commandes Point de Vente synchronisées (modèle Odoo `pos.order`). Limite d'affichage : 500. Tri/filtre mois standard. |
| GET | `/orders/<id>` | Vue détail : en-tête + cartes Total / TVA / Payé / Rendu monnaie + tableau des lignes + tableau des paiements |
| POST | `/orders/sync` | **Synchrone** — lance `sync_pos_orders()` (XML-RPC). Le bouton est désactivé si `ODOO_URL` / `ODOO_DB` / `ODOO_USERNAME` / `ODOO_API_KEY` ne sont pas définis dans `.env`. |

**Effets de la sync** :
- Upsert `pos.order` → `orders` (clé d'idempotence : `odoo_id`)
- Upsert `pos.order.line` → `order_lines` (CASCADE)
- Upsert `pos.payment` → `order_payments` (CASCADE)
- Création auto d'`Entity(entity_type='CLIENT')` par email pour chaque `res.partner` rencontré
- Bascule `is_member=True` + `entity_type='ADHERENT'` pour tout tiers ayant une ligne de commande "Adhésion" (matching `LIKE %adh%sion%`)

---

## Factures clients Odoo (`/customer-invoices/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/customer-invoices/` | Liste des factures clients Odoo (modèle `account.move` filtré `move_type='out_invoice'`). Limite d'affichage : 500. Tri/filtre mois standard + filtres `state`, `payment_state`, `q`. |
| GET | `/customer-invoices/<id>` | Vue détail : cartes HT / TVA / TTC / Reste dû + infos numéro/référence/origine/journal + double badge état comptable + état paiement + tableau des lignes |
| POST | `/customer-invoices/sync` | **Synchrone** — lance `sync_customer_invoices()` (XML-RPC). Désactivé si les variables `ODOO_*` ne sont pas définies. |

**Paramètres GET sur `/customer-invoices/` :**

| Param | Description |
|-------|-------------|
| `state` | `draft`, `posted`, `cancel` |
| `payment_state` | `not_paid`, `in_payment`, `partial`, `paid`, `reversed`, `invoicing_legacy` |
| `q` | Recherche insensible à la casse sur `name`, `partner_name`, `partner_email`, `ref` |
| `sort` / `month` | Voir paramètres communs en tête |

**Effets de la sync** :
- Upsert `account.move` → `customer_invoices`
- Upsert `account.move.line` filtré produit (`display_type='product'` ou `product_id` non vide) → `customer_invoice_lines` (CASCADE)
- Création auto d'`Entity(entity_type='CLIENT')` par email du partenaire (idempotent : si email déjà connu, le tiers existant est réutilisé)
- **Aucun** marquage `is_member` (les factures clients n'impliquent pas d'adhésion)

---

## Tableau de bord (`/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/?fy_id=<id>` | Tableau de bord de l'exercice. Si `fy_id` n'est pas fourni, l'exercice le plus récent (`start_date desc`) est sélectionné par défaut. |

Le tableau de bord affiche :
- Quatre cartes d'indicateurs : nombre d'écritures, transactions non rapprochées **sur la période de l'exercice**, écritures déséquilibrées, dates et statut de l'exercice.
- Trois graphiques ECharts :
  - **Résultat mensuel** — barres Produits (7x) / Charges (6x) + courbe Net.
  - **Ventes mensuelles** — barres sur les comptes 70x.
  - **Solde bancaire** — courbe cumulée fin de mois (base = total des transactions antérieures à l'exercice).
- Liste des 10 dernières écritures de l'exercice.

---

## États financiers (`/reports/`)

Tous les rapports acceptent le paramètre `?fy_id=` pour sélectionner l'exercice.

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/reports/balance` | Balance des comptes (tous les comptes avec mouvements) |
| GET | `/reports/grand-livre` | Grand livre d'un compte. Paramètre supplémentaire : `?account_id=` |
| GET | `/reports/bilan` | Bilan actif/passif, comparaison N / N-1 |
| GET | `/reports/compte-de-resultat` | Compte de résultat, comparaison N / N-1 |
| GET | `/reports/compte-de-resultat.csv` | Export CSV (séparateur `;`, UTF-8 BOM, virgule décimale) du compte de résultat |
| GET | `/reports/compte-de-resultat.ods` | Export ODS (OpenDocument Spreadsheet) avec formules `=SUM`, `[.B<row>]`, styles et format monétaire |

Tous les rapports disposent d'un bouton "Imprimer" qui déclenche `window.print()` avec les éléments de navigation masqués (CSS `@media print`).

---

## Indicateurs — Visibilité & Impact (`/impact/`)

Regroupées dans le menu **« Indicateurs »**. Période sélectionnable (`?gran=month|quarter|year|custom`, `?month=`, `?quarter=`, `?year=`, `?start=&end=`).

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/impact/` | Tableau de bord (4 dimensions : visibilité, **environnemental**, social, économique) + agrégats phares |
| GET | `/impact/report` | Vue rapport imprimable (impression navigateur) |
| GET | `/impact/export.xlsx` | Export XLSX des métriques de la période |
| GET, POST | `/impact/factors` | Facteurs d'impact ADEME éditables (**admin**) |
| GET, POST | `/impact/manual` | Saisie manuelle mensuelle (Vinted, Facebook…) |
| POST | `/impact/sync` | Synchronisation des connecteurs externes (GA4, Facebook) |

> **Impact environnemental** : `CO₂ évité`, `poids réemployé`, `taux de réemploi`, `km voiture` sont calculés (`impact_engine.compute`) à partir des **tonnages éco-organismes** (table `eco_declarations`, cf. import ci-dessous), et **non** des ventes. Le dashboard et le rapport d'activité affichent donc le même CO₂.

## Indicateurs — Rapport d'activité (`/rapport-activite/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/rapport-activite/` | Aperçu du rapport (sélecteur d'exercice, mode prorata éco `?prorata=`) |
| GET | `/rapport-activite/pdf` | PDF serveur (weasyprint), rendu inline |
| GET | `/rapport-activite/export/<fmt>` | Export `html` \| `docx` \| `odt` (pièce jointe, **styles inclus**). HTML autonome (CSS inliné, images data-URI, graphes SVG) ; DOCX/ODT via LibreOffice headless |
| GET, POST | `/rapport-activite/edit` | Éditeur des blocs narratifs — **WYSIWYG Quill** (**admin**) |
| POST | `/rapport-activite/edit/import-site` | Pré-remplissage des blocs depuis le site (**admin**) |
| GET, POST | `/rapport-activite/eco` | Table des **tonnages éco-organismes** : édition + import `.xlsx` (**admin**) |
| POST | `/rapport-activite/eco/import` | Upload `.xlsx` (feuille `Bilan`) → `import_eco_xlsx` (**admin**) |
| GET, POST | `/rapport-activite/photos` | Upload / légendes des photos (**admin**) |
| GET | `/rapport-activite/photo/<id>` | Sert une photo (authentifié) |
| POST | `/rapport-activite/logo` · `/logo/delete` | Logo de structure (**admin**) |
| GET | `/rapport-activite/logo-file` | Sert le logo |
| POST | `/rapport-activite/archive` | Fige une version PDF archivée (**admin**) |
| GET | `/rapport-activite/archives` · `/archive/<id>` | Liste / consultation des archives ; `/archive/<id>/delete` (POST, **admin**) |

L'**import de tonnages** (`/rapport-activite/eco`) est également proposé dans le menu **Imports/Exports** (admin). Le bouton « Imprimer » a été remplacé par les exports PDF / HTML / DOCX / ODT.
