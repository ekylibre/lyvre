# Architecture

## Structure du projet

```
compta-asso/
│
├── run.py                        # Point d'entrée : charge .env, crée l'app Flask
├── seed_accounts.py              # Script one-shot : charge PCA + journaux en base
├── requirements.txt
├── .env                          # Variables d'environnement (gitignorée)
│
├── app/
│   ├── __init__.py               # App factory : create_app(), filtres Jinja2
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
│   │   └── odoo_import.py
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
│   │   ├── entities.py           # CRUD tiers
│   │   ├── rules.py              # Affichage règles + application
│   │   └── payouts.py            # Liste + détail + sync Payouts/Payments Stancer
│   │
│   ├── services/                 # Logique métier (sans dépendance Flask)
│   │   ├── ledger.py             # Moteur comptable : validation, saisie, soldes
│   │   ├── reports.py            # Calcul Bilan et Compte de résultat
│   │   ├── reconciler.py         # Rapprochement bancaire
│   │   ├── ofx_importer.py       # Import fichiers OFX
│   │   ├── odoo_importer.py      # Import CSV Odoo
│   │   ├── rules_engine.py       # Catégorisation automatique des transactions
│   │   ├── stancer_sync.py       # Synchronisation Payouts + Payments Stancer (API v2)
│   │   └── stancer_async.py      # Wrapper threading + suivi via SyncJob
│   │
│   ├── templates/                # Templates Jinja2
│   │   ├── base.html             # Layout principal (nav, Bootstrap, HTMX)
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
│   │   └── payouts/
│   │
│   └── static/
│       ├── css/app.css           # Surcharges Bootstrap + styles impression
│       └── js/app.js             # Indicateur de balance, helpers HTMX
│
├── data/
│   ├── plan_comptable_asso.json  # 783 comptes PCA (source : fichier XLS)
│   └── rules.yml                 # Règles de catégorisation (éditable sans redémarrage)
│
├── migrations/                   # Migrations Alembic (versioning schéma)
├── instance/                     # compta.db (gitignorée)
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
| **requests** | Appels REST à l'API Stancer v2 (Payouts + Payments) — auth HTTP Basic |

### Frontend

| Composant | Rôle |
|-----------|------|
| **Bootstrap 5.3** (CDN) | Grille, composants UI |
| **HTMX 2.0** (CDN) | Chargement partiel : lignes d'écriture, suggestions de rapprochement, recherche de comptes |
| **Apache ECharts 5** (CDN) | Rendu des graphiques du tableau de bord (les options sont préparées côté serveur) |

Pas de build step JavaScript.

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
POST /entries/new
    │
    ├── Validation HTTP (blueprint entries.py)
    │     └── parse form: fy_id, journal_id, lines[]
    │
    ├── ledger.validate_lines(lines)
    │     └── Vérifie Σ débit = Σ crédit, total ≠ 0
    │
    └── ledger.post_entry(...)
          ├── Vérifie FY non clôturé
          ├── Génère référence auto (ex: BQ-2024-0001)
          ├── Crée JournalEntry (is_balanced=True)
          └── Crée N JournalLine (debit_cents / credit_cents)
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
GET /reconciliation/suggest/<bt_id>  [HTMX]
    │
    └── reconciler.suggest_matches(bt_id, window_days=3)
          ├── Lit la transaction (montant signé)
          ├── Cherche JournalLine non liées, même montant, ±3 jours
          └── Trie par score (date exacte=2pts, ±semaine=1pt)

POST /reconciliation/link
    │
    └── reconciler.reconcile(bt_id, line_id)
          ├── SET bank_transaction.journal_line_id = line_id
          └── SET bank_transaction.reconciled = True
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
| Authentification | Flask-Login, mot de passe hashé (Werkzeug `pbkdf2:sha256`) |
| CSRF | Flask-WTF, token dans chaque formulaire POST |
| Injection SQL | Impossible via SQLAlchemy ORM (requêtes paramétrées) |
| Clôture d'exercice | `FiscalYear.closed` vérifié avant toute mutation d'écriture |
| Sessions | Cookie signé par `SECRET_KEY` |

> En production, définir `SECRET_KEY` à une valeur aléatoire forte (ex: `python -c "import secrets; print(secrets.token_hex(32))"`) et servir l'application derrière un reverse proxy HTTPS (nginx, Caddy).
