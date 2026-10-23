# Conception — Ventes (devis, factures, avoirs, encaissements, loyers), abonnements d'achat, Qonto

> Statut : conception (`/sc:design`, 23/10/2026) ; lots S0 (essai Factur-X), S1 (factures et avoirs) et S2 (encaissements, relances) réalisés le 23/10/2026.
> Besoins : `claudedocs/besoins_ventes.md` (décisions V1–V17, questions Q12–Q14).

## 1. Choix structurants

| # | Choix | Raison |
|---|---|---|
| C1 | **Une table `sales`** pour devis, factures, avoirs et modèles de facture récurrente (`kind`) | Mêmes lignes, totaux, mentions, PDF, envoi ; numérotation par série |
| C2 | Numéro attribué **à l'émission**, dans la même transaction que l'écriture, par un compteur `(série, année)` | Numérotation continue sans trou (même garantie que les reçus fiscaux) |
| C3 | Facture Qonto : **validée localement d'abord** (exercice ouvert, comptes, client), puis créée en brouillon et finalisée dans Qonto, puis comptabilisée | Rien n'est écrit dans Qonto pour une facture que l'application refuserait ; le numéro légal vient de Qonto |
| C4 | Comptabilisation calquée sur les achats : `sale_posting` (journal **VE**, 411NNN par client) ; encaissements calqués sur `purchase_settlement` | Même logique, même écran de rapprochement |
| C5 | TVA à l'encaissement (V6) : TVA des lignes de **services** en **44574** à l'émission, virée en **44571** au prorata de chaque encaissement | Méthode habituelle ; option `fiscal_years.vat_on_receipts` |
| C6 | PDF **WeasyPrint** (comme les reçus), variante **PDF/A-3b** ; XML **CII EN 16931** produit par l'application (gabarit) ; insertion et contrôle par `factur-x` (Akretion) | WeasyPrint sait produire du PDF/A-3 ; la bibliothèque contrôle le XML contre le schéma |
| C7 | **Périmètre Qonto** (relevés, achats, ventes) dans la base méta, à côté de l'interrupteur (`Instance.integrations.scopes`) | Lu par la session pour masquer les fonctions, comme l'interrupteur |
| C8 | Factures récurrentes : un **modèle** (`sales.kind = "template"`) et un **échéancier** (`recurrences`) ; les échéances dues sont préparées **à l'ouverture de la liste** « À émettre » (et par un bouton) | Pas de tâche planifiée (V15) ; idempotent par (échéancier, date) |
| C9 | Abonnements d'achat : table `subscriptions` + **périodes** (`subscription_periods`) qui jouent le rôle de « facture attendue » ; la vraie facture d'achat s'y rattache | Pas de fausse facture dans les achats ni dans la comptabilité |
| C10 | Envoi d'emails factorisé dans un service `mailer` (SMTP de l'intégration), en tâche de fond pour les lots, avec notification | Les reçus fiscaux et les relances d'adhésion l'utilisent déjà sous une autre forme ; `require_integration("smtp")` |

## 2. Données (base de l'instance, migration Alembic)

### 2.1 Ventes

**`sales`**

| Colonne | Type | Rôle |
|---|---|---|
| `id` | PK | |
| `kind` | String(12) | `quote`, `invoice`, `credit_note`, `template` |
| `status` | String(16) | devis : `draft`, `issued`, `accepted`, `refused`, `expired`, `invoiced` ; facture / avoir : `draft`, `issued`, `partially_paid`, `paid`, `canceled` ; modèle : `active`, `stopped` |
| `source` | String(8) | `app` ou `qonto` (créée dans Qonto, importée) |
| `qonto_emit` | Boolean | case « Émettre avec Qonto » (décochée par défaut, V10) |
| `number` | String(40) NULL, unique par `kind` | attribué à l'émission (série de l'application ou numéro Qonto) |
| `series_year` / `series_seq` | Integer NULL | position dans la série de l'application (contrôle de continuité) |
| `entity_id` | FK entities | client (locataire) |
| `client_snapshot` | Text (JSON) | nom, adresse, SIREN, TVA du client à l'émission (la fiche peut changer) |
| `issue_date`, `due_date`, `validity_date` | Date | échéance (facture), validité (devis) |
| `service_start`, `service_end` | Date NULL | période de la prestation (loyer : période louée) |
| `operation_type` | String(8) | `goods`, `services`, `both` (mention obligatoire) |
| `purchase_order` | String(100) | référence de commande du client |
| `discount_bp` / `discount_cents` | Integer NULL | remise globale |
| `untaxed_cents`, `tax_cents`, `total_cents` | Integer | totaux (recalculés depuis les lignes) |
| `paid_cents` | Integer | somme des encaissements |
| `terms`, `header`, `footer` | Text | conditions, textes libres |
| `vat_mode` | String(10) | `none` (non assujetti, 293 B), `receipts`, `debits` : figé à l'émission depuis l'exercice |
| `quote_id` | FK sales NULL | devis d'origine d'une facture |
| `invoice_id` | FK sales NULL | facture d'un avoir |
| `recurrence_id`, `lease_id` | FK NULL | échéance d'origine, bail |
| `journal_entry_id` | FK journal_entries NULL | écriture VE |
| `pdf_path` | String(300) NULL | PDF émis, rangé avec les pièces de l'instance (`ventes/AAAA/`) |
| `qonto_id`, `qonto_status`, `qonto_attachment_id` | NULL | facture / devis / avoir Qonto |
| `qonto_error` | Text NULL | échec de création ou de finalisation |
| `issued_at`, `sent_at`, `last_reminder_at` | DateTime NULL | |
| `reminder_count` | Integer | |
| `raw_payload` | Text NULL | dernier objet Qonto |
| `created_at`, `updated_at` | DateTime | |

Index : `(kind, status)`, `(entity_id)`, `(due_date)`, unique `(kind, number)`, unique `qonto_id`.

**`sale_lines`** : `sale_id` (CASCADE), `position`, `product_id` NULL, `label` (300), `description`
(Text), `quantity_milli` (Integer, quantité × 1000), `unit` (20), `unit_price_cents` (HT),
`discount_bp`, `untaxed_cents`, `vat_rate_bp`, `vat_cents`, `total_cents`, `account_id` (70x),
`project_id` NULL, `nature` (`goods` / `services`, pour l'exigibilité de la TVA), `vat_exemption`
(`S293B`, `S261`… NULL).

**`sale_counters`** : `(series, year)` PK, `last_number`. Séries `D`, `F`, `AV` (V7).

**`sale_payments`** : `sale_id`, `amount_cents`, `paid_on`, `origin` (`bank`, `cash`, `manual`),
`bank_transaction_id` NULL, `journal_entry_id` NULL, `qonto_marked` (Boolean). Un encaissement peut
porter plusieurs factures d'un même client (une ligne par facture, même transaction).

**`sale_emails`** : `sale_id`, `purpose` (`send`, `reminder`, `receipt`), `to`, `cc`, `subject`,
`sent_at`, `status` (`sent`, `failed`), `error`, `channel` (`smtp`, `qonto`).

### 2.2 Récurrence, baux, quittances

**`recurrences`** : `template_id` (FK sales, `kind = template`), `frequency` (`monthly`, `quarterly`,
`yearly`), `due_day` (1–28), `start_date`, `end_date` NULL, `in_advance` (terme à échoir), 
`next_date` (prochaine échéance à préparer), `qonto_emit`, `active`.

**`sale_occurrences`** : `(recurrence_id, period_start)` unique, `sale_id` — garantit qu'une échéance
n'est préparée qu'une fois.

**`leases`** : `entity_id` (locataire), `unit_label`, adresse du lot (4 champs), `start_date`,
`end_date` NULL, `rent_cents`, `charges_cents`, `due_day`, `deposit_cents`, `deposit_entry_id` NULL,
`rent_product_id`, `charges_product_id` (comptes et TVA via le catalogue, Q12), `recurrence_id`,
`notes`, `active`.

**`rent_receipts`** : `lease_id`, `sale_id`, `kind` (`quittance`, `recu`), `period_start`,
`period_end`, `rent_cents`, `charges_cents`, `paid_cents`, `paid_on`, `pdf_path`, `sent_at`.

### 2.3 Abonnements d'achat

**`subscriptions`** : `entity_id` (fournisseur), `label`, `category` (internet, téléphone,
assurance, banque, énergie, logiciel, autre), `product_id` (compte de charge, TVA),
`amount_cents` (TTC attendu), `amount_fixed` (Boolean), `frequency`, `due_day`, `bank_account_id`
NULL (compte prélevé), `start_date`, `end_date` NULL, `renewal_date` NULL, `notice_days` NULL,
`attachment_path` NULL, `active`, `notes`.

**`subscription_periods`** : `(subscription_id, due_date)` unique, `expected_cents`,
`purchase_id` NULL (facture réelle rattachée), `bank_transaction_id` NULL (prélèvement),
`status` (`expected`, `invoiced`, `paid`, `missing`, `skipped`). Les périodes sont créées
jusqu'à aujourd'hui à l'ouverture de l'écran Abonnements ou de la liste des achats (idempotent).

### 2.4 Colonnes ajoutées

| Table | Colonnes |
|---|---|
| `entities` | `customer_account_code` (411NNN), `billing_emails` (Text, copies), `delivery_*` NULL ; `person_kind`, adresse, `siret`, `vat_number` existent déjà |
| `products` | `description`, `unit`, `sale_price_cents`, `vat_exemption`, `nature` (`goods`/`services`), `qonto_product_id` |
| `fiscal_years` | `vat_on_receipts` Boolean NOT NULL default true (V6 : prestations à l'encaissement ; faux = débits) |
| `purchases` | `subscription_period_id` NULL (facture rattachée à une période d'abonnement) |
| `bank_transactions` | rien : l'encaissement se lit par `sale_payments.bank_transaction_id` |

**`billing_settings`** (une ligne, comme `receipt_settings`) : `legal_form`, `share_capital_cents`,
`rcs`, `vat_number`, `iban`, `bic`, `payment_terms_days` (30), `late_penalty_text`,
`recovery_fee` (Boolean, 40 €), `discount_text`, `logo_path`, `footer`, modèles d'email
(`send_subject`, `send_body`, `reminder_subject`, `reminder_body`, `receipt_subject`,
`receipt_body`), `quote_validity_days` (30).

### 2.5 Base méta

`instances.integrations` (JSON) gagne `scopes` : `{"qonto": ["transactions", "purchases", "sales"]}`.
Absent → périmètre complet pour `transactions` et `purchases` (usage actuel), `sales` à cocher.

## 3. Comptabilité

### 3.1 Émission d'une facture (journal VE, date d'émission)

| Compte | Débit | Crédit |
|---|---|---|
| 411NNN du client (créé sous 411 si absent, comme 401NNN) | TTC | |
| 70x de chaque ligne | | HT |
| 44571 TVA collectée (biens, ou services si `vat_mode = debits`) | | TVA |
| 44574 TVA collectée à encaisser (services si `vat_mode = receipts`) | | TVA |

- `vat_mode = none` : pas de TVA, mention 293 B (V13).
- 44571 et 44574 sont créés sous 4457 s'ils manquent (le plan SCI n'a que 4457).
- Avoir : écriture inverse au journal VE, au prorata des lignes reprises.

### 3.2 Encaissement (journal de la banque ou de la caisse)

| Compte | Débit | Crédit |
|---|---|---|
| 512 (ou 53x) | montant | |
| 411NNN | | montant |
| 44574 | TVA encaissée | |
| 44571 | | TVA encaissée |

TVA encaissée = TVA en 44574 de la facture × montant / TTC (dernier encaissement : le solde).
Une transaction déjà comptabilisée par une règle de catégorisation est remplacée comme pour les
achats (`replace_many`).

### 3.3 Dépôt de garantie, quittance

Encaissement du dépôt : 512 / 165 (écriture du bail). Une quittance n'a pas d'écriture : elle
constate le paiement.

### 3.4 Abonnements

Aucune écriture propre : la facture d'achat réelle se comptabilise comme aujourd'hui (AC), son
règlement aussi.

## 4. Numérotation (C2)

- `issue(sale)` : verrou d'écriture (SQLite `BEGIN IMMEDIATE`, PostgreSQL `SELECT … FOR UPDATE` sur
  `sale_counters`), `last_number + 1`, numéro `F-2026-0001`, écriture VE, PDF, commit unique. Échec
  → rollback complet, aucun numéro consommé (test « pas de trou » comme `test_no_gap_when_issue_fails`).
- Année = année civile de la date d'émission. Pas d'émission antidatée avant la dernière facture de
  la série (ordre chronologique).
- Facture Qonto : `number` = numéro Qonto, `series_*` NULL ; la série de l'application n'avance pas.

## 5. PDF et Factur-X (C6)

1. Gabarit `templates/sales/document.html` (devis, facture, avoir, relance, quittance, reçu de loyer) :
   logo, mentions du § 4.8 des besoins, lignes, totaux par taux, mention TVA selon `vat_mode`.
2. Facture et avoir de l'application : `HTML(...).write_pdf(pdf_variant="pdf/a-3b")`.
3. XML CII **EN 16931** produit par la bibliothèque à partir des données de la facture (`einvoice.data_dict`).
4. `facturx.generate_from_binary(pdf, xml, flavor="factur-x", level="en16931", check_xsd=True)`.
5. PDF conservé (`sales.pdf_path`) ; l'application relit le Factur-X avec `invoice_reader` dans un
   test (aller-retour).

**Lot S0 — essai de faisabilité : RÉUSSI (23/10/2026).** `factur-x` 7.7 (BSD) installé avec
`lxml`, `pypdf`, `python-stdnum`, `iso4217` ; module `app/services/einvoice.py` :

- le XML CII EN 16931 est **produit par la bibliothèque** (`generate_cii_xml`, à partir d'un
  dictionnaire BT/BG), sans gabarit à écrire (le gabarit Jinja du point 3 est abandonné) ; contrôle
  XSD réussi pour une facture (TVA 20 % et 5,5 %, TVA à l'encaissement, IBAN), une facture en
  franchise 293 B et un avoir ;
- le bloc livraison est obligatoire et non vide : date de livraison (BT-72) = fin de prestation,
  sinon date d'émission ;
- WeasyPrint 69 produit le PDF/A-3b (`pdf_variant`), polices embarquées, OutputIntent présent ;
  la bibliothèque insère le XML (`factur-x.xml`, relation `Data`, XMP Factur-X EN 16931) ;
- le lecteur de factures de l'application relit le Factur-X (numéro, dates, montants, ventilation
  de TVA) — l'essai a révélé et corrigé un plantage du lecteur sur ces PDF (`embfile_info` de
  PyMuPDF) ;
- image Docker construite avec la nouvelle dépendance.

Limites : le contrôle **schematron** EN 16931 (règles métier) demande un serveur Saxon, non lancé
(`check_schematron=False`, la bibliothèque appelle sinon `http://localhost:5000`) ; la conformité
PDF/A complète n'est pas vérifiée par un validateur (veraPDF). À faire avant la mise en production :
passer une facture de test dans un validateur Factur-X de référence. V9 : l'application produit ses
Factur-X.

Facture Qonto : PDF Qonto (Factur-X) récupéré par une tâche de fond (`attachment_id` disponible en
différé, URL valable 30 min, téléchargé et conservé localement).

## 6. Qonto (lot S4)

### 6.1 Périmètre

Fiche Intégration Qonto : cases **Relevés de compte**, **Achats**, **Ventes** (`POST
/api/v1/integrations/qonto/scopes`). `external_config.scope_enabled("qonto", "sales")` ; session :
`instance.integrations.scopes` ; front : `useIntegration("qonto", "sales")`. Chaque fonction Qonto
existante passe derrière son périmètre (synchro des transactions, synchro et dépôt des factures
d'achat).

### 6.2 Émission avec Qonto (facture, avoir, devis)

```
validate(sale)                       # local : exercice ouvert, comptes, client complet
client_id = qonto_clients.ensure(entity)   # recherche SIREN, TVA, email, nom ; sinon création
POST /v2/client_invoices {status: draft, items (titre ≤ 40, reste en description), iban du compte Qonto}
POST /v2/client_invoices/{id}/finalize    → numéro Qonto
post(sale) ; commit                        # écriture VE avec le numéro Qonto
job : PDF (attachment) → sales.pdf_path
```

Échec Qonto avant finalisation : la facture reste brouillon, `qonto_error` affiché, brouillon Qonto
supprimé. Échec après finalisation (rare) : la facture est importée à la synchronisation suivante
(par `qonto_id`) et comptabilisée alors.

Avoir d'une facture Qonto : `POST /v2/credit_notes`. Devis : `POST /v2/quotes`, statut
(accepté, annulé) relu à la synchronisation ; facture depuis un devis Qonto : `quote_id` transmis.

### 6.3 Synchronisation (tâche de fond `qonto_sales`, curseur `sync_cursors`)

Clients, produits, devis, factures, avoirs modifiés depuis le dernier passage (`updated_at`) :
upsert par `qonto_id` ; client rattaché à un tiers (SIREN, TVA, email, nom) sinon proposé comme
pour les fournisseurs ; facture créée dans Qonto → `source = qonto`, lignes au produit de vente par
défaut, comptabilisée quand elle est complète (même logique « à compléter / prête » que les
achats). Facture annulée dans Qonto sans avoir local → signalée « à revoir ».

### 6.4 Paiement

Encaissement rapproché d'une facture Qonto → `POST /v2/client_invoices/{id}/mark_as_paid` à la date
de paiement quand la facture est soldée (V11) ; annulation du rapprochement → `unmark_as_paid`.

## 7. Services (backend)

| Module | Rôle |
|---|---|
| `sale_entry` | Création et modification des brouillons, lignes depuis le catalogue, totaux, doublons |
| `sale_numbering` | Compteurs, `next_number(series, year)` sous verrou |
| `sale_posting` | Écriture VE, 411NNN, 44571/44574, avoir, contre-passation |
| `sale_issue` | Émission (numéro + écriture + PDF), devis → facture, avoir |
| `sale_pdf` / `facturx` | PDF WeasyPrint, XML CII, Factur-X |
| `sale_settlement` | Propositions de rapprochement (montant, client, numéro dans le libellé), encaissements, TVA encaissée, remplacement des écritures de règle |
| `sale_reminders` | Échues non payées, relance (email + compteur) |
| `mailer` | Envoi SMTP avec pièces jointes, journal `sale_emails` ; utilisé aussi par les reçus fiscaux à terme |
| `recurrence` | Échéancier, préparation idempotente des échéances dues |
| `leases` | Bail, dépôt de garantie, quittances et reçus de loyer |
| `qonto_sales` | Clients, produits, devis, factures, avoirs, PDF, paiement (client Qonto étendu) |
| `subscriptions` | Abonnements, périodes, rattachement facture et prélèvement, rappels de préavis |

## 8. API (préfixe `/api/v1`)

| Ressource | Routes |
|---|---|
| Ventes | `GET/POST /sales?kind=` ; `GET/PATCH/DELETE /sales/<id>` (brouillon seulement) ; `POST /sales/<id>/issue` ; `POST /sales/<id>/credit-note` ; `POST /sales/<id>/to-invoice` (devis) ; `POST /sales/<id>/status` (devis : accepté, refusé) ; `GET /sales/<id>.pdf` ; `POST /sales/send` `{ids, to?, subject?, body?}` (lot, tâche de fond) ; `POST /sales/remind` `{ids}` ; `GET /sales/form-options` |
| Encaissements | `GET /sales/receivables` (factures ouvertes, propositions) ; `POST /sales/<id>/payments` (manuel) ; `POST /sales/match` `{bank_transaction_id, allocations}` ; `DELETE /sale-payments/<id>` |
| Récurrence | `GET/POST /recurrences` ; `PATCH/DELETE /recurrences/<id>` ; `GET /sales/due` (prépare puis liste les échéances à émettre) ; `POST /sales/issue-batch` `{ids, send}` |
| Baux | `GET/POST /leases` ; `GET/PATCH /leases/<id>` ; `POST /leases/<id>/deposit` ; `GET /rent-receipts/<id>.pdf` ; `POST /rent-receipts/send` |
| Réglages | `GET/PUT /billing-settings` ; `POST /billing-settings/logo` |
| Qonto | `POST /integrations/qonto/scopes` ; `POST /sales/sync` (tâche) |
| Abonnements | `GET/POST /subscriptions` ; `PATCH/DELETE /subscriptions/<id>` ; `GET /subscriptions/periods` ; `POST /subscription-periods/<id>/link` `{purchase_id | bank_transaction_id}` ; `POST /subscription-periods/<id>/skip` |

Droits : écriture pour administrateur et trésorier, lecture pour l'expert-comptable ; réglages de
facturation et périmètre Qonto : administrateur de l'instance. `require_integration("smtp")` et
`require_integration("qonto")` + périmètre pour les actions qui en dépendent.

## 9. Écrans (SPA)

| Écran | Contenu |
|---|---|
| Ventes › Factures `/sales/` | Liste (onglets Factures, Avoirs ; filtres état, client, mois, échues, origine) ; sélection → Émettre, Envoyer, Relancer ; totaux |
| Facture `/sales/<id>` | En-tête, lignes (éditeur des achats réutilisé), totaux, case « Émettre avec Qonto », Émettre, PDF, Envoyer, Avoir, encaissements, historique des envois et relances |
| Saisie `/sales/new?kind=` | Client (création à la volée), lignes du catalogue, dates, conditions |
| Ventes › Devis `/quotes/` | Liste et fiche, Accepter / Refuser, Transformer en facture |
| Ventes › À émettre `/sales/due` | Échéances préparées (récurrentes, loyers) ; émettre et envoyer en lot |
| Ventes › Encaissements `/sales/receivables` | Factures ouvertes et transactions proposées ; rapprochement |
| Ventes › Relances `/sales/overdue` | Échues non payées, dernière relance ; sélection → Relancer |
| Ventes › Baux `/leases/` | Baux, échéancier, quittances, dépôt de garantie |
| Achats › Abonnements `/subscriptions/` | Contrats, coût mensuel / annuel par catégorie, périodes attendues / manquantes, rappels de préavis |
| Configuration › Structure › Facturation | Mentions, IBAN, conditions, logo, modèles d'email, séries |
| Configuration › Intégrations › Qonto | Cases de périmètre |
| Rapprochement | Une transaction créditrice propose les factures ouvertes du client |
| Tableau de bord | CA facturé, encours clients, échues |

Menus : **Ventes** (toutes structures) ; **Achats** gagne **Abonnements** ; le Catalogue reste dans
Compta.

## 10. Lots

| Lot | Contenu |
|---|---|
| **S0** | Essai Factur-X (dépendances, PDF/A-3, XML CII, contrôle) — décide V9 |
| **S1** | Réglages de facturation, clients 411NNN, catalogue de vente, factures et avoirs de l'application, numérotation, écriture VE (TVA débits / encaissements), PDF (Factur-X si S0 réussi), envoi manuel SMTP |
| **S2** | Encaissements (rapprochement, manuel, TVA encaissée), relances manuelles, tableau de bord |
| **S3** | Devis (émission, statut, transformation en facture) |
| **S4** | Qonto : périmètre, synchronisation clients / produits / devis / factures / avoirs, émission avec Qonto, PDF Qonto, marquer payée |
| **S5** | Factures récurrentes, baux, dépôt de garantie, quittances et reçus de loyer |
| **S6** | Abonnements d'achat (contrats, périodes, rattachement, rappels) |
| **S7** | Documentation utilisateur, E2E de bout en bout |

## 11. Tests

- pytest : totaux et arrondis ; numérotation continue (concurrence simulée, échec → pas de trou) ;
  écritures VE / encaissement / avoir équilibrées, 44574 → 44571 au prorata ; facture émise non
  modifiable ; devis → facture ; échéances préparées une seule fois ; quittance seulement à
  l'encaissement complet ; périodes d'abonnement idempotentes ; Qonto par faux client (jamais le
  vrai) : brouillon puis finalisation, échec avant finalisation sans écriture, synchro, mark_as_paid ;
  emails par faux SMTP ; Factur-X relu par `invoice_reader`.
- Vitest : saisie, émission, case Qonto selon le périmètre, envoi groupé, rapprochement.
- E2E : facture sans Qonto de bout en bout (saisie → émission → PDF → encaissement) ; loyer mensuel
  → quittance ; abonnement → période manquante signalée.

## 12. Risques et points d'attention

- **Conformité** : mentions et numérotation à faire relire par l'expert-comptable (comptes des
  loyers, Q12) avant la mise en production.
- **Factur-X** : la conformité PDF/A-3 de WeasyPrint et le profil EN 16931 sont à prouver (S0).
- **Qonto** : libellés de ligne limités à 40 caractères ; pas de modification des produits ; pas de
  lien facture ↔ transaction (rapprochement par l'application) ; certaines autorisations par clé
  API (devis, finalisation, envoi, avoirs) à confirmer dans le bac à sable avant S4. Aucun appel au
  Qonto réel pendant le développement (règle du projet) : bac à sable ou faux client.
- **Réforme 2027** : une facture de l'application seule ne passe pas par une plateforme agréée ;
  pour une entreprise assujettie, émettre avec Qonto répond à l'obligation.
- **Taille** : sept lots ; S1 est utilisable seul (facturer sans Qonto).
