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
    source="MANUAL",         # ou "OFX_IMPORT", "ODOO_IMPORT"
    source_ref=None,         # référence externe optionnelle
    reference=None,          # si None, généré automatiquement
)
```

**Référence auto-générée :** `{CODE_JOURNAL}-{ANNÉE}-{SÉQUENCE:04d}`, ex : `VT-2024-0003`.

**Lève `LedgerError` si :**
- L'exercice est introuvable
- L'exercice est clôturé
- Les lignes ne sont pas équilibrées (appel interne à `validate_lines`)

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

Ce module calcule les agrégats du Bilan et du Compte de résultat en regroupant les comptes par **préfixe de code**.

### Principe

```python
# "Tous les comptes dont le code commence par '211'"
_net(["211"], fiscal_year_id)   # → débit - crédit = solde net
_net_credit(["756"], fy_id)     # → crédit - débit (comptes de produits)
```

Les lignes du Bilan et du CdR correspondent exactement aux rubriques du fichier XLS de référence `Modele-document-Nouveau-Plan-comptable-Bilan-CDR.xls`.

---

### `build_bilan(fy, fy_prev=None) → dict`

Construit la structure du bilan actif/passif.

```python
data = build_bilan(fy, fy_prev)

# Structure retournée :
data["actif"]["disponibilites"]         # → (net_N_cents, net_N1_cents)
data["passif"]["excedent_deficit"]      # → (net_N_cents, net_N1_cents)
```

Chaque valeur est un tuple `(valeur_exercice_N, valeur_exercice_N1)`. La valeur N-1 est `None` si `fy_prev` n'est pas fourni.

**Rubriques de l'actif :**
- Immobilisations incorporelles (201, 203, 204, 205, 232, 237)
- Immobilisations corporelles (211, 213-214, 215, 231, 238)
- Biens reçus par legs ou donations (24x)
- Immobilisations financières (261, 267, 271, 272, 274, 275, 276)
- Stocks (31x–37x)
- Créances clients (411, 413, 416, 418)
- Créances reçues par legs (461)
- Autres créances (40x, 42x–47x)
- Valeurs mobilières de placement (50x)
- Disponibilités (51x, 53x, 54x)
- Charges constatées d'avance (486)

**Rubriques du passif :**
- Fonds propres sans/avec droit de reprise (102x, 103x)
- Réserves, report à nouveau, résultat (106x, 110, 115, 119, 120, 129)
- Fonds propres consomptibles (108x)
- Subventions d'investissement (131, 138, 139)
- **Fonds reportés et dédiés** (191–196) ← spécifique associations
- Provisions (15x)
- Dettes (163–168, 401–408, 43x, 44x, 46x, 47x)

---

### `build_compte_resultat(fy, fy_prev=None) → dict`

Construit la structure du compte de résultat.

```python
data = build_compte_resultat(fy, fy_prev)

# Accès aux valeurs :
data["produits_exploitation"]["cotisations"]          # (N_cents, N1_cents)
data["charges_exploitation"]["salaires_traitements"]  # (N_cents, N1_cents)
data["contributions_produits"]["benevolat"]           # (N_cents, N1_cents)
```

**Sections :**

| Clé | Contenu |
|-----|---------|
| `produits_exploitation` | Cotisations, ventes, subventions, générosité du public, fonds dédiés |
| `charges_exploitation` | Achats, personnel, dotations, reports en fonds dédiés |
| `produits_financiers` | Participations, intérêts, cessions VMP |
| `charges_financieres` | Intérêts, pertes de change |
| `produits_exceptionnels` | Opérations de gestion et en capital |
| `charges_exceptionnelles` | Opérations de gestion et en capital |
| `contributions_produits` | **Dons en nature, prestations, bénévolat (classe 87)** |
| `contributions_charges` | **Secours, mise à disposition, personnel bénévole (classe 86)** |
| `participation_salaries` | Participation des salariés (691) |
| `impots_benefices` | Impôts sur les sociétés (695, 696, 699) |

Les contributions volontaires en nature (classes 86/87) sont affichées séparément après le résultat, conformément au modèle PCA.

---

## reconciler.py — Rapprochement bancaire

### `suggest_matches(bank_transaction_id, window_days=3) → list[JournalLine]`

Propose des lignes d'écriture candidates pour rapprocher une transaction bancaire.

**Algorithme :**
1. Lit la transaction bancaire et son montant signé
2. Si montant < 0 (débit bancaire) → cherche des lignes avec `credit_cents = abs(montant)`
3. Si montant > 0 (crédit bancaire) → cherche des lignes avec `debit_cents = montant`
4. Filtre : lignes non encore liées, date dans `[transaction_date - window_days, +window_days]`
5. Score : date exacte = 2pts, autres = 1pt
6. Retourne trié par score décroissant

---

### `reconcile(bank_transaction_id, journal_line_id) → BankTransaction`

Lie une transaction bancaire à une ligne d'écriture.

Positionne `bank_transaction.reconciled = True` et `bank_transaction.journal_line_id = journal_line_id`.

---

### `unreconcile(bank_transaction_id) → BankTransaction`

Annule un rapprochement. Remet `reconciled = False` et `journal_line_id = None`.

---

### `auto_reconcile(bank_account_id) → int`

Rapprochement automatique : pour chaque transaction non rapprochée, si `suggest_matches` (avec `window_days=0`, même jour) ne retourne qu'**une seule** correspondance, lie automatiquement.

Retourne le nombre de transactions rapprochées.

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

### `load_rules(path=None) → list[dict]`

Charge les règles depuis le fichier YAML (par défaut `data/rules.yml`).

```python
rules = load_rules()
# [{"name": "EDF", "label_contains": "EDF", "entity": "EDF", "entity_type": "FOURNISSEUR", "category": "Énergie"}, ...]
```

---

### `apply_rules(transactions=None, rules_path=None, overwrite=False) → dict`

Applique les règles sur une liste de transactions bancaires.

**Paramètres :**

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `transactions` | `None` | Liste de `BankTransaction`. Si `None`, traite toutes les transactions non catégorisées |
| `rules_path` | `None` | Chemin vers le fichier YAML. Si `None`, utilise `data/rules.yml` |
| `overwrite` | `False` | Si `True`, ré-applique même sur les transactions déjà catégorisées |

**Comportement :** les règles sont évaluées dans l'ordre de déclaration ; la première règle qui correspond est appliquée et les suivantes sont ignorées.

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

Le montant utilisé est `abs(transaction.amount_cents)` : le signe de la transaction n'est pas pris en compte, c'est le préfixe du compte qui détermine le sens.

**Paramètres dérivés automatiquement :**
- **Journal** : `BQ` (banque)
- **Exercice** : celui qui contient `transaction.transaction_date`
- **Compte bancaire** (côté GL) : `bank_account.account_id`
- **Source** : `OFX_IMPORT`, `source_ref` = `FITID:<fitid>`

**Lève `LedgerError` si :**
- Le code compte `account` n'existe pas dans le plan comptable
- Le compte est un compte d'en-tête (`is_header=True`)
- Le compte ne commence ni par `6` ni par `7`
- Aucun exercice ne couvre la date de transaction (ou exercice clôturé)
- Le journal `BQ` n'existe pas

Les `LedgerError` sont collectées dans la clé `errors` du dictionnaire de retour ; elles n'interrompent pas le traitement des autres transactions.

---

### Syntaxe du fichier YAML

```yaml
rules:
  - name: "Nom lisible de la règle"        # obligatoire
    label_contains: "MOT_CLE"              # correspondance insensible à la casse
    label_regex: "(?i)pattern|autre"       # regex Python
    amount_min: 100.00                     # montant en euros (centimes internement)
    amount_max: 500.00
    raw_type: "DEBIT"                      # type OFX brut
    entity: "Nom de l'entité"             # facultatif — crée l'entité si inexistante
    entity_type: FOURNISSEUR              # CLIENT | FOURNISSEUR | SALARIE | ORGANISME | AUTRE
    category: "Libellé de catégorie"
    account: "707"                         # facultatif — déclenche la création d'une écriture
```

Les conditions (`label_contains`, `label_regex`, `amount_min/max`, `raw_type`) sont cumulatives (ET logique). Le champ `account` doit être un code du plan comptable, exact, non en-tête, commençant par `6` ou `7`.

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

### `from_app_config() → OdooClient`

Construit un client à partir des 4 variables de config Flask `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY`. Lève `OdooConfigError` si une variable manque.

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
