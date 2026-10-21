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

Validation d'une écriture soumise par l'îlot EntryForm / l'API (montants en centimes). Les lignes
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

### `delete_entries(entry_ids) → list[dict]`

Supprime des écritures dans une seule transaction en **défaisant d'abord leurs rapprochements**
(une ligne supprimée ne doit pas rester liée à une transaction bancaire). Exercice clôturé →
refus pour l'écriture concernée. Résultat par écriture : `{entry_id, status, reference | message}`.
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

Crée une adhésion côté HelloAsso pour un tiers ayant une adhésion POS mais pas encore d'adhésion HA. Retourne `(True, info)` en succès, `(False, message_erreur)` sinon. Utilisé par `/entities/create-helloasso-memberships`.

## membership_reminders.py — Relance email des adhérents expirés

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

Lecture par instance (table `external_connections`, repli `.env`) ; voir aussi
[models.md](models.md#integrationstate--activation-et-dernier-test-dune-intégration-tenant).

| Fonction | Rôle |
|----------|------|
| `get(service, key)` / `get_all(service)` / `source(service, key)` | Valeur effective (base puis `.env`) et son origine (`db`, `env`, `none`) |
| `set_many(service, values)` | Upsert ; valeur vide = ligne supprimée |
| `is_configured(service)` | Clés obligatoires renseignées (`SERVICE_REQUIRED_KEYS`) |
| `is_enabled(service)` / `set_enabled(service, bool)` | Interrupteur (`integration_states`) ; ligne absente = activée |
| `is_available(service)` | Activée **et** configurée : à utiliser avant toute action qui dépend du service |
| `unavailable_reason(service)` / `unavailable_message(service)` | `"disabled"` / `"unconfigured"` / `None`, et message français associé (bandeaux, flash, exceptions) |
| `fingerprint(service)` | SHA-256 de la configuration effective (détecte un test périmé) |

Constantes : `SERVICE_KEYS`, `SERVICE_LABELS`, `SERVICE_DESCRIPTIONS`, `SERVICE_REQUIRED_KEYS`,
`SECRET_KEYS` (jamais réaffichées), `ENV_FALLBACK`.

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
| `run(app, instance_id, job_id, work, error_message)` | Corps du thread (appelable directement en test) : finalise le job `done` (avec `result_json`) ou `failed` (message de `error_message(exc)`) |
| `progress_callback(job_id, throttle=5)` | Callback `(done, total, message)` qui met à jour le job une fois sur `throttle` |
| `running_job(kind, **filters)` | Job en cours de ce type, ou None |

Utilisé par `stancer_async` et `qonto_sync.start_sync`. En test, remplacer `sync_jobs.threading.Thread`
par une exécution immédiate.

---

## qonto_client.py — Client de l'API Business Qonto

`QontoClient(login, secret_key, staging_token=None, timeout=30, retry=True)` : en-tête
`Authorization: login:secret` (pas du Basic) ; bac à sable (`thirdparty-sandbox.staging.qonto.co`,
en-tête `X-Qonto-Staging-Token`) si `staging_token`. Méthodes : `organization()`, `bank_accounts()`,
`list_transactions(bank_account_id, statuses, page, per_page, updated_from/to, settled_from/to)`,
`iter_transactions(...)`.

- **429** : jusqu'à 3 nouvelles tentatives (`Retry-After`, sinon 2 s, 4 s, 8 s) ; **5xx / réseau** :
  2 nouvelles tentatives ; **401 / 403** → `QontoAuthError` immédiat (Qonto bloque après 200 réponses
  401 par heure) ; `retry=False` pour le test de l'intégration.
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
paiement (`purchase_settlement.link_invoice`). Une facture **comptabilisée** n'est jamais modifiée sur
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
| `save_lines(p, rows)` | Lignes saisies (TVA calculée si vide, compte 6… exigé) ; `lines_edited = True` ; puis `post_ready` |

---

## invoice_reader.py — Lecture des factures d'achat

`read(path, mime, max_pages=3, ignore_ibans=())` → `Extraction(fields, taxes, source, warnings)` ;
chaque champ est un `Field(value, origin, check)` (`origin` : `facturx`, `text`, `ocr` ; `check` : à
vérifier). Ordre : XML CII embarqué (`factur-x.xml`, `zugferd-invoice.xml`, `xrechnung.xml`, ≤ 1 Mo,
DOCTYPE refusé) qui fait foi ; texte natif des 3 premières pages ; OCR Tesseract `fra` pour une page de
moins de 30 caractères et pour les images (JPEG, PNG). Tesseract absent : avertissement.
`parse_text(text, origin)` : nom (forme juridique suivie du capital / RCS, sinon site web, deviné),
TVA FR (clé contrôlée), SIRET (Luhn), IBAN (mod 97 ; IBAN masqués et ceux de l'organisation ignorés),
n° de facture, dates (facture, échéance), TTC / HT / TVA et ventilation par taux, avoir, remise après
le total (`discount`, points fidélité d'un ticket) ; HT + TVA = TTC complète le montant manquant ou
signale l'incohérence. Champs OCR toujours à vérifier ; champs texte seulement s'ils sont devinés ou
incohérents.

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
| `read_staged(token)` | Lit la pièce en attente (`invoice_reader.read`, IBAN des comptes bancaires ignorés) |
| `form_from_extraction(ext)` | `EntryForm(values, checks, rows, warnings, source)` : fournisseur reconnu (`find_supplier`) ou « à créer », lignes proposées (produit du fournisseur, une par taux) ; une remise après le total devient une ligne négative 6098 / 609 et le TTC devient le montant payé |
| `validate_header(form)` | `(clean, errors)` : date et TTC > 0 obligatoires, SIRET à 14 chiffres, fournisseur existant ou nom à créer |
| `duplicates(entity_id, number, issue_date, total, supplier_name, exclude_id)` | Même fournisseur et même n° (sans n° : même date et TTC) |
| `create(clean, rows, token)` | Facture `source = manual`, `lines_edited`, `idempotency_key` ; fournisseur créé au besoin (homonyme repris, identifiants complétés) ; lignes saisies ou par défaut ; pièce rangée ; `post_ready` |
| `update(p, clean, token)` | En-tête d'une facture saisie non comptabilisée ; pièce remplaçable si non envoyée à Qonto |

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

Dans `qonto_sync.sync_bank_account`, par page : `link_transactions` et `settle` **avant** `apply_rules`
(résumé : `settled`).

