# Services — Logique métier

Les services sont dans `app/services/`. Ils n'ont pas de dépendance directe sur Flask (pas d'import de `flask`, `request` ou `g`). Ils peuvent être testés unitairement sans client HTTP.

---

## ledger.py — Moteur comptable

### `LedgerError`

Exception levée pour toute violation des règles comptables.

```python
from app.services.ledger import LedgerError
```

---

### `validate_lines(lines)`

Vérifie qu'une liste de lignes est valide avant enregistrement.

**Paramètres :**

```python
lines = [
    {"account_id": 42, "label": "Vente", "debit_cents": 0, "credit_cents": 10000},
    {"account_id": 7,  "label": "Recette", "debit_cents": 10000, "credit_cents": 0},
]
```

**Lève `LedgerError` si :**
- La liste est vide ou contient moins de 2 lignes
- Σ débit ≠ Σ crédit
- Le total est nul (écriture à zéro)

---

### `validate_entry_payload(data) → (clean, errors)`

Validation d'une écriture soumise par l'API (écran de saisie de la SPA ; montants en centimes). Les lignes
entièrement vides sont ignorées. `errors` associe un champ à un message :

| Champ | Règle |
|-------|-------|
| `fiscal_year_id` | Exercice existant et **non clôturé** |
| `journal_id` | Journal existant |
| `entry_date` | Date ISO, **comprise dans l'exercice** |
| `lines[i].account_id` | Compte existant et **non regroupement** (`is_header`) |
| `lines[i].amount` | Montants entiers ≥ 0, **soit un débit, soit un crédit** |
| `lines` | Au moins deux lignes, Σ débit = Σ crédit, total non nul |

`clean` contient les objets résolus (`fiscal_year`, `journal`, `entry_date`, `description`, `lines`).

### `post_validated_entry(clean, bank_transaction=None) → JournalEntry`

Crée l'écriture validée. Avec `bank_transaction`, rapproche la ligne banque (même compte comptable,
même montant signé) **dans la même transaction** ; sinon `LedgerError` et rien n'est enregistré.

### `update_entry(entry, clean) → JournalEntry`

Remplace l'en-tête et les lignes. `LedgerError` si l'exercice est clôturé ou si l'écriture est
rapprochée (`entry_is_reconciled(entry)`).

### `delete_entries(entry_ids, allow_managed=False) → list[dict]`

Supprime des écritures dans une seule transaction en **défaisant d'abord leurs rapprochements**
(une ligne supprimée ne doit pas rester liée à une transaction bancaire). Exercice clôturé →
refus pour l'écriture concernée ; écriture gérée par l'assistant de clôture (`MANAGED_SOURCES`)
→ refus, sauf `allow_managed=True` (appels de l'assistant). Résultat par écriture : `{entry_id, status, reference | message}`.
La facture d'achat ou le règlement adossé à une écriture supprimée (`purchases.journal_entry_id`,
`purchase_payments.journal_entry_id`) est délié : SQLite n'applique pas les `ON DELETE SET NULL`.

---

### `post_entry(...) → JournalEntry`

Crée une écriture équilibrée dans la base de données.

```python
entry = post_entry(
    fiscal_year_id=1,
    journal_id=2,
    entry_date=date(2024, 11, 15),
    description="Cotisation annuelle",
    lines=[
        {"account_id": 512_id, "debit_cents": 15000, "credit_cents": 0},
        {"account_id": 756_id, "debit_cents": 0, "credit_cents": 15000},
    ],
    source="MANUAL",         # ou "OFX_IMPORT", "QONTO_IMPORT", "ODOO_IMPORT", "PURCHASE"
    source_ref=None,         # référence externe optionnelle
    reference=None,          # si None, généré automatiquement
)
```

**Référence auto-générée** (`next_reference`) : `{CODE_JOURNAL}-{ANNÉE}-{SÉQUENCE:04d}`, ex :
`VT-2024-0003` ; la séquence suit le **plus grand** numéro du journal et de l'exercice (pas de doublon
après une suppression).

**Lève `LedgerError` si :**
- L'exercice est introuvable
- L'exercice est clôturé
- Les lignes ne sont pas équilibrées (appel interne à `validate_lines`)

`commit=False` se contente d'un `flush` pour inclure la création dans une transaction englobante.

---

### `account_balance(account_id, start_date=None, end_date=None) → (int, int)`

Retourne les totaux débit et crédit d'un compte sur une période.

```python
debit_cents, credit_cents = account_balance(account_id=42, start_date=date(2024,1,1))
solde = debit_cents - credit_cents  # positif = solde débiteur
```

---

### `trial_balance(fiscal_year_id) → (list[dict], FiscalYear)`

Calcule la balance de tous les comptes ayant des mouvements sur un exercice.

**Retourne** une liste de dictionnaires triés par code de compte :

```python
[
    {
        "account": <Account>,
        "debit_cents": 150000,
        "credit_cents": 0,
        "balance_debit": 150000,   # max(net, 0)
        "balance_credit": 0,       # max(-net, 0)
    },
    ...
]
```

---

### `general_ledger(account_id, fiscal_year_id) → (Account, list[dict])`

Retourne le grand livre d'un compte : toutes les lignes avec solde courant.

```python
account, rows = general_ledger(account_id=42, fiscal_year_id=1)
for row in rows:
    print(row["entry"].entry_date, row["line"].debit_cents, row["running_cents"])
```

**Chaque ligne :**
```python
{
    "line": <JournalLine>,
    "entry": <JournalEntry>,
    "running_cents": int,   # solde cumulé = Σ(débit - crédit) jusqu'à cette ligne
}
```

---

## reports.py — États financiers

Ce module calcule le Bilan et le Compte de résultat **selon le plan comptable de l'instance**
(`asso` ou `sci`, voir `app.tenant.current_chart()`), en regroupant les comptes par **préfixe de code**.
Le détail des rubriques et des comptes est dans [reports.md](reports.md).

### Primitives

```python
_net(["211"], fy_id)                      # débit - crédit
_net_credit(["756"], fy_id)               # crédit - débit (comptes de produits)
_net(["60", "61", "62"], fy_id, exclude=["603", "607"])   # préfixes avec exclusions
_amount("debit_only", ["41"], fy_id)      # somme des comptes à solde débiteur (actif)
_amount("credit_only", ["40"], fy_id)     # somme des comptes à solde créditeur (passif)
```

`_amount(mode, prefixes, fy_id, exclude=None)` accepte les modes `debit`, `credit`,
`debit_only` et `credit_only` ; les deux derniers ventilent les comptes de tiers et de
trésorerie **compte par compte** selon le sens de leur solde.

### Mises en page déclaratives

| Constante | Contenu |
|-----------|---------|
| `BILAN_LAYOUTS[chart]["actif" \| "passif"]` | Lignes `("section", libellé)`, `("row", libellé, préfixes, indentation[, mode[, exclusions]])`, `("total", libellé)` |
| `CDR_SECTIONS[chart]` | `(section, sens, [(clé, libellé, préfixes, exclusions), …])` — `ASSO_CDR_SECTIONS`, `SCI_CDR_SECTIONS` |
| `PARTICIPATION`, `IMPOTS_BENEFICES` | `691` et `69 sauf 691`, communs aux deux plans |

Les préfixes sont **disjoints** : chaque compte des référentiels `data/plan_comptable_{asso,sci}.json`
est compté une seule fois (tests de couverture dans `tests/test_reports_charts.py`).
Pour ajouter ou corriger une rubrique, il suffit d'éditer ces constantes.

---

### `build_bilan(fy, fy_prev=None, chart="asso") → dict`

```python
data = build_bilan(fy, fy_prev, chart)
data["actif"]    # → [ {"kind": "section", "label": …},
                 #     {"kind": "row", "label": …, "indent": 1, "n": cents, "p": cents|None},
                 #     {"kind": "total", "label": "TOTAL ACTIF", "n": …, "p": …} ]
data["passif"]   # idem, se termine par "TOTAL PASSIF"
```

`p` vaut `None` sans exercice N-1. Le résultat de l'exercice au passif agrège
`12 + classes 6/7` : le bilan est équilibré avant comme après clôture.

---

### `build_compte_resultat(fy, fy_prev=None, chart="asso") → dict`

```python
data = build_compte_resultat(fy, fy_prev, chart)
data["produits_exploitation"]["cotisations"]     # (N_cents, N1_cents)  — asso
data["produits_exploitation"]["loyers"]          # (N_cents, N1_cents)  — sci
data["participation_salaries"]                   # (N_cents, N1_cents)
```

Les clés de premier niveau sont **les mêmes pour les deux plans** (le tableau de bord
s'en sert quel que soit le plan) :

| Clé | Contenu |
|-----|---------|
| `produits_exploitation` / `charges_exploitation` | Rubriques d'exploitation du plan |
| `produits_financiers` / `charges_financieres` | Rubriques financières |
| `produits_exceptionnels` / `charges_exceptionnelles` | Opérations de gestion, en capital, reprises / dotations |
| `contributions_produits` / `contributions_charges` | Classes 87 / 86 (asso) ; dictionnaires vides pour une SCI |
| `participation_salaries` | 691 |
| `impots_benefices` | 69 sauf 691 |

`section_total(section) → (N, N-1)` additionne une section en **excluant les lignes `dont_*`**.

### `compte_resultat_rows(data, chart="asso")`

Génère la liste à plat `(kind, libellé, N, N-1)` — `kind` ∈ `section`, `subhead`, `row`,
`total`, `result` — utilisée par la page HTML, l'export CSV et l'export ODS. Les espaces en
tête de libellé donnent l'indentation (2 espaces par niveau). La ligne finale est
`EXCÉDENT` / `DÉFICIT` (asso) ou `BÉNÉFICE` / `PERTE` (sci).

---

## reconciler.py — Rapprochement bancaire

Un rapprochement valide lie une transaction bancaire à la ligne d'écriture qui l'enregistre : ligne
sur le **compte comptable du compte bancaire**, **même montant signé** (débit pour une entrée
d'argent, crédit pour une sortie), ni la transaction ni la ligne n'étant déjà rapprochées.

### `suggest_matches_scored(bank_transaction_id, window_days=3) → list[(JournalLine, score)]`

Lignes candidates (compte du compte bancaire, même montant signé, non rapprochées, date à
±`window_days`), triées par score (2 = même date, 1 = dans la fenêtre), puis par écart de date.
`suggest_matches(...)` renvoie seulement les lignes.

### `check_link(bt, line, lines_taken=()) → str | None`

Message d'erreur si le lien est invalide (introuvable, déjà rapprochée, autre compte, montant
différent), sinon `None`.

### `reconcile_many(pairs) → list[dict]`

Rapproche `[(bank_transaction_id, journal_line_id)]` dans **une seule transaction** ; chaque paire
est contrôlée (`check_link`) et une ligne ne peut servir qu'une fois dans le lot. Résultat par
paire : `{bank_transaction_id, journal_line_id, status: "ok" | "error", message?}`.

### `unreconcile_many(bank_transaction_ids) → list[dict]`

Défait des rapprochements ; chaque résultat `ok` donne le `journal_line_id` qui était lié (pour
refaire le lien en cas d'annulation).

### `auto_reconcile(bank_account_id, bank_transaction_ids=None, dry_run=False) → list[dict]`

Ne retient que les paires **sans ambiguïté** (`auto_pairs`) : une seule ligne candidate de même
date, candidate pour aucune autre transaction. `dry_run=True` renvoie les paires trouvées
(`status: "found"`) sans rien enregistrer.

### `reconcile(bank_transaction_id, journal_line_id, commit=True)`

Lien brut, sans contrôle (utilisé par `post_validated_entry` à l'intérieur de sa transaction).

---

## ofx_importer.py — Import OFX

### `import_ofx(file_obj, bank_account_id) → dict`

Parse un fichier OFX et insère les transactions nouvelles en base.

**Formats supportés :** OFX 1.x (SGML, export banques françaises) et OFX 2.x (XML).

**Déduplication :** chaque transaction est identifiée par `(bank_account_id, fitid)`. Les doublons sont comptés mais ignorés — réimporter le même fichier est sans effet.

**Conversion des montants :** `int(Decimal(str(trnamt)) * 100)` pour éviter les erreurs flottantes.

**Retourne :**
```python
{
    "imported": 12,       # nouvelles transactions insérées
    "duplicates": 3,      # FITID déjà présents
    "errors": ["FITID abc: ..."],  # erreurs de parsing par transaction
}
```

---

## rules_engine.py — Moteur de règles de catégorisation

### `load_rules() → list[Rule]`

Charge les règles **actives** de l'instance courante depuis la table `rules`, ordonnées par `position` croissante.

```python
rules = load_rules()
# [<Rule 1:TPE>, <Rule 2:TPE>, <Rule 3:MAIF / Assurance>, ...]
```

> Avant mai 2026, les règles vivaient dans `data/rules.yml`. Ce fichier sert désormais uniquement de gabarit pour `seed_rules.py` (one-shot par instance, idempotent).

### `validate_rule_data(form) → dict`

Valide un payload de formulaire CRUD. Renvoie un dict prêt à passer à `Rule(**data)`. Lève `RuleValidationError(message)` avec message FR-friendly sinon.

Checks effectués : nom non vide, au moins une condition, `re.compile(label_regex)`, `account_code` ∈ {6xx, 7xx, existant, non en-tête}, `amount_min ≤ amount_max`.

---

### `apply_rules(transactions=None, overwrite=False) → dict`

Applique les règles (de la table `rules`) sur une liste de transactions bancaires.

**Paramètres :**

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `transactions` | `None` | Liste de `BankTransaction`. Si `None`, traite toutes les transactions non catégorisées |
| `overwrite` | `False` | Si `True`, ré-applique même sur les transactions déjà catégorisées |

**Comportement :** les règles sont évaluées dans l'ordre de déclaration ; la première règle qui correspond est appliquée et les suivantes sont ignorées.
Les transactions annulées et celles qui **paient une facture d'achat** (`purchase_payments`) sont
ignorées : leur écriture est le règlement 401 / banque (`purchase_settlement`).

Si la règle définit un `entity` nommé, l'entité est créée automatiquement en base si elle n'existe pas encore.

Si la règle définit un `account` (code du plan comptable) et que la transaction
n'est pas déjà liée à une ligne d'écriture, une écriture comptable équilibrée est
créée (voir `_post_entry_for_transaction` ci-dessous) et la transaction est
automatiquement rapprochée.

**Retourne :**
```python
{
    "matched": 12,   # transactions catégorisées
    "posted": 8,     # écritures comptables créées
    "skipped": 5,    # transactions sans correspondance (ou déjà catégorisées si overwrite=False)
    "total": 17,
    "errors": [],    # erreurs de génération d'écriture (ex: compte introuvable, FY clôturé)
}
```

---

### Génération automatique d'écritures (`_post_entry_for_transaction`)

Helper interne, appelé par `apply_rules` lorsqu'une règle définit `account`.

**Convention de sens :**

| Préfixe du compte | Sens | Exemple |
|-------------------|------|---------|
| `6xx` | charge → **débit** sur le compte 6xx, **crédit** sur le compte bancaire | Loyer, salaires, achats, frais bancaires |
| `7xx` | produit → **débit** sur le compte bancaire, **crédit** sur le compte 7xx | Ventes, cotisations, subventions |

Le montant utilisé est `abs(transaction.amount_cents)` : c'est le préfixe du compte qui détermine le sens. Une règle dont le compte contredit le sens de la transaction (6xx sur un encaissement, 7xx sur un décaissement) n'est **pas appliquée** : ni tiers, ni catégorie, ni écriture, et une erreur est remontée (`errors`).

**Paramètres dérivés automatiquement :**
- **Journal** : `BQ` (banque)
- **Exercice** : celui qui contient `transaction.transaction_date`
- **Compte bancaire** (côté GL) : `bank_account.account_id`
- **Source** : `OFX_IMPORT` (`QONTO_IMPORT` pour une transaction synchronisée depuis Qonto), `source_ref` = `FITID:<fitid>`

**Lève `LedgerError` si :**
- Le code compte `account` n'existe pas dans le plan comptable
- Le compte est un compte d'en-tête (`is_header=True`)
- Le compte ne commence ni par `6` ni par `7`
- Aucun exercice ne couvre la date de transaction (ou exercice clôturé)
- Le journal `BQ` n'existe pas

Les `LedgerError` sont collectées dans la clé `errors` du dictionnaire de retour ; elles n'interrompent pas le traitement des autres transactions.

---

### Édition des règles

L'édition se fait depuis l'UI `/rules/` (création, modification, suppression, activation, réordonnancement ↑↓). La page d'édition embarque un testeur REGEX live (JS pur) et une cheat sheet des syntaxes Python courantes (`(?i)`, `|`, `\d`, `\s`, classes, ancres, échappement…).

Validation serveur (cf. `validate_rule_data`) :
- Au moins une condition (`label_contains`, `label_regex`, `amount_min_cents`, `amount_max_cents`, `raw_type`)
- `label_regex` doit compiler en Python
- `account_code`, s'il est fourni : doit commencer par `6` ou `7`, exister dans `accounts`, ne pas être un compte d'en-tête

---

## stancer_sync.py — Synchronisation Stancer (Payouts + Payments)

Doc API : https://docs.stancer.com/en/Concepts/Payouts.html

Le service appelle l'API REST **v2** (`https://api.stancer.com/v2`) via `requests`, en authentification HTTP Basic (clé secrète en username, password vide — convention Stancer).

**Endpoints utilisés** :
- `GET /payouts` — liste paginée des payouts
- `GET /payouts/{id}/payments` — payments rattachés à un payout

**Helpers internes** :
- `_api_get(path, **params)` — GET authentifié + timeout 30 s
- `_paginate(path, collection_key)` — générateur qui itère toutes les pages (`start`/`limit=100`)

### `fetch_payouts` / `fetch_payout_payments` — supprimés

Remplacés par `_paginate("/payouts", "payouts")` et `_paginate(f"/payouts/{id}/payments", "payments")`.

**Erreurs communes** :
- `RuntimeError` si `STANCER_SECRET_KEY` n'est pas défini dans la config Flask
- `requests.HTTPError` si l'API renvoie un statut ≥ 400 (clé invalide, quotas…)

---

### `sync_payouts(progress_cb=None) → dict`

Synchronise les payouts puis, pour chacun, leurs payments. Idempotent : tout est en *upsert* sur `stancer_id`.

**Étapes** :
1. Itère `/v2/payouts` page par page, *upsert* dans la table `payouts`.
2. `db.session.flush()` pour que les nouveaux payouts aient un `id`.
3. Pour chaque payout, appelle `sync_payments_for_payout(payout)` (404 = pas de payments, ignoré).
4. Commit unique en fin de boucle.

**`progress_cb(done, total, message)`** est appelé à chaque payout traité puis à chaque payout dont les payments viennent d'être importés. Utilisé par `stancer_async` pour persister la progression dans la table `sync_jobs`.

**Conversion Payout API → modèle** :

| Champ API v2 | Champ modèle | Note |
|--------------|--------------|------|
| `id` | `stancer_id` | clé d'idempotence |
| `total` | `amount_cents` | montant net versé en banque (= `payments.amount` − `fees`) |
| `currency` | `currency` (upper) | |
| `status` | `status` | `pending`, `to_pay`, `in_progress`, `paid`, `done`, `failed` |
| `date_paym` | `date_payout` | date d'émission par Stancer |
| `date_bank` | `date_bank` | date d'arrivée des fonds en banque |
| `statement_description` | `statement_description` | libellé qui apparaît sur le relevé |
| `fees` | `fees_cents` | commissions Stancer |
| `reference` | `description` | numéro de référence Stancer (ex : `588927`) |
| `created` | `created_at` | timestamp Unix |
| (réponse) | `raw_payload` | JSON brut |

**Rapprochement bank_transaction (cf. `_match_bank_transaction`)** : à chaque *upsert*, si `bank_transaction_id` n'est pas déjà rempli, on cherche une `BankTransaction` correspondante.

**Retourne** :
```python
{
    "imported": 12, "updated": 3, "total": 15,
    "payments_imported": 47, "payments_updated": 2, "payments_total": 49,
}
```

---

### `sync_payments_for_payout(payout, progress_cb=None) → (imported, updated, total)`

Itère `/v2/payouts/{stancer_id}/payments` et fait un *upsert* sur `stancer_id` dans la table `payments`. Ne commite pas (le caller décide).

`progress_cb(done, total, message)` est appelé à chaque payment traité.

**Conversion Payment API → modèle** :

| Champ API | Champ modèle |
|-----------|--------------|
| `id` | `stancer_id` |
| (lien) | `payout_id` (FK vers le payout passé en argument) |
| `amount` | `amount_cents` |
| `currency` | `currency` (upper) |
| `status` | `status` (`authorized`, `to_capture`, `captured`, `paid`, `refused`, `expired`, `canceled`, `disputed`, `failed`) |
| `method` ou `methods_allowed` | `method` |
| `description` | `description` |
| `order_id` | `order_id` |
| `unique_id` | `unique_id` |
| `customer.email` / `customer.name` | `customer_email` / `customer_name` |
| `date_payment` ou `date` | `date_payment` |
| `created` | `created_at` |

---

### `_match_bank_transaction(amount_cents, date_bank, description) → BankTransaction | None`

Recherche la `BankTransaction` qui correspond à un payout. Stratégie en deux passes — on ne lie que si **exactement un** candidat correspond, pour éviter les faux-positifs sur des montants ronds répétés.

**Stratégie 1 (prioritaire — référence Stancer unique)** :
- `amount_cents == payout.amount_cents`
- `label LIKE '%No <description>%'` (le libellé OFX a la forme `... Stancer SECONDE NATURE No <ref> of <date>`)

**Stratégie 2 (fallback si pas de description)** :
- `amount_cents == payout.amount_cents`
- `transaction_date == payout.date_bank`

> **Remarque** : la stratégie 1 tolère naturellement le décalage de 1 à 2 jours dû aux week-ends et jours fériés entre `payout.date_bank` (Stancer) et `bank_transaction.transaction_date` (date effective de crédit en banque), grâce à l'unicité de la référence `No <ref>`. Le rapprochement est appelé depuis `_upsert_payout` uniquement si `bank_transaction_id` n'est pas déjà renseigné — la sync est donc idempotente et ne « démappe » pas un rapprochement existant.

---

## stancer_async.py — Lancement asynchrone des syncs Stancer

Wrapper qui exécute `stancer_sync` dans un thread daemon pour ne pas bloquer la requête HTTP. Chaque exécution est tracée dans la table `sync_jobs` (voir [models.md](models.md#syncjob--job-de-synchronisation-stancer)) avec progression et résultat final.

### `start_sync_payouts(app) → SyncJob`

Crée un `SyncJob` (`kind='payouts'`) en `running`, lance un `threading.Thread` daemon qui pousse un `app.app_context()` et exécute `stancer_sync.sync_payouts(progress_cb=…)`. Retourne immédiatement.

**Idempotent** : si un job de même `kind` est déjà en cours, retourne ce job existant (pas de double-lancement).

---

### `start_sync_payments_for_payout(app, payout_id) → SyncJob`

Idem, mais pour la sync ciblée d'un payout (`kind='payout_payments'`, FK `payout_id`). Lève le job en `failed` si le payout n'existe pas.

---

### `latest_payouts_job() → SyncJob | None`

Retourne le job `kind='payouts'` le plus récent (peu importe le statut). Utilisé par la vue index pour réafficher l'état du dernier sync au chargement de la page.

### `latest_job_for_payout(payout_id) → SyncJob | None`

Retourne le job le plus récent (sync globale OU sync ciblée pour ce payout).

---

### Exécution dans le thread (`_run_in_thread`)

Le helper interne :
1. Pousse un `app.app_context()` (nécessaire pour accéder à `current_app.config`, `db.session`, …).
2. Appelle `work(job_id)` qui exécute la sync via `progress_cb`.
3. Sur succès : positionne `status='done'`, `finished_at=utcnow()`, `result_json=<dict>`.
4. Sur erreur : `RuntimeError` (clé manquante), `requests.HTTPError` (API ≥ 400) ou exception générique → `status='failed'` + message lisible.

### Throttle des écritures de progression

`_PROGRESS_THROTTLE = 5` : on ne pousse l'avancée en DB qu'à chaque 5e tick du callback, pour éviter de saturer SQLite quand la sync défile vite. Le dernier état (job terminal) est toujours persisté via `_finalize`.

---

## odoo_importer.py — Import CSV Odoo

### `import_odoo_csv(file_obj, batch_name) → dict`

Parse un export CSV Odoo et insère les lignes dans la table de staging `odoo_import_lines`.

**Mapping des colonnes CSV Odoo → champs internes :**

| Colonne Odoo | Champ interne |
|-------------|---------------|
| `name` | `invoice_number` |
| `invoice_date` | `invoice_date` |
| `partner_id/name` | `partner_name` |
| `product_id/name` | `product_name` |
| `price_subtotal` | `amount_ht_cents` |
| `price_total` | `amount_ttc_cents` |
| `account_id/code` | `account_code` |

La TVA est calculée : `tax_amount_cents = amount_ttc_cents - amount_ht_cents`.

**Encodage :** tente `utf-8`, bascule automatiquement sur `latin-1` en cas d'erreur.

**Retourne :**
```python
{
    "imported": 45,
    "errors": ["Ligne 12: ..."],
    "preview": [          # 5 premières lignes pour aperçu
        {"invoice_number": "INV/2024/001", "invoice_date": date(2024,1,15), ...}
    ],
    "batch": "odoo-20241115-143022",
}
```

---

## odoo_client.py — Client XML-RPC Odoo

Wrapper autour de `xmlrpc.client.ServerProxy` (stdlib). Partagé par les syncs POS et factures clients.

### `OdooConfigError`

Exception levée si la configuration Odoo est incomplète ou si l'authentification est refusée.

### `OdooClient(url, db, username, password)`

Le `password` est en réalité l'**API key** Odoo (depuis Odoo 14, on n'utilise plus le mot de passe). Endpoints :

- `/xmlrpc/2/common` — `authenticate(db, login, password) → uid` (lazy, cached)
- `/xmlrpc/2/object` — `execute_kw(db, uid, password, model, method, args, kwargs)`

Méthodes :
- `execute_kw(model, method, args=None, kwargs=None)` — appel générique
- `search_read(model, domain=None, fields=None, limit=None, offset=0, order=None)` — sucre pour la pagination

### `from_app_config(timeout=None) → OdooClient`

Construit un client à partir de la configuration de l'instance (`external_config`, repli `ODOO_*`). Lève `OdooConfigError` si l'intégration est désactivée ou si une valeur manque. `timeout` (secondes) borne chaque appel XML-RPC ; par défaut aucun (synchros inchangées). `version()` renvoie la version du serveur sans authentification.

---

## odoo_pos_sync.py — Synchronisation POS Odoo

### `sync_pos_orders(domain=None, limit=None, progress_cb=None) → dict`

Synchronise `pos.order` (+ lignes + paiements + partenaires) depuis Odoo via XML-RPC.

**Étapes** :

1. Pagination `search_read` sur `pos.order` (PAGE_SIZE=200) → upsert sur `odoo_id` dans `orders`.
2. `db.session.flush()` puis `search_read` par lots d'IDs sur `pos.order.line` → upsert dans `order_lines` (FK CASCADE).
3. Même chose pour `pos.payment` → `order_payments`.
4. `_fetch_partners(client, partner_ids)` : `res.partner` par lots de 200 (champs `id`, `name`, `email`, `phone`, `mobile`). `_resolve_partner_entity` crée une `Entity(entity_type='CLIENT')` par email si nouvelle. Rattachement `Order.entity_id` + `Order.partner_email`.
5. `_refresh_pos_member_flag()` : tout tiers ayant ≥ 1 ligne de commande POS matchant `LIKE '%adh%sion%'` (sur `full_product_name` ou `product_name`, insensible casse) bascule `is_member=True` + `entity_type='ADHERENT'`.
6. Commit unique en fin de sync.

**Retourne** :

```python
{
    "orders_imported": int, "orders_updated": int, "orders_total": int,
    "lines_imported": int, "lines_updated": int, "lines_total": int,
    "payments_imported": int, "payments_updated": int, "payments_total": int,
    "entities_created": int, "entities_updated": int,
    "members_flagged": int,
}
```

**Mapping pos.order → modèle Order** :

| Champ Odoo | Champ modèle |
|------------|--------------|
| `id` | `odoo_id` |
| `name` | `name` |
| `state` | `state` (`draft`/`paid`/`done`/`invoiced`/`cancel`) |
| `partner_id` (m2o) | `partner_id` + `partner_name` |
| `session_id` (m2o) | `session_id` + `session_name` |
| `date_order` | `date_order` (parsé `%Y-%m-%d %H:%M:%S` ou ISO) |
| `amount_total` / `amount_tax` / `amount_paid` / `amount_return` | `*_cents` (×100 entier) |
| `currency_id` (m2o) | `currency` (extrait des 3 premiers caractères du nom) |
| (réponse) | `raw_payload` (JSON brut) |

---

## odoo_invoice_sync.py — Synchronisation des factures clients

Service miroir du précédent, ciblant `account.move` filtré `move_type='out_invoice'`. Les helpers internes (`_to_cents`, `_m2o_id`, `_chunked`, `_fetch_partners`, `_resolve_partner_entity`) sont volontairement dupliqués depuis `odoo_pos_sync.py` plutôt que factorisés — l'objectif est de garder les deux modules indépendants l'un de l'autre.

### `sync_customer_invoices(domain=None, limit=None, progress_cb=None) → dict`

**Étapes** :

1. Pagination `search_read` sur `account.move` avec `DEFAULT_DOMAIN = [("move_type", "=", "out_invoice")]` (+ `domain` utilisateur en AND) → upsert dans `customer_invoices`.
2. `search_read` par lots d'IDs sur `account.move.line`. Le filtre `_is_product_line` ne garde que les lignes "produit" :
   - `display_type='product'` (Odoo ≥ 16), OU
   - `product_id` non vide (fallback Odoo < 16).
   Lignes de TVA et de contrepartie tiers ignorées.
3. `_fetch_partners` + `_resolve_partner_entity` (idem POS) → création auto d'`Entity(entity_type='CLIENT')` par email.
4. **Pas** de `_refresh_member_flag` (différence métier voulue : facture client ≠ adhésion).
5. Commit unique en fin de sync.

**Retourne** :

```python
{
    "invoices_imported": int, "invoices_updated": int, "invoices_total": int,
    "lines_imported": int, "lines_updated": int, "lines_total": int,
    "entities_created": int, "entities_updated": int,
}
```

**Mapping account.move → modèle CustomerInvoice** :

| Champ Odoo | Champ modèle |
|------------|--------------|
| `id` | `odoo_id` |
| `name` | `name` (ex : `INV/2026/00042`) |
| `state` | `state` (`draft`/`posted`/`cancel`) |
| `payment_state` | `payment_state` (`not_paid`/`in_payment`/`partial`/`paid`/`reversed`/`invoicing_legacy`) — valeur brute, non validée côté Python |
| `partner_id` (m2o) | `partner_id` + `partner_name` |
| `invoice_date` / `invoice_date_due` | parsés en `date` (pas `datetime`) |
| `amount_untaxed` / `amount_tax` / `amount_total` / `amount_residual` | `*_cents` |
| `journal_id` (m2o) | `journal_name` |
| `invoice_origin` | `invoice_origin` |
| `narration` | `narration` |

**Mapping account.move.line → CustomerInvoiceLine** :

| Champ Odoo | Champ modèle |
|------------|--------------|
| `product_id` (m2o) | `product_id` + `product_name` |
| `name` | `description` |
| `quantity` / `discount` | `qty` / `discount` |
| `price_unit` / `price_subtotal` / `price_total` | `*_cents` |
| `account_id` (m2o) | `account_code` (préfixe extrait du nom : `"707100 Ventes"` → `"707100"`) |
| `tax_ids` | CSV des IDs |

---

## entity_resolver.py — Résolution Entity par email

Helpers utilisés conjointement par `odoo_pos_sync`, `odoo_invoice_sync` et `helloasso_sync`.

### `entity_by_email(cache, email) → Entity | None`

Recherche une `Entity` par email **insensible à la casse**. `cache` est un dict `{email_lower: Entity|None}` mémoire, partagé pour la durée d'un sync, qui évite les requêtes répétées sur les mêmes emails. Retourne `None` si email vide ou non trouvé.

### `unique_entity_name(base_name, email=None) → str`

Garantit l'unicité de `Entity.name` :
1. Si `base_name` est libre → retourné tel quel.
2. Sinon essaye `"{base_name} ({email})"`.
3. Sinon `"{base_name} #2"`, `"#3"`, ... jusqu'à trouver libre.

---

## helloasso_client.py — Client HelloAsso v5

### `HelloAssoConfigError`

Exception levée si `HELLOASSO_CLIENT_ID` / `HELLOASSO_CLIENT_SECRET` / `HELLOASSO_ORG_SLUG` ne sont pas définis.

### `HelloAssoClient`

OAuth2 client_credentials sur `POST /oauth2/token`. Token mis en cache (~30 min, refresh transparent). Méthode utilitaire `paginate(path, params=None)` pour itérer toutes les pages d'une collection.

### `from_app_config() → HelloAssoClient`

Construit un client à partir de la config Flask.

---

## helloasso_sync.py — Synchronisation HelloAsso

### `sync_helloasso() → dict`

Synchronise les formulaires + commandes + items + paiements de l'organisation HelloAsso configurée.

**Étapes** :

1. `GET /v5/organizations/{slug}/forms` → upsert dans `helloasso_forms`.
2. `GET /v5/organizations/{slug}/orders?withDetails=true` (pagination `pageIndex`/`totalPages`) → upsert dans `helloasso_orders`. Le `withDetails=true` embarque items + payments dans la même réponse — pas d'appel supplémentaire.
3. Pour chaque order : upsert des `items[]` et `payments[]` (FK CASCADE).
4. Rattachement Entity : `entity_resolver.entity_by_email` par email du payeur (order) ou de l'user (item). Création auto si nouvel email.
5. Création auto `Entity(entity_type='ADHERENT', is_member=True)` pour toute Entity ayant ≥ 1 item de type `Membership`.

**Retourne** :

```python
{
    "orders_imported": int, "orders_updated": int,
    "items_imported": int, "items_updated": int,
    "payments_imported": int, "payments_updated": int,
    "members_created": int, "members_flagged": int,
}
```

> Les montants HelloAsso sont **déjà en centimes entiers** dans l'API — aucune conversion `×100` n'est appliquée.

---

## helloasso_create.py — Création d'adhésions HelloAsso

### `create_membership_for_entity(entity, amount_cents, payment_date, form_type, form_slug, client) → (bool, str)`

Crée une adhésion côté HelloAsso pour un tiers ayant une adhésion POS mais pas encore d'adhésion HA. Retourne `(True, info)` en succès, `(False, message_erreur)` sinon. Plus d'écran depuis la refonte du front : l'API HelloAsso v5 ne permet pas de créer une adhésion manuelle (le bouton était déjà grisé).

## membership_reminders.py — Relance email des adhérents expirés

Le gabarit, modifiable depuis l'écran, est rendu dans un **bac à sable Jinja** (`SandboxedEnvironment`, échappement HTML) : il n'a accès qu'aux variables `nom`, `email`, `date_anniversaire`, `lien_helloasso`.

Relance par email des adhérents dont l'adhésion est échue (statut `red`). Le service reçoit les `rows` déjà construites par la vue (`membership_status.build_member_rows`) pour éviter toute dépendance circulaire avec le blueprint `entities`.

**Config SMTP per-tenant** : lue via `external_config` (service `smtp`, table `external_connections` de la base tenant) avec repli `.env` (`MAIL_*`). L'envoi se fait en **`smtplib`** (et non Flask-Mail) pour rester correct en multi-tenant.

### `smtp_settings() → dict`
`{host, port, use_tls, username, password, sender}` depuis `external_config` (DB puis repli `.env`).

### `smtp_configured() → bool`
Délègue à `external_config.is_available("smtp")` : intégration activée **et** `host` + `sender` renseignés.

Le test de connexion SMTP est fait par la sonde de `integrations.py` (voir plus bas).

### `members_to_remind(rows) → list[dict]`
Filtre : `color == "red"`, email présent, `status != "?"` (exclut les adhérents sans aucune donnée d'adhésion).

### `helloasso_renewal_url() → str`
Construit `https://www.helloasso.com/associations/{org_slug}/adhesions/{form_slug}`, où `org_slug` vient de `external_config` (per-tenant) et `form_slug` = formulaire Membership le plus fréquent (fallback `adhesion`). Vide si slug non configuré.

### `render_reminder(template, row, helloasso_url) → (subject, html)`
Rend le gabarit `EmailTemplate` pour un adhérent (variables `nom`, `email`, `date_anniversaire`, `lien_helloasso`).

### `send_reminders(rows, dry_run=False) → dict`
Ouvre une connexion `smtplib` unique (`_open_smtp`) selon `smtp_settings()`, envoie un email HTML par adhérent (`EmailMessage` multipart text+html). Une erreur par adhérent est isolée (n'interrompt pas le lot) ; si SMTP non configuré → `skipped`. Retourne `{sent, skipped, errors, error_lines, targets}`.

---

## external_config.py — Configuration et activation des intégrations

Réglages par instance (table `external_connections` ; repli `.env` en développement seulement,
`INTEGRATIONS_ENV_FALLBACK`), interrupteur sur l'instance en base méta (`Instance.integrations`),
intégrations par structure (`SERVICE_CHARTS`) ; voir aussi
[models.md](models.md#integrationstate--activation-et-dernier-test-dune-intégration-tenant).

| Fonction | Rôle |
|----------|------|
| `get(service, key)` / `get_all(service)` / `source(service, key)` | Valeur effective (base, puis `.env` en développement) et son origine (`db`, `env`, `none`) |
| `scopes(service)` / `scope_enabled(service, scope)` / `scope_available` / `set_scopes` | Périmètre d'une intégration (`SCOPES`, `DEFAULT_SCOPES`) enregistré dans `instances.integrations.scopes` |
| `applies(service, chart=None)` / `applicable(chart=None)` / `recommended(chart=None)` | Intégrations de la structure (instance courante par défaut) ; recommandées (`RECOMMENDED`) |
| `set_many(service, values)` | Upsert ; valeur vide = ligne supprimée |
| `is_configured(service)` | Clés obligatoires renseignées (`SERVICE_REQUIRED_KEYS`) |
| `is_enabled(service)` / `set_enabled(service, bool)` | Interrupteur de l'instance courante (base méta) ; faux pour une intégration d'une autre structure ; hors instance (tests unitaires des clients) : vrai |
| `dismiss(service)` / `proposals(instance)` | « Ne plus proposer » ; recommandées ni activées ni écartées |
| `ensure_initialized(instance)` | Première ouverture : active les intégrations de la structure paramétrées en base (jamais d'après le `.env`) et non désactivées par l'ancien interrupteur |
| `state(service)` | `{enabled, available, message}` pour les méta des écrans |
| `required_message(service)` | « Cette action nécessite l'intégration … , désactivée. » |
| `is_available(service)` | Activée **et** configurée : à utiliser avant toute action qui dépend du service |
| `unavailable_reason(service)` / `unavailable_message(service)` | `"disabled"` / `"unconfigured"` / `None`, et message français associé (bandeaux, flash, exceptions) |
| `fingerprint(service)` | SHA-256 de la configuration effective (détecte un test périmé) |

Constantes : `SERVICE_KEYS`, `SERVICE_LABELS`, `SERVICE_DESCRIPTIONS`, `SERVICE_REQUIRED_KEYS`,
`SECRET_KEYS` (jamais réaffichées), `ENV_FALLBACK`, `SERVICE_CHARTS`, `RECOMMENDED`.

Les fabriques des clients (`odoo_client`, `helloasso_client`, `ga4_client`, `facebook_client`,
`stancer_sync._get_secret_key`) refusent de construire un client pour une intégration désactivée.

---

## integrations.py — Statut et test de fonctionnement des intégrations

### `run_check(service) → CheckResult`
Exécute la sonde du service (`PROBES`) : un appel léger en lecture, borné par `CHECK_TIMEOUT = 10` s
pour toute la sonde. Refuse sans appel réseau une intégration désactivée ou incomplète. Traduit
l'échec en message français (`describe_error` : délai dépassé, serveur injoignable, identifiants
refusés, ressource introuvable…, avec l'explication renvoyée par l'API), **masque les secrets**
(message et journaux), tronque à 500 caractères et enregistre le résultat avec l'empreinte de la
configuration.

| Service | Vérification |
|---------|-------------|
| Stancer | `GET /v2/payouts?limit=1` ; avertit si le préfixe de clé (`stest_`/`sprod_`) contredit le mode |
| Odoo | `version()` puis `authenticate()` |
| HelloAsso | jeton OAuth2 puis organisation `org_slug` |
| SMTP | connexion, `STARTTLS`, login, `NOOP` (délai unique partagé entre les étapes) |
| GA4 | rapport minimal (`activeUsers`, hier) |
| Facebook | lecture du nom de la Page |

Limite : la connexion TCP essaie chaque adresse du serveur (IPv6 puis IPv4) avec le délai restant ;
un serveur injoignable sur deux adresses peut porter un test à ~20 s.

### `status(service)` / `overview()` / `detail(service)`
Statut affiché, **sans appel réseau** : `disabled` › `unconfigured` › `untested` (jamais testé ou
configuration modifiée depuis le test) › `ok` / `error`. `detail` ajoute `last_sync(service)` : dernier
`SyncJob` suivi (Stancer : `payouts`/`payout_payments` ; GA4 et Facebook : `metrics`, avec la part de
la source lue dans `result_json`) ; Odoo, HelloAsso et SMTP ne sont pas suivis.

En test, remplacer une sonde : `monkeypatch.setitem(integrations.PROBES, "odoo", lambda: "OK")`.

---

## sync_jobs.py — Synchronisations en arrière-plan

| Fonction | Rôle |
|----------|------|
| `start(app, kind, work, *, message, error_message, **job_fields)` | Crée le `SyncJob` (ou renvoie celui déjà en cours avec les mêmes champs), capture l'instance courante et exécute `work(job_id)` dans un thread **sur la base de cette instance** |
| `run(app, instance_id, job_id, work, error_message)` | Corps du thread (appelable directement en test) : finalise le job `done` (avec `result_json`) ou `failed` (message de `error_message(exc)`), puis crée la notification de fin (`notifications.notify_job` ; son échec est journalisé et ne change pas le job) |
| `progress_callback(job_id, throttle=5)` | Callback `(done, total, message)` qui met à jour le job une fois sur `throttle` |
| `running_job(kind, **filters)` | Job en cours de ce type, ou None |

`start` enregistre l'utilisateur de la requête (`started_by_user_id`). Utilisé par `stancer_async`,
`qonto_sync.start_sync` et `purchase_sync.start_sync`. En test, remplacer `sync_jobs.threading.Thread`
par une exécution immédiate.

---

## notifications.py — Notifications de fin de tâche

| Fonction | Rôle |
|----------|------|
| `notify_job(job)` | Job terminé → `Notification` pour son auteur (toute l'instance si inconnu) : titre selon le type (`JOB_LABELS`), message = `summary(kind, result)` (+ nombre d'erreurs et la première) ou message d'échec, niveau `success` / `warning` / `danger`, lien vers l'écran ; None si le job tourne encore. Purge puis commit |
| `summary(kind, result)` | Résumé lisible du `result_json` d'un job (Qonto transactions, factures Qonto, Stancer) |
| `visible_to(user_id)` | Requête : notifications de l'utilisateur et de toute l'instance |
| `unread_count(user_id)` · `mark_read(user_id, ids=None)` | Non lues ; marque lues (toutes si `ids` est None, jamais celles d'un autre utilisateur) |
| `purge(now=None)` | Supprime les notifications lues depuis plus de `RETENTION_DAYS` (90) jours |

Les synchronisations des indicateurs (`metrics_sync`) restent synchrones : leur résultat s'affiche
directement, sans notification.

---

## instance_access.py — Accès aux instances (méta-base)

Seul porteur des règles d'accès : page Accès (instance courante), fiche instance, création et
import d'instance (claudedocs/design_acces_instances.md). Erreurs : `AccessError(message, field,
status)`, avec `field` au format du formulaire (`members.1.password`).

| Fonction | Rôle |
|----------|------|
| `parse_grants(items, field="members")` | Valide une liste `[{user_id, role}` ou `{email, full_name?, password, role}]` **sans écrire** : rôle connu, compte existant non administrateur global, email nouveau (sinon « choisissez-le dans la liste »), mot de passe de 8 caractères au moins, pas de doublon → `[Grant]` |
| `grants_warnings(grants)` | Avertissements non bloquants : aucun administrateur parmi les lignes, comptes désactivés (accès effectif à la réactivation) |
| `apply_grants(instance, grants, by_user)` | Crée les comptes (`must_change_password`) et les accès ; flush sans commit → `{created, granted}` ; `grants_summary` en donne le texte |
| `create_user(email, full_name, password)` | Nouveau compte non administrateur, mot de passe initial à changer |
| `members(instance, me_id)` | Membres, administrateurs globaux compris (`global_admin`, non modifiables) |
| `add_member(instance, data, by_user)` | `{user_id | email, role, full_name?, password?}` : compte existant ou créé si `password` ; refuse administrateur global et doublon ; commit |
| `set_role(instance, user_id, role)` · `remove_member(instance, user_id)` | Garde « au moins un administrateur » (hors administrateurs globaux) ; commit |

Le service reçoit l'instance en paramètre (pas `g.current_instance`) : il s'applique aussi à une
instance désactivée.

---

## qonto_client.py — Client de l'API Business Qonto

`QontoClient(login, secret_key, staging_token=None, timeout=30, retry=True)` : en-tête
`Authorization: login:secret` (pas du Basic) ; bac à sable (`thirdparty-sandbox.staging.qonto.co`,
en-tête `X-Qonto-Staging-Token`) si `staging_token`. Méthodes : `organization()`, `bank_accounts()`,
`list_transactions(bank_account_id, statuses, page, per_page, updated_from/to, settled_from/to)`,
`iter_transactions(...)`, `list_supplier_invoices(...)` ; **seule écriture** :
`create_supplier_invoice(content, filename, mime, idempotency_key)` → `POST /supplier_invoices/bulk`
(multipart `supplier_invoices[][file]`, `supplier_invoices[][idempotency_key]`) ; la réponse 200 peut
contenir des `errors` → `QontoError` ; renvoie la facture créée (`id`).

- **429** : jusqu'à 3 nouvelles tentatives (`Retry-After`, sinon 2 s, 4 s, 8 s) ; **5xx / réseau** :
  2 nouvelles tentatives ; **401 / 403** → `QontoAuthError` immédiat (Qonto bloque après 200 réponses
  401 par heure) ; `retry=False` pour le test de l'intégration. Un dépôt n'est repris qu'avec sa clé
  d'idempotence (pas de doublon côté Qonto). Message d'erreur : `errors[].detail` de la réponse.
- `from_app_config()` lève `QontoConfigError` si l'intégration est désactivée ou incomplète.

---

## qonto_sync.py — Comptes et transactions Qonto

| Fonction | Rôle |
|----------|------|
| `list_accounts(qonto_accounts)` | Comptes Qonto + compte bancaire rattaché, ou proposé (même IBAN) |
| `link_account(qonto_account, bank_account_id=… \| label=…, gl_account_id=…, sync_from=…)` | Rattache à un compte existant ou en crée un ; `QontoLinkError` si déjà rattaché |
| `unlink_account(ba)` / `set_sync_from(ba, date)` | Détache (transactions conservées) / change la date de début (reculer = synchro complète) |
| `sync_bank_account(bank_account_id, client=None, progress_cb=None)` | Synchronise un compte (voir ci-dessous) ; renvoie le résumé |
| `start_sync(app, bank_account_id)` / `latest_job(bank_account_id)` | Lancement en arrière-plan via `sync_jobs` / dernier job |

**`sync_bank_account`** : fenêtres mensuelles sur `settled_at` (statut `completed`) au premier passage,
puis une fenêtre sur `updated_at` depuis le curseur − 10 min (`completed` + `reversed`) ; une fenêtre de
plus de 9 000 résultats est coupée en deux (limite `page × per_page ≤ 10 000`). Pour chaque transaction
(`upsert_transaction`) : création si absente, sinon mise à jour de libellé, contrepartie, type, note,
justificatifs (jamais montant, date, rapprochement, tiers, catégorie ; un montant différent est
signalé) ; `reversed` → `is_reversed`. Commit **par page**, puis règles et rattachement des tiers sur
les nouvelles de la page ; le curseur n'avance qu'après un succès complet.

Résumé : `created`, `updated`, `unchanged`, `reversed`, `reversed_reconciled`, `skipped`, `conflicts`,
`rules_matched`, `rules_posted`, `linked_entities`, `proposed_counterparties`, `read`, `errors`.

---

## counterparties.py — Contreparties bancaires → tiers

| Fonction | Rôle |
|----------|------|
| `name_key(name)` | Nom normalisé (casse et espaces ignorés, accents conservés) |
| `link_existing(transactions)` | Rattache les transactions sans tiers à l'entité de même nom (débits et crédits), sans créer |
| `proposals(bank_account_id)` | Débits sans tiers groupés par contrepartie (hors `NO_SUPPLIER_TYPES`, annulées, ignorées), avec suggestions d'entités au nom proche |
| `invoice_proposals()` | Fournisseurs des factures d'achat sans tiers, groupés par nom (n° de TVA, IBAN, suggestions par nom ou IBAN) |
| `accept(key, entity_id=… \| create_name=…)` | Rattache les transactions **et factures d'achat** sans tiers de ce nom (crée un `FOURNISSEUR` si besoin, reprend TVA / IBAN / identifiant Qonto), puis comptabilise et règle les factures devenues prêtes ; renvoie `(entité, n_transactions, n_factures)` |
| `ignore(key, label)` | Mémorise la contrepartie dans `ignored_counterparties` (transactions et factures) |

---

## catalog.py — Catalogue produits / services

| Fonction | Rôle |
|----------|------|
| `parse_rate_bp(value)` / `format_rate(bp)` | « 5,5 » → 550 points de base ; 550 → « 5,5 % » |
| `default_purchase_product()` | « Achats divers », créé à la demande sur le premier compte présent : 6068, 628, 606 |
| `product_for(entity)` | Produit par défaut (actif) du fournisseur, sinon « Achats divers » |
| `ensure_default_purchase_product()` | « Achats divers » enregistré (commit) : appelé par les options de saisie et le préremplissage, pour que la ligne proposée désigne un produit de la liste |
| `remember_supplier_product(entity, lines)` | Premier produit précis des lignes (hors « Achats divers ») → produit par défaut du fournisseur qui n'en a pas (sans commit ; `purchase_entry.create`, `purchase_posting.save_lines`) |
| `purchase_products()`, `usage_count(product)` | Produits d'achat actifs ; lignes + fiches qui utilisent un produit |
| `validate_product_data(form, product_id=None)` | Champs d'un produit ; `CatalogError` (compte 6… / 7… selon le sens, taux, unicité) |

---

## purchase_sync.py — Factures d'achat Qonto

`sync_supplier_invoices(client=None, progress_cb=None)` : `GET /v2/supplier_invoices`, fenêtres
mensuelles sur `created_at` depuis `sync_from` au premier passage, puis `updated_at` depuis le curseur
(`sync_cursors`, clé `qonto_supplier_invoices`) − 10 min ; commit par page ; le curseur n'avance qu'après
un succès complet. `start_sync(app)` / `latest_job()` : arrière-plan via `sync_jobs`
(`kind = qonto_supplier_invoices`). `set_sync_from(date)` : reculer la date remet le curseur à zéro.

Par facture (`upsert_invoice`) : montants « 22.10 » → centimes (valeur absolue, `is_credit_note`
porte le sens) ; `rejected` / `discarded` / non financière → `is_hidden` ; fournisseur reconnu par
identifiant Qonto, puis n° de TVA, SIRET, IBAN, puis nom (`find_supplier` ; `match_entity` complète la fiche) ; lignes par défaut
(`default_lines` : une par taux, HT de Qonto conservé si un seul taux, la dernière absorbe l'écart ;
sinon une ligne TTC à taux à confirmer), régénérées tant que `lines_edited` est faux ; liens de
paiement (`purchase_settlement.link_invoice`). Facture **saisie** revenue de Qonto (`source = manual`,
même `qonto_id`) : `_merge_manual` garde la saisie, complète les champs vides et reprend statut, date de
paiement, net à payer et liens de paiement. Une facture **comptabilisée** n'est jamais modifiée sur
ses montants, sa date ou sa nature : le changement est noté dans `review_reason`. Après chaque page :
`post_ready` puis `settle`. Résumé : `read`, `created`, `updated`, `unchanged`, `hidden`, `to_review`,
`without_supplier`, `posted`, `settled`, `to_complete`, `errors`.

---

## purchase_posting.py — Comptabilisation en engagement

| Fonction | Rôle |
|----------|------|
| `purchase_state(p)` | `State(code, reasons)` : `hidden`, `to_complete` (motifs), `ready`, `posted` |
| `post(p)` | Écriture AC à la date de facture : lignes en 6… (HT si l'exercice est `vat_liable`, sinon TTC ; une ligne négative — remise obtenue 609 — passe au crédit), TVA en 44566 / 4456, crédit TTC au 401NNN du fournisseur ; avoir inversé ; `source = PURCHASE`, `source_ref = PURCHASE:<id>` |
| `post_ready(purchases)` | Comptabilise les prêtes, une transaction SQL chacune, puis `settle` ; `{posted, settled, errors}` |
| `supplier_account(entity)` / `next_supplier_code()` | Compte 401 du fournisseur (code de la fiche, sinon 401NNN suivant), créé dans le plan (parent 401, `TIERS`) |
| `unpost(p)` | Supprime l'écriture AC et réapplique la dernière réponse Qonto (`purchase_sync.apply_payload`) |
| `delete_blockers(p)` | Motifs de refus de suppression : statut Qonto validé (`QONTO_VALIDATED_STATUSES` : à payer, programmée, payée, archivée…), paiement lié, avoir lié à une facture (dans un sens ou l'autre), écriture d'un exercice clôturé |
| `delete(p)` | Supprime la facture, son écriture AC et sa pièce jointe ; `LedgerError` avec les motifs si elle est liée ; une facture Qonto n'est supprimée que dans l'application |
| `save_lines(p, rows)` | Lignes saisies (TVA calculée si vide, compte 6… exigé) ; `lines_edited = True` ; puis `post_ready` |

---

## invoice_reader.py — Lecture des factures d'achat

`read(path, mime, max_pages=3, ignore_ibans=(), ignore_sirens=(), ignore_names=(), hints_for=None)` →
`Extraction(fields, taxes, source, warnings, coherent)` ; chaque champ est un `Field(value, origin, check)`
(`origin` : `facturx`, `text`, `ocr` ; `check` : à vérifier). Ordre : XML CII embarqué (`factur-x.xml`,
`zugferd-invoice.xml`, `xrechnung.xml`, ≤ 1 Mo, DOCTYPE refusé) qui fait foi ; texte natif des 3 premières
pages ; OCR Tesseract `fra` pour une page de moins de 30 caractères et pour les images (JPEG, PNG).
Tesseract absent : avertissement.

- **Mise en page** (`layout_lines`) : le texte est reconstruit ligne visuelle par ligne visuelle à partir
  des coordonnées des mots (cellules séparées par trois blancs, lignes pivotées en fin de page) ; un
  libellé de colonne sans valeur à sa droite reçoit la valeur placée dessous (« Total TTC : 102,59 »),
  pour les tableaux de totaux en colonnes.
- **Montants** (`_choose_amounts`) : tous les montants qui suivent un libellé (TTC, HT, TVA, en français
  et en anglais) sont candidats ; le premier trio HT + TVA = TTC avec TVA ≤ 20 % du HT est retenu
  (`coherent`) ; une ligne « TOTAL 119,72 6,58 126,30 » fournit un trio ; « TVA non applicable /
  293 B » donne TVA 0. Sinon : ancienne lecture, et montants à vérifier s'ils sont incohérents ou
  invraisemblables (HT nul, TVA ≥ TTC, TVA > 20 %). Ventilation par taux accordée au trio retenu, ou
  déduite du taux usuel (20 ; 10 ; 8,5 ; 5,5 ; 2,1 %).
- **Autres champs** : nom (forme juridique suivie du capital / RCS, sinon bloc d'adresse — nom puis
  « 5 rue … » —, sinon site web ; deviné hors forme juridique), TVA FR (clé contrôlée), SIRET (Luhn ;
  libellé « référence », « acheminement », « compteur »… écarté), IBAN (mod 97) ; identifiants
  précédés de « client » et ceux de l'organisation (`ignore_sirens`, `ignore_ibans`, nom
  `ignore_names` via `same_name`) écartés ; n° de facture (« Réf. facture », « Facture n° », « N° pièce »,
  ni date ni montant) ; dates par libellé explicite (« Facture du », « Date d'établissement »,
  « Date limite », « à régler … au », « prélevée le »…), mois anglais, « venant à échéance » d'un contrat
  ignoré ; avoir ; remise après le total (`discount`).
- **OCR** : confusions corrigées (« O » → 0, « L 905,00 » → 1 905,00, « Sommeà ») ; si les montants
  ne sont pas confirmés, seconde lecture des pages scannées sur une image nettoyée (`_clean_scan` :
  contraste, bandeaux sombres inversés, filets de tableau effacés) et réunion des deux lectures.
- **Mémoire du fournisseur** : `hints_for(extraction)` renvoie un `SupplierHints(rates, tax_free,
  number_shapes)` pour le fournisseur reconnu ; la lecture est refaite avec : trio aux taux habituels
  d'abord, HT déduit du TTC au taux habituel (à vérifier), TVA 0 pour un fournisseur toujours sans TVA
  (à vérifier), n° de la même forme que les précédents (`number_shape`).

Champs OCR toujours à vérifier ; champs texte seulement s'ils sont devinés, déduits ou incohérents.
Mesure : `python scripts/invoice_corpus.py DOSSIER [--scan] [--memory] [-v]` compare la lecture aux
valeurs attendues d'un corpus (`expected.json` du dossier) et compte les erreurs silencieuses (fausses
et non signalées).

## attachments.py — Pièces des factures saisies

Dossier `instance/uploads/<slug>/` (`instance_dir`). `stage(file)` : 10 Mo maximum, type reconnu à
l'en-tête (PDF, JPEG, PNG), mise en attente dans `tmp/<jeton>` (+ `.json` : nom, type, taille) ;
`staged(token)` (jeton hexadécimal de 32 caractères) ; `store(purchase, token)` : déplace vers
`achats/AAAA/MM/<id>-<nom assaini>` et renseigne `attachment_*` (l'ancienne pièce est supprimée) ;
`path_of(purchase)` : chemin vérifié dans le dossier de l'instance ; `purge_staging()` : attentes de
plus de 24 h (appelé à chaque dépôt).

## purchase_entry.py — Saisie d'une facture d'achat

| Fonction | Rôle |
|----------|------|
| `read_staged(token)` | Lit la pièce en attente (`invoice_reader.read`) : IBAN des comptes bancaires, SIREN et nom de l'organisation écartés ; mémoire du fournisseur reconnu (`supplier_hints`) |
| `supplier_hints(entity)` | `SupplierHints` d'après ses 10 dernières factures : taux de TVA des lignes, toutes sans TVA, forme des n° ; None sans facture |
| `form_from_extraction(ext)` | `EntryForm(values, checks, rows, warnings, source)` : fournisseur reconnu (`find_supplier`) ou « à créer », lignes proposées (produit du fournisseur, une par taux) ; une remise après le total devient une ligne négative 6098 / 609 et le TTC devient le montant payé |
| `validate_header(form)` | `(clean, errors)` : date et TTC > 0 obligatoires, SIRET à 14 chiffres, fournisseur existant ou nom à créer |
| `duplicates(entity_id, number, issue_date, total, supplier_name, exclude_id)` | Même fournisseur et même n° (sans n° : même date et TTC) |
| `create(clean, rows, token)` | Facture `source = manual`, `lines_edited`, `idempotency_key` ; fournisseur créé au besoin (homonyme repris, identifiants complétés) ; lignes saisies ou par défaut ; pièce rangée ; `post_ready` |
| `update(p, clean, token)` | En-tête d'une facture saisie non comptabilisée ; pièce remplaçable si non envoyée à Qonto |
| `send_to_qonto(p, client=None)` | Dépose la pièce (`qonto_client.create_supplier_invoice`, clé `idempotency_key` de la facture) ; succès → `qonto_id`, `qonto_upload_status = sent` ; échec (erreur Qonto, réseau, pièce absente) → `failed` + `qonto_upload_error` ; jamais d'exception ; commit |
| `can_send_to_qonto(p)` / `qonto_upload_available()` | Facture saisie avec pièce, pas encore déposée / intégration Qonto disponible |

---

## purchase_settlement.py — Règlements des factures d'achat

| Fonction | Rôle |
|----------|------|
| `link_invoice(p)` | Aligne les liens `origin = qonto` de `purchase_payments` sur `matched_transactions[].transaction_id` (= `fitid` de la transaction Qonto) ; un lien réglé qui disparaît → `review_reason` ; liens hors Qonto intacts |
| `link_transactions(txns)` | Résout les liens en attente pour des transactions nouvellement importées |
| `linked_transaction_ids(ids)` | Transactions liées à une facture (exclues des règles) |
| `settle(purchases, transactions)` | Pour chaque transaction liée à des factures comptabilisées, non rapprochée : écriture BQ 401NNN / banque + rapprochement, atomiques ; fournisseurs différents ou transaction annulée → erreur |
| `to_replace()` | Transactions liées rapprochées d'une autre écriture : `replaceable` si écriture de règle (2 lignes, 6… + banque, `FITID:`), sinon rapprochement manuel signalé |
| `replace_many(ids)` | Supprime l'écriture de règle et passe le règlement, une transaction SQL par élément ; `{results, counters}` |
| `match_candidates(p)` | Facture saisie : transactions de comptes **hors Qonto**, montant = −TTC (+TTC pour un avoir), date ∈ [date − 5 j ; échéance (ou date) + 60 j], ni annulées, ni déjà liées, ni rapprochées autrement que par une écriture de règle ; même tiers d'abord, puis date la plus proche (`match_window(p)`) |
| `auto_match(purchases=None)` | Factures saisies comptabilisées sans paiement : lien `origin = match` si le candidat est **unique** et n'est candidat d'aucune autre facture en attente, puis `settle` ; `{matched, settled, errors}`. Appelé par `post_ready` (factures saisies) et après un import OFX |
| `link_manual(p, bank_transaction_id)` | Lien choisi parmi les candidats (`origin = manual`) puis `settle` |
| `unlink(payment)` | Lien hors Qonto : supprime l'écriture de règlement (rapprochement défait) et le lien |

Dans `qonto_sync.sync_bank_account`, par page : `link_transactions` et `settle` **avant** `apply_rules`
(résumé : `settled`).

---

## fec.py — Fichier des écritures comptables (FEC)

Format de l'article A47 A-1 du LPF : 18 champs (`JournalCode` … `Idevise`), première ligne = noms
des champs, séparateur tabulation, fin de ligne CRLF, dates `AAAAMMJJ`, montants `1234,56` (virgule,
sans séparateur de milliers), encodage **ISO-8859-15** (ponctuation typographique transcrite, autres
caractères hors jeu sans accent ou « ? »), nom `<SIREN>FEC<AAAAMMJJ>.txt` (date de fin d'exercice).

| Fonction | Rôle |
|----------|------|
| `validate(fy, at=None, user_id=None)` | Clôture provisoire : valide les brouillards restants (`validation.validate_remaining`, lot `closing`), numérotés à la suite ; aucun numéro existant ne change |
| `check(fy)` | `(errors, warnings)` : SIREN, exercice ouvert, écritures vides / déséquilibrées / hors dates ; avertit si l'exercice n'a pas d'à-nouveaux alors qu'un exercice le précède |
| `build(fy)` | `FecFile` (nom, contenu, lignes, écritures, totaux, `sha256`) : à-nouveaux (journal `AN`) en tête puis ordre chronologique ; `EcritureNum` = code journal + numéro sur 6 chiffres ; `PieceRef` = référence affichée ; comptes 401/411 d'un tiers en `CompAuxNum` / `CompAuxLib` |
| `verify(content)` | Relecture : en-têtes, 18 champs, champs obligatoires, formats de dates et montants, équilibre par écriture et global, numérotation continue par journal, caractères de contrôle |
| `preview(fy)` | Essai à blanc sur un exercice ouvert (assistant, étape 5) : brouillards numérotés provisoirement à la suite (`validation.assign`) et fichier relu dans un point de sauvegarde annulé ; renvoie (fichier, erreurs, avertissements, anomalies) |
| `freeze(fy)` | Clôture définitive : fichier écrit dans `instance/uploads/<slug>/fec/` (donc dans les sauvegardes `.zip`), `fec_path` et `fec_sha256` enregistrés |

La validation officielle reste l'outil « Test Compta Demat » de la DGFiP.

---

## validation.py · ledger_guard.py — Validation des écritures (lot F1)

| Fonction | Rôle |
|----------|------|
| `validation.validate(fy, entries, kind, user_id, until, at)` | Lot de validation (sans commit) : refus `ValidationError` (`problems`) si une écriture est déséquilibrée, sans ligne ou hors exercice ; numéros à la suite par journal, ordre (date, id) |
| `validate_until(fy, until)` · `validate_remaining(fy)` | Brouillards jusqu'à une date ; ce qui reste (clôture provisoire) |
| `validate_issued(entry)` | Écriture d'une facture / d'un avoir de vente émis : validée d'office (lot `auto` du jour) |
| `assign(entries, at)` | Numérotation seule (essai à blanc du FEC) |
| `undo_last_batch(fy, reason)` | Dévalide le dernier lot (motif) ; `last_batch`, `batches`, `draft_counts(fy)` (brouillards, plus de 3 mois) |
| `ledger_guard.allow("validation")` | Contexte réservé à `validation.py` pour changer les colonnes de validation |
| `ledger.reverse(entry, on_date, reason, user_id)` | Contrepassation (source `CANCELLATION`, `reverses_entry_id`) ; rapprochement défait, pièces détachées (`_detach`) |
| `ledger.remove_entry(entry)` · `delete_entries(ids, reverse_validated=True)` | Écriture d'une pièce refaite : supprimée en brouillard, contrepassée si validée |
| `ledger.reversed_entry_ids()` | Écritures contrepassées (exclues du rapprochement, des intérêts d'associés) |

La garde (`ledger_guard`, `before_flush`) refuse toute modification d'une écriture validée par
n'importe quel chemin et enregistre l'historique (`entry_events`, `after_flush`).

---

## closing.py — Assistant de clôture

Guide utilisateur : [Clôturer un exercice](cloture.md). Seule la décision de l'utilisateur est
stockée (`closing_steps`) ; les contrôles et soldes sont recalculés à chaque lecture ; toute
action est tracée dans `closing_events`. Erreurs métier : `ClosingError(message, status)`
(409 par défaut, 422 pour une saisie invalide, 404).

| Fonction | Rôle |
|---|---|
| `checks(fy) → list[Check]` | Étape 1 : transactions non rapprochées, écritures déséquilibrées ou hors dates, achats non comptabilisés, achats non réglés (info), 47x non soldés, 512 / 53 créditeurs |
| `add_inventory` · `delete_inventory` | Étape 2 : écriture d'inventaire (OD, dernier jour, `source='INVENTORY'`, `inventory_kind`) ; contreparties imposées par type |
| `result(fy)` | Étape 4 : produits (7), charges (6), résultat |
| `set_step(fy, step, state, note)` | Étapes 1 à 5 : fait, ignoré (motif), à faire |
| `close_provisional` · `close_final` · `reopen` | Étape 6 : numérotation (`fec.validate`), FEC figé (`fec.freeze`), réouverture motivée |
| `opening_lines` · `generate_opening(fy, create_next)` | Étape 7 : à-nouveaux (journal AN, classes 1 à 5, résultat en 120 / 129 ou sous-compte, à défaut 12) et extournes (`reverses_entry_id`) au 1er jour de l'exercice suivant |
| `cumulative_opening` · `_cumulative` | Lot D.5 : premier exercice clôturé en partie double après des exercices sans à-nouveaux (comptabilité simplifiée) — soldes de bilan cumulés depuis l'origine, résultats antérieurs en report à nouveau (110 / 119, à défaut 11) |
| `allocate` · `cancel_allocation` · `result_to_allocate` | Étape 8 : décision (organe, date dans N+1) et répartition sur 10x / 11x / 455x |

## dedicated_funds.py — Fonds dédiés (étape 3)

Ressource affectée (`DedicatedFund`) et ses mouvements (`DedicatedFundMovement`) : dotation
(débit 689x, crédit 19x) l'année de la ressource, utilisation (débit 19x, crédit 789x) les années
suivantes ; écritures OD au dernier jour (`source='DEDICATED_FUND'`). Plafonds : dotations cumulées
≤ ressource, utilisation ≤ solde au début de l'exercice. `funds_for(fy)` liste les fonds de
l'exercice (créés en N, mouvementés en N ou non soldés) ; `payload` donne soldes et reste à doter.
**Lot C.5** — un fonds peut financer un projet (`project_id`, `set_project`) ; `suggestion(fund, fy)`
propose, l'année de la ressource, la dotation du reste non utilisé (ressource − charges de classe 6
du projet sur l'exercice, hors écritures de fonds dédiés) et, les années suivantes, l'utilisation à
hauteur des charges du projet dans la limite du solde du fonds. Les messages affichent les montants
au format français (`app/utils/money.euros`).

## projects.py — Projets / activités (lot C.1)

`resolve(project_id)` (projet saisi, ValueError si inconnu ; utilisé par `ledger`, `purchase_posting`
et `rules_engine`), `totals(fiscal_year_id=None)` (charges, produits, résultat par projet), `save`,
`delete` (refus si utilisé), `set_line_project(line, project_id)` et `split_line(line, parts)` :
la ligne d'origine prend la première part, les suivantes sont de nouvelles lignes de même compte,
libellé et sens — l'écriture reste équilibrée et le FEC garde ses totaux. Refus : exercice clôturé,
écriture de l'assistant de clôture, ligne bancaire rapprochée. Erreurs : `ProjectError(message,
status, field)`.
`statement(project, start, end)` : compte de résultat du projet sur une période (comptes 6 et 7) et
détail des lignes, avec la facture d'achat jointe quand l'écriture vient d'une facture ;
`default_period(project)`.

## budget.py — Budget (lot C.2)

`months(fy)` (mois de l'exercice, libellés courts), `spread(annual, n)` (douzièmes entiers),
`grid(fy, project)` (lignes annuelles ou mensuelles du périmètre), `totals(rows)`, `save(fy,
project, rows)` (remplace le périmètre ; refuse doublons et comptes imbriqués, qui fausseraient le
réalisé), `copy_rows(fy, project, source)` (budget ou réalisé de l'exercice précédent, réalisé
regroupé au compte à 3 chiffres s'il existe ; mensuel si les deux exercices ont autant de mois,
sinon annuel), `actuals(fy, project, start, end)` (réalisé par compte, sens naturel),
`account_options()`. Erreurs : `BudgetError(message, field)`.

**Suivi (lot C.3)** — `tracking(fy, project=None, as_of=None)` : pour chaque poste du budget, prévu
de l'année, prévu à date (somme des mois entamés au `as_of`), réalisé à date (comptes commençant par
le code du poste ; seulement les lignes du projet si un projet est choisi), écart et taux ; le
réalisé non couvert par un poste remonte en lignes « hors budget » (compte à 3 chiffres) ; synthèse
charges / produits / résultat.

## cash_forecast.py — Prévisionnel de trésorerie (lot C.4)

`balances(today)` : par compte bancaire, solde comptable jusqu'à aujourd'hui **hors à-nouveaux**
(qui reprennent des soldes déjà comptés) plus les transactions bancaires non comptabilisées ;
comptes de caisse 53. `forecast(today)` : 12 mois glissants ; factures d'achat non réglées (montant
à payer à l'échéance ; avoir = encaissement), factures clients Odoo au reste dû, budget général
du mois (hors 68 / 78 ; mois en cours : prévu moins réalisé), saisies manuelles répétées ;
échéance dépassée → mois en cours ; `first_negative` (alerte). `save_item`, `item_payload` ;
erreurs `ForecastError(message, field)`.

## receipts.py — Reçus fiscaux (lot B)

**B.1 — paramètres.** `get()` (ligne unique créée au besoin), `readiness()` (mentions requises du
reçu : identité et SIREN ou RNA, adresse, objet, signataire, signature, éligibilité, articles,
comptes de dons présents), `save(data, user_id)` (activation refusée tant qu'une mention manque ou
sans déclaration de responsabilité ; changer l'éligibilité efface la déclaration),
`donation_accounts(prefixes)`, `save_signature` / `delete_signature` (PNG / JPEG ≤ 500 Ko, rangée
avec les pièces de l'instance ; la retirer désactive les reçus). L'outil n'évalue pas l'éligibilité.
Erreurs : `ReceiptError(message, field, status)`.

**B.2 — émission.** `donation_lines(year)` (lignes au crédit des comptes de dons de l'année civile),
`resolve_donors(lines)` (donateur choisi sur la ligne, sinon tiers de la transaction bancaire
rapprochée, sinon tiers dont le compte figure dans l'écriture), `candidates(year)` (par donateur,
hors dons déjà sur un reçu émis ; `donor_problems` : nature, adresse, SIRET d'une entreprise),
`issue(year, entity_ids, mode, user_id)` (un reçu par donateur ou par don ; numéro réservé par
`_next_number` dans la même transaction que le reçu et son PDF : un échec n'en consomme pas),
`render_pdf` (gabarit `templates/receipts/receipt.html`, mentions des Cerfa n° 11580*05 —
particuliers, articles 200 / 978 — et n° 16216*01 / 2041-MEC-SD — entreprises, article 238 bis ;
montant en lettres par `app/utils/money.euros_in_words`), `assign_donor`, `save_in_kind` /
`delete_in_kind`, `receipt_file` / `receipt_payload`.

**B.3 — lot, envoi, annulation, état annuel.** `check_issue(year, mode)` (contrôles avant le job) ;
`issue(..., progress)` exécuté par le job `donation_receipts` (`sync_jobs`, un seul à la fois par
instance, notification de fin) ; `send(receipt_ids, progress)` (SMTP de l'instance, PDF joint,
`sent_at` / `sent_to` ; une erreur n'arrête pas le lot) exécuté par le job `donation_receipts_send` ;
`cancel(receipt_id, reason, reissue)` (statut `cancelled`, motif, dons libérés ; `reissue` : même
dons sous un nouveau numéro, `replaced_by_id`) ; `annual_summary(year)`.

## cash.py — Caisse (lot D.1)

`ledger_balance(account_id, until)` (solde cumulé hors à-nouveaux), `movements(ba, start, end)`,
`record(ba, data)` (mouvement saisi : écriture au journal CA, source `CASH` ; refus d'une caisse
négative ou d'une contrepartie de trésorerie), `deposit(ba, data)` (dépôt en banque par 581, deux
écritures), `transfer_account()`. Le contrôle de clôture signale un compte 58x non soldé.

## simple_categories.py — Catégories (lot D.2)

`ensure_defaults()` (catégories par défaut, compte le plus précis présent dans le plan ; omises si
aucun compte), `listing`, `payload`, `usage_counts`, `save` (recette sur un compte 7, dépense sur
un compte 6), `move`. Erreurs : `CategoryError(message, field, status)`.

## simple_operations.py — Recettes et dépenses (lot D.3)

`create(data)` (écriture `SIMPLE` : trésorerie 512x / 53x contre le compte de la catégorie ; tiers
et projet sur la ligne de catégorie), `categorize(transaction_id, data)` (opération à la date et au
montant de la transaction, rapprochée dans la même transaction ; le sens de la catégorie doit
suivre celui de la transaction), `update` (rapprochée : seuls libellé, catégorie du même sens,
tiers et projet), `delete`, `operations(start, end, …)` (toute ligne 6 / 7 d'une écriture qui
touche la trésorerie), `to_categorize()`. Erreurs : `OperationError(message, field, status)`.

## simple_reports.py — États simplifiés et verrouillage (lot D.4)

`income_statement(fy)` (par catégorie, N / N-1 ; résultat), `treasury_situation(fy)` (soldes
cumulés début / fin de chaque compte bancaire et caisse, via `cash.ledger_balance`), `lock(fy,
locked)` (statut `closed` sans assistant ni FEC ; déverrouillage refusé si un FEC a été figé).
Les catégories par défaut ne partagent jamais un compte (`simple_categories.ensure_defaults`).


## associates.py — Associés (module « Associés », lot A1)

| Fonction | Rôle |
|---|---|
| `enabled()` | Option `has_associates` de l'instance courante (base méta) |
| `next_account_code()` | Premier sous-compte libre de 4551001 à 4551999 |
| `create(data)` / `update(associate, data)` | Tiers existant ou créé (homonyme repris), compte 455 créé au besoin (type `TIERS`, parent 455), taux 0 à 20 % ; le compte ne change plus dès qu'il a des écritures ; `AssociateError(message, field)` sans rien laisser en session |
| `delete_blockers(associate)` / `delete(associate)` | Refus si registre, écritures ou règlements |
| `holdings(at)` / `capital_parts(held)` | Parts par associé et nature à la date ; parts du capital = PP + NP |
| `balance(account_id, at)` | Solde du compte courant, créditeur positif |
| `listing(at)` | Lignes de la liste et totaux |

## share_register.py — Registre des parts (module « Associés », lot A2)

Hors comptabilité. `parse(data)` (erreurs `lines.<i>.<champ>`), `validate(clean, exclude_id)` :
reprise / souscription : parts reçues ; réduction : parts cédées ; ces trois types portent la
valeur nominale ; cession / succession : cédé = reçu par nature ; donation / réunion : capital
(PP + NP) inchangé ; tous : NP et usufruit varient d'autant ; aucune situation négative à la date
du mouvement ni après (le mouvement saisi passe après ceux de la même date). `create`, `update`,
`delete` (refus si un mouvement postérieur s'appuie dessus ; pièce via `attachments.store(…,
folder="parts")`). `situation_after` (prévisualisation), `capital(at, held)` (parts, nominal du
dernier mouvement qui le porte, capital, solde créditeur des 101…, avertissements), `payload`,
`movements(associate_id, until)`.

`attachments.store(target, token, folder="achats", day=None)` et `path_of(target)` servent tout
enregistrement portant les colonnes `attachment_*`.

## associate_operations.py — Opérations des comptes courants (module « Associés », lot A3)

Journal **AS « Associés »** (créé à la première écriture), `source = "ASSOCIATE"`. Rien n'est écrit dans Qonto.

| Fonction | Rôle |
|---|---|
| `payment_blocker(p)` / `pay_purchase(p, associate_id, paid_on)` | Facture comptabilisée, sans règlement, pas un avoir : écriture 401 du fournisseur / 455 de l'associé, `PurchasePayment(origin="associate")`, `source_ref = PURCHASE_PAYMENT:<id>` |
| `unpay_purchase(payment)` | Supprime paiement et écriture (exercice ouvert) |
| `create_expense(data, token)` / `delete_expense` | Note de frais : charge (6…) et TVA (`vat_account`) / 455, justificatif `frais/AAAA/MM/`, `source_ref = EXPENSE:<id>` |
| `bank_entry_lines(bt, associate)` | Lignes préremplies d'un apport (512 / 455) ou d'un remboursement (455 / 512) |
| `statement(associate, start, end)` | Relevé : solde d'ouverture, lignes avec origine (facture réglée, note de frais, banque, affectation…), solde progressif |
| `balances_by_fiscal_year()` | Soldes à la fin de chaque exercice par associé |

| `interest_preview(fy)` / `post_interest(fy)` | Intérêts (lot A4) : Σ des soldes créditeurs de fin de journée × taux / 365, hors intérêts déjà passés sur l'exercice ; taux de l'associé, sinon `organization.associate_interest_rate_bp` ; écriture AS par associé au dernier jour (6615, créé sous 661 / 66 s'il manque, / 455), `source_ref = INTEREST:<fy>:<associé>`, remplacée si on relance ; exercice ouvert |

`ledger.delete_entries` détache aussi les notes de frais de l'écriture supprimée.

`associates.allocation_proposal(fy)` (lot A4) : résultat à affecter (`closing.result_to_allocate`) réparti au prorata
des parts en pleine propriété et en usufruit à la date de clôture (nus-propriétaires exclus), centimes au plus fort
reste départagés par le nom ; l'affectation reste enregistrée par `closing.allocate`.

## associates_import.py — Import CSV des associés (module « Associés », lot A5)

Une ligne par associé et par nature : `nom ; compte ; nature ; parts ; date ; nominal ; solde ; taux` (UTF-8 ou
Windows-1252, séparateur `;` ou `,`, en-têtes sans casse ni accents). `analyse(content)` n'écrit rien : associé
existant repris (même nom), sinon entité de même nom reprise, sinon créée ; compte 455 donné ou prochain 4551… ;
compte, solde et taux identiques sur toutes les lignes d'un associé ; une reprise (`opening`) par date, avec sa
valeur nominale et les règles du registre ; solde d'ouverture passé seulement si le compte courant n'a encore aucune
écriture (sinon « ignoré »). `run(content, counterpart_code)` refait l'analyse et importe tout ou rien : associés,
mouvements de reprise, écritures AN datées de la reprise contre le compte de contrepartie choisi
(`source_ref = OPENING:<associé>`).

## Ventes — sale_entry, sale_posting, sale_issue, sale_documents, billing, einvoice (lots S0, S1)

| Module | Rôle |
|---|---|
| `sale_entry` | Brouillons : client (ou nouveau client), lignes (produit, quantité, prix HT, remise, TVA, compte), `compute` (HT par ligne, TVA par taux répartie sur les lignes), `vat_mode_for(date)` d'après l'exercice |
| `sale_posting` | Écriture VE : 411NNN du client (créé et noté sur la fiche) au débit TTC ; 7… au crédit HT ; 44571 (biens, ou débits) et 44574 (services à l'encaissement), créés sous 4457 s'ils manquent ; avoir inversé |
| `sale_issue` | `next_number` sous verrou, `issue_problems`, `issue` (numéro + client figé + écriture + PDF, un commit ; échec → rien), `credit_note`, `send` (SMTP, PDF joint, journal `sale_emails`) |
| `sale_documents` | Gabarit `templates/sales/document.html` (mentions obligatoires), PDF/A-3 Factur-X pour une pièce émise, PDF simple pour un brouillon ; conservation `ventes/AAAA/<numéro>.pdf` |
| `billing` | Réglages de facturation, mentions requises (`readiness`), logo |
| `einvoice` | XML CII EN 16931 (bibliothèque `factur-x`, contrôle XSD) et insertion dans le PDF/A-3 |
| `sale_issue` (S3, devis) | `quote_status` (expiré : émis et validité passée), `set_quote_status`, `to_invoice`, `quote_invoices` ; un devis s'émet (numéro, PDF simple) sans exercice ni écriture |
| `qonto_sales` (S4) | Périmètre « Ventes » de Qonto : `ensure_client` (recherche SIREN, TVA, email, nom, sinon création), `items` (libellé ≤ 40 caractères, suite en description, remise incluse au prix), `emit` (facture : brouillon puis finalisation, brouillon supprimé si la finalisation échoue ; avoir ; devis), `fetch_pdf`, `mark_paid` / `unmark_paid`, `send`, `sync` (lecture seule) ; client Qonto sans reprise automatique des écritures |
| `recurrence` (S5) | Échéancier (`period_of`, `period_label`, `first_due`, `add_months`), saisie du modèle, `prepare_due` (brouillons datés du jour, payables à l'échéance, idempotent), `issue_batch` |
| `leases` (S5) | Bail et sa récurrence de loyer (lignes loyer / provisions sur charges, comptes 706 / 708 par défaut), dépôt de garantie (165), `receipt` (quittance ou reçu, loyer et charges séparés par compte), `render_pdf` (`templates/sales/rent_receipt.html`), `send_receipt` |
| `subscriptions` (S6) | Abonnements : `due_dates`, `refresh` (échéances créées une fois, facture du fournisseur la plus proche — montant égal ou ±30 % si estimé — et prélèvement du même montant, du même tiers ou citant le fournisseur ; manquante 10 jours après l'échéance), `link`, `skip`, `candidates`, `monthly_cents`, `next_renewal` (tacite, annuelle), `notice_deadline`, `notice_alert` (45 jours), `summary` |
| `sale_settlement` (S2) | Restant dû, statut payé, TVA à virer au prorata (`vat_release`), candidats (crédits libres, écriture de règle 7… / 411 remplaçable), `match` (transaction → factures d'un client), `record_manual`, `auto_match` (candidat unique et exclusif), `unlink`, `forget_entry_payments` (appelé par `ledger.delete_entries`), `receivables_summary` (tableau de bord) ; les règles de catégorisation ignorent les transactions qui encaissent une facture |
