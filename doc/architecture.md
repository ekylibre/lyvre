# Architecture

## Structure du projet

```
compta-asso/
│
├── run.py                        # Point d'entrée : charge .env, crée l'app Flask
├── seed_accounts.py              # Charge le plan comptable (asso|sci, détecté si omis) + journaux
├── seed_meta.py                  # Méta-base : admin, instance par défaut, colonnes ajoutées
├── requirements.txt
├── Makefile                      # make check (typecheck, Vitest, build, pytest) ; make e2e (Playwright)
├── .nvmrc                        # Node 22 (développement et build du front uniquement)
├── .env                          # Variables d'environnement (gitignorée)
├── scripts/e2e_server.py         # Serveur jetable (port 5099) des tests de bout en bout
├── scripts/readme_screenshots.mjs # Captures du README (doc/images/) sur ce serveur jetable
│
├── frontend/                     # SPA React 19 + Mantine 9 (TypeScript, Vite) → app/static/dist/
│   ├── vite.config.ts            # base /static/dist/, manifest, serveur de dev :5173
│   ├── e2e/                      # Parcours Playwright (fixtures.json, helpers.ts, *.spec.ts)
│   └── src/
│       ├── main.tsx              # Point d'entrée unique : fournisseurs + routeur
│       ├── app/                  # Coquille : AppShell (menus, en-tête, cloche des notifications), routes.ts (spa_routes.json →
│       │                         #   pages), navigation (AppLink, useGoTo), thème Lyvre (theme.ts,
│       │                         #   lyvre.css), palette Ctrl+K (Spotlight), useRouteModal
│       ├── api/                  # client.ts (fetch + CSRF, ApiError), resources.ts (useList,
│       │                         #   useAction, notices), session.ts, upload.ts (multipart + progression),
│       │                         #   jobs.ts (jobs suivis à l'écran)
│       ├── components/           # DataGrid, FormModal/FormDrawer, ApiForm, FilterBar, Money,
│       │                         #   StatusBadge, AccountSelect, EntitySelect, JobStatus, ConfirmButton…
│       ├── features/             # Un dossier par domaine (pages, types, logique testée)
│       └── lib/                  # format.ts, money.ts, types.ts, recentAccounts.ts
│
├── app/
│   ├── __init__.py               # App factory : create_app(), blueprints, filtre `euros` (rapport)
│   ├── spa.py                    # Coquille spa.html servie sous les endpoints d'origine (url_for)
│   ├── spa_routes.json           # Pages de la SPA : règle Flask, endpoint, publique ou non
│   ├── frontend.py               # vite_assets() : bundle (manifest) ou serveur de dev Vite
│   ├── menu_config.py            # Menus par plan comptable (MENUS, build_nav) → /api/v1/session
│   ├── tenant.py                 # Routage multi-tenant, current_instance(), current_chart()
│   ├── decorators.py             # admin_required
│   ├── config.py                 # Classes de configuration (Dev / Prod)
│   ├── extensions.py             # Singletons : db, migrate, login_manager, csrf
│   │
│   ├── api/                      # API JSON /api/v1 (un module par domaine, conventions §API)
│   │   ├── __init__.py           # Blueprint, ApiError, notice(), get_or_404, json_body, erreurs JSON
│   │   ├── session.py            # Session, connexion, instance, préférences, tâches (jobs)
│   │   ├── journals.py · fiscal_years.py · chart.py · products.py · rules.py · task_types.py
│   │   ├── entries.py · reports.py · lookups.py · search.py
│   │   ├── entities.py · members.py · work_times.py · users.py
│   │   ├── bank_accounts.py · reconciliation.py · imports.py · payouts.py · purchases.py
│   │   ├── odoo.py · impact.py · activity_report.py
│   │   └── integrations.py · instances.py
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
│   ├── views/                    # Routes Flask restantes : fichiers et exports seulement
│   │   ├── auth.py               # Chargement de l'utilisateur, /logout
│   │   ├── reports.py            # Exports CSV / ODS des états
│   │   ├── entities.py           # Exports des adhérents (CSV / XLSX)
│   │   ├── purchases.py          # Pièces des factures d'achat
│   │   ├── impact.py             # Export XLSX Visibilité & Impact
│   │   ├── activity_report.py    # Aperçu HTML, PDF, exports, photos, logo, archives du rapport
│   │   ├── instances.py          # Téléchargement d'une sauvegarde
│   │   └── integrations.py       # Ancienne adresse des intégrations → page de la SPA
│   │
│   ├── queries/                  # Requêtes de lecture partagées (tableau de bord, tiers)
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
│   ├── utils/                    # Helpers transverses
│   │   └── list_filters.py       # Parse sort/month, options de mois des exercices
│   │
│   ├── templates/
│   │   ├── spa.html              # Coquille de la SPA (CSRF, favicon, bundle Vite)
│   │   └── activity_report/      # _body.html, pdf.html, export.html : PDF, exports, aperçu
│   │
│   └── static/
│       ├── dist/                 # Build Vite (gitignoré)
│       ├── css/report.css        # Styles du rapport d'activité (inlinés dans le PDF et les exports)
│       └── favicon.svg
│
├── data/
│   ├── plan_comptable_asso.json  # 783 comptes PCA (source : fichier XLS)
│   ├── plan_comptable_sci.json   # 576 comptes SCI (source : doc/plan-comptable-SCI.pdf)
│   └── rules.yml                 # Règles de catégorisation (éditable sans redémarrage)
│
├── migrations/                   # Migrations Alembic (versioning schéma)
├── tests/                        # pytest : services, API (tests/api/), coquille
├── instance/                     # Bases SQLite, pièces jointes, sauvegardes (gitignoré)
└── doc/                          # Cette documentation
```

---

## Stack technique

### Backend

| Composant | Rôle |
|-----------|------|
| **Flask 3.1** | Framework web WSGI : API JSON, coquille de la SPA, fichiers et exports |
| **SQLAlchemy 3.1** | ORM, gestion des modèles, requêtes |
| **Flask-Migrate** | Migrations de schéma via Alembic |
| **Flask-Login** | Session ; non connecté → 401 JSON sur `/api/`, redirection vers `/login` sinon |
| **Flask-WTF** | Protection CSRF : jeton `X-CSRFToken` envoyé par la SPA sur toute écriture |
| **Jinja2** | Coquille `spa.html` et gabarits du rapport d'activité (PDF weasyprint, exports) |
| **ofxtools** | Parsing OFX 1.x (SGML) et 2.x (XML) |
| **pandas** | Lecture et mapping des CSV Odoo, exports XLSX |
| **PyYAML** | Lecture du fichier de règles de catégorisation |
| **odfpy** | Génération des exports ODS du compte de résultat |
| **PyMuPDF / Tesseract** | Lecture des factures d'achat (texte, Factur-X, OCR) |
| **weasyprint / LibreOffice** | PDF et exports DOCX / ODT du rapport d'activité |
| **requests** | Appels REST : Stancer v2, HelloAsso v5 (OAuth2), Qonto, GA4, Facebook |
| **xmlrpc.client** (stdlib) | Client XML-RPC Odoo — `/xmlrpc/2/common` + `/xmlrpc/2/object`, clé API comme mot de passe |

### Frontend

**SPA** React + Mantine servie par Flask aux **mêmes URL** que les anciennes pages (détail :
`claudedocs/design_front_mantine.md`) :

| Composant | Rôle |
|-----------|------|
| **React 19 + TypeScript** (build Vite 8) | Toutes les pages, un seul bundle, pages chargées à la demande |
| **Mantine 9** (core, form, dates, modals, notifications, spotlight, dropzone, charts, tiptap) | Composants, thème Lyvre (clair / sombre), palette Ctrl+K, dépôt de fichiers, éditeur de texte |
| **mantine-datatable** | Tableaux (tri, sélection, colonnes masquables mémorisées dans le compte, pagination) |
| **TanStack Query 5** | Lecture de l'API, cache, invalidation après une action |
| **react-router 8** | Routes déduites de `app/spa_routes.json` |
| **@mantine/charts** (Recharts) | Graphiques du tableau de bord et tendances des indicateurs ; le rapport d'activité garde `chart_svg` (SVG côté serveur) |
| **Vitest / Playwright** | Tests des composants et de la logique ; parcours de bout en bout |

**Pages et URL.** `app/spa_routes.json` liste chaque page (règle Flask, endpoint d'origine,
`public`). `app/spa.py` enregistre la coquille sous ces endpoints avant les blueprints : `url_for`
continue de fonctionner, et un endpoint en double fait échouer le démarrage (une page ne peut pas être
à la fois Flask et SPA). Côté client, `frontend/src/app/routes.ts` associe chaque endpoint à sa page
(vérifié par un test).

**Conventions de l'API** (`app/api/`) : erreurs `{error: {code, message, fields}}` ; 422 validation,
409 refus métier, 404, 403 admin ; les actions renvoient `item` et `notices` (messages affichés en
notifications) ; listes `{items, meta}` ; tâches longues → `job` suivi par `GET /api/v1/jobs/<id>`.
Les exports, PDF et pièces jointes restent des routes Flask (liens directs).

**Notifications** : à la fin d'une tâche en arrière-plan, `sync_jobs.run` crée une notification
pour l'utilisateur qui l'a lancée (`services/notifications.py`). La cloche de l'en-tête
(`AppShell/NotificationBell.tsx`) interroge `GET /api/v1/notifications` toutes les 30 s (pas quand
l'onglet est caché) et aussitôt qu'un `JobStatus` affiché voit son job finir ; une notification
arrivée pendant la session s'affiche aussi en message, sauf si son job est déjà suivi à l'écran.

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
[API /api/v1 ou route Flask] ← HTTP, session, JSON (ou fichier)
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
/entries/new (page de la SPA, EntryEditor au clavier)
    │
    ├── GET /api/v1/entries/form[?entry_id=|bt_id=]  (exercices ouverts, journaux, préremplissage)
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
POST /api/v1/imports/ofx         (multipart, page /imports/ofx)
    │
    ├── Récupère bank_account_id + fichier
    │
    └── ofx_importer.import_ofx(file, bank_account_id)
          ├── Parse OFX (ofxtools)
          ├── Pour chaque transaction :
          │     ├── Cherche (bank_account_id, fitid) en base
          │     ├── Si trouvé → duplicate++
          │     └── Sinon → INSERT bank_transactions
          ├── Retourne {imported, duplicates, errors}
          └── puis purchase_settlement.auto_match : règlement des factures d'achat saisies

POST /api/v1/payouts/sync        (asynchrone, non-bloquant)
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
    └── Réponse : {job} ; la SPA (composant JobStatus) interroge
          GET /api/v1/jobs/<id> chaque seconde jusqu'à done / failed (résultat affiché)

POST /api/v1/payouts/<id>/sync-payments   (asynchrone, sync ciblée d'un payout)
    │
    └── stancer_async.start_sync_payments_for_payout(app, payout_id)
          (même contrat : SyncJob kind='payout_payments', suivi identique)

POST /api/v1/rules/apply
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
/reconciliation/ (page de la SPA, raccourcis clavier, panneau de saisie EntryEditor)
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
POST /api/v1/orders/sync            (sync POS, synchrone)
POST /api/v1/customer-invoices/sync (sync factures clients, synchrone)
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
POST /api/v1/helloasso/sync
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
GET /api/v1/reports/bilan        (page /reports/bilan ; exports CSV / ODS : routes Flask)
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

Les listes datées (écritures, transactions bancaires, versements Stancer et leurs paiements, commandes
POS, factures clients, factures d'achat, rapprochement, lots Odoo) partagent les mêmes paramètres
d'URL, transmis tels quels à l'API :

- `sort` = `asc` | `desc` (défaut `desc`) ;
- `month` = `YYYY-MM` (ex : `2026-03` → `column >= 2026-03-01 AND column < 2026-04-01`).

**Côté serveur** (`app.utils.list_filters`) :

```python
parse_sort(arg, default='desc')         # → 'asc' | 'desc'
parse_month(arg)                        # → (year, month) | None
apply_date_sort(query, column, sort)    # → order_by(column.desc().nullslast()) ou .asc().nullsfirst()
apply_month_filter(query, column, ym)   # → filter(column >= start, column < end)
month_options_for_fy(fy=None)           # → [{value:'2026-03', label:'mars 2026'}, ...] (renvoyé dans meta.months)
```

`month_options_for_fy()` lit l'exercice non clôturé le plus récent (sinon le plus récent) et génère
ses 12 mois en français.

**Côté SPA** : `useUrlParams` (`components/FilterBar.tsx`) garde les filtres dans l'URL (liens
partageables, retour arrière) ; `MonthSelect` affiche `meta.months` ; `DataGrid` envoie le tri par
`onSortChange`. Exemple :

```tsx
const [params, setParams] = useUrlParams({ month: "", sort: "desc" });
const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
const { data } = useList<Order, OdooMeta>(ORDERS_KEY, `/api/v1/orders${query ? `?${query}` : ""}`);
// <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={data?.meta?.months} />
```

---

## Gestion des montants

Tous les montants sont stockés en **centimes entiers** (`INTEGER`) :

```python
# Stockage
debit_cents = int(round(float(form_value) * 100))   # ex: 1234 pour 12,34 €

# Affichage : SPA (MoneyText, formatEuros) ou gabarits du rapport (filtre `euros`)
<MoneyText cents={amount_cents} />   # → « 1 234,00 € » (moins typographique « − »)
```

Cela évite tout problème d'arrondi flottant dans les calculs comptables.

---

## Sécurité

| Mécanisme | Implémentation |
|-----------|---------------|
| Credentials services externes | Table tenant `external_connections(service, key, value)` (voir [multi_tenant.md](multi_tenant.md#credentials-externes-per-instance)). Repli sur `.env` global quand la ligne est absente. Activation et dernier test : table `integration_states`. UI : **Configuration › Intégrations** (admin uniquement), services `external_config` + `integrations`. |
| Sauvegardes d'instance | Archive `.zip` (copie SQLite atomique + pièces jointes) dans `instance/backups/`. Restauration via dépôt + contrôle de l'archive + `PRAGMA integrity_check` + snapshot `pre-restore-…`, après **confirmation forte** (slug saisi, vérifié côté serveur). Voir [backups.md](backups.md). |
| Authentification | Flask-Login, utilisateurs stockés en méta-base avec `password_hash` (Werkzeug `pbkdf2:sha256`) |
| Autorisation | `@admin_required` (administrateur global : utilisateurs, instances) ; accès par instance et rôles `admin` / `treasurer` / `accountant` (`app/access.py`, `@instance_admin_required`) ; l'expert-comptable est en lecture seule sur toute l'API (refus centralisé dans `app/api/__init__.py`) |
| Isolation multi-tenant | `before_request` charge l'instance depuis `session["instance_id"]` ; les requêtes SQLAlchemy par défaut sont rebindées vers l'engine tenant correspondant |
| CSRF | Flask-WTF : en-tête `X-CSRFToken` sur toute écriture de la SPA (jeton de la coquille, renouvelé par `/api/v1/session` à la connexion) |
| API JSON `/api/v1` | Même session et même routage d'instance que les pages ; non connecté → 401 JSON (pas de redirection) ; même origine uniquement (pas de CORS) |
| Secrets | Jamais renvoyés par l'API (intégrations : champ vide = valeur conservée ; URL de base d'une instance sans mot de passe) — test dédié |
| Contenus HTML | Notes Odoo en texte seul ; aperçu du rapport d'activité dans un `iframe` en bac à sable (`script-src 'none'`) ; gabarit de relance rendu en bac à sable Jinja |
| Injection SQL | Impossible via SQLAlchemy ORM (requêtes paramétrées) |
| Clôture d'exercice | `FiscalYear.closed` vérifié avant toute mutation d'écriture |
| Sessions | Cookie signé par `SECRET_KEY` |

> En production, définir `SECRET_KEY` à une valeur aléatoire forte (ex: `python -c "import secrets; print(secrets.token_hex(32))"`) et servir l'application derrière un reverse proxy HTTPS (nginx, Caddy).
