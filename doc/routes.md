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
| GET | `/login` | Page de la SPA (connexion) ; `?next=` suivi seulement s'il désigne une page de l'application |
| GET | `/select-instance` | Page de la SPA (choix de l'instance) ; connexion exigée |
| GET | `/logout` | Détruit la session (login + instance), redirige vers `/login` (lien direct ; la SPA utilise `POST /api/v1/session/logout`) |

Connexion, déconnexion et choix d'instance passent par l'API (`/api/v1/session/*`, ci-dessous). La session ne liste que les instances accessibles à l'utilisateur et renvoie son `role` et ses `permissions` sur l'instance courante.

## Pages de la SPA

Toutes les pages sont servies par la SPA React + Mantine et listées dans `app/spa_routes.json`
(règle Flask, nom d'endpoint d'origine, `public`). Flask y sert la coquille `templates/spa.html` en
GET ; le routeur React affiche la page, qui lit et écrit par l'API `/api/v1`. Les seules autres
routes Flask servent des fichiers (exports CSV / ODS / XLSX, PDF, pièces jointes, sauvegardes) et
`/logout`.

> Toutes les routes ci-dessous nécessitent d'avoir choisi une instance. Sinon, redirection vers `/select-instance`. Les routes `/users/*` et `/instances/*` font exception : elles ne tapent que dans la méta-base et restent accessibles sans instance sélectionnée.

---

## Utilisateurs (`/users/`) — admin uniquement

Pages de la SPA (liste ; la création / modification s'ouvre dans une fenêtre portée par l'URL) : `/users/`, `/users/new`, `/users/<id>/edit`. API (méta-base, sans instance) :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/users` | Utilisateurs (`is_me` pour le compte connecté, `memberships` : instance et rôle) ; `meta` : instances, rôles |
| POST | `/api/v1/users` | `email` (unique, en minuscules), `password` (obligatoire), `full_name`, `is_admin`, `is_active`, `memberships` (`[{instance_id, role}]`, remplace les accès) |
| PATCH | `/api/v1/users/<id>` | Mêmes champs (`password` vide = inchangé) ; `{"is_active"}` seul = activer / désactiver |
| DELETE | `/api/v1/users/<id>` | Supprime (refusé sur soi-même, 409) |

Un admin ne peut pas retirer son propre `is_admin`, se désactiver, ni se supprimer. Les autres
utilisateurs reçoivent 403.

---

## Structure (`/configuration/organization`)

Page de la SPA `/configuration/organization` (modifiable par l'administrateur de l'instance, lisible par tous).

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/organization` | Identité de la structure (créée au besoin avec le nom de l'instance) ; `fec_ready` = SIREN renseigné |
| PUT | `/api/v1/organization` | `name`, `siren` (9 chiffres, clé de Luhn), `rna` (`W` + 9 chiffres), adresse, `purpose`, signataire ; 422 `fields` ; administrateur de l'instance |

## Accès à l'instance (`/configuration/access/`) — administrateur de l'instance

Page de la SPA `/configuration/access/`. API (instance courante, rôle `admin` ou administrateur global ; sinon 403) :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/access/members` | Membres de l'instance (administrateurs globaux compris, non modifiables) : rôle, compte actif ; `meta.roles` |
| POST | `/api/v1/access/members` | `{email, role, full_name?, password?}` : compte existant, sinon créé avec le mot de passe initial (8 caractères au moins, sinon 422) → 201 |
| PATCH | `/api/v1/access/members/<user_id>` | `{role}` ; 409 si l'instance perdait son dernier administrateur |
| DELETE | `/api/v1/access/members/<user_id>` | Retire l'accès (le compte reste) ; même garde |

Rôles et lecture seule de l'expert-comptable : voir [multi_tenant.md](multi_tenant.md#accès-par-instance-et-rôles).

## Instances (`/instances/`) — admin uniquement

Pages de la SPA (méta-base seule, sans instance choisie) : `/instances/` (`/new` et `/<id>/edit` ouvrent la fenêtre de création ou de modification), `/instances/<id>` (`/restore` ouvre la restauration), `/instances/import`. L'URL d'une base est toujours renvoyée **sans son mot de passe** (`postgresql://u:***@hôte/base`). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/instances` | Instances (slug, libellé, base masquée, plan comptable, statut, SQLite ou non) ; `meta.charts` |
| POST | `/api/v1/instances` | Création (paramètres ci-dessous) → 201 ; 422 `fields` (slug invalide ou pris, libellé, URL en mode manuel) |
| GET | `/api/v1/instances/<id>` | Instance et sauvegardes (`filename`, taille, date, pré-restauration, `database_only` pour les anciens `.db`, `download_url`) |
| PATCH | `/api/v1/instances/<id>` | `label`, `is_active` ; vide le cache d'engine de l'instance |
| POST | `/api/v1/instances/<id>/backups` | Sauvegarde `.zip` (base + pièces jointes) → 201 ; 409 hors SQLite |
| DELETE | `/api/v1/instances/<id>/backups/<filename>` | Supprime une sauvegarde (404 si nom invalide ou absent) |
| POST | `/api/v1/instances/<id>/restore` | Multipart `backup_file` + **`confirm` = slug de l'instance** (sinon 422) ; sauvegarde de sécurité `pre-restore-…` créée avant |
| POST | `/api/v1/instances/import` | Multipart `backup_file`, `slug` (déduit du nom sinon), `label` : slug inconnu → **création** (201) ; slug existant → **restauration**, 409 `confirmation_required` tant que `confirm` ≠ slug |

Fichier servi par Flask : `GET /instances/<id>/backups/<filename>/download`. Le nom de fichier doit correspondre à `(pre-restore-)?<slug>-\d{8}-\d{6}\.(zip|db)` (pas de traversée de chemin).

Voir [doc/backups.md](backups.md) pour le workflow utilisateur détaillé.

## Intégrations (`/configuration/integrations/`) — admin uniquement

Pages de la SPA : `/configuration/integrations/`, `/configuration/integrations/<service>`. Services : `stancer`, `odoo`, `helloasso`, `smtp`, `ga4`, `facebook`, `qonto`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/integrations` | Une entrée par intégration : statut (Opérationnelle, En erreur, Non testée, À configurer, Désactivée), dernier test. **Aucun appel réseau.** |
| GET | `/api/v1/integrations/<service>` | Fiche : statut, dernier test, dernière synchronisation suivie, champs (`label`, `input`, `help`, `required`, `secret`, `source` db/env/none, `value` — **toujours vide pour un secret** —, `env_value` pour un non-secret). 404 si service inconnu |
| PUT | `/api/v1/integrations/<service>` | `{values, clear}` : secret vide = valeur conservée, clé dans `clear` = effacée ; non-secret vide = ligne supprimée (repli `.env`). Si l'intégration est activée et complète, **lance son test** |
| POST | `/api/v1/integrations/<service>/enabled` | `{enabled}` : l'interrupteur prime sur la base et sur `.env` |
| POST | `/api/v1/integrations/<service>/check` | Test de fonctionnement (« Tester maintenant ») ; 409 si désactivée ou incomplète |
| GET | `/configuration/external-connections/` | Ancienne adresse : redirection 301 vers la page de la SPA |

Les actions renvoient la fiche à jour et `notices`. Un test (`tests/test_integrations_api.py::test_no_secret_in_any_api_response`) vérifie qu'aucun secret (base ou `.env`) ni mot de passe d'URL de base n'apparaît dans les réponses.

Les valeurs sont stockées dans `external_connections` de la base **tenant** (donc per-instance). Les variables d'environnement `STANCER_*`, `ODOO_*`, `HELLOASSO_*`, `MAIL_*` servent de **repli global** quand la table est vide. Service `smtp` : clés `host`, `port`, `use_tls`, `username`, `password`, `sender` (repli `MAIL_SERVER`/`MAIL_PORT`/`MAIL_USE_TLS`/`MAIL_USERNAME`/`MAIL_PASSWORD`/`MAIL_DEFAULT_SENDER`).

---

**Paramètres de `POST /api/v1/instances` (JSON) :**

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

## Plan comptable (`/accounts/`)

Pages de la SPA (liste ; la création / modification s'ouvre dans une fenêtre portée par l'URL) : `/accounts/` (`?q=` : code ou mots du libellé), `/accounts/new`, `/accounts/<id>/edit`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/chart-of-accounts` | Tous les comptes (`is_header`, `parent_code`) ; `meta.types` |
| POST | `/api/v1/chart-of-accounts` | `code` (unique), `label`, `account_type` (`ASSET`, `LIABILITY`, `EQUITY`, `EXPENSE`, `REVENUE`, `TIERS`, `OFFBALANCE`, `OTHER`), `parent_code` |
| PATCH | `/api/v1/chart-of-accounts/<id>` | `label`, `account_type` (le code ne change pas) |

La recherche des listes de saisie reste `GET /api/v1/accounts?q=` (ci-dessous).

---

## Exercices comptables (`/fiscal-years/`)

Pages de la SPA : `/fiscal-years/` (liste ; la création s'ouvre dans une fenêtre portée par l'URL,
`/fiscal-years/new`) et `/fiscal-years/<id>/closing` (**assistant de clôture**, 8 étapes, ouvert par
« Clôturer… » ; consultable par l'expert-comptable). Guide : [Clôturer un exercice](cloture.md). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/fiscal-years` | Exercices, du plus récent au plus ancien |
| POST | `/api/v1/fiscal-years` | `label`, `start_date`, `end_date` (ISO, fin ≥ début), `vat_liable` |
| PATCH | `/api/v1/fiscal-years/<id>` | `vat_liable` (exercice ouvert ; vaut pour les comptabilisations suivantes) |
| GET | `/api/v1/fiscal-years/<id>/closing` | État de l'assistant : `steps` (état, motif, disponibilité), `checks` recalculés, `inventory`, `inventory_options`, `dedicated_funds`, `result`, `opening` (à-nouveaux prévus et portés), `allocation`, `next_fiscal_year`, `events` (historique) |
| POST | `/api/v1/fiscal-years/<id>/closing/<step>` | Étapes 1 à 5 : `{state: done\|skipped\|todo, note}` ; motif ≥ 5 caractères pour `skipped` ; « contrôles » fait refusé s'il reste une anomalie, « FEC » fait refusé si l'essai à blanc échoue |
| POST · DELETE | `/api/v1/fiscal-years/<id>/inventory[/<entry_id>]` | Écriture d'inventaire `{kind, account_code, amount_cents, label, counterpart_code?}` (OD, dernier jour) |
| POST · DELETE | `/api/v1/fiscal-years/<id>/dedicated-funds[/<fund_id>]` | Ressource affectée `{label, kind: subsidy\|contribution\|public_generosity, amount_cents, resource_account_code?}` ; suppression si aucun mouvement |
| POST | `/api/v1/fiscal-years/<id>/dedicated-funds/<fund_id>/movements` | `{kind: allocation\|use, amount_cents}` : dotation 689x / 19x ou utilisation 19x / 789x |
| DELETE | `/api/v1/fiscal-years/<id>/dedicated-fund-movements/<movement_id>` | Supprime le mouvement et son écriture |
| GET | `/api/v1/fiscal-years/<id>/fec/preview` | FEC à blanc sur l'exercice ouvert (numérotation provisoire annulée) : erreurs, avertissements, relecture, totaux |
| POST | `/api/v1/fiscal-years/<id>/close` | `{final: false}` **clôture provisoire** (trésorier, administrateur ; 422 si une étape 1-5 est à faire) : écritures verrouillées et numérotées. `{final: true}` **clôture définitive** (administrateur) : FEC figé (SHA-256), irréversible |
| POST | `/api/v1/fiscal-years/<id>/reopen` | Administrateur, `{reason}` : clôture provisoire rouverte, numéros retirés, à-nouveaux et extournes de l'exercice suivant supprimés ; 409 si le résultat est affecté ou l'exercice suivant clôturé |
| POST | `/api/v1/fiscal-years/<id>/opening` | `{create_next}` : à-nouveaux (journal AN) et extournes dans l'exercice suivant, créé au besoin ; regénération |
| POST · DELETE | `/api/v1/fiscal-years/<id>/allocation` | `{decided_on, body, lines: [{account_code, amount_cents}]}` : affectation du résultat (OD dans l'exercice suivant) ; DELETE l'annule |
| GET | `/api/v1/fiscal-years/<id>/fec/check` | Contrôles avant export (`errors` bloquantes : SIREN, exercice ouvert, écriture déséquilibrée ou hors dates ; `warnings` : à-nouveaux absents…), puis relecture du fichier produit (`problems`), totaux, nom, empreinte SHA-256, `download_url` |
| GET | `/fiscal-years/<id>/fec` (route Flask) | Téléchargement du FEC (tous les rôles) : fichier figé si l'exercice est clôturé définitivement (409 si son empreinte ne correspond plus), sinon produit à la demande (409 si un contrôle bloque) |

> Une écriture de l'assistant (`INVENTORY`, `DEDICATED_FUND`, `OPENING`, `REVERSAL`,
> `ALLOCATION`) ne se modifie ni ne se supprime depuis les écritures (409) : seulement depuis
> l'assistant.

---

## Journaux (`/journals/`)

Pages de la SPA (liste ; la création / modification s'ouvre dans une fenêtre portée par l'URL) : `/journals/`, `/journals/new`. API : `GET /api/v1/journals`, `POST /api/v1/journals`
(`code` unique, 10 caractères au plus, mis en capitales ; `label`).

---

## Écritures comptables (`/entries/`)

Pages de la SPA : `/entries/` (filtres `fy_id`, `journal_id`, `month`, `q`, `sort`, `page`),
`/entries/new` (`?bt_id=` : depuis une transaction bancaire, retour au rapprochement après
l'enregistrement), `/entries/<id>`, `/entries/<id>/edit` ([guide de saisie](saisie_rapprochement.md)). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/entries` | Liste paginée côté serveur (`page`, `per_page` ≤ 200 ; exercice ouvert le plus récent par défaut) ; `meta` : exercices, journaux, mois de l'exercice |
| GET | `/api/v1/entries/form` | Préparation du formulaire : options (exercices ouverts, journaux, portée des comptes récents) et valeurs initiales ; `?entry_id=` modification (409 si exercice clôturé ou écriture rapprochée), `?bt_id=` création depuis une transaction (409 si déjà rapprochée) |
| POST | `/api/v1/entries/validate` | Validation à blanc |
| POST / PUT | `/api/v1/entries[/<id>]` | Création (`bank_transaction_id` facultatif : création et rapprochement atomiques) / modification |
| GET | `/api/v1/entries/<id>` | Fiche : journal, exercice, origine, lignes, totaux, `reconciled`, `editable` |
| DELETE | `/api/v1/entries/<id>` | Supprime l'écriture et **défait d'abord ses rapprochements** (`ledger.delete_entries`) ; 409 si l'exercice est clôturé |
| PUT | `/api/v1/entries/<id>/lines/<line_id>/project` | `{project_id}` (null : aucun) : projet d'une ligne, même sur une écriture rapprochée ; 409 si exercice clôturé ou écriture de l'assistant |
| POST | `/api/v1/entries/<id>/lines/<line_id>/split` | **Ventilation** `{parts: [{project_id, amount_cents}]}` (≥ 2 parts, total = montant de la ligne) : lignes de même compte et même sens ; 409 sur la ligne rapprochée elle-même |
---

## Comptes bancaires (`/bank-accounts/`)

Pages de la SPA : `/bank-accounts/`, `/bank-accounts/new`, `/bank-accounts/<id>/edit` (fenêtre),
`/bank-accounts/<id>/transactions` (filtres : toutes, à rapprocher, justificatif manquant, débit
sans facture ; mois ; carte Qonto avec synchronisation, date de début, détachement),
`/bank-accounts/<id>/counterparties`, `/bank-accounts/qonto` (admin). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/bank-accounts` | Comptes (compte 512, Qonto, nombre de transactions et à rapprocher) ; `meta.gl_accounts` (51… hors regroupement), état de Qonto |
| POST / PATCH | `/api/v1/bank-accounts[/<id>]` | `label`, `iban` (espaces retirés), `account_id` (compte 51…) |
| DELETE | `/api/v1/bank-accounts/<id>` | 409 si des transactions y sont liées |
| GET | `/api/v1/bank-accounts/<id>` | Compte, dernière synchronisation Qonto (`qonto_job`), nombre de contreparties à valider, transactions annulées encore rapprochées, mois de l'exercice |
| GET | `/api/v1/bank-accounts/<id>/transactions` | `status` = `unreconciled` (défaut) / `reconciled` / `all`, `month`, `sort`, `missing=1`, `no_invoice=1` ; chaque transaction porte justificatif, tiers, écriture, factures d'achat payées |
| GET | `/api/v1/qonto/accounts` | (admin) Comptes Qonto de l'organisation (lecture seule) avec rattachement et compte proposé (même IBAN) ; `error` lisible, secrets masqués |
| POST | `/api/v1/qonto/accounts/link` | (admin) `qonto_account_id`, `mode` = `existing` (+ `bank_account_id`) ou `new` (+ `label`, `gl_account_id`), `sync_from` |
| PATCH / DELETE | `/api/v1/bank-accounts/<id>/qonto` | (admin) Date de début (reculer relance une synchronisation complète, sans doublon) / détacher (transactions conservées) |
| POST | `/api/v1/bank-accounts/<id>/qonto/sync` | Synchronisation en arrière-plan (lecture des transactions Qonto) → `job`, suivi par `/api/v1/jobs/<id>` |
| GET | `/api/v1/bank-accounts/<id>/counterparties` | Contreparties de débits sans tiers, regroupées |
| POST | `/api/v1/counterparties` | `action` = `create` (+ `name`) / `link` (+ `entity_id`) / `ignore`, `key`, `label` |

---

## Projets (`/projects/`)

Pages de la SPA : `/projects/`, `/projects/new`, `/projects/<id>/edit` (Compta › Projets). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/projects` | Projets (archivés en dernier) avec charges (6), produits (7), résultat et nombre de lignes ; `?fiscal_year_id=` limite à un exercice |
| GET | `/api/v1/projects/options` | Projets actifs pour les listes de choix |
| POST · PUT | `/api/v1/projects[/<id>]` | `{name, description, start_date, end_date, manager, archived}` ; nom unique (sans casse), fin ≥ début |
| GET · DELETE | `/api/v1/projects/<id>` | Fiche ; suppression refusée (409) si le projet est utilisé : l'archiver |

Le projet se saisit aussi dans l'éditeur d'écriture (colonne « Projet » si l'instance a des projets ;
`project_id` dans `lines` et dans `GET /api/v1/entries/form`), sur la fiche d'une écriture (affecter,
ventiler), sur les lignes de facture d'achat (`project_id` des `rows`, `meta.projects`) et dans les
règles.

---

## Budget (`/budget/`)

Page de la SPA : `/budget/?fiscal_year_id=&project_id=` (Compta › Budget) : grille comptes × mois,
budget général ou d'un projet, saisie annuelle (répartie par douzièmes) ou mensuelle, copie de
l'exercice précédent à relire avant d'enregistrer. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/budgets/<fy_id>` | `?project_id=` (vide : budget général) : `months`, `rows` (`mode` annual\|monthly, `months`, `total_cents`), `totals`, options de comptes (6 et 7, regroupements compris) et de projets |
| PUT | `/api/v1/budgets/<fy_id>` | `{project_id, rows: [{account_id, annual_cents} \| {account_id, months: [...]}]}` : remplace le budget du périmètre ; 422 si compte hors classes 6/7, doublon, ou compte qui en regroupe un autre |
| GET | `/api/v1/budgets/<fy_id>/copy` | `?source=budget\|actual&project_id=` : grille proposée d'après l'exercice précédent (réalisé regroupé au compte à 3 chiffres), non enregistrée |

---

## Catalogue (`/products/`)

Pages de la SPA (liste ; la création / modification s'ouvre dans une fenêtre portée par l'URL) : `/products/` (`?archived=1`), `/products/new`, `/products/<id>/edit`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/products` | Produits actifs (`?archived=1` : archivés aussi), `usages` ; `meta` : sens, comptes 6 et 7 |
| POST | `/api/v1/products` | `name`, `reference`, `kind` (`purchase`/`sale`/`both`), `purchase_account_code` (6…), `sale_account_code` (7…), `vat_rate` (« 20 », « 5,5 ») |
| PATCH | `/api/v1/products/<id>` | Mêmes champs ; `{"active"}` seul = archiver / réactiver |
| DELETE | `/api/v1/products/<id>` | Supprime un produit **inutilisé** (sinon 409) |

---

## Factures d'achat (`/purchases/`)

Pages de la SPA : `/purchases/` (filtres `q`, `source` (`qonto` / `manual`), `state` (`to_complete`/`ready`/`posted`), `status` (statut Qonto), `entity_id`, `unpaid=1`, `no_supplier=1`, `hidden=1`, `month`, `sort`), `/purchases/new` (`?manual=1` : sans fichier), `/purchases/<id>`, `/purchases/<id>/edit`, `/purchases/settlements`, `/purchases/suppliers`. Les champs de saisie gardent le format texte du formulaire (montants « 39,99 », `entity_id` = id, `new` ou vide). API :

| Méthode | URL | Description |
|---|---|---|
| GET | `/api/v1/purchases` | Liste (mêmes filtres, 500 au plus) ; `meta` : compteurs des bandeaux (`to_complete`, `to_review`, `to_replace`, `supplier_proposals`, `hidden`, `without_supplier`, `ready`), fournisseurs, états, statuts Qonto, mois, synchronisation (`from`, `synced_at`, dernier `job`), état de Qonto |
| POST | `/api/v1/purchases/sync` | Synchronisation des factures Qonto en arrière-plan → `job` (409 si Qonto indisponible) |
| PATCH | `/api/v1/purchases/sync-from` | **Admin.** `sync_from` ; reculer la date remet le curseur à zéro (relecture complète, sans doublon) |
| POST | `/api/v1/purchases/post-ready` | Comptabilise toutes les factures prêtes (puis leurs règlements) |
| GET | `/api/v1/purchases/form-options` | Tiers, produits d'achat (compte, taux), comptes de charge, état de Qonto (`upload` : envoi possible) |
| POST | `/api/v1/purchases/read` | Multipart `invoice_file` (PDF, JPEG, PNG ≤ 10 Mo) : mise en attente et lecture → `token`, `preview` (`url`, `mime`), `form` (`values`, `checks` à vérifier, `rows`, `warnings`, `source` `facturx`/`text`/`ocr`/`none`) ; 422 si refusé |
| POST | `/api/v1/purchases/stage` | Multipart `invoice_file` : mise en attente sans lecture (remplacement de la pièce) → `token`, `preview` |
| POST | `/api/v1/purchases` | Création : en-tête (`entity_id`, `new_name`, `supplier_name`, `supplier_vat`, `supplier_siret`, `supplier_iban`, `invoice_number`, `issue_date`, `due_date`, `is_credit_note`, `untaxed`, `tax`, `total`), `rows` (`product_id`, `account_code`, `label`, `untaxed`, `vat_rate`, `vat`), `token` facultatif, `send_to_qonto` (dépôt de la pièce dans Qonto, si configuré) → 201 `item.url` ; 422 `fields.form` (liste) ; 409 `duplicate` + `duplicates`, sauf `confirm_duplicate` |
| GET | `/api/v1/purchases/<id>` | Fiche : `item` (état et motifs, montants, pièce, écriture, envoi Qonto), exercice, `lines` (saisie) et `lines_view`, `payments` (état), `awaiting_payment`, `suggestions` (transactions de même montant ; `rule` : déjà passée par une règle), `match_window`, `can_send` |
| GET | `/api/v1/purchases/<id>/header` | En-tête d'une facture saisie non comptabilisée (sinon 409), aperçu de la pièce, `can_replace_attachment` |
| PATCH | `/api/v1/purchases/<id>` | Modifie cet en-tête (mêmes champs et erreurs que la création ; `token` remplace la pièce, refusé si déjà envoyée à Qonto) |
| PUT | `/api/v1/purchases/<id>/lines` | `rows` ; 422 si invalide ; comptabilise si complète |
| POST | `/api/v1/purchases/<id>/post` | Comptabilise une facture prête (422 sinon) |
| POST | `/api/v1/purchases/<id>/unpost` | Supprime l'écriture d'achat et réapplique les données Qonto |
| DELETE | `/api/v1/purchases/<id>` | Supprime la facture, son écriture d'achat et sa pièce ; 409 si elle est validée dans Qonto, liée à un paiement ou à un avoir, ou dans un exercice clôturé |
| POST | `/api/v1/purchases/<id>/qonto` | **Écrit dans Qonto** : envoie (ou renvoie après échec) la pièce d'une facture saisie ; 409 si Qonto indisponible ou envoi impossible |
| POST | `/api/v1/purchases/<id>/payments` | `bank_transaction_id` : règle une facture saisie par une transaction proposée |
| DELETE | `/api/v1/purchases/<id>/payments/<payment_id>` | Défait un règlement hors Qonto (écriture supprimée, rapprochement défait) |
| GET | `/api/v1/purchases/settlements` | `replaceable` (écritures de règle) et `manual` (rapprochements manuels à vérifier) |
| POST | `/api/v1/purchases/settlements/replace` | `transaction_ids` : remplace les écritures de règle par des règlements 401 / banque |
| GET | `/api/v1/purchases/suppliers` | Fournisseurs des factures à valider (nom, nombre, total, période, TVA, IBAN, tiers proches) ; `meta.entities` |
| POST | `/api/v1/purchases/suppliers` | `{action: create\|link\|ignore, key, label, name?, entity_id?}` : vaut pour ses factures et ses transactions sans tiers |

Fichiers servis par Flask : `GET /purchases/<id>/attachment` (`inline` ; `?download=1` : téléchargement), `GET /purchases/staged/<token>` (pièce en attente).

## Imports (`/imports/`)

### Import OFX

Page de la SPA `/imports/ofx` (`?bank_account_id=` présélectionne le compte, dépôt glisser-déposer).
`POST /api/v1/imports/ofx` (multipart : `bank_account_id`, `ofx_file` `.ofx` / `.qfx`) insère les
transactions non dupliquées puis règle les factures d'achat saisies en attente dont le débit est
unique (`purchase_settlement.auto_match`) ; réponse `result` (`imported`, `duplicates`, `errors`,
`matched`, `settled`) et `notices`. Fichier illisible : 422.

### Import Odoo

Pages de la SPA : `/imports/odoo` (dépôt du CSV, lots importés), `/imports/odoo/batch/<batch_name>` (`?month=`, `?sort=`). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/imports/odoo` | Lots importés (`name`, `lines`, `url`) |
| POST | `/api/v1/imports/odoo` | Multipart `csv_file` (export Odoo : `name`, `invoice_date`, `partner_id/name`, `product_id/name`, `price_subtotal`, `price_total`, `account_id/code`), `batch_name` facultatif (généré si vide, 50 caractères) → `result` (`batch`, `imported`, `errors`, `preview`, `url`) ; 422 si fichier absent ou illisible |
| GET | `/api/v1/imports/odoo/batches/<batch_name>` | Lignes du lot (montants, compte, `entry_url` si comptabilisée) |

---

## Rapprochement bancaire (`/reconciliation/`)

Page de la SPA ([guide](saisie_rapprochement.md)) : `?bank_account_id=`, `?month=YYYY-MM`.
`GET /api/v1/reconciliation/context` donne les comptes bancaires, les mois de l'exercice et le
journal par défaut ; le panneau « Créer l'écriture » est préparé par
`GET /api/v1/entries/form?bt_id=`. Les actions (rapprocher, défaire, automatique, règles) sont
décrites dans la section API ci-dessous.

---

## Entités et adhérents (`/entities/`)

Pages de la SPA : `/entities/` (`?q=`), `/entities/new`, `/entities/<id>/edit` (panneau latéral),
`/entities/<id>` (fiche), `/entities/members` (filtres `q`, `date_from`, `date_to`, `sort_by`
= `name`/`birthday`/`status`, `sort`), `/entities/members/reminders`,
`/entities/members/reminder-template`. Fichiers servis par Flask :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/entities/members/export` | Export des adhérents — `?format=csv\|xlsx` (alias `xls`→`xlsx`), mêmes filtres + tri que la liste. Colonnes : Nom, Email, Adhérent, Bénévole, Dernière adh. HA, Dernière adh. POS, Date anniversaire, Statut, Couleur, Notes |
| GET | `/entities/members.csv` | Compat : redirige (302) vers `/members/export?format=csv` |

API (la recherche des listes de saisie reste `GET /api/v1/entities?q=`) :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/tiers` | Tiers hors adhérents (`?q=` nom ou email), dernières adhésions HelloAsso / caisse, nombre de transactions ; `meta` : types, produits d'achat, état des intégrations HelloAsso / Odoo / SMTP |
| POST | `/api/v1/tiers` | `name` (unique), `entity_type`, `account_code`, `email`, `is_member`, `is_benevole`, `notes`, `default_product_id`, `vat_number`, `siret` (14 chiffres, espaces et points tolérés), `iban` |
| GET | `/api/v1/tiers/<id>` | Fiche : identité, solde du compte fournisseur, factures d'achat, commandes de caisse Odoo (lignes, paiements), factures clients, temps de travaux, HelloAsso (commandes, articles, paiements) |
| PATCH | `/api/v1/tiers/<id>` | Mêmes champs que la création |
| DELETE | `/api/v1/tiers/<id>` | Supprime (409 si des transactions y sont liées) |
| POST | `/api/v1/tiers/<id>/odoo-note` | Écrit la note d'adhésion dans « Notes interne » d'Odoo (409 si Odoo indisponible) |
| POST | `/api/v1/helloasso/sync` | Synchronisation HelloAsso (synchrone, voir [services.md](services.md#helloasso_syncpy--synchronisation-helloasso)) |
| GET | `/api/v1/members` | Adhérents filtrés et triés (`color` : `red` échue, `orange` sous 30 jours, `green` à jour) ; `meta.export_urls` |
| POST | `/api/v1/members/benevole` | `{ids, value}` : marque ou retire le statut bénévole |
| POST | `/api/v1/members/odoo-notes` | `{ids, filtres}` : notes d'adhésion des fiches Odoo choisies |
| GET / POST | `/api/v1/members/reminders` | Adhérents à relancer (échus, email connu) / `{ids, filtres}` : envoie la relance (409 si SMTP indisponible) |
| GET / PUT | `/api/v1/members/reminder-template` | Gabarit du message (`subject`, `body_html`, modèle `EmailTemplate` clé `membership_reminder`) |
| POST | `/api/v1/members/reminder-template/preview` | Rendu du gabarit (bac à sable Jinja) avec un adhérent réel ou fictif ; `error` si le gabarit est invalide |

## Temps de travaux (`/work-times/`)

Pages de la SPA : `/work-times/` (filtres `entity_id`, `task_type_id`, `month`, `sort`),
`/work-times/new`, `/work-times/<id>/edit`, `/work-times/import`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/work-times` | Temps filtrés ; `meta` : bénévoles, types de tâches, mois de l'exercice, `total_hours`, `total_valuation_cents` |
| POST / PATCH | `/api/v1/work-times[/<id>]` | `entity_id`, `task_type_id`, `work_date`, `hours` (0 à 24), `notes` |
| DELETE | `/api/v1/work-times/<id>` | Supprime le temps |
| POST | `/api/v1/work-times/import` | Fichier `file` CSV (séparateur `;`) ou XLSX : colonnes Bénévole, Type de tâche, Date, Heures, Notes |
---

## Moteur de règles (`/rules/`)

Pages de la SPA (liste ; la création / modification s'ouvre dans une fenêtre portée par l'URL) : `/rules/`, `/rules/new`, `/rules/<id>/edit` (panneau latéral, avec testeur d'expression). API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/rules` | Règles dans l'ordre d'évaluation ; `meta.entity_types`, `meta.projects` (champ `project_id` d'une règle : projet de la ligne 6xx/7xx générée) |
| POST | `/api/v1/rules` | Crée la règle (position = max + 1) |
| PATCH | `/api/v1/rules/<id>` | Met à jour ; `{"is_active"}` seul = activer / désactiver |
| DELETE | `/api/v1/rules/<id>` | Supprime |
| POST | `/api/v1/rules/<id>/move` | `{"direction": "up"\|"down"}` : échange avec la voisine ; renvoie la liste |
| POST | `/api/v1/rules/apply` | `{"overwrite": bool}` : applique aux transactions (catégorisées aussi si `overwrite`) ; `result` + `notices` |

**Champs d'une règle :**

| Champ | Obligatoire | Description |
|-------|-------------|-------------|
| `name` | oui | Libellé court |
| `label_contains` | non | Sous-chaîne (insensible à la casse) |
| `label_regex` | non | Regex Python (validée serveur via `re.compile`) |
| `amount_min_cents` / `amount_max_cents` | non | En centimes |
| `raw_type` | non | Filtre type OFX |
| `entity_name` / `entity_type` | non | Tiers à rattacher (créé si nécessaire) |
| `category` | non | Étiquette libre |
| `account_code` | non | Code 6xx/7xx du plan comptable — déclenche la génération d'écriture |
| `is_active` | non | Règle active (vrai par défaut) |

Au moins une condition (`label_contains`, `label_regex`, `amount_min_cents`, `amount_max_cents`, `raw_type`) est obligatoire (422 sinon).

**Effet sur les écritures :** pour chaque règle qui définit `account`, une écriture est créée dans le journal `BQ` :
- compte commençant par `6` (charge) → débit du compte 6xx, crédit du compte bancaire
- compte commençant par `7` (produit) → débit du compte bancaire, crédit du compte 7xx

La transaction bancaire est automatiquement rapprochée à la ligne d'écriture côté banque.

---

## Versements Stancer (`/payouts/`)

Pages de la SPA : `/payouts/` (`?month=`, `?sort=`), `/payouts/<id>`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/payouts` | Versements (montant, frais, paiements, opération bancaire, statut) ; `meta` : mois, état de Stancer, dernière synchronisation |
| GET | `/api/v1/payouts/<id>` | Versement et ses paiements (date, moyen, client, montant, statut) ; dernière synchronisation du versement |
| POST | `/api/v1/payouts/sync` | Synchronisation des versements en arrière-plan → `job` (409 si Stancer indisponible ; idempotent pendant qu'un job tourne) |
| POST | `/api/v1/payouts/<id>/sync-payments` | Synchronisation des paiements d'un versement → `job` |

---

## Commandes POS Odoo (`/orders/`)

Pages de la SPA : `/orders/` (`?month=`, `?sort=`), `/orders/<id>`. Synchronisations **synchrones** ; Odoo indisponible (non configurée ou désactivée) → bouton grisé et 409. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/orders` | Commandes (`pos.order`), 500 au plus : référence, session, client, montants, nombre de lignes et de paiements, statut ; `meta` : mois, état d'Odoo |
| GET | `/api/v1/orders/<id>` | Commande, lignes, paiements |
| POST | `/api/v1/orders/sync` | `sync_pos_orders()` (XML-RPC) → `result`, `notices` ; 409 Odoo indisponible, 502 erreur Odoo |

**Effets de la sync** :
- Upsert `pos.order` → `orders` (clé d'idempotence : `odoo_id`)
- Upsert `pos.order.line` → `order_lines` (CASCADE)
- Upsert `pos.payment` → `order_payments` (CASCADE)
- Création auto d'`Entity(entity_type='CLIENT')` par email pour chaque `res.partner` rencontré
- Bascule `is_member=True` + `entity_type='ADHERENT'` pour tout tiers ayant une ligne de commande "Adhésion" (matching `LIKE %adh%sion%`)

---

## Factures clients Odoo (`/customer-invoices/`)

Pages de la SPA : `/customer-invoices/` (filtres ci-dessous), `/customer-invoices/<id>`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/customer-invoices` | Factures (`account.move`, `out_invoice`), 500 au plus ; `meta` : états, états de paiement, mois, état d'Odoo |
| GET | `/api/v1/customer-invoices/<id>` | Facture et lignes ; `narration` en texte seul (le HTML d'Odoo n'est pas repris) |
| POST | `/api/v1/customer-invoices/sync` | `sync_customer_invoices()` (XML-RPC) → `result`, `notices` ; 409 / 502 comme les commandes |

**Filtres** :

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

Page de la SPA (`?fy_id=`, exercice le plus récent par défaut) ; `GET /api/v1/dashboard` renvoie :
- `stats` : ventes de l'exercice (caisse Odoo et factures Odoo hors caisse), adhésions de
  l'exercice (HelloAsso ou caisse), résultat courant (exploitation et financier, selon le plan de
  l'instance), versements Stancer ;
- `monthly` : par mois, produits (7x) / charges (6x) / net, ventes (70x, caisse, factures Odoo),
  solde bancaire cumulé fin de mois (base = transactions antérieures à l'exercice), en euros ;
- `recent_entries` : les 10 dernières écritures.

Graphiques **Mantine Charts** (résultat : barres et courbe ; ventes : barres ; solde : aire).
---

## États financiers (`/reports/`)

Pages de la SPA : `/reports/balance`, `/reports/grand-livre` (`?account_id=`), `/reports/bilan`,
`/reports/compte-de-resultat`, toutes avec `?fy_id=` (exercice ouvert le plus récent par défaut)
et un bouton « Imprimer » (`window.print()`, navigation masquée en `@media print`).

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/reports/balance` | Balance (comptes avec mouvements : débit, crédit, soldes) |
| GET | `/api/v1/reports/grand-livre` | Lignes d'un compte avec solde cumulé ; `meta.accounts` |
| GET | `/api/v1/reports/bilan` | Actif / passif selon le plan de l'instance, N et N-1 (lignes `section` / `row` / `total`) |
| GET | `/api/v1/reports/compte-de-resultat` | Lignes `section` / `subhead` / `row` / `total` / `result` avec `indent`, N et N-1 ; `meta.export_urls` |
| GET | `/reports/compte-de-resultat.csv` | Export CSV (séparateur `;`, UTF-8 BOM, virgule décimale) |
| GET | `/reports/compte-de-resultat.ods` | Export ODS avec formules de totaux (somme des cellules, lignes « dont » exclues), styles et format monétaire |
---

## Indicateurs — Visibilité & Impact (`/impact/`)

Menu **« Indicateurs »** (plan associatif). Pages de la SPA : `/impact/`, `/impact/report` (rapport imprimable : impression du navigateur), `/impact/manual` (`?month=`), `/impact/factors` (**admin**). Période : `?gran=month|quarter|year|custom`, `?month=`, `?quarter=AAAA-Qn`, `?year=`, `?start=&end=`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/impact` | Période (`label`, bornes), valeurs effectives du filtre (`current`), indicateurs phares, sections par dimension (valeur, évolution, tendance, source), fraîcheur des sources ; `meta` : mois, années, état de GA4 et Facebook, lien d'export XLSX |
| POST | `/api/v1/impact/sync` | `{scope: month, month}` ou `{scope: year, year}` : connecteurs externes (GA4, Facebook), **synchrone** |
| GET | `/api/v1/impact/manual?month=` | Métriques sans API du mois (valeurs en euros pour les montants) |
| PUT | `/api/v1/impact/manual` | `{month, values: {clé: valeur}}` ; vide = inchangé ; 422 `fields` si une valeur est invalide (rien n'est écrit) |
| GET | `/api/v1/impact/factors` | **Admin.** Facteurs d'impact (créés au besoin) |
| PUT | `/api/v1/impact/factors` | **Admin.** `{items: [{id, value, source_label, source_url}]}` ; adresse http(s) seulement |

Fichier servi par Flask : `GET /impact/export.xlsx` (mêmes paramètres de période).

> **Impact environnemental** : `CO₂ évité`, `poids réemployé`, `taux de réemploi`, `km voiture` sont calculés (`impact_engine.compute`) à partir des **tonnages éco-organismes** (table `eco_declarations`, cf. import ci-dessous), et **non** des ventes. Le dashboard et le rapport d'activité affichent donc le même CO₂.

## Indicateurs — Rapport d'activité (`/rapport-activite/`)

Pages de la SPA : `/rapport-activite/` (`?fy_id=`, `?prorata=0|1` : aperçu, PDF et exports), `/rapport-activite/edit` (**admin**, éditeur Tiptap + code HTML par bloc), `/rapport-activite/eco` (**admin**, aussi au menu **Imports/Exports**), `/rapport-activite/photos` (**admin**), `/rapport-activite/archives`. Sans exercice comptable : 409 `no_fiscal_year`. API :

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/v1/activity-report` | Exercices, exercice retenu (le plus récent par défaut), mode éco, liens (aperçu, PDF, HTML, DOCX, ODT) |
| GET / PUT | `/api/v1/activity-report/texts` | **Admin.** Blocs narratifs (`key`, `title`, `body` HTML) et import du site disponible ; PUT `{fy_id, blocks}` (titre et contenu vides : bloc supprimé) |
| POST | `/api/v1/activity-report/texts/import-site` | **Admin.** `{fy_id, overwrite}` : pré-remplissage depuis le site |
| GET / PUT | `/api/v1/activity-report/eco` | **Admin.** Tonnages éco-organismes ; PUT `{rows: [{id, entrant_t, sortant_t, financing_cents, delete?}]}` |
| POST | `/api/v1/activity-report/eco/import` | **Admin.** Multipart `file` `.xlsx` (feuille `Bilan`) |
| GET / POST | `/api/v1/activity-report/photos` | **Admin.** Emplacements (couverture, sections) et logo ; POST multipart `fy_id`, `slot`, `file` (png, jpg, webp, gif) remplace la photo |
| PATCH / DELETE | `/api/v1/activity-report/photos/<id>` | **Admin.** Légende / suppression |
| POST / DELETE | `/api/v1/activity-report/logo` | **Admin.** Logo de la structure (png, jpg, svg, webp, gif) |
| GET | `/api/v1/activity-report/archives` | Versions archivées de l'exercice |
| POST / DELETE | `/api/v1/activity-report/archives[/<id>]` | **Admin.** `{fy_id, label, prorata}` fige un PDF (201) ; suppression |

Fichiers servis par Flask : `GET /rapport-activite/apercu` (HTML autonome, graphes SVG, `script-src 'none'` ; affiché dans un `iframe` en bac à sable), `/pdf` (weasyprint, inline), `/export/<html|docx|odt>`, `/photo/<id>`, `/logo-file`, `/archive/<id>`. Le PDF et les exports sont produits comme avant la refonte.

---

## API JSON (`/api/v1`)

Utilisée par la SPA. Mêmes règles que les pages : session Flask-Login
(**connexion exigée sur toute l'API** sauf `session/login` et `session/logout`), instance courante
(`app/tenant.py`), CSRF obligatoire en POST/PUT/PATCH/DELETE via l'en-tête `X-CSRFToken`. Montants
en **centimes entiers**, dates ISO `YYYY-MM-DD`. Les actions renvoient `item` (la ressource à jour)
et `notices` (`[{"level": "success|info|warning|danger", "message"}]`, affichés en notifications) ;
un refus métier est un 409 `conflict`.

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
| GET | `/api/v1/session` | Utilisateur, instance courante, instances actives, menus (`nav`, URL résolues selon le plan et les droits), liens d'administration, préférences, jeton CSRF |
| POST | `/api/v1/session/login` | `{email, password}` → session (comme ci-dessus) ; 422 si identifiants faux ou compte désactivé ; une seule instance active : choisie d'office |
| POST | `/api/v1/session/logout` | Déconnexion (instance oubliée) |
| POST | `/api/v1/session/instance` | `{instance_id}` → session ; 422 si l'instance est inconnue ou désactivée |
| PATCH | `/api/v1/me/preferences` | Fusion profonde dans `users.preferences` (`null` supprime une clé) ; `color_scheme` ∈ `light`/`dark`/`auto` ; 413 au-delà de 16 Ko |
| GET | `/api/v1/jobs/<id>` | État d'une tâche longue (`sync_jobs`) : statut, progression, résultat |
| GET | `/api/v1/notifications` | Notifications de l'utilisateur dans l'instance (les siennes et celles de toute l'instance), plus récentes d'abord : `level`, `title`, `message`, `url`, `job_id`, `read` ; `?unread=1`, `?limit=` (20, 100 au plus) ; `meta.unread` |
| POST | `/api/v1/notifications/read` | `{ids: [..]}` marque ces notifications comme lues (sans `ids` : toutes) → `marked`, `meta.unread` ; 422 si `ids` n'est pas une liste d'entiers |
| GET | `/api/v1/search?q=` | Palette Ctrl+K : tiers, factures d'achat, écritures (5 par groupe, 2 caractères au moins) |
| GET/POST | `/api/v1/task-types` | Types de tâches des temps de travaux (`name` unique, `hourly_rate_cents`, `is_active` ; `work_times` = temps saisis). Pages SPA `/work-times/task-types`, `…/new`, `…/<id>/edit` |
| PATCH/DELETE | `/api/v1/task-types/<id>` | Modifie ; supprime un type sans temps saisis (sinon 409) |
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
partie réussie (`{"method": "POST", "url": ..., "body": ...}`), rejouée par la SPA pour « Annuler ».
