# Architecture

## Structure du projet

```
compta-asso/
│
├── run.py                        # Point d'entrée : charge .env, crée l'app Flask
├── seed_accounts.py              # Charge le plan comptable (asso|sci, détecté si omis) + journaux
├── seed_meta.py                  # Méta-base : admin, instance par défaut, migration instances.chart
├── requirements.txt
├── Makefile                      # make check : typecheck + tests front + build + pytest
├── .nvmrc                        # Node 22 (dev et build du front uniquement)
├── .env                          # Variables d'environnement (gitignorée)
│
├── frontend/                     # Îlots React (TypeScript + Vite), compilés vers app/static/dist/
│   ├── vite.config.ts            # base /static/dist/, manifest, serveur de dev :5173
│   └── src/
│       ├── main.tsx              # Monte les éléments [data-island] (aussi après un swap HTMX)
│       ├── islands/              # registry.ts, EntryForm/, ReconcileWorkspace/
│       ├── components/           # AccountCombobox (ARIA combobox, comptes récents)
│       └── lib/                  # api.ts (fetch + CSRF), money.ts, types.ts, toast.ts
│
├── app/
│   ├── __init__.py               # App factory : create_app(), filtres Jinja2, menus (nav_menus)
│   ├── menu_config.py            # Menus de navigation par plan comptable (MENUS, build_nav)
│   ├── tenant.py                 # Routage multi-tenant, current_instance(), current_chart()
│   ├── frontend.py               # Conventions HTMX (toasts, HX-Location) + vite_assets()
│   ├── api/                      # API JSON /api/v1 pour les îlots (entries, lookups, reconciliation)
│   ├── config.py                 # Classes de configuration (Dev / Prod)
│   ├── extensions.py             # Singletons : db, migrate, login_manager, csrf
│   │
│   ├── models/                   # Modèles SQLAlchemy (un fichier par table)
│   │   ├── fiscal_year.py
│   │   ├── account.py
│   │   ├── journal.py
│   │   ├── journal_entry.py
│   │   ├── journal_line.py
│   │   ├── bank_account.py
│   │   ├── bank_transaction.py
│   │   ├── entity.py
│   │   ├── payout.py             # Versements Stancer
│   │   ├── payment.py            # Paiements Stancer rattachés à un payout
│   │   ├── sync_job.py           # Suivi des syncs Stancer asynchrones
│   │   ├── odoo_import.py
│   │   ├── order.py              # Commandes POS Odoo (pos.order)
│   │   ├── order_line.py         # Lignes de commande POS
│   │   ├── order_payment.py      # Paiements POS
│   │   ├── customer_invoice.py   # Factures clients Odoo (account.move)
│   │   ├── customer_invoice_line.py
│   │   ├── helloasso.py          # Forms / Orders / Items / Payments HelloAsso
│   │   ├── rule.py               # Règles de catégorisation (per-instance)
│   │   ├── external_connection.py # Credentials services externes (per-instance)
│   │   ├── integration_state.py  # Activation + dernier test d'une intégration (per-instance)
│   │   ├── ignored_counterparty.py # Contreparties à ne plus proposer comme fournisseurs
│   │   ├── product.py            # Catalogue produits / services (comptes 6… / 7…, TVA)
│   │   ├── purchase.py           # Factures d'achat (Qonto ou saisies), lignes, paiements
│   │   ├── sync_cursor.py        # Curseurs de synchronisation (factures Qonto)
│   │   ├── user.py               # Utilisateurs (méta-base)
│   │   └── instance.py           # Déclaration d'instance (méta-base)
│   │
│   ├── views/                    # Blueprints Flask (un fichier par domaine)
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── accounts.py
│   │   ├── fiscal_years.py
│   │   ├── journals.py
│   │   ├── entries.py
│   │   ├── imports.py
│   │   ├── reconciliation.py
│   │   ├── reports.py
│   │   ├── entities.py           # CRUD tiers (dont TVA, SIRET, IBAN) + listes HelloAsso/POS/factures par tiers
│   │   ├── products.py           # Catalogue produits / services
│   │   ├── purchases.py          # Factures d'achat : liste, synchro Qonto, saisie, pièce, règlements
│   │   ├── instances.py          # Instances (admin) : création, sauvegardes .zip, restauration, import
│   │   ├── rules.py              # Affichage règles + application
│   │   ├── payouts.py            # Liste + détail + sync Payouts/Payments Stancer
│   │   ├── integrations.py       # Écran Intégrations : index, détail, interrupteur, test (admin)
│   │   ├── orders.py             # Commandes POS Odoo : liste + détail + sync
│   │   └── customer_invoices.py  # Factures clients Odoo : liste + détail + sync
│   │
│   ├── services/                 # Logique métier (sans dépendance Flask)
│   │   ├── ledger.py             # Moteur comptable : validation, saisie, soldes
│   │   ├── reports.py            # Bilan et Compte de résultat par plan comptable (asso|sci)
│   │   ├── instance_provisioning.py  # Création des bases d'instance (migrations + plan comptable)
│   │   ├── reconciler.py         # Rapprochement bancaire
│   │   ├── ofx_importer.py       # Import fichiers OFX
│   │   ├── odoo_importer.py      # Import CSV Odoo (staging)
│   │   ├── rules_engine.py       # Catégorisation automatique des transactions
│   │   ├── stancer_sync.py       # Synchronisation Payouts + Payments Stancer (API v2)
│   │   ├── external_config.py    # Config + activation des intégrations (base, repli .env)
│   │   ├── integrations.py       # Statut + test de fonctionnement des intégrations (sondes)
│   │   ├── sync_jobs.py          # Synchros en arrière-plan (SyncJob + thread sur la base de l'instance)
│   │   ├── qonto_client.py       # Client API Business Qonto (clé API, pagination, 429)
│   │   ├── qonto_sync.py         # Rattachement des comptes + synchro des transactions Qonto
│   │   ├── counterparties.py     # Contreparties bancaires → tiers / propositions de fournisseurs
│   │   ├── catalog.py            # Catalogue : produit par défaut, taux de TVA
│   │   ├── purchase_sync.py      # Synchro des factures d'achat Qonto, find_supplier, lignes par défaut
│   │   ├── purchase_posting.py   # États, comptabilisation en engagement (AC), lignes saisies
│   │   ├── purchase_settlement.py # Règlements 401 / banque : Qonto, débits OFX (auto / choisis)
│   │   ├── purchase_entry.py     # Saisie d'une facture : préremplissage, doublons, envoi à Qonto
│   │   ├── invoice_reader.py     # Lecture : Factur-X, texte PDF, OCR Tesseract (PyMuPDF)
│   │   ├── attachments.py        # Pièces jointes par instance (instance/uploads/<slug>/)
│   │   ├── instance_backup.py    # Sauvegardes .zip (base + pièces) et restauration
│   │   ├── stancer_async.py      # Wrapper threading + suivi via SyncJob
│   │   ├── odoo_client.py        # Client XML-RPC Odoo (commun POS + factures)
│   │   ├── odoo_pos_sync.py      # Sync pos.order → orders / order_lines / order_payments
│   │   ├── odoo_invoice_sync.py  # Sync account.move → customer_invoices / lines
│   │   ├── entity_resolver.py    # Helpers email → Entity (cache + unicité du nom)
│   │   ├── helloasso_client.py   # OAuth2 + REST v5 HelloAsso
│   │   ├── helloasso_sync.py     # Sync forms/orders/items/payments + flag is_member
│   │   └── helloasso_create.py   # Création de Memberships côté HelloAsso
│   │
│   ├── utils/                    # Helpers transverses (sans dépendance Flask hors `request`)
│   │   └── list_filters.py       # Parse sort/month, calcule les options de mois pour le FY courant
│   │
│   ├── templates/                # Templates Jinja2
│   │   ├── base.html             # Layout principal (nav générée depuis menu_config, Bootstrap, HTMX)
│   │   ├── _list_helpers.html    # Macros partagées : sortable_date_header, month_filter_select
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── accounts/
│   │   ├── fiscal_years/
│   │   ├── journals/
│   │   ├── entries/
│   │   ├── imports/
│   │   ├── reconciliation/
│   │   ├── reports/
│   │   ├── entities/
│   │   ├── rules/
│   │   ├── payouts/
│   │   ├── products/             # Catalogue
│   │   ├── purchases/            # Factures d'achat (liste, fiche, saisie, éditeur de lignes)
│   │   ├── orders/               # Commandes POS Odoo
│   │   └── customer_invoices/    # Factures clients Odoo
│   │
│   └── static/
│       ├── css/app.css           # Surcharges Bootstrap + styles impression
│       └── js/app.js             # Indicateur de balance, helpers HTMX
│
├── data/
│   ├── plan_comptable_asso.json  # 783 comptes PCA (source : fichier XLS)
│   ├── plan_comptable_sci.json   # 576 comptes SCI (source : doc/plan-comptable-SCI.pdf)
│   └── rules.yml                 # Règles de catégorisation (éditable sans redémarrage)
│
├── migrations/                   # Migrations Alembic (versioning schéma)
├── instance/                     # seconde-nature.db (gitignorée)
└── doc/                          # Cette documentation
```

---

## Stack technique

### Backend

| Composant | Rôle |
|-----------|------|
| **Flask 3.1** | Framework web WSGI, routing, Jinja2 |
| **SQLAlchemy 3.1** | ORM, gestion des modèles, requêtes |
| **Flask-Migrate** | Migrations de schéma via Alembic |
| **Flask-Login** | Gestion de session, décorateur `@login_required` |
| **Flask-WTF** | Protection CSRF sur tous les formulaires POST |
| **ofxtools** | Parsing OFX 1.x (SGML) et 2.x (XML) |
| **pandas** | Lecture et mapping des CSV Odoo |
| **PyYAML** | Lecture du fichier de règles de catégorisation |
| **odfpy** | Génération des exports ODS du compte de résultat |
| **echarts-python** | Construction côté serveur des options ECharts pour le tableau de bord |
| **requests** | Appels REST à l'API Stancer v2 + HelloAsso v5 (OAuth2 client_credentials) |
| **xmlrpc.client** (stdlib) | Client XML-RPC Odoo — endpoints `/xmlrpc/2/common` + `/xmlrpc/2/object`, API key passée comme password |

### Frontend

Architecture **hybride** (détail : `claudedocs/design_front_reactif.md`) :

| Composant | Rôle |
|-----------|------|
| **Bootstrap 5.3** (CDN) | Grille, composants UI, toasts |
| **HTMX 2.0** (CDN) | Toutes les pages Jinja : filtres, tri, recherche, actions et formulaires **sans rechargement** (zone `#page-content`, voir ci-dessous) |
| **React 18 + TypeScript** (build Vite) | Deux îlots au clavier : saisie d'écriture (`EntryForm`) et espace de rapprochement (`ReconcileWorkspace`), via l'API `/api/v1` |
| **Apache ECharts 5** (CDN) | Graphiques (options préparées côté serveur), réinitialisés après un swap HTMX |

**Conventions HTMX** (`app/frontend.py`, macros `app/templates/_list_helpers.html`) :

- `base.html` enveloppe le contenu dans `<main id="page-content">`. Les macros `hx_filter` (formulaire
  de filtre GET), `hx_nav` (liens de tri) et `hx_submit` (formulaires POST, `hx-boost`) demandent la
  page complète au serveur ; HTMX n'en garde que la zone (`hx-select`) et met l'URL à jour. Les vues
  restent de simples vues Flask.
- Une recherche au fil de la frappe cible une zone `#list` qui n'inclut pas le champ saisi.
- Les messages `flash()` d'une réponse HTMX partent dans l'en-tête `HX-Trigger` (événement `toast`) ;
  une redirection devient `HX-Location` (rechargement AJAX de la zone) ou, vers la connexion,
  `HX-Redirect`.
- Formulaire invalide → réponse **422** affichée (erreurs sous les champs, macros `field_error`).
- Confirmations par `hx-confirm` : HTMX ignore un `onsubmit="return confirm()"`.

**Îlots React** : la macro `island(name, props)` (`_island.html`) place un `<div data-island>` avec
ses props JSON ; `vite_assets()` charge le bundle (manifest Vite en production, serveur Vite avec
rechargement à chaud si `VITE_DEV_SERVER` est défini). Node n'est utilisé qu'en développement et à
l'étape de build Docker.

---

## Architecture multi-tenant

Depuis mai 2026, l'application gère plusieurs associations (« instances »), chacune avec sa propre base de données. Une **méta-base** (`instance/meta.db`) globale stocke les utilisateurs et la liste des instances. Voir [multi_tenant.md](multi_tenant.md) pour le détail.

```
                  ┌──────────────────┐
                  │ instance/meta.db │  ← users, instances
                  └──────────────────┘
                          ▲
   Login                  │ __bind_key__='meta'
   ─────────────► db.session ◄───── all models without __bind_key__
                          │
                          ▼ g.tenant_engine (rebindé par requête)
                  ┌────────────────────────────┐
                  │ instance/seconde-nature.db │  ← écritures, comptes…
                  ├────────────────────────────┤
                  │ instance/tenants/asso2.db  │  ← écritures, comptes…
                  ├────────────────────────────┤
                  │ instance/tenants/asso3.db  │  ← …
                  └────────────────────────────┘
```

Routage géré par `MultiTenantSession.get_bind` (`app/extensions.py`) + hook `before_request` (`app/tenant.py`).

---

## Séparation des couches

```
HTTP Request
    │
    ▼
[Blueprint / View]          ← gère HTTP, session, flash, redirect
    │
    ▼
[Service]                   ← logique métier pure, testable sans Flask
    │
    ▼
[SQLAlchemy Model]          ← accès base de données
    │
    ▼
[SQLite]
```

Les services (`app/services/`) n'importent jamais de `flask` directement. Ils reçoivent des identifiants et retournent des objets métier. Cela permet de les tester unitairement sans client HTTP.

---

## Flux de données principaux

### Saisie d'une écriture manuelle

```
GET /entries/new  → page Jinja + îlot EntryForm (props : exercices ouverts, journaux, préremplissage)
    │
    ├── POST /api/v1/entries/validate   (400 ms après chaque modification, rien n'est enregistré)
    │     └── ledger.validate_entry_payload(data) → (clean, errors par champ)
    │
    └── POST /api/v1/entries
          ├── validate_entry_payload → 422 + erreurs par champ si invalide
          └── ledger.post_validated_entry(clean, bank_transaction=None)
                ├── post_entry(..., commit=False) : référence auto (BQ-2024-0001), lignes
                ├── si transaction bancaire : rapprochement de la ligne banque (même compte,
                │   même montant signé) dans la même transaction, sinon 409 et rien n'est créé
                └── commit
```

### Import OFX

```
POST /imports/ofx
    │
    ├── Récupère bank_account_id + fichier
    │
    └── ofx_importer.import_ofx(file, bank_account_id)
          ├── Parse OFX (ofxtools)
          ├── Pour chaque transaction :
          │     ├── Cherche (bank_account_id, fitid) en base
          │     ├── Si trouvé → duplicate++
          │     └── Sinon → INSERT bank_transactions
          └── Retourne {imported, duplicates, errors}

POST /payouts/sync               (asynchrone, non-bloquant)
    │
    └── stancer_async.start_sync_payouts(app)
          ├── Si un SyncJob kind='payouts' status='running' existe → le retourne (idempotent)
          ├── Sinon : INSERT sync_jobs (status='running', progress_done=0)
          ├── threading.Thread(daemon=True) :
          │     with app.app_context():
          │       └── stancer_sync.sync_payouts(progress_cb=…)
          │             ├── Boucle paginée GET https://api.stancer.com/v2/payouts
          │             │     auth=(secret_key, "")  ← convention Stancer (HTTP Basic)
          │             │     params={"start": N, "limit": 100}
          │             ├── Pour chaque payout reçu :
          │             │     ├── UPSERT payouts (amount=total net, date_paym→date_payout,
          │             │     │     fees, status, description=reference, raw_payload, …)
          │             │     ├── Si bank_transaction_id nul → _match_bank_transaction() :
          │             │     │     ├── 1. amount + label LIKE '%No <reference>%'
          │             │     │     └── 2. fallback : amount + transaction_date == date_bank
          │             │     └── progress_cb(done, None, "Payout pout_…")
          │             ├── flush(), puis pour chaque payout :
          │             │     sync_payments_for_payout(payout)  ← boucle /v2/payouts/<id>/payments
          │             │     UPSERT payments, 404 ignoré
          │             └── progress_cb(done=idx, total=N, "Paiements : i/N")
          ├── _finalize : status='done'/'failed', finished_at, result_json
          └── retourne SyncJob immédiatement
    │
    └── Réponse HTTP : fragment _sync_status.html (HTMX), qui s'auto-rafraîchit
          via hx-get="/payouts/sync/status/<id>" hx-trigger="every 2s"

POST /payouts/<id>/sync-payments     (asynchrone, sync ciblée d'un payout)
    │
    └── stancer_async.start_sync_payments_for_payout(app, payout_id)
          (même contrat : SyncJob kind='payout_payments', polling identique)

GET /payouts/sync/status/<job_id>    (polling HTMX)
    │
    └── retourne le fragment HTML du SyncJob (running/done/failed,
        progress_done/total, message, result_json affiché si terminé)

POST /rules/apply
    │
    └── rules_engine.apply_rules(overwrite=False)
          ├── Charge data/rules.yml
          ├── Pour chaque transaction sans catégorie :
          │     ├── Évalue chaque règle dans l'ordre
          │     ├── Première règle qui correspond :
          │     │     ├── entity → get_or_create Entity
          │     │     ├── category → SET bank_transaction.category
          │     │     └── account (si défini, txn non liée) →
          │     │           ├── 6xx : débit charge / crédit banque
          │     │           ├── 7xx : débit banque / crédit produit
          │     │           ├── ledger.post_entry(journal=BQ, fy=auto)
          │     │           └── lien txn ↔ ligne écriture (rapprochement)
          │     └── Si aucune règle → ignorée
          └── Retourne {matched, posted, skipped, total, errors}
```

### Rapprochement bancaire

```
GET /reconciliation/  → page Jinja + îlot ReconcileWorkspace
    │
    ├── GET /api/v1/bank-accounts/<id>/transactions?status=unreconciled&month=
    ├── GET /api/v1/bank-transactions/<id>/suggestions
    │     └── reconciler.suggest_matches_scored : lignes du compte comptable du compte
    │         bancaire, même montant signé, non rapprochées, ±3 jours ; score 2 (même date) / 1
    │
    └── POST /api/v1/reconciliations {items: [{bank_transaction_id, journal_line_id}]}
          └── reconciler.reconcile_many : check_link par paire, une seule transaction SQL
              → {results (par élément), counters, undo (requête inverse à rejouer)}
```

### Synchronisation Odoo POS / Factures clients

```
POST /orders/sync            (sync POS, synchrone)
POST /customer-invoices/sync (sync factures clients, synchrone)
    │
    └── odoo_pos_sync.sync_pos_orders()        OU
        odoo_invoice_sync.sync_customer_invoices()
          ├── odoo_client.from_app_config() → OdooClient (XML-RPC, auth via API key)
          ├── Étape 1 — pagination search_read sur le modèle Odoo principal :
          │     pos.order            (POS)
          │     account.move filtré move_type='out_invoice' (factures)
          │     UPSERT sur odoo_id dans la table locale (orders ou customer_invoices)
          ├── Étape 2 — search_read par lots d'IDs sur les lignes :
          │     pos.order.line       (POS)
          │     account.move.line filtrée display_type='product' ou product_id≠False
          │     UPSERT sur odoo_id (order_lines ou customer_invoice_lines, CASCADE)
          ├── Étape 3 (POS uniquement) — pos.payment → order_payments (CASCADE)
          ├── Étape 4 — _fetch_partners(client, partner_ids) → res.partner
          │     entity_resolver.entity_by_email + unique_entity_name
          │     Création auto Entity(entity_type='CLIENT') par email
          ├── Étape 5 (POS uniquement) — _refresh_pos_member_flag :
          │     Toute Entity ayant une OrderLine "Adhésion" → is_member=True
          │     + bascule entity_type=ADHERENT
          └── commit unique en fin de sync
```

### Synchronisation HelloAsso

```
POST /entities/sync-helloasso
    │
    └── helloasso_sync.sync_helloasso()
          ├── helloasso_client.from_app_config() → token OAuth2 client_credentials
          ├── GET /v5/organizations/{slug}/forms       → helloasso_forms
          ├── GET /v5/organizations/{slug}/orders?withDetails=true
          │     (items + payments embarqués dans la réponse)
          │     UPSERT helloasso_orders / _items / _payments
          ├── entity_resolver.entity_by_email pour rattacher orders + items :
          │     items rattachés par user_email, fallback payer email
          │     Entity créée si besoin (entity_type='ADHERENT' pour items Membership)
          └── Pour toute Entity avec ≥ 1 item Membership → is_member=True

helloasso_create.create_membership_for_entity(...)
    (création côté HelloAsso pour tiers ayant adhésion POS sans HA : plus d'écran,
     l'API HelloAsso v5 ne permettant pas de créer une adhésion manuelle)
```

### États financiers (Bilan / CdR)

```
GET /reports/bilan
    │
    ├── Détermine l'exercice courant et N-1
    │
    └── reports.build_bilan(fy, fy_prev)
          └── Pour chaque ligne du bilan :
                _net(["211"], fy.id)
                  └── SELECT SUM(debit) - SUM(credit)
                       FROM journal_lines
                       JOIN journal_entries ON ...
                       JOIN accounts ON code LIKE "211%"
                       WHERE fiscal_year_id = fy.id
```

---

## Tri & filtre par mois sur les listes

Les 8 listes datées de l'application partagent un mécanisme commun de tri par date + filtre par mois, factorisé dans `app/utils/list_filters.py` et `app/templates/_list_helpers.html`.

**Listes concernées** :

| Liste | Endpoint Flask | Colonne triée |
|-------|---------------|---------------|
| Écritures | `entries.index` | `JournalEntry.entry_date` |
| Transactions bancaires | `bank_accounts.transactions` | `BankTransaction.transaction_date` |
| Versements Stancer | `payouts.index` | `Payout.date_payout` |
| Paiements d'un versement | `payouts.detail` | `Payment.date_payment` |
| Commandes POS | `orders.index` | `Order.date_order` |
| Factures clients | `customer_invoices.index` | `CustomerInvoice.invoice_date` |
| Rapprochement | `reconciliation.index` | `BankTransaction.transaction_date` |
| Lot Odoo CSV | `imports.odoo_batch` | `OdooImportLine.invoice_date` |

**Convention des paramètres GET** :

- `sort` = `asc` | `desc` (défaut `desc`)
- `month` = `YYYY-MM` (ex : `2026-03` → filtre `WHERE column >= 2026-03-01 AND column < 2026-04-01`)

**Helpers Python** (`app.utils.list_filters`) :

```python
parse_sort(arg, default='desc')         # → 'asc' | 'desc'
parse_month(arg)                        # → (year, month) | None
apply_date_sort(query, column, sort)    # → query.order_by(column.desc().nullslast()) ou .asc().nullsfirst()
apply_month_filter(query, column, ym)   # → query.filter(column >= start, column < end)
month_options_for_fy(fy=None)           # → [{value:'2026-03', label:'mars 2026'}, ...]
sort_and_filter_context(sort, month)    # sucre qui prépare le dict pour le template
```

`month_options_for_fy()` lit l'exercice non clôturé le plus récent (sinon le plus récent tout court) et génère les 12 mois en français (`janvier 2026`, `février 2026`, ...).

**Macros Jinja** (`templates/_list_helpers.html`) :

- `sortable_date_header(label, current_sort, endpoint, extra_args)` — génère le `<th>` avec lien qui bascule `asc ↔ desc` à chaque clic, indicateur ▲/▼, en préservant les autres query args (filtre les valeurs nulles/vides). Exemple :

  ```jinja
  {% from "_list_helpers.html" import sortable_date_header, month_filter_select %}
  <th>{{ sortable_date_header('Date', current_sort, 'orders.index', {'month': current_month}) }}</th>
  ```

- `month_filter_select(name, options, selected)` — `<select>` Bootstrap-friendly avec option « Tous les mois » en tête.

**Pattern d'intégration dans une vue** :

```python
from app.utils.list_filters import (
    parse_sort, parse_month, apply_date_sort, apply_month_filter,
    sort_and_filter_context,
)

@bp.route("/")
@login_required
def index():
    sort = parse_sort(request.args.get("sort"))
    month_arg = request.args.get("month")
    month_tuple = parse_month(month_arg)

    query = MyModel.query
    query = apply_month_filter(query, MyModel.my_date, month_tuple)
    query = apply_date_sort(query, MyModel.my_date, sort)
    rows = query.all()
    return render_template(
        "my/index.html", rows=rows,
        **sort_and_filter_context(sort, month_arg),
    )
```

---

## Gestion des montants

Tous les montants sont stockés en **centimes entiers** (`INTEGER`) :

```python
# Stockage
debit_cents = int(round(float(form_value) * 100))   # ex: 1234 pour 12,34 €

# Affichage (filtre Jinja2)
{{ amount_cents | euros }}   # → "1 234,00 €"
```

Cela évite tout problème d'arrondi flottant dans les calculs comptables.

---

## Sécurité

| Mécanisme | Implémentation |
|-----------|---------------|
| Credentials services externes | Table tenant `external_connections(service, key, value)` (voir [multi_tenant.md](multi_tenant.md#credentials-externes-per-instance)). Repli sur `.env` global quand la ligne est absente. Activation et dernier test : table `integration_states`. UI : **Configuration › Intégrations** (admin uniquement), services `external_config` + `integrations`. |
| Sauvegardes d'instance | Copie SQLite atomique (`sqlite3.Connection.backup`) déposée dans `instance/backups/`. Restauration via upload + `PRAGMA integrity_check` + snapshot `pre-restore-…`. Voir [backups.md](backups.md). |
| Authentification | Flask-Login, utilisateurs stockés en méta-base avec `password_hash` (Werkzeug `pbkdf2:sha256`) |
| Autorisation admin | Décorateur `@admin_required` (`app/decorators.py`) — 403 si `current_user.is_admin` est faux |
| Isolation multi-tenant | `before_request` charge l'instance depuis `session["instance_id"]` ; les requêtes SQLAlchemy par défaut sont rebindées vers l'engine tenant correspondant |
| CSRF | Flask-WTF : jeton dans chaque formulaire POST ; en-tête `X-CSRFToken` (balise `<meta name="csrf-token">`) pour les requêtes HTMX et l'API JSON |
| API JSON `/api/v1` | Même session et même routage d'instance que les pages ; non connecté → 401 JSON (pas de redirection) ; même origine uniquement (pas de CORS) |
| Injection SQL | Impossible via SQLAlchemy ORM (requêtes paramétrées) |
| Clôture d'exercice | `FiscalYear.closed` vérifié avant toute mutation d'écriture |
| Sessions | Cookie signé par `SECRET_KEY` |

> En production, définir `SECRET_KEY` à une valeur aléatoire forte (ex: `python -c "import secrets; print(secrets.token_hex(32))"`) et servir l'application derrière un reverse proxy HTTPS (nginx, Caddy).
