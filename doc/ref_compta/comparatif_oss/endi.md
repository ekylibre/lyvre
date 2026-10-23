# enDI / CAERP : analyse comparative pour Lyvre

*Recherche du 23/10/2026. Sources consultées : https://endi.coop/offre ; https://doc.endi.coop/ (sommaire Scenari extrait du JSON `outlineSource`) et plusieurs pages `co/*.html` ; code source https://framagit.org/caerp/caerp (clone `--depth 1`, dernier commit du 15/10/2026, lu sans être exécuté) ; démo https://demo.endi.coop/admin.*

**Démo** : https://demo.endi.coop/admin redirige vers un SSO Keycloak (`/sso/realms/demoendi/...openid-connect/auth`), sans identifiants publics. Elle n'a donc pas été explorée.

**Positionnement** : CAERP est le progiciel libre des CAE (coopératives d'activité et d'emploi). enDI en est la distribution SaaS, éditée par Coopérer pour Entreprendre. Le même code alimente d'autres marques : `endi_setup.json`, `gescoop_setup.json`, `moogli-erp_setup.json`. Ce n'est **pas un logiciel de comptabilité**. C'est une gestion commerciale et RH multi-« enseignes » (une enseigne par entrepreneur salarié), qui **exporte des écritures vers un logiciel comptable externe** puis **réimporte le grand livre** pour produire des états de gestion par enseigne.

---

## 1. Technologies

| Élément | Constat (source : dépôt) |
|---|---|
| Langage | Python 3 (`python_requires>=3.7`) |
| Framework web | **Pyramid 2.0** (pyramid-tm, pyramid-layout, pyramid-services, pyramid-mailer, pyramid-celery) |
| ORM / migrations | **SQLAlchemy 1.4.50** + zope.sqlalchemy, **Alembic 1.13** |
| Formulaires | **Colander / Deform 2** + ColanderAlchemy : les métadonnées de formulaire sont déclarées dans `info={"colanderalchemy": ...}` sur chaque colonne |
| Templates | Mako + Chameleon (rendu serveur) |
| Base de données | **MariaDB/MySQL** (`mysqlclient`, `mariadb:10.5` dans `compose.yaml`) |
| Tâches asynchrones | **Celery 5.4 + Redis** (exports, imports comptables, PDP, mails, RGPD) |
| Front | Hybride : ancien JS **Backbone/Marionette + jQuery** (webpack, `js_sources/`) et nouveau front **Vue 3.5 + Pinia + Vite** (`vue_sources/`), en îlots dans les pages serveur |
| PDF | **WeasyPrint 66**, **factur-x 2.3** (embarquement XML CII dans le PDF) |
| Documents | Fusion documentaire ODT (champs de fusion) pour les documents commerciaux et RH |
| Licence | **GPL v3** (`LICENSE.txt`) ; l'offre parle de « Community Edition » gratuite |
| Déploiement | Paquet Python + Docker/compose (mariadb, redis), builds JS via docker-compose. SaaS enDI à 9 € HT par utilisateur actif et par mois, 10 utilisateurs minimum, engagement de 24 mois, hébergement en France ou en Allemagne, 3 mises à jour par an |
| Plugins | `plugins/sap` (attestations fiscales des services à la personne), `plugins/sap_urssaf3p` (avance immédiate Urssaf, API tierce prestation), `plugins/solo` |

Source : https://framagit.org/caerp/caerp (`requirements.txt`, `compose.yaml`, `vue_sources/package.json`) et https://endi.coop/offre

---

## 2. Méthodes et données comptables

### 2.1 Principe : pré-comptabilité, export puis remontée

1. **Génération d'écritures à l'export** (pas de journal interne). `caerp/compute/sage/*.py` contient des « BookEntryFactory » : `SageFacturation` (crédit HT par produit et compte de TVA, débit TTC au compte client), `SageRGInterne`, et des factories pour paiements, notes de dépenses, paiements de notes de dépenses, factures fournisseurs et leurs paiements. Chaque ligne existe en double, écriture générale et écriture analytique : le code analytique est le `code_compta` de l'enseigne.
2. **Writers par logiciel cible** (`caerp/export/`) : `sage.py`, `sage_generation_expert.py`, `cegid.py`, `cegid_tra.py`, `isacompta.py`, `isuite.py`, ainsi qu'un export générique tableur (`excel.py`, `ods.py`).
3. **Traçabilité des exports** : un drapeau `exported` sur `Invoice`, `CancelInvoice`, `BaseTaskPayment` et `SupplierInvoice`, deux drapeaux `purchase_exported` / `expense_exported` sur `ExpenseSheet`, et un journal `AccountingExportLogEntry`, décliné en `InvoiceAccountingExportLogEntry`, `PaymentAccountingExportLogEntry`, `ExpenseAccountingExportLogEntry`, `SupplierInvoiceAccountingExportLogEntry`, etc., qui conserve le fichier exporté et l'utilisateur. Les critères d'export disponibles sont : éléments non exportés, plage de numéros, période, identifiant, enseigne (https://doc.endi.coop/co/GestionEntreprise_3.html).
4. **Modules de contribution personnalisés** (`CustomInvoiceBookEntryModule`) : ce sont des lignes supplémentaires générées à l'export, calculées en pourcentage du HT (contribution à la CAE, assurance). Ils portent `compte_cg_debit`/`compte_cg_credit`, un `label_template` à variables (`{invoice.customer.label}`, `{invoice.official_number:.9}`), un `percentage` et un `is_provision`.
5. **Remontée comptable** (`AccountingOperationUpload` avec `filetype` ∈ `general_ledger`, `analytical_balance`, `synchronized_accounting`, déduplication par `md5sum`). Elle produit des `AccountingOperation` (`date`, `analytical_account`, `general_account`, `label`, `debit`, `credit`, `balance`, `company_id`). Des parseurs Celery existent pour **EBP, Cegid, Isacompta, iSuite, Quadra, Sage, Sage Génération Expert** (`caerp/celery/parsers/`). Une synchronisation par API (`celery/tasks/accounting_api.py`) envoie un mail de succès ou d'échec.
6. **États de gestion calculés depuis le grand livre remonté** : `TreasuryMeasureGrid/Type/Measure`, `IncomeStatementMeasure*` et `BalanceSheetMeasure*` (actif/passif). Chaque type de mesure est défini par un **`account_prefix`** (préfixes de comptes), une catégorie, `is_total`/`total_type` (formules de totaux) et `invert_default_cd_or_dc`. L'admin configure librement la grille du compte de résultat et de la trésorerie ; chaque enseigne voit sa trésorerie, son compte de résultat annuel exportable en tableur et son grand livre (`views/accounting/company_general_ledger.py`, libellés de comptes personnalisables via `GeneralLedgerAccountWording`). Source : https://doc.endi.coop/co/EtatGestion.html et https://doc.endi.coop/co/GestionEntreprise_4.html
7. **Clôture** : `AccountingClosure` se réduit à `year`, `active` (clos) et `datetime`. C'est un simple verrou d'exercice ; la clôture réelle se fait dans le logiciel comptable.

### 2.2 Ventes

- **Modèle commun `Task`** (devis `Estimation`, facture `Invoice`, avoir `CancelInvoice`, ainsi que `InternalEstimation`/`InternalInvoice` pour la facturation **entre enseignes**). Champs notables : `official_number` (attribué **à la validation**), `internal_number`, `legacy_number`, `mode` (HT/TTC), `display_units`, `display_ttc`, `payment_conditions`, `start_date`/`end_date` (période de prestation), `workplace`, `insurance_id`, `pdf_file_hash` (PDF scellé), `frozen_settings`, `auto_validated`, `business_id`, `business_type_id`.
- **Lignes** : `TaskLineGroup` (chapitres avec `display_details`), `TaskLine` (`cost`, `quantity`, `unity`, `tva_id`, `product_id`, `date`), `DiscountLine` (remises par taux de TVA), `PostTTCLine` (lignes après TTC, par exemple une retenue).
- **Acomptes** : `Invoice.is_deposit`, avec un échéancier rattaché à l'affaire, `BusinessPaymentDeadline` (`deposit`, `amount_ttc`, `amount_ht`, `date`, `invoiced`, `invoice_id`, `estimation_id`). Les factures d'acompte et de solde sont générées depuis l'échéancier du devis.
- **Facturation à l'avancement / de situation** : `Business.invoicing_mode` ∈ `classic` / `progress`. Les modèles `ProgressInvoicingPlan`, `ProgressInvoicingChapter`, `ProgressInvoicingProduct/Work/WorkItem` portent `percentage` et `already_invoiced` par ligne de devis (https://doc.endi.coop/co/Facture_Avancement_Creer.html).
- **Études de prix** (`price_study/`) : chapitres, ouvrages (`work`, `work_item`), remises, coefficient de frais généraux (`Company.general_overhead`) et taux de marge (`margin_rate`), utiles pour le bâtiment.
- **Encaissements** : `Payment` (`mode`, `bank_id`, `issuer`, `customer_bank_id`, `check_number`, `bank_remittance_id`, `exported`) et **remises en banque** `BankRemittance` (`payment_mode`, `bank_id`, `remittance_date`, `closed`), avec bordereau exportable (https://doc.endi.coop/co/GestionEntreprise_2.html). Les corrections passent par des contre-écritures, sans modification directe (https://doc.endi.coop/co/Facture.html).
- **Numérotation** (`models/services/official_number.py`, `sequence_number.py`) : gabarit configurable avec `{YYYY}`, `{YY}`, `{MM}`, `{SEQGLOBAL}`, `{SEQYEAR}`, `{SEQMONTH}` et `{SEQMONTHANA}` (séquence mensuelle par code analytique d'enseigne). Les séquences sont `GlobalSequence`, `YearSequence`, `MonthSequence` et `MonthCompanySequence`. L'unicité du gabarit est contrôlée.
- **Mentions** configurables par type d'affaire (`task/mentions.py`, `project/mentions.py`), CGV par enseigne (`Company.cgv`, `cgv_pdf_id`).
- **Factur-X** : XML CII généré et embarqué à la création du PDF (`views/task/pdf_rendering_service.py`, `_get_facturx_xml`, `_embed_facturx`, `flavor="factur-x"`).
- **Facturation électronique (réception)** : intégration **SuperPDP** (`utils/superpdp/api.py`, `models/pdp/in_invoice.py`). `PdpInInvoice` (`remote_number`, `reception_date`, `ht/tva/ttc`, `amount_due_for_payment`, `pdp_status`, `workflow_type` B2B…), puis **affectation et ventilation** (`PdpInInvoiceAssignment` : `amount`, `amount_to_pay`, `status`, `partial`, `lines`, `company_id`, `supplier_id`), génération d'une `SupplierInvoice`, et **renvoi des statuts de cycle de vie** (`create_in_invoice_event`). Annuaire : `Company.peppol_id`, `ppf_id`, `pdp_*_directory_id`, recherche dans l'annuaire PPF. L'**émission** vers la PDP n'apparaît pas dans `utils/superpdp/api.py` à ce jour : non vérifié.
- **Services à la personne** : attestations fiscales annuelles (`SAPAttestation`) et **avance immédiate Urssaf** (`URSSAFPaymentRequest`, `UrssafCustomerData`).

### 2.3 Achats et dépenses

- **Notes de dépenses** (`ExpenseSheet` : `month`, `year`, `title`, `justified`, `purchase_exported`, `expense_exported`, `user_id`, `company_id`). Les lignes `ExpenseLine` portent `ht`, `tva`, `manual_ttc`, `supplier_id`, `invoice_number`, `justified` et le lien à une affaire. Il existe aussi `ExpenseKmLine` (`start`, `end`, `km`, barème `ExpenseKmType.amount` par `year`) et `ExpenseTelType` (forfait téléphone en %). Types de dépense : `ExpenseType` (`code`, `code_tva`, `compte_tva`, `tva_on_margin`, `compte_produit_tva_on_margin`, `contribution`, `category` frais/achats). Les justificatifs sont attachés, liés à une ligne puis **validés par l'entreprise** (https://doc.endi.coop/co/Depense.html).
- **Commandes fournisseurs** (`SupplierOrder`, `SupplierOrderLine`) converties en **factures fournisseurs** (`SupplierInvoice` : `remote_invoice_number`, `supplier_id`, `payer_id`, `cae_percentage` = part payée par la structure plutôt que par l'entrepreneur, `exported`, `pdp_in_invoice_id`). Ventilation d'une facture fournisseur sur plusieurs enseignes.
- **Paiements groupés par virement SEPA** (`models/sepa.py`) : `ExpenseSepaWaitingPayment`, `SupplierInvoiceSupplierSepaWaitingPayment` et `SupplierInvoiceUserSepaWaitingPayment` alimentent un `SepaCreditTransfer` (`execution_date`, `bank_account_id`, `status`, `reference`, `sepa_pain_version`, fichier pain.001 généré).

### 2.4 TVA, analytique, affaires

- **TVA** : `Tva` (`value`, `compte_cg`, `code`, `compte_a_payer`, `compte_client`, `mention`) et `Product` (sous-compte produit par taux : `compte_cg`, `tva_id`, `urssaf_code_nature`). TVA sur marge pour les agences de voyage et la vente d'occasion. Le logiciel ne prépare **aucune déclaration de TVA** : elle se fait dans la comptabilité externe.
- **Analytique** : un axe structurel, l'**enseigne** (`Company.code_compta`), avec des comptes clients et fournisseurs par enseigne (`general_customer_account`, `third_party_customer_account`, `general_supplier_account`…, en variantes `internal*`).
- **Dossiers / Affaires** : `Project` (dossier client) → `Phase` → `Business` (affaire : `status`, `business_type_id`, `invoicing_mode`). Les **types d'affaire** pilotent les mentions, les **pièces obligatoires** (`SaleFileRequirement`, `BusinessFileRequirementService`) et des **indicateurs** personnalisés (`CustomBusinessIndicator`). Notes de dépenses et achats sont rattachables à une affaire (`BusinessLinkedModelMixin`).

### 2.5 Workflows de validation

Statuts `draft → wait → valid / invalid` (`ALL_STATES` dans `task.py`), journalisés par `StatusLogEntry`. Le même cycle s'applique aux devis, factures, avoirs, notes de dépenses, commandes et factures fournisseurs (« demander la validation », « valider », « invalider », « repasser en brouillon »). La validation peut être automatique (`auto_validated`). Les pièces obligatoires bloquent la validation. Statuts de paiement : `PaidStatusHolderMixin`. Statuts d'affectation pour les factures PDP : `AssignationStatusHolderMixin`.

---

## 3. Fonctionnalités par domaine

- **Accompagnement** : rendez-vous (`Activity`, `ActivityType`, `ActivityMode`, `ActivityAction`, émargement `Attendance`), parcours d'entrepreneur (`CareerPath` : étapes, contrats, motifs de sortie), grilles de **compétences** avec échéances et échelles (https://doc.endi.coop/co/Accompagnement.html).
- **RH / gestion sociale** : dossier de données sociales (`UserDatas` : situation CAE, prescripteur, niveau d'études, PCS, zone, antenne, contrats), **congés** (`Holiday`), groupes et droits fins (`access_right.py`, `group.py`), SSO OIDC/OAuth2, RGPD (anonymisation, tâches `rgpd.py`).
- **Formation** : sessions et ateliers (`Workshop`, `Timeslot`, émargements, PDF de feuille de présence), données formateur (`TrainerDatas`), **BPF** (bilan pédagogique et financier : `business_bpf_data`, spécialités NSF, sources de financement).
- **Agenda / mémo / notifications** : mémos, notifications, rendez-vous.
- **Catalogue** : produits, ouvrages, catégories, produits formation (`sale_product/`), import et export.
- **Ventes** : clients (import et export CSV), dossiers et affaires, devis, factures, avoirs, acomptes, facturation à l'avancement, études de prix, facturation interne entre enseignes, encaissements, remises de chèques, export PDF en masse, récapitulatifs, fusion documentaire ODT.
- **Achats** : fournisseurs, commandes, factures fournisseurs, ventilation multi-enseignes, réception PDP, notes de dépenses (frais, kilométriques, téléphone), virements SEPA.
- **Trésorerie / comptabilité** : exports vers 6 logiciels, remontée du grand livre ou de la balance analytique, états de trésorerie, compte de résultat et bilan par enseigne, grand livre par enseigne, verrou de clôture.
- **Statistiques** : feuilles de statistiques sauvegardées (`StatisticSheet`, `StatisticEntry`, `StatisticCriterion`) sur les données sociales, une vingtaine de **requêtes prédéfinies** (`dataqueries/queries/` : CA analytique par période, porteurs actifs, achats non exportés, fournisseurs sans SIREN, contrats par période, frais kilométriques, BPF…), état « gestion commerciale » (CA prévisionnel / réalisé / écart).
- **Filières métier** : bâtiment, formation, services à la personne (attestations fiscales, avance immédiate Urssaf), agence de voyage et occasion (TVA sur marge).

---

## 4. Écarts vs Lyvre

*Rappel : enDI ne tient pas de comptabilité. Lyvre est bien plus complet sur le cœur comptable (partie double, journaux, balance, bilan, clôture complète, FEC, rapprochement bancaire). Les écarts ci-dessous portent sur la gestion commerciale, les achats et les processus.*

| # | Fonction enDI absente ou meilleure | Intérêt pour une association / SCI | Source |
|---|---|---|---|
| 1 | **Notes de dépenses** mensuelles par personne (frais réels, **indemnités kilométriques au barème annuel**, forfait téléphone), justificatifs liés à chaque ligne et validés, paiement de la note | Fort : remboursement des frais de bénévoles et de salariés, et base pour l'**abandon de frais en don** (reçu fiscal) | https://doc.endi.coop/co/Depense.html ; `caerp/models/expense/` |
| 2 | **Workflow de validation** brouillon → attente → validé / invalidé, avec historique des statuts, sur toutes les pièces | Moyen à fort : double contrôle trésorier/président avant émission ou paiement, traçabilité exigée par certains financeurs | https://doc.endi.coop/co/Depense_2.html ; `caerp/models/status.py` |
| 3 | **Factures d'acompte** et échéancier de paiement depuis le devis (`BusinessPaymentDeadline`, `is_deposit`) | Moyen : prestations facturées en plusieurs fois (formations, événements, location de salle) | https://doc.endi.coop/co/Facture.html ; `caerp/models/project/business.py` |
| 4 | **Facturation à l'avancement / de situation** (pourcentage par ligne de devis, déjà facturé) | Faible pour une association, faible à moyen pour une SCI qui refacture des travaux | https://doc.endi.coop/co/Facture_Avancement_Creer.html |
| 5 | **Remises de chèques en banque** (bordereau, clôture et réouverture d'une remise) | Fort : les associations encaissent beaucoup de chèques (cotisations, dons). Le bordereau facilite le rapprochement d'une ligne de banque groupée | https://doc.endi.coop/co/GestionEntreprise_2.html ; `BankRemittance` |
| 6 | **Virements SEPA groupés (pain.001)** pour payer notes de dépenses et factures fournisseurs | Moyen : paiement en lot des remboursements de bénévoles et des fournisseurs, utile si la banque n'est pas Qonto | `caerp/models/sepa.py` |
| 7 | **Réception de factures électroniques via une PDP** (SuperPDP), annuaire PPF/Peppol, affectation et ventilation, **renvoi des statuts de cycle de vie** | Fort à l'horizon 2026-2027 : toute structure assujettie, SCI à la TVA ou association à activité lucrative, doit pouvoir recevoir. Lyvre lit le Factur-X déposé mais n'est raccordé à aucune PDP | `caerp/utils/superpdp/api.py` ; `caerp/models/pdp/in_invoice.py` |
| 8 | **Commandes fournisseurs** converties en factures, et **ventilation d'une facture fournisseur** sur plusieurs entités | Faible à moyen : engagement de dépenses par projet. La ventilation ressemble au découpage analytique de Lyvre, mais en amont | https://doc.endi.coop/co/Achat.html |
| 9 | **Pièces obligatoires par type d'affaire**, bloquantes avant validation (`SaleFileRequirement`) | Moyen : justificatifs exigés par les subventions (convention, devis signé, feuille d'émargement) | `caerp/models/indicators.py`, `caerp/models/services/sale_file_requirements.py` |
| 10 | **Numérotation configurable par gabarit** (`{YYYY}-{SEQYEAR}`, séquence par mois ou par code analytique) | Faible à moyen : reprise d'une numérotation existante, séries distinctes par activité | `caerp/models/services/official_number.py` |
| 11 | **Exports vers logiciels comptables tiers** (Sage, Cegid, Isacompta, iSuite, Sage GE) avec **journal des exports** et drapeau « exporté » | Moyen : le FEC de Lyvre couvre l'expert-comptable, mais un journal d'export (qui, quand, quoi) éviterait les doubles envois | https://doc.endi.coop/co/GestionEntreprise_3.html ; `caerp/models/export/accounting_export_log.py` |
| 12 | **Lignes de contribution automatiques** (pourcentage du HT, gabarit de libellé, mode provision) | Faible : utile pour une fédération qui prélève une quote-part, ou pour les frais de gestion refacturés d'une SCI | `caerp/models/accounting/bookeeping.py` |
| 13 | **Grilles d'états paramétrables par préfixes de comptes** (trésorerie, compte de résultat, bilan) avec totaux configurables | Moyen : soldes intermédiaires de gestion ou tableaux de bord pour le CA ou les financeurs, définis par l'utilisateur sans développement | https://doc.endi.coop/co/EtatGestion_1.html ; `caerp/models/accounting/base.py` |
| 14 | **Émargements et sessions de formation/ateliers**, **BPF** | Moyen pour une association organisme de formation (déclaration BPF annuelle) ou qui organise des ateliers (preuve de réalisation pour les subventions) | https://doc.endi.coop/co/Atelier.html ; `caerp/models/training/bpf.py` |
| 15 | **Services à la personne** : attestations fiscales annuelles et **avance immédiate Urssaf** | Niche : associations SAP agréées (aide à domicile, soutien scolaire) | `caerp/plugins/sap`, `caerp/plugins/sap_urssaf3p` |
| 16 | **Requêtes / statistiques prédéfinies et feuilles de statistiques sauvegardées** (« fournisseurs sans SIREN », « achats non exportés »…) | Moyen : contrôles qualité des données avant clôture, reporting d'activité | `caerp/dataqueries/queries/` ; `caerp/models/statistics.py` |
| 17 | **Facturation interne entre entités** (devis et factures internes, comptes `internal*`) | Faible à moyen pour une installation multi-structures (association et SCI liées, refacturation de loyers ou de personnel) | https://doc.endi.coop/co/FactureInterne.html |
| 18 | **Fusion documentaire ODT** (modèles Writer avec champs de fusion) | Faible à moyen : courriers et conventions personnalisés aux couleurs de la structure | https://doc.endi.coop/co/FusionDocCom.html |
| 19 | **PDF de facture scellé** (`pdf_file_hash`) et encaissements corrigés uniquement par contre-passation (conformité loi de finances 2016) | Moyen : à vérifier dans Lyvre (immutabilité des pièces émises) | https://doc.endi.coop/co/Facture.html ; https://endi.coop/offre |

**Points où Lyvre est nettement en avance** : vraie comptabilité en partie double, rapprochement bancaire et synchronisation Qonto, clôture complète avec écritures d'inventaire, FEC, PCG associatif et SCI, dons et reçus Cerfa, bénévolat, budget et prévisionnel. enDI délègue tout cela à un logiciel externe.
