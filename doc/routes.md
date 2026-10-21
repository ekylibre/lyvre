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

## Intégrations (`/configuration/integrations/`) — admin uniquement

Blueprint `integrations` (`app/views/integrations.py`). Services : `stancer`, `odoo`, `helloasso`,
`smtp`, `ga4`, `facebook`.

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/configuration/integrations/` | Index : une carte par intégration avec son statut (Opérationnelle, En erreur, Non testée, À configurer, Désactivée) et son dernier test. **Aucun appel réseau.** |
| GET | `/configuration/integrations/<service>` | Détail : interrupteur, formulaire de configuration, dernier test, dernière synchronisation suivie. 404 si service inconnu. |
| POST | `/configuration/integrations/<service>` | Enregistre la configuration puis, si l'intégration est activée et complète, **lance son test**. Champ secret vide = valeur conservée ; case `clear_<clé>` = valeur effacée ; champ non secret vide = ligne supprimée (repli `.env`). |
| POST | `/configuration/integrations/<service>/enabled` | `enabled=1\|0` : active ou désactive l'intégration (l'interrupteur prime sur la base et sur `.env`). |
| POST | `/configuration/integrations/<service>/check` | Lance le test de fonctionnement (« Tester maintenant ») et affiche le résultat en toast. |
| GET | `/configuration/external-connections/` | Ancienne adresse : redirection 301 vers l'index. |

Les secrets (`SECRET_KEYS` de `external_config`) ne sont jamais renvoyés au navigateur. La route
`/configuration/external-connections/smtp/test` a été supprimée (remplacée par `/check`).

Les valeurs sont stockées dans `external_connections` de la base **tenant** (donc per-instance). Les variables d'environnement `STANCER_*`, `ODOO_*`, `HELLOASSO_*`, `MAIL_*` servent de **repli global** quand la table est vide. Service `smtp` : clés `host`, `port`, `use_tls`, `username`, `password`, `sender` (repli `MAIL_SERVER`/`MAIL_PORT`/`MAIL_USE_TLS`/`MAIL_USERNAME`/`MAIL_PASSWORD`/`MAIL_DEFAULT_SENDER`).

---

**Paramètres POST `/instances/new` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `slug` | oui | `^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$`. Sert de nom de fichier SQLite. |
| `label` | oui | Libellé affiché |
| `provisioning_mode` | oui | `auto` (crée le SQLite local + migrations + seed) ou `manual` (URL fournie) |
| `database_url` | oui en mode manuel | URL SQLAlchemy (SQLite ou Postgres) pointant sur une base **déjà** prête |
| `chart` | non (défaut `asso`) | Plan comptable : `asso` (associations) ou `sci` (SCI). Mémorisé sur l'instance ; en mode `auto`, détermine le référentiel chargé |

En mode `auto`, le service `instance_provisioning.provision_sqlite_database` exécute :

1. Validation du slug
2. Refus si `instance/tenants/<slug>.db` existe déjà avec du contenu
3. `flask db upgrade` (subprocess, `DATABASE_URL` surchargé)
4. `python seed_accounts.py <chart>` (subprocess) — charge le plan comptable choisi (783 comptes asso ou 576 comptes SCI) + 6 journaux

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
| POST | `/fiscal-years/<id>/vat` | `vat_liable=1\|0` : exercice soumis ou non à la TVA (exercice ouvert ; vaut pour les comptabilisations suivantes) |

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
| GET | `/entries/` | Liste les écritures avec actions Modifier / Supprimer. Filtres : `?fy_id=`, `?journal_id=`, `?month=`, `?q=` (référence ou description, recherche au fil de la frappe) |
| GET | `/entries/new` | Page de saisie : îlot React **EntryForm** ([guide](saisie_rapprochement.md)). Paramètre optionnel `?bt_id=` pour préremplir depuis une transaction bancaire (date, journal `BQ`, exercice englobant la date, ligne banque au débit ou au crédit selon le signe) ; transaction déjà rapprochée → retour au rapprochement. L'enregistrement passe par `POST /api/v1/entries`. |
| GET | `/entries/<id>` | Détail d'une écriture avec toutes ses lignes |
| GET | `/entries/<id>/edit` | Modification dans l'îlot EntryForm (`PUT /api/v1/entries/<id>`) ; refusée (redirection + message) si l'exercice est clôturé ou si une ligne est rapprochée |
| POST | `/entries/<id>/delete` | Supprime l'écriture et **défait d'abord ses rapprochements** (`ledger.delete_entries`) ; interdit si l'exercice est clôturé |

Les anciennes routes `POST /entries/new`, `POST /entries/<id>/edit`, `/entries/new-line` et
`/accounts/search` (formulaire HTMX) ont été supprimées.

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
| GET | `/bank-accounts/<id>/transactions` | Liste les transactions importées. `?unreconciled=1` : non rapprochées ; `?missing=1` : justificatif manquant ou perdu (Qonto) ; `?no_invoice=1` : débits qu'aucune facture d'achat ne désigne. Badge « Facture n° … » sur les transactions liées. Bloc Qonto (synchro), bandeaux « contreparties à valider » et « annulées encore rapprochées » |
| GET | `/bank-accounts/qonto` | **Admin.** Comptes Qonto de l'organisation (solde, IBAN) et leur rattachement ; même IBAN proposé d'office. Aucun appel à Qonto si l'intégration est indisponible |
| POST | `/bank-accounts/qonto/link` | **Admin.** `qonto_account_id`, `mode=existing` + `bank_account_id`, ou `mode=new` + `label` + `gl_account_id` ; `sync_from` (défaut : début de l'exercice ouvert) |
| POST | `/bank-accounts/<id>/qonto/settings` | **Admin.** `sync_from` ; reculer la date remet le curseur à zéro (synchro complète, sans doublon) |
| POST | `/bank-accounts/<id>/qonto/unlink` | **Admin.** Détache le compte Qonto (transactions conservées) |
| POST | `/bank-accounts/<id>/qonto/sync` | Lance la synchronisation Qonto en arrière-plan (une à la fois par compte) ; en HTMX, renvoie le fragment de suivi |
| GET | `/bank-accounts/<id>/qonto/sync/<job_id>` | Fragment de suivi (rafraîchi toutes les 2 s tant que la synchro tourne), puis résumé |
| GET | `/bank-accounts/<id>/counterparties` | Contreparties de débits sans tiers, groupées, à valider |
| POST | `/bank-accounts/<id>/counterparties` | `action=create` (+ `name`), `link` (+ `entity_id`) ou `ignore`, avec `name_key` / `label` : s'applique à toutes les transactions sans tiers de cette contrepartie |

**Paramètres POST `/bank-accounts/new` et `/bank-accounts/<id>/edit` :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `label` | oui | Nom affiché (ex : `CIC Compte courant`) |
| `iban` | non | IBAN — les espaces sont supprimés automatiquement |
| `account_id` | oui | ID du compte GL 512x associé |

> Le formulaire ne propose que les comptes dont le code commence par `51` et qui ne sont pas des comptes d'en-tête (`is_header = False`).

---

## Catalogue (`/products/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/products/` | Produits actifs (`?archived=1` : archivés aussi), nombre d'utilisations |
| GET/POST | `/products/new`, `/products/<id>/edit` | `name`, `reference`, `kind` (`purchase`/`sale`/`both`), `purchase_account_code` (6…), `sale_account_code` (7…), `vat_rate` (« 20 », « 5,5 ») |
| POST | `/products/<id>/archive` | Archive / réactive |
| POST | `/products/<id>/delete` | Supprime un produit **inutilisé** (sinon refus) |

---

## Factures d'achat (`/purchases/`)

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/purchases/` | Liste ; filtres `q`, `source` (`qonto` / `manual`), `state` (`to_complete`/`ready`/`posted`), `status` (statut Qonto), `entity_id`, `unpaid=1` (ni payée selon Qonto, ni règlement comptabilisé), `no_supplier=1`, `hidden=1`, `month`, `sort`. Bandeaux : à compléter, à revoir, fournisseurs à valider, règlements à remplacer |
| POST | `/purchases/sync` | Lance la synchronisation des factures Qonto en arrière-plan ; en HTMX, fragment de suivi |
| GET | `/purchases/sync/<job_id>` | Fragment de suivi puis résumé |
| POST | `/purchases/sync/settings` | **Admin.** `sync_from` ; reculer la date remet le curseur à zéro (relecture complète, sans doublon) |
| GET | `/purchases/new` | Dépôt du fichier (« Lire la facture ») ; `?manual=1` : formulaire vide |
| POST | `/purchases/new` | `step=read` + `invoice_file` : mise en attente, lecture, formulaire prérempli avec aperçu ; `step=save` + `token`, en-tête (`entity_id` id / `new` + `new_name`, `supplier_vat`, `supplier_siret`, `supplier_iban`, `invoice_number`, `issue_date`, `due_date`, `is_credit_note`, `untaxed`, `tax`, `total`) et lignes (champs répétés), `send_to_qonto=1` : création puis dépôt dans Qonto ; doublon → réaffichage, `confirm_duplicate=1` pour passer outre |
| GET | `/purchases/staged/<token>` | Pièce en attente (aperçu du formulaire) |
| GET/POST | `/purchases/<id>/edit` | En-tête d'une facture saisie non comptabilisée ; `invoice_file` facultatif remplace la pièce |
| GET | `/purchases/<id>/attachment` | Pièce de la facture (`inline` ; `?download=1` : téléchargement) |
| GET | `/purchases/<id>` | Fiche : état et motifs, montants, pièce (aperçu), règlements, lignes éditables, écriture |
| POST | `/purchases/<id>/lines` | Champs répétés `product_id[]`, `account_code[]`, `label[]`, `untaxed[]`, `vat_rate[]`, `vat[]` ; refusé si comptabilisée ; comptabilise si complète |
| POST | `/purchases/<id>/qonto` | Envoie (ou renvoie après échec) la pièce d'une facture saisie à Qonto |
| POST | `/purchases/<id>/payments` | `bank_transaction_id` : règle une facture saisie par une transaction proposée |
| POST | `/purchases/<id>/payments/<payment_id>/delete` | Défait un règlement hors Qonto (écriture supprimée, rapprochement défait) |
| POST | `/purchases/<id>/post` | Comptabilise une facture prête |
| POST | `/purchases/<id>/unpost` | Supprime l'écriture d'achat et réapplique les données Qonto |
| POST | `/purchases/post-ready` | Comptabilise toutes les factures prêtes (puis leurs règlements) |
| GET/POST | `/purchases/suppliers` | Fournisseurs des factures à valider : `action` = `create` (+`name`), `link` (+`entity_id`) ou `ignore`, `name_key`, `label` |
| GET | `/purchases/settlements` | Paiements de factures déjà passés par une écriture de règle (remplaçables) ou manuelle (signalés) |
| POST | `/purchases/settlements/replace` | `transaction_ids` (répété) : remplace les écritures de règle par des règlements 401 / banque |

---

## Imports (`/imports/`)

### Import OFX

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/imports/ofx` | Formulaire d'import OFX avec liste des comptes bancaires |
| POST | `/imports/ofx` | Upload du fichier, parse et insère les transactions non-dupliquées ; puis règle les factures d'achat saisies en attente dont le débit est unique (`purchase_settlement.auto_match`) |

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
| GET | `/reconciliation/` | Espace de rapprochement : îlot React **ReconcileWorkspace** ([guide](saisie_rapprochement.md)). Paramètres `?bank_account_id=` et `?month=YYYY-MM` (repris dans l'URL par l'îlot). Toutes les actions passent par `/api/v1` (ci-dessous). |

Les anciennes routes `/reconciliation/suggest/<id>`, `/link`, `/unlink/<id>` et `/auto` ont été
supprimées.

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
| POST | `/entities/new` | Crée l'entité ; champs fournisseur : `default_product_id`, `vat_number`, `siret` (14 chiffres, espaces et points tolérés ; sinon refus), `iban` |
| GET | `/entities/<id>/edit` | Formulaire de modification |
| POST | `/entities/<id>/edit` | Enregistre les modifications (mêmes champs fournisseur) |
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
| GET | `/reports/bilan` | Bilan actif/passif selon le plan comptable de l'instance, comparaison N / N-1 |
| GET | `/reports/compte-de-resultat` | Compte de résultat selon le plan comptable de l'instance, comparaison N / N-1 |
| GET | `/reports/compte-de-resultat.csv` | Export CSV (séparateur `;`, UTF-8 BOM, virgule décimale) du compte de résultat |
| GET | `/reports/compte-de-resultat.ods` | Export ODS (OpenDocument Spreadsheet) avec formules de totaux (somme des cellules, lignes « dont » exclues), références `[.B<row>]`, styles et format monétaire |

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

---

## API JSON (`/api/v1`)

Utilisée par les îlots React (saisie, rapprochement). Mêmes règles que les pages : session
Flask-Login, instance courante (`app/tenant.py`), CSRF obligatoire en POST/PUT/DELETE via l'en-tête
`X-CSRFToken`. Montants en **centimes entiers**, dates ISO `YYYY-MM-DD`.

**Erreurs** (format unique) :

```json
{"error": {"code": "validation_error", "message": "L'écriture contient des erreurs.",
           "fields": {"lines[1].account_id": "Compte obligatoire."}}}
```

Codes : `bad_request` / `csrf_error` (400), `unauthenticated` (401, jamais de redirection),
`forbidden` (403), `not_found` (404), `method_not_allowed` (405), `conflict` / `no_instance` (409),
`validation_error` (422), `server_error` (500).

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/session` | Utilisateur et instance courants (vérification de session) |
| GET | `/api/v1/accounts?q=&limit=20` | Comptes utilisables (hors regroupement) : début de code, puis mots du libellé (sans accents) |
| GET | `/api/v1/entities?q=&limit=20` | Tiers par nom ou email |
| POST | `/api/v1/entries/validate` | Validation à blanc : `{"errors": {champ: message}}`, rien n'est enregistré |
| POST | `/api/v1/entries` | Crée l'écriture (201 + `Location`) ; `bank_transaction_id` facultatif → création et rapprochement atomiques (409 si la ligne banque ne correspond pas ou si la transaction est déjà rapprochée) |
| GET | `/api/v1/entries/<id>` | Écriture avec ses lignes, `reconciled`, `editable` |
| PUT | `/api/v1/entries/<id>` | Modifie (409 si rapprochée ou exercice clôturé) |
| POST | `/api/v1/entries/bulk-delete` | `{"entry_ids": [...]}` : supprime en défaisant les rapprochements (annulation des règles) |
| GET | `/api/v1/bank-accounts/<id>/transactions` | `?status=unreconciled\|reconciled\|all&month=&sort=` → transactions + `counters` |
| GET | `/api/v1/bank-transactions/<id>/suggestions` | Lignes candidates avec `score` (2 = même date, 1 = ±3 jours) |
| POST | `/api/v1/reconciliations` | `{"items": [{bank_transaction_id, journal_line_id}]}` : rapproche, contrôle par élément |
| POST | `/api/v1/reconciliations/delete` | `{"bank_transaction_ids": [...]}` : défait des rapprochements |
| POST | `/api/v1/reconciliations/auto` | `{bank_account_id, bank_transaction_ids?, dry_run?}` : paires sans ambiguïté (même date, même montant) |
| POST | `/api/v1/bank-transactions/apply-rules` | `{"ids": [...]}` : applique les règles à la sélection |

Les écritures groupées renvoient `{"results": [...], "counters": {...}, "undo": {...}}` : `results`
donne le statut de chaque élément (`ok` / `error` + `message`) et `undo` la requête qui annule la
partie réussie (`{"method": "POST", "url": ..., "body": ...}`), rejouée par l'îlot pour « Annuler ».
