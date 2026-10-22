# Modèles de données

Toutes les tables sont gérées par SQLAlchemy. Les migrations du schéma comptable sont versionnées via Alembic (`migrations/`).

L'application sépare deux bases :
- **Méta-base** (`instance/meta.db`) — tables `users` + `instances` (modèles portant `__bind_key__ = "meta"`).
- **Bases tenant** (`instance/<slug>.db`) — toutes les autres tables, une base par instance/association.

Voir [multi_tenant.md](multi_tenant.md) pour l'architecture du routage par requête.

---

## Rule — Règle de catégorisation (tenant)

**Table :** `rules` (bind par défaut = tenant)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `position` | Integer NOT NULL (indexé) | Ordre d'évaluation croissant. Première règle qui matche → appliquée. |
| `name` | String(200) NOT NULL | Libellé affiché |
| `label_contains` | String(500) nullable | Sous-chaîne du libellé (case-insensitive) |
| `label_regex` | String(500) nullable | Regex Python (`re.IGNORECASE` appliqué) |
| `amount_min_cents` | Integer nullable | Montant min signé (centimes) |
| `amount_max_cents` | Integer nullable | Montant max signé (centimes) |
| `raw_type` | String(20) nullable | Type OFX brut (`DEBIT`, `CREDIT`, `INT`…) |
| `entity_name` | String(200) nullable | Nom de l'entité à rattacher (créée si absente) |
| `entity_type` | String(20) nullable | `CLIENT`/`FOURNISSEUR`/`SALARIE`/`ADHERENT`/`ORGANISME`/`AUTRE` |
| `category` | String(200) nullable | Étiquette libre posée sur la transaction |
| `account_code` | String(20) nullable | Code 6xx/7xx du plan comptable — déclenche la création d'écriture |
| `project_id` | Integer FK→projects SET NULL nullable | Projet porté sur la ligne 6xx/7xx de l'écriture générée (exige `account_code`) |
| `is_active` | Boolean default=True | Désactivable sans suppression |
| `created_at` / `updated_at` | DateTime | |

**Validations** (côté service `rules_engine.validate_rule_data`) :
- `name` obligatoire
- Au moins une condition (label_contains, label_regex, amount_min, amount_max, raw_type)
- `label_regex` doit compiler (`re.compile`)
- `account_code` doit commencer par 6 ou 7, exister, ne pas être un en-tête
- `amount_min_cents ≤ amount_max_cents` si les deux fournis

**Origine** : seed initial via `seed_rules.py` qui importe `data/rules.yml`. Idempotent. Appelé automatiquement par le provisioning de nouvelle instance au plan comptable associatif (pas pour une SCI).

---

## ExternalConnection — Credentials services externes (tenant)

**Table :** `external_connections` (bind par défaut = tenant)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `service` | String(30) NOT NULL (indexé) | `stancer`, `odoo`, `helloasso` |
| `key` | String(50) NOT NULL | `secret_key`, `mode`, `url`, `db`, `username`, `api_key`, `client_id`, `client_secret`, `org_slug`, `api_base` |
| `value` | Text nullable | Valeur en clair (ou NULL = non configurée) |
| `updated_at` | DateTime NOT NULL default=utcnow onupdate=utcnow | Horodatage de la dernière modification |

**Contrainte unique** : `(service, key)`.

**Sémantique** : chaque tenant gère ses propres credentials. Le helper `app.services.external_config` lit en base, puis tombe en repli sur le `.env` global si la ligne est absente — la migration vers la nouvelle UI est donc progressive (aucun big-bang).

**Clés attendues par service** (validation côté Python uniquement, voir `SERVICE_KEYS` / `SERVICE_REQUIRED_KEYS`) :

| `service` | Clés `key` | Origine `.env` (repli) |
|-----------|-----------|-------------------------|
| `stancer` | `secret_key`, `mode` | `STANCER_SECRET_KEY`, `STANCER_MODE` |
| `odoo` | `url`, `db`, `username`, `api_key` | `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY` |
| `helloasso` | `client_id`, `client_secret`, `org_slug`, `api_base` | `HELLOASSO_CLIENT_ID`, `HELLOASSO_CLIENT_SECRET`, `HELLOASSO_ORG_SLUG`, `HELLOASSO_API_BASE` |
| `smtp` | `host`, `port`, `use_tls`, `username`, `password`, `sender` | `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` |
| `ga4` | `property_id`, `credentials_json` | `GA4_PROPERTY_ID`, `GA4_CREDENTIALS_JSON` |
| `facebook` | `page_id`, `page_token`, `app_id`, `app_secret` | `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` |

---

## IntegrationState — Activation et dernier test d'une intégration (tenant)

**Table :** `integration_states` (bind par défaut = tenant ; migration `c3f8a1d5e297`)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `service` | String(30) NOT NULL UNIQUE | slug du service (`stancer`, `odoo`…) |
| `enabled` | Boolean NOT NULL default `True` | interrupteur ; prime sur la base **et** sur le repli `.env` |
| `checked_at` | DateTime nullable | date du dernier test (UTC) |
| `check_ok` | Boolean nullable | résultat ; `NULL` = jamais testé |
| `check_message` | Text nullable | message lisible, secrets masqués |
| `check_duration_ms` | Integer nullable | durée du test |
| `checked_fingerprint` | String(64) nullable | SHA-256 de la configuration effective testée : si elle a changé depuis (base ou `.env`), le statut redevient « Non testée » |
| `updated_at` | DateTime NOT NULL | |

**Ligne absente = intégration activée, jamais testée** : la table n'est remplie qu'au premier
changement d'interrupteur ou au premier test.

---

## User — Utilisateur (méta-base)

**Table :** `users` (bind `meta`)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `email` | String(200) UNIQUE NOT NULL | Login (case-insensitive) |
| `password_hash` | String(255) NOT NULL | Hash Werkzeug `pbkdf2:sha256` |
| `full_name` | String(200) nullable | Nom affiché |
| `is_admin` | Boolean default=False | Administrateur global : CRUD users + instances, administrateur de toutes les instances |
| `is_active` | Boolean default=True | Faux = login refusé, déconnexion forcée |
| `last_login_at` | DateTime nullable | Mis à jour à chaque login réussi |
| `preferences` | Text NOT NULL default=`{}` | Préférences d'interface de la SPA (JSON : `color_scheme`, `tables.<id>.hidden`…), modifiées par `PATCH /api/v1/me/preferences` |
| `created_at` | DateTime default=utcnow | |

Hérite de `flask_login.UserMixin`. Méthodes `set_password(p)` / `check_password(p)`.

### InstanceMembership — Accès d'un utilisateur à une instance

**Table :** `instance_memberships` (méta-base)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `user_id` | Integer FK→users ON DELETE CASCADE (indexé) | |
| `instance_id` | Integer FK→instances ON DELETE CASCADE (indexé) | |
| `role` | String(20) NOT NULL | `admin`, `treasurer`, `accountant` |
| `created_at` | DateTime NOT NULL | |
| `created_by_user_id` | Integer | Auteur de l'accès |

Contrainte `uq_membership_user_instance (user_id, instance_id)`. Un administrateur global n'a pas
besoin de ligne. Voir [multi_tenant.md](multi_tenant.md#accès-par-instance-et-rôles).

---

## Instance — Instance/Association (méta-base)

**Table :** `instances` (bind `meta`)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `slug` | String(50) UNIQUE NOT NULL | Identifiant URL-safe, sert de nom de fichier SQLite (`tenants/<slug>.db`) |
| `label` | String(200) NOT NULL | Nom affiché (ex : « Seconde Nature ») |
| `database_url` | String(500) NOT NULL | URL SQLAlchemy de la base tenant (SQLite relatif au dossier `instance/`, ou Postgres) |
| `chart` | String(20) NOT NULL default=`asso` | Plan comptable de l'instance : `asso` (associations) ou `sci` (SCI). Choisi à la création, non modifiable ensuite ; pilote le référentiel chargé, les menus et la présentation du Bilan / Compte de résultat |
| `is_active` | Boolean default=True | Faux = retirée du sélecteur d'instance ; sortie de session forcée si elle était choisie |
| `created_at` | DateTime default=utcnow | |

`slug`, `database_url` et `chart` sont **immuables** en UI après création (édition `label` + `is_active` uniquement). Cette contrainte évite les fuites du cache d'engines (`app/tenant.py:_ENGINE_CACHE`).

La méta-base n'étant pas gérée par Alembic, `seed_meta.py` ajoute les colonnes `instances.chart` (valeur `asso`) et `users.preferences` (valeur `{}`) aux bases existantes (`ALTER TABLE` idempotent, à chaque démarrage du conteneur).

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
| `closed` | Boolean default=False | Verrou lu par tous les contrôles d'écriture : vrai dès la clôture provisoire. Tenu à jour avec `status` à chaque enregistrement |
| `status` | String(12) NOT NULL default=`open` | `open`, `provisional` (clôture provisoire, réversible), `closed` (clôture définitive) |
| `provisional_at` · `closed_at` · `closed_by_user_id` | DateTime · DateTime · Integer | Horodatages de clôture et auteur (méta-base) |
| `fec_sha256` · `fec_path` | String | FEC figé à la clôture définitive (phase A.3) |
| `allocation_decided_on` · `allocation_body` | Date · String(100) | Décision d'affectation du résultat (phase A.5) |
| `vat_liable` | Boolean NOT NULL default=False | Soumis à la TVA : TVA des factures d'achat en 44566 ; sinon incluse dans la charge |
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
| `source` | String(20) default=`MANUAL` | `MANUAL`, `OFX_IMPORT`, `QONTO_IMPORT`, `ODOO_IMPORT`, `PURCHASE` (écriture d'achat) ; assistant de clôture (non modifiables ailleurs) : `INVENTORY`, `DEDICATED_FUND`, `OPENING`, `REVERSAL`, `ALLOCATION` |
| `source_ref` | String(200) | Référence d'origine (FITID OFX ou numéro de facture Odoo) |
| `created_at` | DateTime | |
| `validation_number` · `validated_at` | Integer · DateTime | Numéro continu par journal et exercice, attribué à la clôture provisoire (FEC) |
| `reverses_entry_id` | Integer FK→journal_entries ON DELETE SET NULL | Écriture d'inventaire extournée |
| `inventory_kind` | String(20) | `accrued_expense`, `accrued_income`, `prepaid_expense`, `deferred_income` |

Sources de clôture (`OPENING`, `REVERSAL`, `ALLOCATION`, `CLOSING`) : jamais proposées au rapprochement bancaire.

## Organization — Identité de la structure

**Table :** `organization` (une ligne par base d'instance, créée à la première lecture avec le nom de l'instance)

| Colonne | Type | Description |
|---------|------|-------------|
| `name` | String(200) NOT NULL | Raison sociale |
| `siren` | String(9) | Contrôlé par la clé de Luhn ; nomme le FEC |
| `rna` | String(10) | `W` + 9 chiffres |
| `address_line1/2` · `postal_code` · `city` · `country` | String | Adresse du siège (`country` défaut `France` ; code postal français sur 5 chiffres) |
| `purpose` | Text | Objet |
| `signatory_name` · `signatory_title` · `signature_path` | String | Signataire des reçus fiscaux (lot B) |

## ClosingStep / ClosingEvent — Assistant de clôture

`closing_steps(fiscal_year_id, step, state todo|done|skipped, note, user_id, updated_at)`, unique par
exercice et étape (`checks`, `inventory`, `dedicated_funds`, `result`, `fec`, `close`, `opening`,
`allocation`) ; `closing_events(fiscal_year_id, step, action, user_id, at, details_json)` : journal
d'audit. L'étape `close` est déduite du statut de l'exercice ; `opening` et
`allocation` sont marquées par l'assistant (remises à faire à la réouverture).

## Project — Projet / activité

**Table :** `projects` (lot C.1, migration `e7a4c2d9f531`) : `name` unique, `description`,
`start_date` · `end_date` (facultatives), `manager` (texte libre), `archived` (n'est plus proposé à la
saisie), `created_at`. Axe analytique unique (OA11), porté par `journal_lines`, `purchase_lines` et
`rules` (`project_id`, ON DELETE SET NULL). Un projet utilisé ne se supprime pas : on l'archive.

## BudgetLine — Budget

**Table :** `budget_lines` (lot C.2, migration `f2b6d8a3c147`) : `fiscal_year_id` CASCADE,
`account_id` (classe 6 ou 7, regroupement admis : le réalisé se calcule par préfixe), `project_id`
CASCADE (NULL : budget général), `month` (rang du mois dans l'exercice, 1 = premier mois ; NULL =
montant annuel réparti par douzièmes), `amount_cents` (≥ 0, dans le sens naturel du compte). Index
`(fiscal_year_id, project_id)`. Un projet qui a un budget ne se supprime pas (archivage).

## CashForecastItem — Saisie du prévisionnel

**Table :** `cash_forecast_items` (lot C.4, migration `a8c3e5f7b209`) : `date`, `label`, `amount_cents`
(positif : encaissement, négatif : décaissement), `bank_account_id` SET NULL (facultatif),
`repeat_monthly_until` (répétition mensuelle jusqu'à cette date), `created_at`. Le prévisionnel
lui-même est calculé à la demande (`services/cash_forecast.py`), sans stockage.

## DedicatedFund / DedicatedFundMovement — Fonds dédiés

`dedicated_funds(label, kind subsidy|contribution|public_generosity, resource_account_id NULL,
entity_id NULL (financeur), project_id NULL (projet financé, lot C.5, migration `b9d4f6a8c310`),
origin_fiscal_year_id, amount_cents, created_at)` : ressource affectée
reçue. Comptes par nature (ANC 2018-06) : 6894 / 194 / 7894, 6895 / 195 / 7895, 6896 / 196 / 7896.
`dedicated_fund_movements(fund_id CASCADE, fiscal_year_id CASCADE, kind allocation|use, amount_cents,
entry_id SET NULL)` : dotation ou utilisation d'un exercice, avec son écriture
(`source='DEDICATED_FUND'`). Migration `d5f3b8e1a426` (phase A.6).

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
| `project_id` | Integer FK→projects SET NULL, indexé | Projet / activité (lot C.1) ; une ligne ventilée devient plusieurs lignes de même compte |
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
| `qonto_account_id` | String(36) UNIQUE nullable | Compte Qonto rattaché (UUID) ; NULL = pas synchronisé avec Qonto |
| `qonto_sync_from` | Date nullable | Date de début de la synchronisation Qonto |
| `qonto_synced_at` | DateTime nullable | Curseur : début de la dernière synchronisation Qonto **réussie** (UTC) ; NULL = jamais (prochaine synchro complète) |
| `created_at` | DateTime | |

**Relations :** `transactions` → `BankTransaction[]` (lazy dynamic)

---

## BankTransaction — Transaction bancaire importée

**Table :** `bank_transactions`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `bank_account_id` | Integer FK→bank_accounts | |
| `fitid` | String(100) NOT NULL | Identifiant unique : `<FITID>` OFX, ou UUID de la transaction Qonto |
| `source` | String(10) NOT NULL default `ofx` | Origine : `ofx` ou `qonto` |
| `transaction_date` | Date NOT NULL | Date de l'opération (`<DTPOSTED>`) |
| `value_date` | Date | Date de valeur (`<DTAVAIL>`) |
| `amount_cents` | Integer NOT NULL | Signé : négatif = débit, positif = crédit |
| `label` | String(500) | Libellé (`<MEMO>` ou `<NAME>`) |
| `raw_type` | String(40) | Type OFX (`DEBIT`, `CREDIT`, `INT`…) ou `operation_type` Qonto (`transfer`, `card`, `qonto_fee`…) — filtrable par les règles |
| `reconciled` | Boolean default=False | `True` si liée à une ligne d'écriture |
| `journal_line_id` | Integer FK→journal_lines nullable | Lien de rapprochement |
| `entity_id` | Integer FK→entities nullable | Tiers assigné (par règle ou manuellement) |
| `category` | String(100) | Catégorie libre assignée par le moteur de règles |
| `imported_at` | DateTime | |
| `counterparty` | String(200) | Contrepartie normalisée (Qonto `clean_counterparty_name`) |
| `note` | Text | Note saisie dans Qonto |
| `is_reversed` | Boolean NOT NULL default=False | Annulée par la banque après règlement : plus rapprochable, ignorée par les règles |
| `attachment_count` | Integer nullable | Nombre de justificatifs dans Qonto (NULL pour l'OFX) |
| `attachment_required` / `attachment_lost` | Boolean nullable | Justificatif exigé / déclaré perdu (Qonto) |
| `source_updated_at` | DateTime nullable | `updated_at` Qonto de la dernière mise à jour reçue |

**Contrainte unique :** `(bank_account_id, fitid)` — empêche les doublons à la réimportation et entre deux synchronisations Qonto.

---

## Product — Produit / service du catalogue (tenant)

**Table :** `products` — `id`, `name` (String(200) UNIQUE), `reference`, `kind` (`purchase` / `sale` /
`both`), `purchase_account_id` (FK accounts, 6…), `sale_account_id` (FK accounts, 7…), `vat_rate_bp`
(Integer, points de base : 2000 = 20 %), `active` (archivé = faux), `created_at`.

---

## Purchase — Facture d'achat (tenant)

**Table :** `purchases` — facture fournisseur reçue dans Qonto (`source = qonto`) ou saisie dans
l'application (`manual`).

| Colonne | Type | Description |
|---------|------|-------------|
| `qonto_id` | String(36) UNIQUE nullable | `id` Qonto |
| `entity_id` | FK→entities ON DELETE SET NULL (indexé) | Fournisseur rattaché |
| `supplier_name`, `qonto_supplier_id`, `supplier_vat`, `supplier_siret`, `supplier_iban` | String | Instantané du fournisseur (Qonto ou facture lue) |
| `invoice_number`, `issue_date` (indexé), `due_date`, `payment_date`, `currency` | | |
| `total_cents` | Integer NOT NULL | TTC **positif** (avoir : `is_credit_note`) |
| `untaxed_cents`, `tax_cents`, `payable_cents` | Integer nullable | Souvent NULL hors facture électronique |
| `is_credit_note`, `is_einvoice` | Boolean | |
| `qonto_status` | String(20) (indexé) | `to_review`, `to_approve`, `awaiting_payment`, `pending`, `scheduled`, `paid`, `archived`, `rejected`, `discarded` |
| `is_hidden` | Boolean (indexé) | Rejetée, écartée ou non financière : jamais comptabilisée |
| `attachment_id`, `related_qonto_ids` | String / Text (JSON) | Pièce Qonto ; factures liées d'un avoir |
| `attachment_path`, `attachment_name`, `attachment_mime`, `attachment_size` | String / Integer | Pièce d'une facture saisie (chemin relatif au dossier de l'instance) |
| `idempotency_key`, `qonto_upload_status`, `qonto_upload_error` | String(36) / String(10) / Text | Envoi à Qonto d'une facture saisie : clé réutilisée au renvoi, NULL / `sent` / `failed` |
| `lines_edited` | Boolean | Lignes modifiées par le trésorier : plus régénérées |
| `journal_entry_id` | FK→journal_entries | Écriture d'achat (AC) = comptabilisée |
| `review_reason` | Text | Changement Qonto après comptabilisation, à revoir |
| `source_updated_at`, `raw_payload`, `created_at`, `updated_at` | | `raw_payload` : dernière réponse Qonto |

**`purchase_lines`** (CASCADE) : `position`, `product_id`, `account_id`, `label`, `untaxed_cents`,
`vat_rate_bp` (NULL = à confirmer), `vat_cents`, `total_cents`, `project_id` (repris sur la ligne de
charge à la comptabilisation).

**`purchase_payments`** (CASCADE) : `qonto_transaction_id` (UUID de la transaction = `fitid` ;
NULL pour un lien hors Qonto), `origin` (`qonto`, `match` automatique, `manual` choisi),
`bank_transaction_id` (résolu à l'import), `journal_entry_id` (règlement BQ) ; uniques
`(purchase_id, qonto_transaction_id)` et `(purchase_id, bank_transaction_id)`.

---

## SyncCursor — Curseur de synchronisation (tenant)

**Table :** `sync_cursors` — `key` (UNIQUE, ex. `qonto_supplier_invoices`), `sync_from` (date de
début), `synced_at` (début de la dernière synchronisation réussie, UTC).

---

## IgnoredCounterparty — Contrepartie à ne plus proposer (tenant)

**Table :** `ignored_counterparties` — `id`, `name_key` (String(200) UNIQUE, nom normalisé), `label`, `created_at`.
Une contrepartie de débit ignorée sur l'écran « Contreparties à valider » n'est plus jamais proposée
comme fournisseur, pour les transactions présentes et futures.

---

## Entity — Tiers (clients, fournisseurs, adhérents, salariés…)

**Table :** `entities`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `name` | String(200) UNIQUE NOT NULL | Nom affiché (ex : `"URSSAF"`, `"EDF"`) |
| `entity_type` | String(20) NOT NULL default=`AUTRE` | Type parmi les valeurs ci-dessous |
| `account_code` | String(20) nullable | Code compte GL associé ; fournisseur : `401NNN` (attribué et créé dans le plan à la première facture comptabilisée) |
| `email` | String(200) nullable (indexé) | Clé de rattachement HelloAsso / Odoo |
| `is_member` | Boolean default=False | `True` pour les adhérents (basculé auto par les syncs) |
| `notes` | Text nullable | Informations libres |
| `default_product_id` | FK→products ON DELETE SET NULL | Produit proposé sur les lignes de ses factures d'achat |
| `qonto_supplier_id` | String(36) (indexé) | Identifiant du fournisseur dans Qonto |
| `vat_number` / `siret` / `iban` | String(30) / String(14) (indexés) / String(34) | Reconnaissance du fournisseur : id Qonto → TVA → SIRET → IBAN → nom (`purchase_sync.find_supplier`) |
| `created_at` | DateTime | |

**Types d'entité (`entity_type`) :**

| Valeur | Signification |
|--------|---------------|
| `CLIENT` | Client (créé auto par sync POS / factures Odoo) |
| `FOURNISSEUR` | Fournisseur |
| `SALARIE` | Salarié |
| `ADHERENT` | Adhérent (basculé auto si item Membership HelloAsso ou ligne `Adhésion` POS) |
| `ORGANISME` | Organisme public ou social (URSSAF, DGFIP…) |
| `AUTRE` | Autre |

**Relations :**
- `transactions` → `BankTransaction[]` (lazy dynamic)
- côté inverse non déclaré, mais référencé via FK `entity_id` (ON DELETE SET NULL) par : `Order`, `CustomerInvoice`, `HelloAssoOrder`, `HelloAssoItem`.

**Helpers de résolution** (`app/services/entity_resolver.py`) :
- `entity_by_email(cache, email)` — recherche insensible à la casse avec cache local au sync.
- `unique_entity_name(base_name, email=None)` — garantit l'unicité de `Entity.name` (suffixe par email puis `#N`).

**Statut d'adhésion** (`app/services/membership_status.py`, fonctions pures) — la date anniversaire et le statut sont **calculés**, non stockés :
- `member_birthday(last_ha, last_pos)` → échéance = date d'adhésion la plus récente + 365 j (date du jour si aucune).
- `member_status(last_ha, last_pos)` → `{status, color, label, css}`. `status` ∈ `?`/`asha`/`ok` (présence de données) ; `color` ∈ `red` (échéance ≤ aujourd'hui) / `orange` (≤ +30 j) / `green` (à jour).
- `build_member_rows(...)`, `sort_member_rows(rows, sort_by, sort)` — utilisés par la liste, les exports et la relance.

---

## EmailTemplate — Gabarit d'email éditable

**Table :** `email_templates` (base tenant) — migration `b3e1a7c2d9f4`.

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `key` | String(50) UNIQUE NOT NULL | Identifiant du gabarit (ex. `membership_reminder`) |
| `subject` | String(300) NOT NULL | Sujet (rendu Jinja) |
| `body_html` | Text NOT NULL | Corps HTML (rendu Jinja) |
| `updated_at` | DateTime | Dernière modification |

Variables de rendu de la relance : `{{ nom }}`, `{{ email }}`, `{{ date_anniversaire }}`, `{{ lien_helloasso }}`.
`EmailTemplate.get_or_default(key)` retourne le gabarit en base ou un objet par défaut non persisté.
Le gabarit `membership_reminder` est seedé par la migration.

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

## SyncJob — Job de synchronisation en arrière-plan

**Table :** `sync_jobs`

Suit l'exécution d'une synchronisation lancée en arrière-plan (thread daemon, voir `services/sync_jobs.py`) : Stancer, Qonto, et métriques (GA4 / Facebook, synchrones). Permet à la SPA d'afficher la progression (`GET /api/v1/jobs/<id>`, composant `JobStatus`) sans bloquer la requête HTTP.

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `kind` | String(40) NOT NULL (indexé) | `payouts`, `payout_payments`, `qonto_transactions`, `qonto_supplier_invoices`, `metrics` |
| `payout_id` | Integer FK→payouts ON DELETE SET NULL (indexé) | Renseigné uniquement pour `kind='payout_payments'` |
| `bank_account_id` | Integer FK→bank_accounts ON DELETE SET NULL (indexé) | Renseigné pour `kind='qonto_transactions'` |
| `started_by_user_id` | Integer | Utilisateur (méta-base, sans clé étrangère) qui a lancé le job : destinataire de la notification de fin ; nul hors requête |
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

**Idempotence :** `sync_jobs.start` refuse de créer un nouveau job si un job de même type et mêmes champs (`payout_id`, `bank_account_id`) est déjà `running` — il retourne le job existant. L'utilisateur peut donc cliquer plusieurs fois sans déclencher de doublon.

**Throttle :** la progression n'est persistée en DB qu'à chaque 5e tick du callback (`sync_jobs.PROGRESS_THROTTLE`) pour ne pas saturer SQLite. Le statut terminal (`done` / `failed`) est toujours écrit.

---

## Notification — Notification d'un utilisateur

**Table :** `notifications` (base de l'instance)

Créée à la fin d'une tâche en arrière-plan (`services/notifications.py`, appelé par `sync_jobs.run`), lue par `GET /api/v1/notifications`.

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `user_id` | Integer (indexé) | Destinataire (utilisateur de la méta-base, sans clé étrangère) ; nul = tous les utilisateurs de l'instance |
| `kind` | String(40) NOT NULL | `job_done`, `job_failed` |
| `level` | String(10) NOT NULL | `success`, `info`, `warning` (job terminé avec des erreurs), `danger` (échec) |
| `title` | String(200) NOT NULL | « Synchronisation des transactions Qonto terminée » |
| `message` | Text | Résumé du résultat, ou message d'erreur du job |
| `url` | String(300) | Écran de la SPA concerné (`/bank-accounts/<id>/transactions`, `/payouts/`, `/purchases/`…) |
| `job_id` | Integer FK→sync_jobs ON DELETE SET NULL (indexé) | Job à l'origine |
| `created_at` | DateTime NOT NULL (indexé) | |
| `read_at` | DateTime | Nul tant que non lue |

Les notifications **lues** depuis plus de 90 jours (`notifications.RETENTION_DAYS`) sont supprimées à chaque création. Une notification destinée à toute l'instance (`user_id` nul) a un seul état de lecture, partagé.

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

---

## Order — Commande POS Odoo

**Table :** `orders` — miroir local du modèle Odoo `pos.order`, synchronisé via XML-RPC par `app/services/odoo_pos_sync.py`.

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL (indexé) | ID Odoo — clé d'idempotence |
| `name` | String(200) | Nom Odoo (ex : `POS/0042`) |
| `pos_reference` | String(200) (indexé) | Référence POS |
| `state` | String(20) | `draft`, `paid`, `done`, `invoiced`, `cancel` |
| `session_id` / `session_name` | Integer / String(200) | Session POS |
| `partner_id` / `partner_name` / `partner_email` | Integer / String(200) / String(200) (indexé) | Partenaire Odoo |
| `entity_id` | Integer FK→entities ON DELETE SET NULL (indexé) | Tiers local rattaché par email |
| `user_id` / `user_name` | Integer / String(200) | Vendeur |
| `company_id` | Integer | Société Odoo |
| `date_order` | DateTime (indexé) | Date de la commande |
| `amount_total_cents` / `amount_tax_cents` / `amount_paid_cents` / `amount_return_cents` | Integer NOT NULL default=0 | Montants TTC / TVA / payé / rendu monnaie |
| `currency` | String(3) NOT NULL default `EUR` | |
| `note`, `raw_payload` | Text | Note + JSON brut de la réponse Odoo |
| `created_at`, `imported_at` | DateTime | |

**Relations :**
- `lines` (lazy dynamic, cascade) → `OrderLine[]`
- `payments` (lazy dynamic, cascade) → `OrderPayment[]`
- `entity` → `Entity` (par FK `entity_id`)

**Constantes** (`app/models/order.py`) :

```python
POS_ORDER_STATES = [
    ("draft", "Brouillon"), ("paid", "Payée"), ("done", "Comptabilisée"),
    ("invoiced", "Facturée"), ("cancel", "Annulée"),
]
```

---

## OrderLine — Ligne de commande POS

**Table :** `order_lines` (FK CASCADE depuis `orders`)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL (indexé) | `pos.order.line.id` |
| `order_id` | Integer FK→orders ON DELETE CASCADE (indexé) | |
| `product_id` / `product_name` / `full_product_name` | Integer / String(300) / String(500) | Produit |
| `qty` / `discount` | Float NOT NULL default=0 | |
| `price_unit_cents` / `price_subtotal_cents` / `price_subtotal_incl_cents` | Integer NOT NULL default=0 | |
| `tax_ids` | String(200) | CSV des IDs taxes Odoo |
| `note`, `raw_payload` | Text | |
| `imported_at` | DateTime | |

> Le matching d'adhérent utilise `LIKE '%adh%sion%'` sur `product_name` / `full_product_name` (insensible à la casse).

---

## OrderPayment — Paiement POS

**Table :** `order_payments` (FK CASCADE depuis `orders`)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL (indexé) | `pos.payment.id` |
| `order_id` | Integer FK→orders ON DELETE CASCADE (indexé) | |
| `name` | String(200) | |
| `payment_method_id` / `payment_method_name` | Integer / String(200) | |
| `amount_cents` | Integer NOT NULL default=0 | |
| `currency` | String(3) NOT NULL default `EUR` | |
| `payment_date` | DateTime (indexé) | |
| `card_type`, `transaction_id` | String | |
| `raw_payload` | Text | |
| `imported_at` | DateTime | |

---

## CustomerInvoice — Facture client Odoo

**Table :** `customer_invoices` — miroir local d'`account.move` filtré sur `move_type='out_invoice'`, synchronisé via XML-RPC par `app/services/odoo_invoice_sync.py`.

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL (indexé) | `account.move.id` — clé d'idempotence |
| `name` | String(100) (indexé) | Numéro de facture (ex : `INV/2026/00042`) |
| `ref` | String(200) | Référence libre |
| `state` | String(20) (indexé) | `draft`, `posted`, `cancel` |
| `payment_state` | String(20) (indexé) | `not_paid`, `in_payment`, `partial`, `paid`, `reversed`, `invoicing_legacy` |
| `partner_id` / `partner_name` / `partner_email` | Integer / String(200) / String(200) (indexé) | Client Odoo |
| `entity_id` | Integer FK→entities ON DELETE SET NULL (indexé) | Tiers local rattaché par email |
| `invoice_date` | Date (indexé) | Date d'émission |
| `invoice_date_due` | Date | Échéance |
| `currency` | String(3) NOT NULL default `EUR` | |
| `amount_untaxed_cents` / `amount_tax_cents` / `amount_total_cents` / `amount_residual_cents` | Integer NOT NULL default=0 | HT / TVA / TTC / Reste dû |
| `invoice_origin` | String(200) | Origine (ex : `SO/2026/0042`) |
| `journal_name` | String(100) | Nom du journal de ventes Odoo |
| `narration`, `raw_payload` | Text | Note bas de facture + JSON brut |
| `created_at`, `imported_at` | DateTime | |

**Relations :**
- `lines` (lazy dynamic, cascade) → `CustomerInvoiceLine[]`
- `entity` → `Entity` (par FK `entity_id`)

**Constantes** (`app/models/customer_invoice.py`) :

```python
CUSTOMER_INVOICE_STATES = [
    ("draft", "Brouillon"), ("posted", "Comptabilisée"), ("cancel", "Annulée"),
]
CUSTOMER_INVOICE_PAYMENT_STATES = [
    ("not_paid", "Non payée"), ("in_payment", "En cours de paiement"),
    ("partial", "Partiellement payée"), ("paid", "Payée"),
    ("reversed", "Annulée par avoir"), ("invoicing_legacy", "Hérité"),
]
```

> **Différence métier avec POS** : aucune notion de `is_member` n'est dérivée des factures clients. Le marquage d'adhérent reste exclusivement piloté par HelloAsso et les lignes `Adhésion` POS.

---

## CustomerInvoiceLine — Ligne de facture client

**Table :** `customer_invoice_lines` (FK CASCADE depuis `customer_invoices`)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL (indexé) | `account.move.line.id` |
| `invoice_id` | Integer FK→customer_invoices ON DELETE CASCADE (indexé) | |
| `product_id` / `product_name` | Integer / String(300) | |
| `description` | String(500) | Champ Odoo `name` (souvent verbeux) |
| `qty` / `discount` | Float NOT NULL default=0 | |
| `price_unit_cents` / `price_subtotal_cents` / `price_total_cents` | Integer NOT NULL default=0 | HT / TTC |
| `tax_ids` | String(200) | CSV des IDs taxes Odoo |
| `account_code` | String(20) | Préfixe extrait du nom de compte produit Odoo |
| `raw_payload` | Text | |
| `imported_at` | DateTime | |

**Filtrage** : seules les lignes "produit" sont synchronisées. Le filtre côté `odoo_invoice_sync._is_product_line()` accepte `display_type='product'` (Odoo ≥ 16) ou — en fallback — toute ligne ayant un `product_id` non vide.

---

## HelloAssoForm / Order / Item / Payment

**Tables :** `helloasso_forms`, `helloasso_orders`, `helloasso_items`, `helloasso_payments` — miroir des formulaires HelloAsso et de leurs commandes. Synchronisé par `app/services/helloasso_sync.py` (API v5, OAuth2 client_credentials).

Schéma simplifié :

| Table | FK | Champs notables |
|-------|-----|-----------------|
| `helloasso_forms` | — | `form_slug` (PK fonctionnelle), `form_type`, `title`, `currency` |
| `helloasso_orders` | `entity_id` ON DELETE SET NULL | `helloasso_id`, `date`, `amount_total_cents`, `payer_*`, `form_slug`/`form_type` |
| `helloasso_items` | `order_id` CASCADE + `entity_id` ON DELETE SET NULL | `helloasso_id`, `name`, `type` (`Membership`, `Donation`, ...), `state`, `amount_cents`, `user_first_name`/`user_last_name`/`user_email` |
| `helloasso_payments` | `order_id` CASCADE | `helloasso_id`, `payment_date`, `payment_means`, `state`, `amount_cents` |

**Règle métier** : toute Entity ayant ≥ 1 `helloasso_items.type='Membership'` (ou ligne POS `Adhésion`) bascule en `is_member=True` + `entity_type='ADHERENT'`. Cette logique est centralisée dans `helloasso_sync.py` (création) et `odoo_pos_sync._refresh_pos_member_flag` (rattrapage).

**Endpoints HelloAsso utilisés** :
- `POST /oauth2/token` (token ~30 min)
- `GET /v5/organizations/{slug}/forms`
- `GET /v5/organizations/{slug}/orders?withDetails=true` (items + payments embarqués, pagination `pageIndex`/`totalPages`)

Les montants HelloAsso sont **déjà en centimes entiers** dans l'API.
