# Modèles de données

Toutes les tables sont gérées par SQLAlchemy. Les migrations sont versionnées via Alembic (répertoire `migrations/`).

---

## Diagramme des relations

```
FiscalYear ──────────────────── JournalEntry ──── JournalLine ──── Account
                                      │                │                │
                                      │                └── BankTransaction ──── Entity
                                      │
                              Journal │               BankAccount ──── Account
                                      │                    │
                              OdooImportLine         BankTransaction
```

---

## FiscalYear — Exercice comptable

**Table :** `fiscal_years`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `label` | String(50) NOT NULL | Ex : `"2024-2025"` |
| `start_date` | Date NOT NULL | |
| `end_date` | Date NOT NULL | |
| `closed` | Boolean default=False | Si `True`, les écritures ne peuvent plus être supprimées |
| `created_at` | DateTime | |

**Relations :** `entries` → liste de `JournalEntry`

**Règle métier :** un exercice clôturé (`closed=True`) est immuable. Toute tentative de modification d'écriture lève une `LedgerError`.

---

## Account — Compte du plan comptable

**Table :** `accounts`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `code` | String(20) UNIQUE NOT NULL | Ex : `"512"`, `"6411"` |
| `label` | String(255) NOT NULL | Ex : `"Banque"` |
| `account_type` | String(20) | Voir tableau ci-dessous |
| `is_header` | Boolean default=False | `True` pour les comptes de regroupement (classe, sous-classe) |
| `parent_id` | Integer FK→accounts | Compte parent (lien par préfixe de code) |
| `created_at` | DateTime | |

**Types de compte (`account_type`) :**

| Valeur | Signification |
|--------|---------------|
| `ASSET` | Actif (classe 2, 3, 5) |
| `LIABILITY` | Passif |
| `EQUITY` | Capitaux propres (classe 1) |
| `EXPENSE` | Charges (classe 6) |
| `REVENUE` | Produits (classe 7) |
| `TIERS` | Comptes de tiers (classe 4) |
| `OFFBALANCE` | Hors bilan (classe 8 — contributions volontaires) |
| `OTHER` | Autre |

**Relations :**
- `parent` / `children` → hiérarchie self-référentielle par préfixe de code
- `journal_lines` → toutes les lignes comptabilisées sur ce compte
- `bank_accounts` → comptes bancaires liés à ce compte GL

**Propriété calculée :** `is_leaf` — retourne `True` si le compte n'a pas d'enfants.

---

## Journal — Journal comptable

**Table :** `journals`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `code` | String(10) UNIQUE NOT NULL | Ex : `"BQ"`, `"VT"` |
| `label` | String(100) NOT NULL | Ex : `"Banque"` |
| `created_at` | DateTime | |

**Journaux créés par défaut :**

| Code | Libellé | Usage |
|------|---------|-------|
| `BQ` | Banque | Opérations bancaires |
| `CA` | Caisse | Opérations en espèces |
| `VT` | Ventes | Factures de ventes / Odoo |
| `AC` | Achats | Factures fournisseurs |
| `OD` | Opérations diverses | Régularisations, paie |
| `AN` | À-nouveaux | Reprise des soldes en début d'exercice |

---

## JournalEntry — Écriture comptable (en-tête)

**Table :** `journal_entries`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `fiscal_year_id` | Integer FK→fiscal_years NOT NULL | |
| `journal_id` | Integer FK→journals NOT NULL | |
| `entry_date` | Date NOT NULL | |
| `reference` | String(50) | Auto-générée : `{CODE}-{ANNÉE}-{SÉQUENCE:04d}` ex : `BQ-2024-0001` |
| `description` | String(500) | Libellé libre |
| `is_balanced` | Boolean default=False | `True` si Σ débit = Σ crédit (validé au moment de la saisie) |
| `source` | String(20) default=`MANUAL` | `MANUAL`, `OFX_IMPORT`, `ODOO_IMPORT` |
| `source_ref` | String(200) | Référence d'origine (FITID OFX ou numéro de facture Odoo) |
| `created_at` | DateTime | |

**Propriétés calculées :**
- `total_debit` — somme des `debit_cents` de toutes les lignes
- `total_credit` — somme des `credit_cents` de toutes les lignes

**Relations :** `lines` (cascade delete) → `JournalLine[]`, `odoo_lines` → `OdooImportLine[]`

---

## JournalLine — Ligne d'écriture

**Table :** `journal_lines`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `entry_id` | Integer FK→journal_entries ON DELETE CASCADE | |
| `account_id` | Integer FK→accounts | |
| `label` | String(300) | Libellé optionnel de la ligne |
| `debit_cents` | Integer default=0 | Montant débit **en centimes** |
| `credit_cents` | Integer default=0 | Montant crédit **en centimes** |
| `created_at` | DateTime | |

> Les montants sont stockés en centimes entiers pour éviter les erreurs d'arrondi flottant. Ex : 1 234,56 € → `123456`.

---

## BankAccount — Compte bancaire

**Table :** `bank_accounts`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `label` | String(100) NOT NULL | Ex : `"CIC Compte courant"` |
| `iban` | String(34) | Ex : `"FR76 3000 6000 0112 3456 7890 189"` |
| `account_id` | Integer FK→accounts NOT NULL | Compte GL associé (ex : compte `512xxx`) |
| `created_at` | DateTime | |

**Relations :** `transactions` → `BankTransaction[]` (lazy dynamic)

---

## BankTransaction — Transaction bancaire importée

**Table :** `bank_transactions`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `bank_account_id` | Integer FK→bank_accounts | |
| `fitid` | String(100) NOT NULL | Identifiant unique OFX (`<FITID>`) |
| `transaction_date` | Date NOT NULL | Date de l'opération (`<DTPOSTED>`) |
| `value_date` | Date | Date de valeur (`<DTAVAIL>`) |
| `amount_cents` | Integer NOT NULL | Signé : négatif = débit, positif = crédit |
| `label` | String(500) | Libellé (`<MEMO>` ou `<NAME>`) |
| `raw_type` | String(20) | Type OFX : `DEBIT`, `CREDIT`, `INT`, etc. |
| `reconciled` | Boolean default=False | `True` si liée à une ligne d'écriture |
| `journal_line_id` | Integer FK→journal_lines nullable | Lien de rapprochement |
| `entity_id` | Integer FK→entities nullable | Tiers assigné (par règle ou manuellement) |
| `category` | String(100) | Catégorie libre assignée par le moteur de règles |
| `imported_at` | DateTime | |

**Contrainte unique :** `(bank_account_id, fitid)` — empêche les doublons à la réimportation.

---

## Entity — Tiers (clients, fournisseurs, salariés…)

**Table :** `entities`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `name` | String(200) UNIQUE NOT NULL | Nom affiché (ex : `"URSSAF"`, `"EDF"`) |
| `entity_type` | String(20) NOT NULL default=`AUTRE` | Type parmi les valeurs ci-dessous |
| `account_code` | String(20) nullable | Code compte GL associé (ex : `"401000"`) |
| `notes` | Text nullable | Informations libres |
| `created_at` | DateTime | |

**Types d'entité (`entity_type`) :**

| Valeur | Signification |
|--------|---------------|
| `CLIENT` | Client / adhérent |
| `FOURNISSEUR` | Fournisseur |
| `SALARIE` | Salarié |
| `ORGANISME` | Organisme public ou social (URSSAF, DGFIP…) |
| `AUTRE` | Autre |

**Relations :** `transactions` → `BankTransaction[]` (lazy dynamic)

---

## Payout — Versement Stancer

**Table :** `payouts`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `stancer_id` | String(64) UNIQUE NOT NULL | ID renvoyé par l'API Stancer (sert de clé d'idempotence à la sync) |
| `amount_cents` | Integer NOT NULL | Montant **net** versé en banque, en centimes (champ API `total`) |
| `currency` | String(3) NOT NULL default=`EUR` | Code ISO 4217 |
| `status` | String(20) NOT NULL default=`pending` | `pending`, `to_pay`, `in_progress`, `paid`, `done`, `failed` |
| `date_payout` | Date | Date d'émission du versement par Stancer (`date_paym`) |
| `date_bank` | Date | Date d'arrivée sur le compte bancaire |
| `statement_description` | String(200) | Libellé qui apparaîtra sur le relevé bancaire |
| `fees_cents` | Integer default=0 | Frais Stancer prélevés sur ce versement |
| `description` | String(500) | Référence Stancer (champ API `reference`, ex : `588927`) |
| `raw_payload` | Text | JSON brut renvoyé par l'API (utile pour debug et champs additionnels) |
| `bank_transaction_id` | Integer FK→bank_transactions ON DELETE SET NULL (indexé) | Lien automatique vers la transaction bancaire correspondante |
| `created_at` | DateTime | Horodatage Stancer (champ `created` de l'API) |
| `imported_at` | DateTime | Horodatage de la dernière synchro |

**Relations :**
- `payments` (lazy dynamic) → `Payment[]`
- `bank_transaction` → `BankTransaction` (rapprochement automatique au moment de la sync)

**Comportement :**
- *Upsert* sur la clé `stancer_id`. Les statuts évoluent typiquement de `pending` → `to_pay` → `paid` au fil des resyncs.
- À chaque *upsert*, si `bank_transaction_id` est nul, le service tente un appariement par référence Stancer dans le libellé OFX (voir `_match_bank_transaction` dans services.md). Le lien existant n'est jamais cassé.

---

## Payment — Paiement Stancer rattaché à un payout

**Table :** `payments`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `stancer_id` | String(64) UNIQUE NOT NULL | ID Stancer du paiement (clé d'idempotence) |
| `payout_id` | Integer FK→payouts ON DELETE SET NULL (indexé) | Payout dans lequel ce paiement a été inclus |
| `amount_cents` | Integer NOT NULL | Montant brut du paiement |
| `currency` | String(3) NOT NULL default=`EUR` | |
| `status` | String(20) | `authorized`, `to_capture`, `captured`, `paid`, `refused`, `expired`, `canceled`, `disputed`, `failed` |
| `method` | String(20) | Moyen de paiement (`card`, `sepa`, …) |
| `description` | String(500) | Description du paiement |
| `order_id` | String(64) | Identifiant de commande côté marchand |
| `unique_id` | String(64) | Identifiant unique fourni à la création |
| `customer_email` | String(200) | Email client (extrait de `customer.email`) |
| `customer_name` | String(200) | Nom client (extrait de `customer.name`) |
| `date_payment` | DateTime | Date du paiement |
| `raw_payload` | Text | JSON brut Stancer |
| `created_at` | DateTime | Horodatage Stancer |
| `imported_at` | DateTime | |

**Relation :** `payout` → `Payout`. Côté `Payout`, accès via `payout.payments` (lazy dynamic).

**Source :** route `GET /v2/payouts/{id}/payments` de l'API Stancer, appelée pendant `sync_payouts()` après l'*upsert* du payout parent.

---

## SyncJob — Job de synchronisation Stancer

**Table :** `sync_jobs`

Suit l'exécution d'une synchronisation Stancer lancée en arrière-plan (thread daemon). Permet à l'UI HTMX d'afficher la progression sans bloquer la requête HTTP.

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `kind` | String(40) NOT NULL (indexé) | `payouts` (sync globale) ou `payout_payments` (sync ciblée d'un payout) |
| `payout_id` | Integer FK→payouts ON DELETE SET NULL (indexé) | Renseigné uniquement pour `kind='payout_payments'` |
| `status` | String(20) NOT NULL default=`running` (indexé) | `running`, `done`, `failed` |
| `started_at` | DateTime NOT NULL | |
| `finished_at` | DateTime | Renseigné quand `status` passe à `done` ou `failed` |
| `progress_done` | Integer NOT NULL default=0 | Compteur d'éléments traités |
| `progress_total` | Integer | Total connu (peut être nul tant que la pagination n'est pas terminée) |
| `message` | Text | Dernier message de progression ou erreur |
| `result_json` | Text | Dictionnaire de résultats sérialisé (ex : `{"imported": 12, "updated": 3, ...}`) |

**Propriétés calculées :**
- `is_running` — `True` si `status == 'running'`
- `is_terminal` — `True` si `status in ('done', 'failed')`

**Idempotence :** `stancer_async.start_sync_payouts` et `start_sync_payments_for_payout` refusent de créer un nouveau job si un job de même `(kind, payout_id)` est déjà `running` — ils retournent le job existant. L'utilisateur peut donc cliquer plusieurs fois sans déclencher de doublon.

**Throttle :** la progression n'est persistée en DB qu'à chaque 5e tick du callback (constante `_PROGRESS_THROTTLE` dans `stancer_async.py`) pour ne pas saturer SQLite. Le statut terminal (`done` / `failed`) est toujours écrit.

---

## OdooImportLine — Ligne Odoo en staging

**Table :** `odoo_import_lines`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `import_batch` | String(50) NOT NULL (indexé) | Nom du lot d'import, ex : `"odoo-20250115"` |
| `invoice_number` | String(100) | Numéro de facture Odoo |
| `invoice_date` | Date | |
| `partner_name` | String(200) | Nom du client/fournisseur |
| `product_name` | String(200) | Désignation du produit |
| `amount_ht_cents` | Integer | Montant HT en centimes |
| `tax_amount_cents` | Integer | Montant TVA en centimes |
| `amount_ttc_cents` | Integer | Montant TTC en centimes |
| `account_code` | String(20) | Code compte proposé par Odoo |
| `journal_entry_id` | Integer FK→journal_entries nullable | Lien après comptabilisation |
| `imported_at` | DateTime | |

**Flux :** Les lignes arrivent dans cette table en état "en attente". Elles sont examinées par le comptable, puis comptabilisées (création d'une `JournalEntry` liée).
