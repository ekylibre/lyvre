# Ekylibre et Lexicon : ce que Lyvre peut reprendre pour la comptabilité agricole

Audit du 03/11/2026. Lecture seule, aucun dépôt n'a été modifié.

## 0. Sources examinées et constat préalable

- Les dépôts `ekylibre-sas` et `ekylibre-old` ne contiennent pas le code Rails. On y trouve le site Astro ekylibre.com, la documentation Clic&Farm, WordPress et github.io. Le code a été lu sur GitHub avec `gh api` :
  - `ekylibre/ekylibre`, branche `main`, AGPL-3.0, poussé le 25/10/2026 ;
  - `ekylibre/onoma`, branche `master`, AGPL-3.0 : c'est le dépôt des nomenclatures, avec un fichier unique `db/reference.xml` de 1 Mo et 61 nomenclatures.
- Lexicon a été lu dans les dépôts locaux `lexicon` (pipeline Ruby, MIT), `lexicon-rest-api` (Bun/TS, site et API) et `lexicon_mcp` (démonstrateur Gradio).
- Vérifications en ligne : `https://lexicon.osfarm.org/catalog.json`, `/catalog/chart_of_accounts`, `/production/productions.json`, `POST /mcp tools/list`, et la doc utilisateur `https://ekylibre.org/fr/user-doc/chapitre5/`.
- Lyvre dispose déjà de `app/services/ekylibre/` (importer, mapping, reader, checks, report) pour reprendre des dumps Ekylibre, et de la méthode days360.

---

## 1. Ekylibre : ce que fait l'ERP en comptabilité agricole

### 1.1 Plans comptables et nomenclature des comptes

**Fichier clé : `onoma/db/reference.xml`.** Les nomenclatures utiles à la compta sont les suivantes.

- **`accounting_systems`**
  - Valeurs : `fr_pcg82`, `fr_pcga` (ancien PCG agricole), `fr_pcg2019`, `fr_pcg2023`, `fr_pcga2023` et `pt_snc`.
- **`accounts`**
  - 601 comptes « à usage », identifiés par une clé sémantique : `fertilizer_expenses`, `short_cycle_cultivation_advances`, `adult_animal_assets`, etc.
  - Chaque compte porte un numéro par plan (`fr_pcga2023="60111"`) et des propriétés `centralizing`/`debtor`. La valeur `NONE` signifie que le compte n'existe pas dans le plan.
  - Le code ne manipule jamais un numéro, toujours un usage : `Account.find_or_import_from_nomenclature(:vat_to_pay)`.
  - **85 usages diffèrent entre `fr_pcga2023` et `fr_pcg2023`.** Ce sont les spécificités agricoles :
    - stocks d'approvisionnements détaillés en `31111` à `31116` (engrais, semences, phytos, aliments, produits vétérinaires, reproduction) ;
    - stocks animaux `3112` (cycle long) et `3113` (cycle court) ;
    - avances aux cultures, à cycle long (`331`, `311411` à `311415`) comme à cycle court (`31151`, `311511` à `311515`) ;
    - en-cours et produits `33x` et `35x` ;
    - achats `60111` à `60117` et variations `603111` à `603116` ;
    - `6051` (façons), `60615` (irrigation), `6451` (MSA exploitant), `657` (valeur comptable des animaux immobilisés) ;
    - `7041` (travaux à façon), `7042` (intégration), `7121`/`7122` (production immobilisée animaux) ;
    - `713553`/`713554` (variations d'inventaire des végétaux) ;
    - `741` (remboursement forfaitaire de TVA, soit « vat_compensations »), `745` (subventions), `757` (cession d'animaux) ;
    - `172`, `2071`, `2672x` (parts de coopératives et CUMA), `2723` ;
    - `4552`/`45582` (comptes d'associés bloqués), `461`/`497` (caisse de péréquation), `4952` à `4954` (associés GAEC et GIE).
- **`fiscal_positions`**
  - Valeurs : `fr_ba_ir`, `fr_ba_is` (associés à `fr_pcga2023`), `fr_bic_*` et `fr_bnc_*` (associés à `fr_pcg2023`).
  - **C'est le régime fiscal qui choisit le plan** : BA donne le PCGA, BIC et BNC donnent le PCG.
- **`tax_natures` et `taxes`**
  - Chaque nature porte ses comptes de collecte et de déduction (`collect_account`, `deduction_account`, `fixed_asset_deduction_account`) et un suffixe.
  - Les taux français sont datés : 2,1 %, 5,5 %, 10 % depuis 2014, 20 %, ainsi que l'historique 19,6 %, 7 %, etc.
  - Il n'y a **pas de taux forfaitaire agricole** (4,43 % ou 5,59 %).
- **`activity_families`**
  - Valeurs : `plant_farming`, `animal_farming`, `vine_farming`, `processing`, `service_delivering`, etc.
- **`document_natures`**
  - Exemples : `fr_pcga_balance_sheet`, `fr_pcga_profit_and_loss_statement`, `exchange_accountancy_file_fr`.

**Choix du plan selon l'exercice.**
- `app/models/financial_year.rb` porte `accounting_system`.
- Un changement de plan relance `Accountancy::AccountingSystemChangingJob`, implémenté dans `app/services/accountancy/accounting_system_changing.rb`.
- La normalisation des numéros (8 à 14 chiffres, radicaux 401/411 en 4011/4111) est dans `app/services/accountancy/account_number_normalizer.rb`.

### 1.2 Journaux

- Fichier : `app/models/journal.rb`.
- Natures : `sales`, `purchases`, `fixed_assets`, `bank`, `forward`, `various`, `cash`, `stocks`, `closure`, `result`, `payslip`.
- Dix journaux sont créés au premier lancement. Les journaux Achats, Banque, Caisse et Ventes ne peuvent pas être supprimés. Un code fait 4 caractères au maximum.
- Un journal OD peut être rattaché à un `accountant`, c'est-à-dire au cabinet comptable, pour les échanges.

### 1.3 TVA

- **Fichiers** : `app/models/tax_declaration.rb`, `tax_declaration_item.rb`, `tax_declaration_item_part.rb`, `tax_payment.rb`, et les éditions `app/services/printers/vat_register_printer.rb` et `pending_vat_register_printer.rb`.
- **Paramétrage, porté par l'exercice** :
  - `tax_declaration_mode` vaut `debit`, `payment` ou `none` ;
  - `tax_declaration_frequency` vaut `monthly`, `quaterly`, `yearly` ou `none`.
- **Cycle de vie** : la déclaration passe de brouillon à validée, puis envoyée. Elle se calcule à partir des lignes d'écritures non déclarées (`undeclared_tax_journal_entry_items`).
- **Écriture produite** (bookkeep) :
  - débit de la TVA collectée, crédit de la TVA déductible (biens et services, immobilisations, intracommunautaire) ;
  - le solde va en 44567 (crédit à reporter) ou en 44551 (TVA à décaisser) ;
  - l'arrondi à l'euro va en 658 ou 758.
- **Ce qui manque** :
  - pas de cerfa CA3 ni CA12A ;
  - pas de télédéclaration ;
  - pas de régime du remboursement forfaitaire agricole (RFA) ;
  - pas de CA12A agricole avec acomptes ;
  - pas de gestion de l'option RSA ou RNA.
  - Lyvre est déjà plus avancé sur ce point (CA3 dans `data/ca3`).

### 1.4 Inventaires, stocks, avances aux cultures

- **Écriture d'inventaire** (`app/models/inventory.rb`, `app/models/bookkeepers/inventory_bookkeeper.rb`, inventaire physique, stock non permanent) :
  - pour chaque article stockable, elle compare le solde du compte de stock 3x depuis le début de l'exercice à la valeur inventoriée ;
  - elle passe l'écart en débit 3x / crédit 603x ou 71x ;
  - elle lève une erreur si le stock est négatif.
- **Valorisation** : c'est la valeur saisie par ligne (`actual_pretax_stock_amount`). **Il n'y a ni méthode de valorisation des animaux (coût de production, prix de marché −20 %, barème), ni calcul automatique des avances aux cultures.** Les avances (comptes 3114x et 3115x) ne sont que des comptes de stock alimentés par l'inventaire.
- **Stock permanent** (option « stock permanent ») : il est alimenté par `reception_bookkeeper.rb`, `shipment_bookkeeper.rb` et `parcel_bookkeeper.rb`.
- **Correspondance article → comptes** : `app/models/product_nature_category.rb` (`stock_account`, `stock_movement_account`, `charge_account`, `product_account`, `fixed_asset_*`). Les catégories de référence viennent de Lexicon, avec `master_variant_categories` (voir 2.3).
- **Éditions** : `printers/inventory_sheet_printer.rb`.

### 1.5 Immobilisations et dépréciations

- **Fichiers** : `app/models/fixed_asset.rb`, `fixed_asset_depreciation.rb`, `app/services/fixed_asset_depreciator.rb`, `app/services/fixed_asset/transitions/{start_up,sell,scrap,stand_by}.rb` et `app/models/bookkeepers/fixed_asset_*_bookkeeper.rb`.
- **Méthodes** : linéaire, dégressive (`depreciation_fiscal_coefficient`) ou aucune. La période est mensuelle, trimestrielle ou annuelle.
- **États** : brouillon, en attente, en service, vendue, mise au rebut. Il y a un compte d'attente (`waiting_asset_account`) et un compte d'imputation spéciale.
- **Spécificités agricoles** :
  - animaux reproducteurs immobilisés (241 / 2841, `657`, `7122`, `757`) ;
  - plantations pérennes (246, `sustainables_plants_assets`) ;
  - dépréciation des biens vivants (`294`, `68164`).
  - Dans la doc, les dotations sont affectables à une activité ou réparties au prorata de la marge brute.
- **Éditions** :
  - `printers/fixed_asset_registry_printer.rb` ;
  - `by_account_fixed_asset_registry_printer.rb` ;
  - `gain_and_loss_fixed_asset_registry_printer.rb`, pour les plus et moins-values ;
  - `loan_registry_printer.rb`, qui porte sur les emprunts (`app/models/loan.rb`, `loan_repayment.rb`).

### 1.6 Analytique : activités, productions, campagnes, marges

- **Modèles** : `app/models/activity.rb`, `activity_production.rb`, `campaign.rb`, `activity_budget(_item).rb`, `activity_distribution.rb`, `intervention_costing.rb` et `activity_productions_interventions_cost.rb`.
- **Fonctionnement d'une activité** :
  - une activité a une famille, une nature `main`, `auxiliary` ou `standalone`, et un cycle `annual` ou `perennial` ;
  - les activités auxiliaires sont réparties sur les principales via `distributions` (pourcentages normalisés à 100), avec une clé `gross_margin`, `percentage` ou `equipment_intervention_duration` ;
  - un champ `isacompta_analytic_code` de 2 caractères permet l'export analytique Isacompta.
- **Axes analytiques des lignes d'écriture** : `journal_entry_items` porte `activity_budget_id` (activité × campagne), `project_budget_id`, `equipment_id`, `team_id` et `variant_id`.
- **Coûts** : `app/services/activities/costs_calculation.rb` et `activity_productions/costs_calculation.rb` agrègent les coûts d'interventions (intrants, main-d'œuvre, matériel, réceptions) pondérés par `imputation_ratio`. Les éditions sont `printers/activity_cost_printer.rb` et `planned_budget_printer.rb`.
- **Budgets prévisionnels** par activité : `app/models/lexicon/master_budget.rb`, qui s'appuie sur le jeu Lexicon `budgets`.

### 1.7 Aides PAC

- **Fichiers** : `app/models/cap_statement.rb` (campagne, n° PACAGE, SIRET), `cap_islet.rb`, `cap_land_parcel.rb` et `cap_neutral_area.rb`.
- **Imports Telepac** : `app/exchangers/telepac/v2015 … v2025/cap_statements_exchanger.rb`. Ils lisent les îlots, les parcelles et les SNA de la déclaration de surfaces.
- **Ce qui manque** : pas de suivi comptable des aides (DPB, écorégime, aides couplées, ICHN, MAEC). Seul le compte 74/745 est mappé. La déclaration PAC sert à l'assolement, pas à la compta.

### 1.8 États et clôture

- **Éditions** (`app/services/printers/`) :
  - `balance_sheet_printer.rb` et `short_balance_sheet_printer.rb` ;
  - `income_statement_printer.rb` ;
  - `trial_balance_printer.rb` (balance), avec `app/services/accountancy/trial_balance_calculator.rb` ;
  - `general_ledger_printer.rb`, `general_journal_printer.rb`, `journal_ledger_printer.rb` (journal centralisateur) ;
  - `account_journal_entry_sheet_printer.rb`.
- **Correspondance comptes → postes, la ressource la plus réutilisable** : `config/accountancy/accountancy_mandatory_documents_fr_pcga2023.yml`, 257 lignes. Il existe aussi des variantes `fr_pcga`, `fr_pcg82`, `fr_pcg2019` et `fr_pcg2023`.
  - Pour chaque poste du compte de résultat, des ratios et du bilan, le fichier donne une formule de comptes. Exemples :
    - `animal_sales: '704 756 C, - 7094'` ;
    - `inventory_variations: '- 712 713'` ;
    - `subsidies: '74 C'`.
  - Il fournit aussi des ratios agricoles : production de l'exercice, valeur ajoutée, `operating_margin` (EBE incluant les subventions 742 à 745).
  - Le calcul est fait par `app/services/accountancy_computation.rb` et `economic_accountancy_computation.rb`.
- **Clôture** :
  - `app/services/financial_year_close.rb` et `financial_year_locker.rb` ;
  - archives ZIP pré- et post-clôture signées : `financial_year_archive.rb` et `lib/ekylibre/document_management/` ;
  - au plus deux exercices ouverts, de 12 mois ;
  - des contrôles bloquants ou de vigilance, dans les vues `backend/financial_years/close`.
- **Ce qui manque** : pas de liasse fiscale BA (2139, 2143 à 2146), ni de 2033/2050 automatisée.

### 1.9 Exports, échanges avec l'expert-comptable, imports

- **FEC**
  - `app/concepts/fec/` contient `exporter/{csv,xml}.rb`, les validateurs XSD `A47A-I-VII-1`, `VIII-3`, `VIII-5` et `VIII-7`, des notices PDF par régime et `check/journal_entry.rb`.
  - Le format est choisi selon le régime fiscal et le mode de comptabilité, dans `FinancialYear#fec_format` :
    - BA-IR en trésorerie ;
    - BNC-IR en trésorerie ;
    - BA/BNC-IR en engagement ;
    - « all ».
  - L'écriture du fichier est dans `app/services/financial_year_exchanges/fec_txt_export.rb`, `fec_xml_export.rb` et `csv_export.rb`.
- **Échanges comptables** (`app/models/financial_year_exchange.rb`)
  - Une période est ouverte et verrouillée, exportée en CSV ou FEC, réimportée en CSV corrigé, notifiée par mail au cabinet, puis clôturée.
  - Il existe un format Isacompta, avec export analytique.
- **Imports d'écritures** (`app/exchangers/`) :
  - FEC des logiciels agricoles concurrents : `isagri/isacompta/{fec_txt,journal_entries,fixed_assets,export}_exchanger.rb`, `agrigest/`, `quadra/`, `sage/coala`, `sage/i_seven`, `acom/`, `odicom/`, `bordeaux_sciences_agro/istea/` (balance et FEC), `listo/od_txt` ;
  - paie : `isagri/isapaye/` ;
  - EDI : `ebp/edi_exchanger.rb`.
  - **Ce sont des références utiles pour importer les FEC des cabinets agricoles.**
- **Banque** : CFONB (`app/services/accountancy/cfonb/`, avec la table des codes interbancaires `interbank_transaction_codes.csv`) et OFX.

### 1.10 Échéancier

- Il n'y a pas d'échéancier fiscal ou social agricole (MSA, TVA, IR). On trouve seulement l'échéancier des emprunts (`loan_repayment`), les paiements fournisseurs (`outgoing_payment_list`) et une fréquence de paiement par catégorie d'article (`payment_frequency_*`).

---

## 2. Lexicon : jeux de données utiles

### 2.1 Accès

- **Site et API** : `https://lexicon.osfarm.org`. Chaque page existe en HTML, JSON, CSV et GeoJSON selon l'extension, par exemple `/production/productions.json`. Le JSON est servi en `text/plain`.
  - Pagination : 150 lignes par page.
  - Accès anonyme : limité à 30 requêtes par fenêtre (en-têtes `RateLimit-*`).
  - Accès avec clé (`Authorization: Bearer lex_…`) : réservé aux membres de l'association OSFarm.
  - CORS ouvert (`*`) sur les données.
- **Catalogue** :
  - `https://lexicon.osfarm.org/catalog.json` recense 54 jeux, dont 46 ouverts et 8 réservés ;
  - `/catalog/<nom>` donne le détail d'un jeu ;
  - les paquets téléchargeables sont à `https://lexicon-packages.osfarm.org/<nom>/<version>/` (exemple : `chart_of_accounts/2026.10.03.1/`).
- **MCP** : serveur sans état à `POST https://lexicon.osfarm.org/mcp`, vérifié en ligne.
  - Outils : `list_datasets`, `describe_dataset`, `list_resources`, `read_resource`, `get_parcel`, `get_crop_history`, `get_crop_figures` (rendements et prix par département), `get_input_price`, `search_phytosanitary_products`, `get_phytosanitary_purchases`, `get_commune`, `get_enterprise`, `search_rd_documents`, `get_rd_document`, `find_agricultural_trainings`.
  - Un assistant, « Duke », est disponible à `/tools/assistant` (Mistral).
  - `lexicon_mcp` est un démonstrateur Gradio plus ancien qui appelle l'API REST (`gradio_mcp_server.py`, `BASE_URL`).
- **Schéma** :
  - `lexicon/SCHEMA.md` décrit 30 sources et 56 tables, préfixées `master_*` (référentiels Ekylibre) ou `registered_*` (données officielles) ;
  - les sources de chaque jeu sont dans `lexicon/data/<jeu>/` (CSV, ODS), les sources de données dans `lexicon/lib/datasources/*.rb` (crédits et licence) ;
  - la liste des routes est dans `lexicon-rest-api/src/namespaces/`.
- **Licences** :
  - code Lexicon : MIT ;
  - référentiels Ekylibre (`master_*`) : CC-BY-SA 4.0, ce qui impose attribution et partage à l'identique pour une donnée dérivée ;
  - données publiques : Licence Ouverte 2.0 ;
  - exceptions : `rd_agri` en CC BY-NC-SA, `vine_varieties` en NC-BY-SA, AgroEDI propriétaire, et la mention « réutilisation avec attribution » (Cereapro, Germineo) pour les prix engrais, semences et phytos, réservés.

### 2.2 Jeux utiles à la comptabilité

| Jeu (table) | Contenu | Accès / licence | Usage Lyvre |
|---|---|---|---|
| `chart_of_accounts` (`master_chart_of_accounts`) | **1 595 comptes** libellés en français. Le CSV `lexicon/data/chart_of_accounts/chart_of_accounts - chart_of_accounts.csv` a les colonnes `name`, `label_fr`, `fr_pcg82`, `fr_pcga`, `fr_pcg2019`, `fr_pcg2023`. On compte 1 173 comptes PCGA, dont **806 propres au PCGA** (31/33/35, 6011 à 6018, 604x, 7091 à 7098, 246, 461, 452 GAEC…). La table servie n'expose que `fr_pcga` et `fr_pcg82`. **Pas de colonne `fr_pcga2023`** : elle n'existe que dans onoma. 824 lignes n'ont pas de `name`. | Ouvert, CC-BY-SA 4.0 | Base de `data/plan_comptable_agri.json` |
| `open_nomenclature` (`master_nomenclatures`) | Les 61 nomenclatures onoma (comptes, taxes, positions fiscales, familles d'activité) avec libellés multilingues et propriétés | Ouvert, CC-BY-SA | Correspondance usage → numéro PCGA 2023 |
| `variants` (`master_variant_categories`, 95 catégories) | Pour chaque catégorie d'article : comptes immobilisation, amortissement, dotation, charge, produit, stock et variation, plus `depreciation_percentage` et **`default_vat_rate`**. Exemples : engrais 20 %, eau d'irrigation 5,5 %, reproduction animale 10 %, animal reproducteur adulte 241/2841, 20 %/an | Ouvert, CC-BY-SA | Règles d'imputation et codes TVA par défaut (`rules.yml`) |
| `legal_positions` | Formes juridiques (EI, GAEC, EARL, SCEA…), avec code INSEE et positions fiscales admises (`fr_ba_ir`…) | Ouvert, CC-BY-SA | Choix plan, régime et FEC à la création d'une structure |
| `productions` (`master_productions`, `master_crop_production_cap_codes`, `…_cap_sna_codes`, `…_tfi_codes`, `master_production_yields`, `master_production_prices`) | 330 productions végétales et 54 animales (famille d'activité, espèce, cycle). **Codes cultures PAC 2017 à 2026** (209 codes en 2026, catégorie TA/PP…). SNA. Rendements par département. Prix (MATIF, lait, viande par région et par mois) | Ouvert, CC-BY-SA. Pages `/production/productions`, `/production/prices` | Axes analytiques « production », valorisation des stocks de récoltes au prix du marché |
| `budgets` (`master_budgets`) | Budgets types par famille d'activité (charges et produits, quantité, prix HT, taux de TVA, mois) | Ouvert, CC-BY-SA | Prévisionnel et marges de référence |
| `prices` (`master_prices`, `master_doer_contracts`) | Prix de référence des intrants et du matériel. Coûts main-d'œuvre : SMIC horaire, ratio de charges sociales | Ouvert, CC-BY-SA. Page `/inputs` | Suggestion de prix, contrôle de vraisemblance |
| `fuel_prices` | Prix hebdomadaire du GNR (DGEC) | Ouvert, LO 2.0 | Remboursement TICPE du GNR (aide aux saisies) |
| `fertilizers`, `seeds`, `phytosanitary_prices` | Prix relevés chez des marchands | **Réservé**, attribution | Valorisation des stocks d'intrants |
| `eu_market_prices` | Cotations des marchés UE | Ouvert, licence non précisée | Valorisation des récoltes |
| `cap_beneficiaries` (`registered_cap_beneficiaries`, `registered_cap_subsidies`) | Aides PAC versées (FEAGA et FEADER) par bénéficiaire et par année, à ne jamais cumuler entre années | Ouvert, LO 2.0 | Contrôle des montants d'aides comptabilisés (74x) |
| `graphic_parcels` (RPG, avec historique) | Parcelles déclarées à la PAC, campagnes 2022 à 2025, et code culture | Ouvert, LO 2.0 | Assolement d'une exploitation et répartition analytique par surface |
| `rica` (`registered_rica_*`) | Microdonnées comptables du RICA (SSP/Agreste) : exploitations, variables, modalités | Ouvert, LO 2.0. Pages `/enterprises/rica` | **Ratios de référence par OTEX** (EBE/produit, charges/ha) pour l'assistant |
| `enterprise_classifications` | Codes NAF agricoles et OTEX, avec la table de passage NAF → OTEX | Ouvert, LO 2.0 | Typer la structure à partir du code NAF (SIRENE) |
| `enterprises` (SIRENE), `postal_codes`, `administrative_areas` | Établissements, communes, départements | Ouvert | Fiche tiers, préremplissage |
| `msa_populations` | **Populations** MSA par commune (retraités, chefs, salariés). **Ce ne sont pas des taux de cotisation.** | Ouvert, LO 2.0 | Peu utile pour la compta |
| `taxonomy`, `units`, `seed_varieties`, `vine_varieties` (réservé), `phenological_stages`, `technical_workflows`, `intervention_models` | Espèces, unités et conditionnements, variétés GNIS, itinéraires techniques | Ouvert sauf vigne | Libellés d'articles, unités de stock |
| `phytosanitary`, `phytosanitary_substances` (E-Phy, EIQ, HRAC), `phytosanitary_purchases` | Produits autorisés, usages, substances | Ouvert | Assistant (registre phyto), hors compta |
| `weather` | Stations et relevés horaires Météo-France | Ouvert, LO 2.0 | Justificatifs de calamités agricoles (assistant) |
| `protected_natural_zones`, `protected_water_zones`, `soil`, `hydrography`, `cadastre`, `cadastral_prices` | Zonages et valeurs foncières (DVF) | Ouvert | Valeur des terres (immobilisations 211) |
| `quality_and_origin_signs`, `organic_farming`, `hve_farms` (réservé) | AOC/IGP, bio, HVE | Ouvert | Crédit d'impôt bio, crédit HVE (contexte assistant) |

**Absents de Lexicon** :
- taux de TVA (ils sont seulement dans onoma) ;
- taux de cotisations MSA et assiettes ;
- **zones ICHN** et zones défavorisées ;
- calendriers fiscaux ;
- barèmes de valorisation des animaux ;
- forfait TVA agricole.

Ces données restent à constituer dans Lyvre.

---

## 3. Propositions concrètes pour Lyvre

1. **Créer `data/plan_comptable_agri.json`, le PCGA, au format actuel** (`code`, `label`, `account_type`, `is_header`).
   - Partir du CSV Lexicon : les lignes où `fr_pcga` est renseigné (1 173), avec `label_fr`.
   - Compléter ou corriger avec les numéros `fr_pcga2023` d'onoma : les 85 usages listés en 1.1, en particulier 31111 à 31116, 311411 à 311515, 60111 à 60117, 603111 à 603116, 713553/713554, 741, 745, 757.
   - Vérifier le résultat contre le règlement ANC 2020-04 (`claudedocs/compta_agricole/Reglt_2020_04_comptes-annuels-exploitations-agricoles.pdf`).
   - Conserver une colonne `usage`, la clé onoma, pour faire correspondre les imports Ekylibre et Isacompta.
   - Mentionner l'attribution « Ekylibre SAS / Lexicon, CC-BY-SA 4.0 » dans le fichier, qui sera lui-même sous CC-BY-SA.
2. **Choisir le plan selon le régime fiscal, comme dans onoma `fiscal_positions`.**
   - Ajouter à la structure un régime `BA-IR`, `BA-IS`, `BIC-*` ou `BNC-*`. BA donne `plan_comptable_agri.json`, sinon le plan de la société.
   - Reprendre `legal_positions` (GAEC, EARL, SCEA, EI) pour proposer les régimes compatibles.
3. **Reprendre le mapping des états** de `config/accountancy/accountancy_mandatory_documents_fr_pcga2023.yml`.
   - Il couvre le compte de résultat agricole (ventes d'animaux, variations d'inventaire 712/713, subventions 74), les ratios (production de l'exercice, VA, EBE) et le bilan PCGA.
   - Le syntaxe est simple (préfixes, sens C/D, `-` pour soustraire, `!` pour exclure) ; la convertir en YAML Lyvre.
   - Il faut réimplémenter le calcul (AGPL pour le code), mais la table de correspondance est une donnée réutilisable.
4. **Ajouter des règles d'imputation et une TVA par défaut à partir de `master_variant_categories`.**
   - Alimenter `data/rules.yml` (exemples : engrais → 60111 / TVA 20 %, aliments du bétail → 60114 / 10 %, eau d'irrigation → 60615 / 5,5 %, semences → 60112 / 10 %).
   - Proposer les durées d'amortissement par défaut des immobilisations agricoles (`depreciation_percentage`).
   - Comparer avec les codes Qonto (`qonto_categories.json`).
5. **Écriture d'inventaire de clôture**, sur le modèle d'`InventoryBookkeeper`.
   - Écran de saisie de l'inventaire par catégorie de stock (approvisionnements 3111x, animaux 3112/3113, avances aux cultures 3114x/3115x, produits 33x/35x).
   - Écriture automatique de variation : 3x / 603x pour les approvisionnements, 3x / 713x pour les produits et en-cours, avec contre-passation à l'ouverture si le stock n'est pas permanent.
   - Ajouter ce qu'Ekylibre n'a pas : une aide à la valorisation (prix `master_production_prices`, `eu_market_prices`, rendements `master_production_yields`) et un calcul des avances aux cultures à partir des factures d'intrants rattachées à une culture en terre.
6. **Immobilisations agricoles**, en plus de days360 déjà en place.
   - Ajouter les comptes 241/2841 (animaux reproducteurs), 246 (plantations), 294 et 68164 (dépréciation des biens vivants), et le cycle de cession d'animaux (657 / 757).
   - Ajouter la production immobilisée (7121/7122).
   - Reprendre les transitions `start_up`, `sell`, `scrap` et `stand_by` d'Ekylibre comme modèle d'états.
7. **TVA agricole**, que Lyvre devra concevoir seul puisqu'Ekylibre ne l'a pas.
   - Ajouter dans `vat_codes.json` des `regimes` agricoles : RSA (CA12A annuelle avec acomptes, ou CA3 sur option), RFA (remboursement forfaitaire 4,43 % ou 5,59 % au compte 741), franchise.
   - Ajouter les taux 10 % et 5,5 % propres aux produits agricoles.
   - Le CA3 existant pourra être réutilisé tel quel.
8. **Analytique « activité × campagne »** comme `activity_budget_id`.
   - Axes : famille d'activité (onoma `activity_families`) et production (`master_productions`), ventilation des charges communes par clé (marge brute, %, surface RPG).
   - Calcul de marge brute par atelier et ratios RICA par OTEX comme référence (jeu `rica`).
9. **FEC et échanges**
   - Reprendre les validateurs XSD (`app/concepts/fec/validators/*.xsd`) et la règle de choix du format BA-IR trésorerie ou engagement.
   - S'inspirer des importeurs `isagri/isacompta/fec_txt_exchanger.rb`, `agrigest/` et `bordeaux_sciences_agro/istea/` pour reprendre les dossiers tenus par des cabinets agricoles.
   - L'export analytique Isacompta passe par un code activité sur 2 caractères.
10. **Aides PAC**
    - Ajouter des sous-comptes 74x par type d'aide (DPB, écorégime, couplées, ICHN, MAEC, assurance récolte) et une règle de rattachement à l'exercice.
    - Contrôle croisé avec `cap_beneficiaries` (montants publiés par l'ASP) par SIREN, par année, sans jamais cumuler les années.
    - Optionnel : import Telepac (format des `cap_statements_exchanger` v2025) pour l'assolement.
11. **Assistant Lyvre (base documentaire)** : brancher le MCP Lexicon public (`https://lexicon.osfarm.org/mcp`).
    - Outils : `get_crop_figures` (rendements et prix pour valoriser une récolte), `get_input_price`, `get_enterprise` et `get_commune`, `read_resource` sur `/production/productions`.
    - En anonyme, prévoir un cache à cause de la limite de 30 requêtes par fenêtre, ou une clé membre OSFarm.
12. **Données à constituer hors Lexicon**, en fichiers YAML de règles dans `doc/base_documentaire` :
    - barème et méthodes de valorisation des animaux ;
    - taux et échéances MSA ;
    - zones ICHN ;
    - calendrier fiscal BA (2139/2143, CA12A, acomptes) ;
    - seuils micro-BA, réel simplifié et réel normal.

**Points de vigilance juridiques**
- Le code Ekylibre et onoma est sous AGPL-3.0 : reprendre les méthodes, mais réécrire le code plutôt que de le copier.
- Les données `master_*` sont sous CC-BY-SA 4.0 : elles imposent attribution et partage à l'identique des fichiers dérivés.
- Ne pas embarquer les jeux réservés (prix marchands) ni les jeux NC (`rd_agri`, `vine_varieties`).
