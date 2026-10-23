# Dokos et Frappe Books : analyse comparative avec Lyvre

*Recherche du 23/10/2026. Sources : dépôts clonés (Dokos `develop` @889b6b3 du 23/10/2026, en sparse checkout sur les JSON des doctypes ; Frappe Books `main` du 02/10/2026), doc.dokos.io, dokos.io, frappe.io/books, GitHub. Aucun code n'a été exécuté. Je n'ai lu que les schémas et quelques fichiers : les comportements cités viennent des schémas, des docstrings et de la doc officielle.*

---

## Partie A : Dokos

### A.1 Technologies

| Point | Détail |
|---|---|
| Langage | Python ≥ 3.14 côté serveur (pyproject), JavaScript côté client |
| Framework | **Dodock**, fork du Frappe Framework (dépendance `frappe >=17.0.0-dev,<18`), maintenu par Dokos SAS (Lyon). Modèle « DocType » : chaque objet métier est un JSON de schéma, un contrôleur Python et un formulaire JS générés |
| Base de données | MariaDB (PostgreSQL toléré par Frappe), Redis pour les files et le cache, workers RQ |
| Front | Desk Frappe (jQuery/Vue), portail web, `dokos-ui` |
| Licence | **GPLv3** (ERPNext d'origine). Lyvre est sous AGPL, donc les licences sont compatibles dans le sens GPL vers AGPL |
| Déploiement | bench / docli, Docker ; SaaS sur cloud.dokos.io ; autohébergement. Applications séparées : `bookings` (réservations), `payments`, `hrms`, `etransactions` (factures électroniques UBL/CII), `ocr`, `bank`/`bank-api`, `certification_caisse` (archivage sécurisé NF), `ruche` (CAE), `agicap`, `woocommerce`, `nextcloud`… (groupe gitlab.com/dokos, 36 projets) |
| Taille | 214 doctypes dans `erpnext/accounts/doctype` seulement. C'est un ERP complet : ventes, achats, stock, production, CRM, projets, RH, qualité, support |

Remarque : le module **non-profit** d'ERPNext (Member, Donor, Donation, Chapter, Membership) **n'existe plus dans le dépôt Dokos**. Aucun doctype donor/donation/member/chapter n'apparaît dans l'arbre, Frappe l'a sorti d'ERPNext en v14. Le module « Lieu / Venue » a été déplacé vers l'application séparée `bookings` (« Dokos Bookings », plus `federated-venue` et `venues-federation`).

### A.2 Méthodes et données comptables

**Grand livre (GL Entry) et immuabilité**
- Les pièces sont des documents *soumissibles* (`is_submittable`), avec trois états : brouillon, validé, annulé. Une fois validée, une pièce n'est plus modifiable. Pour corriger, on **annule** la pièce, ce qui pose des écritures contraires et marque les lignes `is_cancelled`, puis on la **modifie (amend)** : une nouvelle pièce `XXX-1` est créée avec `amended_from`. Le paramètre `Accounts Settings.delete_linked_ledger_entries` décide si la suppression d'une pièce annulée efface ses lignes du GL.
- Champs de `GL Entry` : `posting_date`, `transaction_date`, `account`, `party_type`/`party`, `cost_center`, `project`, `debit`/`credit`, plus les montants en devise du compte, en devise de transaction et en devise de reporting, `against_voucher_type/against_voucher`, `voucher_type/voucher_no/voucher_detail_no`, `is_opening`, `is_advance`, `finance_book`, `due_date`, `is_cancelled`. Champs ajoutés par Dokos pour la France : **`accounting_journal`**, **`accounting_entry_number`**, **`ecriturenum`** (numéro FEC) et **`vat_declaration`** (rattachement de la ligne à une déclaration de TVA).
- **Payment Ledger Entry** est un second registre, réservé aux tiers (créances et dettes). Il relie chaque montant à la facture qu'il solde (`against_voucher_no`, `delinked`). Le **lettrage** et les balances âgées en dépendent.
- **Accounting Journal** et **Accounting Journal Rule** (spécifiques à Dokos) : une pièce est affectée automatiquement à un journal (code journal FEC) selon des conditions sur le type de document. L'option `mandatory_accounting_journal` rend le journal obligatoire.
- Outils d'intégrité : **Repost Accounting Ledger** (reconstruit le GL d'une pièce), **Repost Payment Ledger**, **Ledger Health / Ledger Health Monitor** (détecte les déséquilibres débit/crédit et les écarts entre GL et payment ledger), rapport `general_and_payment_ledger_comparison`, **Bisect Accounting Statements** (localise par dichotomie la date d'apparition d'un écart).

**Passage du document au GL**
- Les factures de vente et d'achat, les paiements (Payment Entry), les écritures (Journal Entry), les immobilisations, la paie (Payroll Summary), le stock (valorisation perpétuelle), les Dunning, les Trade Bill (effets de commerce) et le Period Closing Voucher passent tous par `make_gl_entries` à la validation. **Journal Entry Template** fournit des modèles d'écritures récurrentes, et Dokos livre des modèles français (`regional/france/journal_entry_templates.py`).

**Rapprochement paiement ↔ facture (lettrage)**
- Un **Payment Entry** porte une table `references` (Payment Entry Reference) pour allouer un paiement à une ou plusieurs factures, et `deductions` pour les escomptes, frais et écarts de change.
- **Payment Reconciliation** est l'outil de lettrage. Pour un tiers et un compte 411/401, il liste les factures ouvertes et les paiements non alloués (filtres par dates, montants, centre de coût et projet), puis alloue. Partiel et multi-factures sont possibles.
- **Process Payment Reconciliation** fait le lettrage automatique en tâche de fond, avec un journal. L'option `auto_reconcile_payments` existe.
- **Unreconcile Payment** sert au délettrage.
- **Advance Payment Ledger Entry** gère les acomptes. **Party Link** et `enable_common_party_accounting` compensent un tiers qui est à la fois client et fournisseur.

**Clôture**
- **Accounting Period** verrouille une période et un type de document (`closed_documents`), avec un rôle exempté.
- `Company.accounts_frozen_till_date` gèle les comptes jusqu'à une date.
- **Period Closing Voucher** solde les comptes de gestion vers le résultat (`closing_account_head`, `closing_account_head_loss`, `accounting_journal_for_closing_voucher`). **Process Period Closing Voucher** le traite par lots. **Account Closing Balance** stocke les soldes de clôture pour accélérer les rapports.
- Dokos ajoute `opening_balances.py`, un service qui calcule les à-nouveaux à partir du grand livre, commun au FEC et à MyUnisoft.
- Verrou TVA (`vat_lock.py`) : une déclaration de TVA déposée tamponne ses écritures, qui ne peuvent plus être annulées. Une pièce postée plus tard dans la période déjà déclarée part en « régularisation tardive » sur la déclaration suivante (verrou souple). Le verrou dur gèle la société jusqu'à la fin de la période déclarée.

**Dimensions analytiques et centres de coût**
- **Cost Center** est un arbre. **Cost Center Allocation** répartit en pourcentages un centre principal sur d'autres centres à partir d'une date (`valid_from`). Le rapport `distributed_cost_center` existe.
- **Accounting Dimension** ajoute des axes analytiques illimités (`document_type` = n'importe quel doctype : projet, activité, financeur…). Ils sont propagés automatiquement sur tous les documents et le GL. **Accounting Dimension Filter** restreint les valeurs autorisées par compte, et `dimension_defaults` fixe des valeurs par défaut par société. Le rapport `dimension_wise_accounts_balance_report` donne les soldes par axe.

**Budgets avec contrôles**
- **Budget**, par centre de coût ou par projet et par compte. Pour chaque niveau (demande d'achat, bon de commande, dépenses réelles, dépense cumulée), on choisit l'action en cas de dépassement annuel ou mensuel cumulé : **Stop / Warn / Ignore**. Le budget peut être pluriannuel (`from_fiscal_year`/`to_fiscal_year`), réparti par période (**Budget Distribution**, **Monthly Distribution**) et révisé (`revision_of`). Rapports `budget_variance_report` et `cash_flow_budget`.

**Immobilisations et amortissements** (module `assets`)
- **Asset**, **Asset Category** (comptes par catégorie), **Asset Depreciation Schedule**. Méthodes : *Straight Line*, *Double Declining Balance*, *Written Down Value*, *Manual*, au prorata journalier (`daily_prorata_based`) ou par équipes. **Finance Book** permet plusieurs plans (comptable / fiscal). S'y ajoutent **Asset Value Adjustment** (dépréciation), **Asset Capitalization** (composants), **Asset Repair**, **Asset Movement** (localisation, responsable), **Asset Maintenance**, cession et mise au rebut avec écritures. La comptabilisation automatique des dotations est une option (`book_asset_depreciation_entry_automatically`). Dokos ajoute `regional/france/assets.py`. Rapports : `asset_depreciation_ledger`, `asset_depreciations_and_balances`.

**Produits et charges constatés d'avance**
- Sur chaque ligne de facture : `enable_deferred_revenue`, `deferred_revenue_account`, `service_start_date`, `service_end_date` (même chose pour les charges sur les factures d'achat). **Process Deferred Accounting** étale les montants mois par mois (automatiquement ou manuellement, par JE ou GL direct, au prorata des jours ou des mois). Rapport `deferred_revenue_and_expense`.

**Taxes**
- **Sales/Purchase Taxes and Charges Template**, **Item Tax Template**, **Tax Rule** (choix automatique du modèle selon le tiers, l'adresse et la catégorie), **Tax Category**, retenue à la source (Tax Withholding). Dokos fournit le **VAT Configuration Tool**, qui détermine la TVA par pays/groupe (France, UE, export).
- France (Dokos) : **préparation de la CA3 / CA12** (`France Tax Declaration Preparation`, formulaires `3310CA3_2026`, `3310A`, `3519` pour le remboursement de crédit), **EDI-TVA** (EDIFACT/XML, `edi_tva/`), contrôles TVA, TVA sur encaissements/débits, annexes, gestion des régularisations tardives, **DEB/DES intra-UE** (`intra_eu/`, XML DES et INSTAT, VIES), **DAS2** (honoraires), **Tax Obligation / Tax Obligation Schedule** (échéancier des impôts : IS, CFE, TVA… vers la prévision de trésorerie).

**Multidevise**
- Devise par compte et par tiers, **Currency Exchange Settings** (API de taux), **Exchange Rate Revaluation** (réévaluation de fin de période des comptes en devises, gains et pertes réalisés ou latents), devises arrimées (`pegged_currencies`), devise de reporting.

**Relances**
- **Dunning** + **Dunning Type**. Il s'agit de lettres de relance multilingues, **avec frais de relance et intérêts de retard** (`dunning_fee`, `rate_of_interest`) qui sont comptabilisés (`income_account`). La table `overdue_payments` liste les échéances en retard. **Process Statement of Accounts** envoie automatiquement par courriel des relevés de compte client (GL ou balance âgée) selon une périodicité.

**Abonnements**
- **Subscription** + **Subscription Plan** : récurrence, jour de facturation, facturation en début ou fin de période, période d'essai, **prorata**, validation automatique des factures, génération de commandes en amont, **lien avec Payment Request et le paiement en ligne** (`dokos_payment_request_status`), modèle de courriel, état (`subscription_state`). Rapport et graphique `monthly_recurring_revenue` (MRR).

**Paiements**
- **Payment Request** : lien de paiement en ligne envoyé par courriel (Stripe, GoCardless, PayPal… via l'app `payments`), création possible de la facture à la réception du paiement.
- **SEPA Direct Debit** + **SEPA Mandate** + **SEPA Direct Debit Settings** : génération du fichier **pain.008** (CORE/B2B, séquences FRST/RCUR/OOFF/FNAL, lot), paiements générés à partir des factures ouvertes des clients qui ont un mandat actif, empreinte du fichier (`file_hash`, `content_fingerprint`), compte de transit et écriture de compensation. Côté fournisseurs, **Payment Order** sert aux virements groupés.
- **Trade Bill** (effets de commerce LCR/BOR) : remise, encaissement et impayé, chacun avec son écriture.

**Banque**
- **Bank Transaction**, à importer en OFX, CSV/XLSX avec mapping, ou PDF dans le module unifié. Un transaction_id unique protège contre les doublons.
- **Bank Reconciliation Tool**, avec rapprochement 1 banque ↔ n pièces et création à la volée d'un Payment Entry ou d'un JE. Le rapprochement automatique se fait par numéro de facture dans le libellé ou par identifiant Stripe, et des méthodes peuvent être ajoutées par hook.
- **Bank Transaction Rule** : catégorisation, et **détection des récurrences pour la prévision** (`forecast_enabled`, `periodicity`, `learned_amount`, `amount_tolerance_percent`, `expected_day`, `next_expected_date`, `proposal_status` : règles *apprises* et proposées).
- **Cash Flow Forecast Scenario / Snapshot** : scénarios de trésorerie avec décalage des délais clients et fournisseurs, ajustement des recettes et dépenses, seuil minimal de trésorerie, instantanés. **Bank Clearance** sert au pointage des chèques.

**Spécificités françaises**
- PCG 2025 généré depuis un CSV (`chart_of_accounts/pcg_2025.csv`, `build.py`), libellés PCG et DGFiP. **Pas de plan associatif ANC 2018-06 dédié** (rien de tel dans l'arbre `regional/france`).
- **FEC** : rapport `fichier_des_ecritures_comptables` (zip), **descriptif du FEC** (`fec_descriptif.py`), à-nouveaux calculés, option `use_supplier_invoice_number_in_fec`. **Import FEC** (`FEC Import`, mapping des journaux) pour reprendre l'historique d'un autre logiciel.
- Bilan et compte de résultat au format français (`balance_sheet_presentation.py`, `profit_and_loss` France), balance France (format d'impression), **Soldes Intermédiaires de Gestion**.
- **Facturation électronique** : app `etransactions` (lecture des factures UBL et CII), format d'impression `purchase_einvoice`, `Import Supplier Invoice`, registre `electronic_invoice_register`. Contrôle du SIREN (`extensions/siren.py`) et intégration **Pappers** (remplissage automatique des tiers par SIREN).
- Archivage : empreintes SHA-256 des fichiers de déclaration (`archive.py`). L'app `certification_caisse` sert à l'inaltérabilité de caisse (loi anti-fraude TVA).
- **MyUnisoft** : synchronisation bidirectionnelle avec le logiciel de l'expert-comptable (plan, journaux, écritures, pièces jointes, à-nouveaux, rapport de rapprochement).

**Piste d'audit**
- `track_changes` sur la plupart des doctypes : l'historique **Version** enregistre chaque modification de champ avec l'utilisateur et la date. Il existe aussi un journal d'accès et d'activité. Les pièces validées sont figées, et l'annulation laisse une trace par contre-passation.

**Autres** : **Shareholder / Share Type / Share Transfer** (registre des parts, rapports `share_balance` et `share_ledger`), **Finance Book**, **Bank Guarantee**, **Loyalty Program**, **Pricing Rule**, **POS**, **Opening Invoice Creation Tool** (reprise des encours), **Chart of Accounts Importer**, **Financial Report Template** (états financiers personnalisés), **Financial ratios**, **consolidation multisociété**.

### A.3 Fonctionnalités par domaine

- **Comptabilité générale** : plan multi-pays, journaux FEC, JE et modèles, GL, balance, bilan, résultat, SIG, flux de trésorerie, ratios, états personnalisés, consolidation multisociété, finance books, clôture, verrous de période.
- **Tiers** : comptes clients et fournisseurs, lettrage manuel et automatique, balances âgées, relevés automatiques, relances avec frais, effets de commerce, acomptes, compensation client/fournisseur.
- **Banque et trésorerie** : imports OFX/CSV/PDF, connecteurs bancaires (`bank`, `bank-api`), rapprochement avec règles, prévisionnel par scénarios, catégories de flux, obligations fiscales planifiées, SEPA (prélèvement), ordres de virement, synchronisation Agicap.
- **Fiscalité FR** : CA3/CA12, EDI-TVA, DEB/DES, DAS2, FEC export et import, facturation électronique.
- **Ventes** : devis, commandes, factures, avoirs, acomptes, factures de situation, abonnements, demande de paiement en ligne, portail client, webshop, POS.
- **Achats** : demandes d'achat, commandes, réceptions, factures, OCR (app `ocr`), import de factures électroniques.
- **Analytique et budget** : centres de coût, dimensions illimitées, budgets bloquants, rapports par dimension, rentabilité par projet.
- **Immobilisations** : registre, plans d'amortissement, maintenance, mouvements, cessions.
- **Lieux / réservations** (app `bookings`) : ressources réservables, crédits de réservation, abonnements, événements, portail (cible : tiers-lieux, coworkings).
- **Autres** : stock, production, CRM, projets et feuilles de temps facturables, RH et paie (`hrms`), qualité, support, low-code (champs et scripts personnalisés, workflows, rapports), API REST, webhooks.

### A.4 Écarts par rapport à Lyvre

| Fonctionnalité Dokos absente ou plus aboutie que dans Lyvre | Intérêt pour une association ou une SCI | Source |
|---|---|---|
| **Lettrage des comptes de tiers** : Payment Reconciliation, lettrage automatique en tâche de fond, délettrage, Payment Ledger séparé | Fiabiliser les 411/401/467, retrouver les impayés ; utile pour la SCI (locataires) et pour les asso qui facturent | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/payment_reconciliation |
| **Immobilisations et plans d'amortissement** (linéaire, dégressif, manuel, prorata journalier, plusieurs finance books, dotations automatiques, cessions) | Obligatoire dès qu'une asso ou SCI possède du matériel ou un immeuble ; la SCI amortit le bâti par composants | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/assets/doctype |
| **CA3/CA12 préparée depuis le GL** + EDI-TVA + **verrou des périodes déclarées** avec régularisations tardives | Asso fiscalisée (activités lucratives) ou SCI à l'IS/TVA sur option ; le verrou évite de modifier une période déjà déclarée | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/regional/france |
| **Prélèvement SEPA (pain.008) + mandats** | Encaisser cotisations et loyers par prélèvement sans HelloAsso ni Qonto | https://doc.dokos.io/fr/v5/dokos/comptabilite/prelevement-sepa |
| **Dimensions analytiques multiples** + filtres de valeurs autorisées par compte + répartition par % de centres de coût | Croiser projet × financeur × site (comptes d'emploi des subventions) ; Lyvre n'a qu'un axe « projets » | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/accounting_dimension |
| **Budgets avec contrôle** (Stop/Warn/Ignore à la saisie, mensuel cumulé, pluriannuel, révisions) | Bloquer ou alerter quand une dépense dépasse l'enveloppe d'une subvention ; Lyvre ne fait que le suivi | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/budget |
| **Produits et charges constatés d'avance par ligne** (dates de service) + étalement automatique | Cotisations ou abonnements à cheval sur deux exercices, assurance annuelle ; Lyvre ne traite que les 486/487 à la clôture | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/process_deferred_accounting |
| **Relances structurées (Dunning)** avec niveaux, frais et intérêts de retard comptabilisés + **relevés de compte automatiques** | SCI : relancer les loyers impayés avec pénalités prévues au bail ; Lyvre n'a que des relances manuelles | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/dunning |
| **Demande de paiement en ligne** (Payment Request, Stripe/GoCardless) liée aux factures et aux abonnements | Paiement en ligne de factures ou d'adhésions sans plateforme tierce | https://doc.dokos.io/fr/v5/integrations/payments |
| **Abonnements de vente complets** (prorata, essai, validation automatique, MRR) | Plus riche que les factures récurrentes en brouillon de Lyvre (location de salles, prestations récurrentes) | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/subscription |
| **Piste d'audit** (`track_changes` → Version) + pièces validées non modifiables (annulation par contre-passation, amend avec `amended_from`) | Exigence de probité et d'auditabilité pour le commissaire aux comptes et les financeurs publics | https://gitlab.com/dokos/dokos/-/blob/develop/erpnext/accounts/doctype/gl_entry/gl_entry.json |
| **Import FEC** (reprise d'historique depuis un autre logiciel) + **descriptif du FEC** | Migration d'une asso depuis un logiciel ou un cabinet ; le descriptif est exigé en cas de contrôle | https://doc.dokos.io/fr/v5/dokos/comptabilite/import-fec |
| **Prévision de trésorerie par scénarios** + règles bancaires qui *apprennent* les récurrences + échéancier des obligations fiscales | Plus fin que le prévisionnel 12 mois de Lyvre : scénario pessimiste (subvention en retard) et seuil d'alerte | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/cash_flow_forecast_scenario |
| **Effets de commerce / Trade Bill**, **Bank Clearance** (pointage des chèques), **Payment Order** (virements groupés) | Remises de chèques et paiements groupés de fournisseurs ; Lyvre n'a pas de bordereau de remise de chèques | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/bank_clearance |
| **Outils d'intégrité du grand livre** (Ledger Health, Bisect, Repost) | Diagnostiquer un déséquilibre ou un écart avant la clôture | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/ledger_health_monitor |
| **Synchronisation avec l'expert-comptable (MyUnisoft)** | Asso ou SCI dont la comptabilité est révisée par un cabinet : plus besoin de réimporter des FEC | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/regional/france/integrations/myunisoft |
| **Pappers / contrôle du SIREN** à la création des tiers | Fiches fournisseurs justes, utiles pour la facturation électronique 2026-2027 | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/regional/france/pappers |
| **Réservation de ressources (app Bookings)** avec facturation | Asso ou SCI qui loue des salles ou des espaces partagés (tiers-lieux) | https://doc.dokos.io/fr/v5/dokos/lieu |
| **Multidevise + réévaluation de change** | Rarement utile (asso avec partenaires hors zone euro) | https://gitlab.com/dokos/dokos/-/tree/develop/erpnext/accounts/doctype/exchange_rate_revaluation |

Points où **Lyvre est plus adapté** : plan associatif ANC 2018-06 (Dokos n'a que le PCG), dons et reçus Cerfa, bénévolat valorisé (86/87), fonds dédiés et assistant de clôture associatif, adhérents via HelloAsso, compte d'emploi et rapport d'activité, mode recettes/dépenses simplifié, synchronisation Qonto, simplicité (Dokos est un ERP complet, lourd à paramétrer, sur MariaDB et Redis). Le module non-profit d'ERPNext n'est **plus présent** dans Dokos.

---

## Partie B : Frappe Books

### B.1 Technologies

| Point | Détail |
|---|---|
| Statut | **Fin de vie** : le dépôt Electron/Vue `frappe/books` (v0.37.0) a été archivé le **02/10/2026** (issue #1566). Son successeur est **`frappe/frappe-books`**, une application web bâtie sur le Frappe Framework (Python/JS, interface Frappe UI en Vue, servie sous `/books`, PWA mobile, AGPL-3.0, autohébergée, sans offre cloud annoncée) |
| Ancienne version (analysée ici) | Application **de bureau Electron**, **TypeScript**, **Vue 3** + vue-router + Tailwind, ORM maison « fyo » sur **knex + better-sqlite3**, montants en virgule fixe via **pesa**, tâches planifiées via bree. Un fichier **SQLite par société**, hors ligne |
| Licence | **AGPL-3.0**, comme Lyvre |
| Modèle de données | Schémas JSON déclaratifs (`schemas/app/*.json`) + classes de modèles (`models/baseModels/*`). Pattern doctype hérité de Frappe, en plus simple |

### B.2 Méthodes et données comptables

- **Grand livre** : `AccountingLedgerEntry` (`date`, `party`, `account`, `debit`, `credit`, `referenceType`, `referenceName`, **`reverted`**, **`reverts`**). Aucune dimension analytique ni centre de coût, aucune devise sur la ligne.
- **Passage au GL** (`models/Transactional/LedgerPosting.ts`) : à la soumission (`afterSubmit`), le document crée ses écritures. Un contrôle d'équilibre est fait et un arrondi est posté sur le compte d'arrondi (`roundOffAccount`). À l'annulation (`afterCancel`), des **écritures inverses** sont créées (`reverts` = ligne d'origine, `reverted = true`). Mais **`afterDelete` supprime les écritures normales et inverses** : l'immuabilité n'est donc pas garantie, un document annulé peut être supprimé avec sa trace.
- **Documents soumissibles** : SalesInvoice, PurchaseInvoice, Payment, JournalEntry (`entryType` : Journal, Bank, Cash, Credit Card, Debit/Credit Note, Contra, Write Off, Opening, **Depreciation Entry**, simple type sans module d'amortissement), SalesQuote, Shipment/PurchaseReceipt (stock).
- **Rapprochement paiement ↔ facture** : un `Payment` porte une table `for` (`PaymentFor` : `referenceType`, `referenceName`, `amount`), donc un paiement solde n factures, avec `writeoff` (écart passé en perte), `clearanceDate` (simple date de pointage bancaire) et `referenceId`. Le champ `outstandingAmount` de la facture est mis à jour à la soumission. Option `makeAutoPayment` sur la facture. Pas d'outil de lettrage à part, pas de lettrage différé.
- **Clôture** : **aucune**. Exercice défini par `fiscalYearStart/End` dans `AccountingSettings`, sans verrou de période, sans écriture de clôture ni à-nouveaux.
- **Analytique, budgets, immobilisations, produits constatés d'avance, relances, abonnements, rapprochement bancaire, SEPA** : **absents**.
- **Taxes** : `Tax` + `TaxDetail` (modèle de taxes par article), `TaxSummary`. Régional : **Inde** (GSTIN, rapports GSTR-1/GSTR-2 avec export) et Suisse (champs). Pas de déclaration française.
- **Multidevise** : par tiers. `Invoice.currency`, `exchangeRate`, `entryCurrency` (Party/Company), `baseGrandTotal`, taux récupérés en ligne (`models/exchangeRate.ts`). Pas de réévaluation.
- **France** : plan « France - Plan Comptable Général » livré (`fixtures/verified/fr.json`). Pas de FEC, pas de Factur-X, pas de plan associatif.
- **Audit** : pas d'historique des modifications. Seuls le statut soumis/annulé et la numérotation par `NumberSeries` sont présents.
- **Plan comptable** : `Account` avec `rootType` (Asset/Liability/Equity/Income/Expense) et `accountType` (Bank, Cash, Receivable, Payable, Tax, Fixed Asset, Depreciation, Stock…), arborescent via `isGroup`.

### B.3 Fonctionnalités par domaine

- **Comptabilité** : plan par pays, écritures, grand livre, balance, bilan, compte de résultat, tableau de bord, exports CSV/JSON des rapports.
- **Ventes et achats** : devis, factures, factures d'achat, avoirs et retours (`returnAgainst`, `isReturned`), paiements partiels, remises, listes de prix, règles de prix, coupons, programme de fidélité, prospects (Lead), demandes d'articles.
- **Point de vente** : profils POS, ouverture et fermeture de caisse avec comptage des espèces, codes-barres, ticket.
- **Stock** : emplacements, réceptions et expéditions, lots, numéros de série, valorisation FIFO, `StockLedgerEntry`.
- **Personnalisation** : **Template Builder** (éditeur de modèles d'impression Vue/HTML avec CodeMirror), **Customize Form et champs personnalisés**, séries de numérotation.
- **Import** : **Import Wizard** générique en CSV pour tous les doctypes (tiers, articles, écritures…).
- **Intégration** : synchronisation avec ERPNext (`ERPNextSyncSettings`, files de synchronisation).
- **Plateforme** : hors ligne, une base SQLite par société, multiplateforme (Windows, macOS, Linux), mono-utilisateur dans la version de bureau. Le successeur web est multi-utilisateur avec des droits.

### B.4 Écarts par rapport à Lyvre

Frappe Books est **nettement moins riche que Lyvre** sur la comptabilité associative et française : pas de clôture, de FEC, de banque, d'analytique ni de budget. Écarts pertinents :

| Fonctionnalité | Intérêt pour une association ou une SCI | Source |
|---|---|---|
| **Annulation par écritures inverses** (`reverted`/`reverts`) au lieu d'une suppression, pour les documents soumis. Modèle simple à imiter, mais Lyvre devrait éviter le `afterDelete` qui efface la trace | Traçabilité minimale : une facture annulée laisse sa contre-passation dans le GL | https://github.com/frappe/books/blob/master/models/Transactional/LedgerPosting.ts |
| **Paiement alloué à n factures avec écart passé en perte** (`writeoff`) + `outstandingAmount` tenu sur la facture | Solder une facture de loyer ou de prestation à quelques centimes près sans écriture manuelle | https://github.com/frappe/books/blob/master/schemas/app/Payment.json |
| **Template Builder** : éditeur WYSIWYG de modèles d'impression | Personnaliser factures, quittances et reçus sans développeur | https://github.com/frappe/books/tree/master/src/pages/TemplateBuilder |
| **Import Wizard générique** (CSV vers n'importe quel objet) | Reprise des adhérents, tiers, articles ou soldes d'ouverture depuis un tableur | https://github.com/frappe/books/blob/master/src/pages/ImportWizard.vue |
| **Champs personnalisés** (CustomField/CustomForm) | Ajouter un n° d'adhérent, un lot ou un financeur sans modifier le code | https://github.com/frappe/books/tree/master/schemas/core |
| **Point de vente avec ouverture et fermeture de caisse** (comptage des espèces) | Buvette, billetterie sur place, boutique d'asso ; Lyvre passe par l'import Odoo POS | https://frappe.io/books |
| **Stock avec lots et péremption** | Épicerie solidaire, recyclerie, banque alimentaire | https://frappe.io/books |
| **Fonctionnement hors ligne** (une base SQLite locale par société) | Trésorier sans connexion fiable ; sans intérêt pour un usage web multi-utilisateur | https://github.com/frappe/books |

**À retenir** : le dépôt est **archivé depuis le 02/10/2026**. Ce n'est pas une cible de référence durable. Son successeur `frappe-books` reste orienté TPE avec la TVA indienne. Il peut servir d'**exemple d'architecture légère** (schémas JSON, ledger avec reverts, monnaie en virgule fixe via pesa, SQLite) proche de celle de Lyvre, mais il n'apporte presque rien sur le plan comptable que Lyvre n'ait déjà.

---

## Sources principales
- Dépôt Dokos : https://gitlab.com/dokos/dokos (branche develop, commit 889b6b3)
- Projets Dokos : https://gitlab.com/dokos
- Doc Dokos : https://doc.dokos.io/fr/v5/dokos/comptabilite, …/rapprochement-bancaire, …/prelevement-sepa, …/import-fec, …/dimensions-comptables
- Page produit : https://www.dokos.io/features/comptabilite
- Frappe Books : https://github.com/frappe/books (archivé), https://github.com/frappe/books/issues/1566, https://github.com/frappe/frappe-books, https://frappe.io/books
