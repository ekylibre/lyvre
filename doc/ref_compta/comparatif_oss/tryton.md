# Tryton : analyse comparative avec Lyvre

*Recherche du 23/10/2026. Version étudiée : série **8.2** (sortie le 6 oct. 2026 ; trytond 8.2.1, modules 8.2.0).
Méthode : le code source des modules a été lu dans les wheels officielles PyPI (B2CK SRL, publiées depuis le dépôt `foss.heptapod.net/tryton/tryton`, sans jamais exécuter leur code), puis recoupé avec docs.tryton.org.
Modules lus : account, account_fr, account_fr_chorus, account_invoice, account_invoice_defer, account_invoice_correction, account_invoice_factur_x, edocument_uncefact, account_statement, account_statement_rule, account_statement_ofx, account_statement_sepa, account_payment, account_payment_sepa, account_payment_clearing, account_payment_stripe, account_dunning (+ _letter, _email, _fee), account_asset, account_budget, analytic_account, analytic_invoice, account_tax_cash, account_tax_non_deductible, account_rule, account_receivable_rule, account_consolidation, account_deposit, account_cash_rounding, account_move_line_grouping, account_export, account_credit_limit, account_eu, sale_subscription.*

---

## 1. Technologies

| Aspect | Tryton |
|---|---|
| Langage | Python ≥ 3.10 (serveur `trytond`). Dépendances : werkzeug, python-sql (requêtes SQL construites en objets), genshi, relatorio (rapports ODT/FODT convertis en PDF par LibreOffice), lxml, simpleeval, pwdlib[argon2]. |
| Framework | Framework maison à trois niveaux. Un ORM déclaratif (`ModelSQL`, `ModelView`, `Workflow`, `fields.*`), un `Pool` de modèles extensibles par héritage (`metaclass=PoolMeta`) et des vues XML. Les états et domaines des champs sont exprimés par `Eval()` (PYSON). Les assistants (`Wizard`) servent aux traitements. |
| Base de données | **PostgreSQL** en production (psycopg 3). **SQLite** est aussi un backend officiel (`trytond/backend/sqlite`), surtout pour les tests et les petites installations. |
| Clients | **tryton** : client bureau GTK (Linux, Windows, macOS). **sao** : client web JavaScript, avec la même interface générée depuis les vues XML. **proteus** : bibliothèque de scripts Python, utilisée aussi pour les tests en scénarios `.rst`. Un client REST (« tryton-naiad ») est documenté. Le transport est en JSON-RPC/XML-RPC, plus des routes HTTP (webhooks Stripe, etc.). Pas d'application mobile native. |
| Licence | **GPL-3.0-or-later** pour le serveur et les modules. La documentation est sous CC BY-SA. Gouvernance par la Tryton Foundation (association belge, sans éditeur unique) ; B2CK SRL est le principal contributeur. |
| Déploiement | Docker (image `tryton/tryton`, méthode recommandée par la doc), pip/PyPI (un paquet par module, ex. `trytond_account_fr`), ou paquets des distributions. Serveur WSGI (werkzeug), cron et workers de file de tâches séparés. Configuration en `trytond.conf`. |
| Modularité | Très forte : environ 200 modules officiels. Chaque module déclare `depends`/`extras_depend` dans `tryton.cfg`. Les fonctions comptables sont éclatées en petits modules optionnels (ex. dunning → dunning_letter, dunning_email, dunning_fee). Le multi-société est natif (`company` sur presque tous les modèles, valeurs par société via `MultiValue`). |
| Cycle de version | Deux versions par an (x.0 et x.2), avec une LTS régulière. Scripts de migration entre séries. |
| Traduction | Le français est livré (locale `fr.po` dans chaque module). |

---

## 2. Méthodes et données comptables

### 2.1 Pièces et lignes d'écritures (module `account`)
- **`account.move`** (pièce) porte `journal`, `period`, `date` (date d'effet), `post_date` (date de validation, en lecture seule), `number` (numéro attribué à la validation par séquence de journal), `origin` (référence polymorphe : facture, relevé, immobilisation…), `description`, `lines` et `state` ∈ {`draft`, `posted`}.
  - Une fois validée (`post`), la pièce est **en lecture seule et non supprimable**. Le contrôle `_check_modify` interdit toute écriture sur une pièce ou une ligne postée.
  - La correction passe par l'assistant **`account.move.cancel`** : il crée une **contre-passation** (`cancel(reversal=True)`), avec en option un lettrage automatique de l'original et de l'extourne.
- **`account.move.line`** porte `account`, `party` (obligatoire sur les comptes de tiers `party_required`), `debit`/`credit`, `amount_second_currency`/`second_currency` (devise), `maturity_date` (échéance), `reconciliation` (lien de lettrage), `tax_lines` (codes de taxe) et `state` ∈ {`draft`, `valid`}. Le contrôle d'équilibre est fait par pièce.
- **Modèles d'écritures** (`account.move.template`, avec mots-clés `keyword` saisis à l'exécution) pour les écritures récurrentes, lancés via *Create Move from Template*.
- **Assistants sur les lignes de tiers** : `reschedule` (rééchelonner une créance en plusieurs échéances), `delegate` (transférer une dette ou créance à un autre tiers), `group` (compenser plusieurs lignes clients et fournisseurs d'un même tiers en une seule ligne nette).

### 2.2 Périodes et exercices
- **`account.period`** a pour états **`open` → `closed` → `locked`**. Une période close peut être rouverte ; une période **verrouillée** ne le peut plus.
  - La clôture partielle se fait par journal (`account.journal.period`).
  - Les types de période incluent `adjustment` (période d'ajustement datée du dernier jour, pour les écritures d'inventaire).
- **`account.fiscalyear`** a pour états `open` → `closed` → `locked`.
  - **`account.fiscalyear.balance_non_deferral`** : assistant qui solde les comptes de gestion (classes 6/7, « non-deferral ») vers un compte de bilan (résultat), dans une période d'ajustement et un journal « Situation ».
  - **`close()`** calcule et fige les **`account.account.deferral`** : les soldes débit, crédit et devise par compte de bilan et par exercice. Les reports à nouveau sont donc stockés comme cumuls, sans écriture d'à-nouveaux. `reopen()` supprime ces cumuls.
  - **`account.fiscalyear.renew`** crée l'exercice suivant (dates, périodes mensuelles ou trimestrielles, séquences de pièces et de factures dupliquées et éventuellement réinitialisées).
- La doc impose un ordre de clôture : toutes les périodes closes, puis solde des comptes non reportés, puis autres écritures de fin d'exercice, puis clôture de l'exercice.

### 2.3 Lettrage (réconciliation de comptes de tiers)
- **`account.move.reconciliation`** porte `number`, `date`, `lines`, `delegate_to` (une ligne ne peut appartenir qu'à un seul lettrage, total à zéro exigé).
- Assistants :
  - **`account.reconcile`** : lettrage interactif par compte et tiers, avec proposition automatique des combinaisons qui soldent.
  - **`account.move.reconcile_lines`** : lettrage de lignes choisies, avec **écart passé en perte ou profit** via `account.move.reconcile.write_off` (méthodes d'ajustement paramétrées : journal et comptes).
  - `unreconcile_lines` pour délettrer.
- Les écarts de change au lettrage sont passés automatiquement (`currency_exchange_journal`, `currency_exchange_credit_account`/`debit_account` dans la configuration).
- Un cron de lettrage automatique est disponible. Le paiement d'une facture lettre lui-même ses lignes.
- **`account_receivable_rule`** : des règles (`account.account.receivable.rule`) lettrent automatiquement les créances entre comptes, par exemple un acompte sur un compte et une facture sur un autre. Un compte de débordement reçoit l'excédent. Exécution par cron.
- **`account_move_line_grouping`** ajoute une vue des lignes groupées par pièce, compte, tiers et échéance (`account.move.line.group`).
- **Balance âgée** des tiers : `account.aged_balance`, par tranches de jours, semaines ou mois.

### 2.4 TVA : taxes, règles, déclarations
- **`account.tax`** est arborescent. Types : pourcentage, fixe ou aucun (taxes « parent » avec enfants). Il porte des comptes de facture et d'avoir, la gestion de l'arrondi par document ou par ligne (`tax_rounding`) et un `group`.
- **`account.tax.rule`** (règles fiscales) remplace une taxe par une autre selon le tiers : intracommunautaire, export, autoliquidation. Le module `account_tax_rule_country` ajoute des règles par pays d'origine et de destination.
- **`account.tax.code`** (codes de déclaration) agrège des lignes de taxe, en base ou en montant, par formule (`account.tax.code.line`, opérateur +/−). Le module **`account_fr` livre ~113 codes calqués sur les cases de la CA3** : 0206 base TVA 20 %, 0105 base 5,5 %, 0151 base 10 %, 0034 livraisons intracommunautaires, 0032 exportations, régularisations, etc. Le rapport *Tax Codes* sur une période donne les montants à reporter sur la CA3. Il n'y a ni télédéclaration (EDI-TVA) ni formulaire PDF.
- **`account.tax.test`** : un simulateur de calcul de taxes.
- **`account_tax_cash`** gère la **TVA sur les encaissements** (prestations de services en France).
  - Elle s'active par groupe de taxes, par société, par exercice ou période (`tax_group_on_cash_basis`) et par tiers.
  - Les lignes `account.tax.line` reçoivent `on_cash_basis` et `period`, et ne sont rattachées à une période que lorsque la facture est payée, au prorata (`cash_paid_ratio`).
  - Fermer une période attribue les lignes de taxe des paiements reçus.
- **`account_tax_non_deductible`** : TVA non récupérable, réintégrée dans le coût de la ligne.
- **`account_eu`** : déclaration européenne de services (`account.ec_sales_list`).

### 2.5 Relevés bancaires et rapprochement
- **`account.statement`** a pour états `draft` → `validated` → `posted` (ou `cancelled`).
  - Contrôle de validation par journal (`validation` ∈ {`balance` : solde initial et final ; `amount` : total ; `number_of_lines`}).
  - Les lignes de relevé (`account.statement.line`) sont rattachées à un tiers, une facture ou un paiement, et génèrent la pièce comptable à la validation.
  - Les **`account.statement.origin`** sont les opérations brutes importées, avec `information` (clés et valeurs dictionnaire : IBAN, référence…). Elles restent non affectées tant qu'aucune ligne ne les solde.
- **Imports** (`account.statement.import`) :
  - CSV (natif) ;
  - **OFX** (`account_statement_ofx`) ;
  - **CAMT.052/053/054** (`account_statement_sepa`) ;
  - CODA belge (`account_statement_coda`) ;
  - AEB43 espagnol (`account_statement_aeb`) ;
  - MT940 (`account_statement_mt`).
- **`account_statement_rule`** : règles de rapprochement automatique (`account.statement.rule`). Critères : journal, montant min/max, **expression régulière sur le libellé** avec groupes nommés `party`, `bank_account`, `invoice`, `payment_reference`, et règles sur les informations (`information_rules`). Des lignes de règle répartissent le montant (`amount` = expression Python sur `amount`/`pending`, tiers, compte). Un mode « keywords » permet le rattachement automatique à la facture via la référence de paiement structurée.

### 2.6 Paiements, SEPA, encaissements
- **`account_payment`** :
  - `account.payment.journal`, `account.payment.group` (lot) et `account.payment` (états draft, submitted, approved, processing, succeeded, failed).
  - Paiement des lignes échues (`account.move.line.pay`) et prélèvements automatiques par tiers (`party.party.reception_direct_debit`, assistant `create_direct_debit`).
  - Planification par date d'échéance.
- **`account_payment_sepa`** :
  - Génère les fichiers **pain.001** (virements, `sepa_payable_flavor`) et **pain.008** (prélèvements, `sepa_receivable_flavor`).
  - Les **mandats** `account.payment.sepa.mandate` portent `identification` (RUM), `type` (récurrent ou ponctuel), `scheme` (CORE/B2B), `signature_date`, des états (requested → validated → cancelled) et un PDF de mandat imprimable.
  - Les retours ou rejets sont gérés (`sepa_return_reason_code`). Les messages SEPA entrants et sortants sont stockés (`account.payment.sepa.message`). L'identifiant créancier ICS est un identifiant de tiers.
- **`account_payment_clearing`** : comptabilise les paiements sur un compte d'attente (511 / 58), soldé à l'arrivée du relevé.
- **`account_payment_stripe`** : encaissement par carte via Stripe Checkout, avec clients, remboursements et litiges. On trouve aussi `account_payment_braintree`.
- **`account_payment_check`** : gestion et impression de chèques de paiement.
- **`account_deposit`** : **acomptes clients** (compte de type *deposit*, 4191) avec rappel de l'acompte sur la facture finale (`recall_deposit`). Ce n'est pas une remise de chèques.
- **Moyens de paiement** sur facture : `account.invoice.payment.mean` et règles associées.

### 2.7 Relances
- **`account_dunning`** :
  - `account.dunning.procedure` contient des **niveaux** `account.dunning.level` avec un délai `overdue` (TimeDelta).
  - `account.dunning` (une ligne échue = un dossier) porte `level`, `state` (draft, waiting, final), `blocked` (litige) et `age`.
  - L'assistant `create` est lancé à une date donnée, `process` fait passer au niveau suivant, `reschedule` rééchelonne.
- **`account_dunning_letter`** (lettre PDF par tiers), **`account_dunning_email`** (courriel par niveau), **`account_dunning_fee`** (frais de relance comptabilisés par niveau), **`account_credit_limit`** (plafond de crédit par tiers, bloquant selon le niveau de relance).

### 2.8 Charges et produits constatés d'avance
- **`account_invoice_defer`** :
  - Sur une ligne de facture, l'utilisateur saisit `defer_from`/`defer_to`.
  - À la validation, le montant est porté sur un **compte d'attente** (`deferred_account_expense` = 486 ou `deferred_account_revenue` = 487).
  - Le modèle `account.invoice.deferred` (`start_date`, `end_date`, `moves`, états draft, running, closed) génère ensuite **une écriture par période** pour reconnaître la charge ou le produit au prorata, via l'assistant `create_moves` ou un cron.
  - Exemples d'usage : un abonnement annuel ou une assurance à cheval sur deux exercices.

### 2.9 Immobilisations et amortissements
- **`account_asset`** :
  - `account.asset` porte `product`, `supplier_invoice_line`, `value`, `residual_value`, `start_date`/`end_date`, `depreciation_method` (**linéaire uniquement** en standard), `frequency` (mensuelle ou annuelle), `state` (draft, running, closed) et un journal dédié.
  - Le tableau d'amortissement `account.asset.line` (montant, cumul, valeur nette) est imprimable (*depreciation_table*).
  - **Révisions** (`account.asset.revision`) : modification de valeur ou de durée en cours de vie, avec recalcul.
  - **Cession / mise au rebut** (`close`) avec écriture de sortie.
  - Création **automatique** depuis la facture fournisseur, via le produit de type « asset » et les comptes de la catégorie.
  - Écritures périodiques générées par l'assistant `create_moves`.

### 2.10 Budgets
- **`account_budget`** :
  - `account.budget` (par exercice) contient des `account.budget.line` arborescentes, par **type de compte ou compte**.
  - La ventilation par période (`account.budget.line.period`) se fait en répartition égale ou manuelle (assistant `create_periods`).
  - Calcul `actual_amount` (réalisé) et `percentage` (consommé).
  - Assistant de **copie** de budget N → N+1 avec coefficient.
  - L'option `posted` permet de ne prendre que les écritures validées.

### 2.11 Analytique
- **`analytic_account`** :
  - **Plusieurs axes** (plusieurs racines `root`).
  - Types de comptes : `view`, `normal` et **`distribution`** (un compte « répartiteur » qui ventile par pourcentage sur d'autres comptes, `analytic_account.account.distribution`).
  - Les lignes analytiques `analytic_account.line` sont générées depuis les lignes d'écriture via les entrées `analytic.account.entry` (un compte par axe).
  - **Règles** `analytic_account.rule` : affectation automatique selon le compte général, le tiers ou le journal.
  - Un axe peut être rendu **obligatoire** pour certains comptes.
- **`analytic_invoice`** : analytique sur les lignes de facture, les immobilisations et les produits constatés d'avance.

### 2.12 Règles d'imputation
- **`account_rule`** (`account.account.rule`) substitue un compte selon la période (`start_date`/`end_date`), le type (revenu, charge, stock), le compte d'origine, la taxe, le retour, l'entrepôt ou le tiers.
- **`account_rule` également** : comptes par catégorie de produit, par tiers et par défaut (`account.configuration.default_account`).

### 2.13 France
- **`account_fr`** :
  - **Plan comptable général** (~1 230 comptes, structure antérieure au règlement ANC 2022-06 : la classe 77 « exceptionnel » y figure encore). **Il n'y a ni plan associatif (ANC 2018-06 : 19, 86/87, 689/789…) ni plan SCI.**
  - Plan de types de compte pour le bilan et le compte de résultat au format français.
  - Codes de taxe calqués sur la CA3.
  - Assistant **FEC** (`account.fr.fec`) : choix de l'exercice et de la période de report. Il **calcule les à-nouveaux** depuis les cumuls de report. Format IS-BIC.
- **`account_fr_chorus`** : **envoi des factures clients B2G à Chorus Pro** par l'API PISTE (`chorus_piste_client_id/secret`, `chorus_login/password`, environnement qualification ou production). Syntaxes CII/UBL. Le suivi de statut (`account.invoice.chorus` : number, date, data, state) se fait par cron. Le tiers doit avoir un SIRET (`party_siret`).
- **`edocument_uncefact`** : génère et **analyse** les factures UN/CEFACT CII. L'import d'une facture fournisseur CII crée la facture, le tiers et les lignes.
- **`account_invoice_factur_x`** (nouveau en 8.2) : Factur-X par client, profils MINIMUM à EN16931/EXTENDED.

### 2.14 Factures (module `account_invoice`)
- `account.invoice` a pour types `out`/`in` et pour états **draft → validated → posted → paid** (ou cancelled).
  - Numérotation par **séquence propre à l'exercice** (`account.fiscalyear.invoice_sequence`) ; plusieurs séquences sont possibles (factures, avoirs, par période).
  - **Conditions de paiement** paramétrables (`account.invoice.payment_term` avec lignes et décalages : 30 j fin de mois, fractionnement), avec testeur.
  - Paiement partiel, en trop-perçu ou avec passage en perte (`pay` : writeoff, partial, overpayment).
  - Bénéficiaire alternatif (`alternative_payee`, cession de créance).
  - **Révisions du rapport PDF figées** (`account.invoice.report.revision`) : le PDF émis est conservé.
- `account_invoice_correction` : avoir partiel corrigeant une ligne.
- `account_cash_rounding` : arrondi d'espèces.

### 2.15 Multi-société, multi-devise, consolidation
- Le multi-société est natif. L'utilisateur choisit sa société courante. Plans de comptes séparés, avec règles d'accès par société.
- Pour le multi-devise, chaque ligne porte un montant en devise secondaire, et les taux viennent de `currency` (avec mises à jour automatiques via `currency_rs`/BCE). Les écarts de change sont comptabilisés au lettrage.
  - **Aucun assistant de réévaluation de fin d'exercice des soldes en devise n'a été trouvé dans les modules examinés.**
- **`account_consolidation`** : bilan et compte de résultat consolidés multi-sociétés (`account.consolidation`), avec élimination des opérations intra-groupe via `consolidation_company` sur les pièces et les factures.
- **`account_export`** : socle d'export des pièces vers un logiciel comptable tiers (`account.move.export`). L'adaptateur `account_export_winbooks` est fourni.

---

## 3. Fonctionnalités par domaine

| Domaine | Fonctionnalités Tryton |
|---|---|
| **Comptabilité générale** | Pièces brouillon ou validées (contre-passation), modèles d'écritures récurrentes, journaux, grand livre, balance, balance âgée, bilan et compte de résultat (comparatif), journal général, périodes ouvertes, closes ou verrouillées (et par journal), clôture d'exercice avec solde des comptes de gestion, renouvellement d'exercice, mise à jour du plan depuis le modèle (`update_chart`). |
| **Tiers** | Lettrage manuel ou automatique avec passage en perte, écarts de change, rééchelonnement, délégation, compensation clients/fournisseurs, règles de lettrage inter-comptes, plafond de crédit, RGPD (`party.erase`), fusion de tiers (`party.replace`). |
| **TVA** | Taxes arborescentes, règles fiscales (intracommunautaire, export, autoliquidation), codes de déclaration CA3, TVA sur les encaissements, TVA non déductible, DES européenne, testeur de taxes. |
| **Trésorerie** | Relevés (CSV, OFX, CAMT, CODA, MT940, AEB43), règles de rapprochement par regex et référence structurée, comptes d'attente de paiement (clearing), caisses (`open_cash`). |
| **Paiements** | Lots de paiement, virements SEPA, **prélèvements SEPA avec mandats**, rejets, Stripe et Braintree, chèques, acomptes clients avec rappel. |
| **Relances** | Procédures à niveaux, lettres PDF, courriels, frais de relance, blocage des litiges. |
| **Ventes et achats** | Factures, avoirs, corrections, conditions de paiement, Factur-X, Chorus Pro, import de factures CII, devis et commandes (`sale`, `purchase`), **abonnements** (`sale_subscription` : services, règles de récurrence de type RRULE, consommations, facturation par cron). |
| **Clôture et régularisations** | Charges et produits constatés d'avance automatiques (486/487 étalés par période), immobilisations avec amortissement linéaire, révisions et cessions. |
| **Pilotage** | Budgets par compte ou type et par période avec réalisé et %, analytique multi-axes avec comptes répartiteurs et règles, consolidation multi-sociétés. |
| **Conformité FR** | PCG, FEC, Chorus Pro, Factur-X, CA3 (codes). |
| **Hors périmètre comptable** | Stock et valorisation (continental, anglo-saxon), production, CRM, projets et temps, commerce électronique (`web_shop`), point de vente, notes de frais, etc. Pas de paie ni de module association (adhérents, dons, reçus fiscaux). |

---

## 4. Écarts avec Lyvre : fonctions que Tryton a et que Lyvre n'a pas (ou que Tryton fait mieux)

| # | Fonction Tryton | Intérêt pour une association ou une SCI | Source |
|---|---|---|---|
| 1 | **Lettrage des comptes de tiers** (`account.move.reconciliation`, assistant `reconcile` avec proposition automatique, perte ou profit sur écart, délettrage, cron) | Savoir précisément quelles factures restent dues (411/401). C'est indispensable pour le suivi des loyers impayés en SCI et des cotisations ou subventions à recevoir. | https://docs.tryton.org/latest/modules-account/usage/index.html#reconciling-accounts |
| 2 | **Verrouillage des périodes** mensuel (`open → closed → locked`) et clôture par journal | Figer les mois déjà rapprochés ou transmis à l'expert-comptable. Le trésorier ne peut plus modifier un mois validé. | https://docs.tryton.org/latest/modules-account/usage/index.html#closing-a-period |
| 3 | **Codes de taxe calqués sur la CA3** (`account_fr/tax_fr.xml`, cases 0206, 0105, 0151…) et rapport par période | Les associations assujetties (activités lucratives, buvette, billetterie au-delà de la franchise) et les SCI optant pour la TVA (locaux professionnels) préparent leur CA3 directement. | https://docs.tryton.org/latest/modules-account-fr/index.html |
| 4 | **TVA sur les encaissements** (`account_tax_cash`, exigibilité au prorata du paiement) | C'est le régime par défaut des prestations de services, cas typique des associations et des loyers commerciaux à TVA. | https://docs.tryton.org/latest/modules-account-tax-cash/index.html |
| 5 | **Immobilisations et amortissements** (`account_asset` : création depuis la facture fournisseur, tableau, révisions, cession, écritures périodiques) | Amortir le matériel associatif et surtout l'immeuble de la SCI (hors terrain), qui est obligatoire à l'IS et utile au suivi. | https://docs.tryton.org/latest/modules-account-asset/index.html |
| 6 | **Charges et produits constatés d'avance automatiques** (`account_invoice_defer` : dates de début et de fin sur la ligne de facture, étalement par période sur 486/487) | Assurances, abonnements, cotisations annuelles à cheval sur deux exercices. Lyvre ne fait que des écritures 486/487 manuelles à la clôture avec extourne ; Tryton les étale dès la saisie de la facture. | https://docs.tryton.org/latest/modules-account-invoice-defer/index.html |
| 7 | **Prélèvement SEPA avec mandats** (`account_payment_sepa` : RUM, CORE/B2B, PDF de mandat, pain.008, rejets) | Collecter les cotisations ou les loyers mensuels par prélèvement, sans dépendre de HelloAsso ni de Qonto. | https://docs.tryton.org/latest/modules-account-payment-sepa/index.html |
| 8 | **Virements SEPA groupés** (pain.001 depuis les échéances fournisseurs) | Payer en lot les fournisseurs et les remboursements de frais de bénévoles avec n'importe quelle banque, pas seulement Qonto. | https://docs.tryton.org/latest/modules-account-payment/index.html |
| 9 | **Relances à niveaux** (procédures et niveaux à délai, lettres PDF, courriels automatiques, frais de relance, blocage des litiges) | Automatiser les relances de loyers ou de factures (J+15 courriel, J+30 lettre, J+60 mise en demeure). Lyvre n'a que des relances manuelles. | https://docs.tryton.org/latest/modules-account-dunning/index.html |
| 10 | **Import CAMT.053/054** (et MT940, CODA) | Ouvre l'import de relevés à toutes les banques françaises, dont l'export CAMT se généralise, au-delà d'OFX et Qonto. | https://docs.tryton.org/latest/modules-account-statement-sepa/index.html |
| 11 | **Règles de rapprochement par expression régulière à groupes nommés** (`party`, `invoice`, `payment_reference`) et référence de paiement structurée sur la facture | C'est mieux que des règles de catégorisation simples : on rattache automatiquement un virement à la bonne facture ou au bon locataire grâce à la référence. | https://docs.tryton.org/latest/modules-account-statement-rule/index.html |
| 12 | **Envoi Chorus Pro** (`account_fr_chorus`, API PISTE, suivi de statut) | Associations qui facturent des collectivités (prestations, conventions) : le dépôt sur Chorus Pro est obligatoire pour le B2G. | https://docs.tryton.org/latest/modules-account-fr-chorus/index.html |
| 13 | **Import de factures fournisseurs CII structurées** (`edocument_uncefact`, analyse CII avec création du tiers et des lignes) | Prépare la réforme de la facturation électronique 2026-2027. Lyvre lit déjà le Factur-X, mais Tryton reconstruit la facture ligne à ligne avec les taxes, de façon déterministe. | https://docs.tryton.org/latest/modules-edocument-uncefact/index.html |
| 14 | **Analytique multi-axes** avec comptes répartiteurs (`distribution`, en %) et règles d'affectation automatique | Ventiler à la fois par projet, financeur et site, et répartir automatiquement les frais de structure (loyer, assurance) entre projets subventionnés. Lyvre n'a qu'un axe, avec ventilation manuelle. | https://docs.tryton.org/latest/modules-analytic-account/index.html |
| 15 | **Budget par période** avec copie N → N+1 et coefficient | Dupliquer le budget voté en AG avec une indexation, et suivre l'écart mois par mois. | https://docs.tryton.org/latest/modules-account-budget/index.html |
| 16 | **Acomptes clients** (`account_deposit` : compte 4191, rappel sur la facture finale) | Arrhes de séjours ou d'événements, dépôts de garantie des locataires en SCI. | https://docs.tryton.org/latest/modules-account-deposit/index.html |
| 17 | **Comptes d'attente de paiement** (`account_payment_clearing`, comptabilisation à l'émission puis solde au relevé) | Suivre les chèques émis non encaissés et les prélèvements en transit, ce qui fiabilise le rapprochement. | https://docs.tryton.org/latest/modules-account-payment-clearing/index.html |
| 18 | **Encaissement en ligne par Stripe** (Checkout, remboursements, litiges, rapprochés comptablement) | Paiement en ligne des factures ou cotisations par l'outil lui-même. Lyvre n'importe que les virements Stripe/Stancer. | https://docs.tryton.org/latest/modules-account-payment-stripe/index.html |
| 19 | **Rééchelonnement et délégation de créances** (`reschedule`, `delegate`), plus compensation clients/fournisseurs (`group`) | Plans d'apurement de loyers impayés, compensation quand un tiers est à la fois client et fournisseur (association partenaire). | https://docs.tryton.org/latest/modules-account/usage/index.html#grouping-payable-or-receivable-lines |
| 20 | **Abonnements de vente avec règles de récurrence de type RRULE et consommations** (`sale_subscription`, facturation par cron) | C'est mieux que la récurrence en brouillon de Lyvre : les factures sont générées automatiquement, avec calendrier complexe (ex. « le 1er de chaque trimestre sauf août ») et proratisation. | https://docs.tryton.org/latest/modules-sale-subscription/index.html |
| 21 | **Modèles d'écritures récurrentes à mots-clés** (`account.move.template`) | Écritures mensuelles répétitives (quote-part de charges, intérêts d'emprunt SCI) saisies en un clic. | https://docs.tryton.org/latest/modules-account/usage/index.html#reoccurring-entries |
| 22 | **Conservation des révisions du PDF de facture** (`account.invoice.report.revision`) et numérotation par exercice | Inaltérabilité de la facture émise, au-delà de la seule pièce comptable. | https://foss.heptapod.net/tryton/tryton/-/tree/branch/default/modules/account_invoice |
| 23 | **Multi-devise** (devise secondaire par ligne, écarts de change au lettrage, taux BCE automatiques) | Rare en association, mais utile pour les projets de solidarité internationale (achats en devises, subventions UE). | https://docs.tryton.org/latest/modules-account/index.html |
| 24 | **Consolidation multi-sociétés** (`account_consolidation`) | Groupe d'associations (fédération et antennes) ou plusieurs SCI d'une même famille : états consolidés. Lyvre a le multi-structure mais pas la consolidation. | https://docs.tryton.org/latest/modules-account-consolidation/index.html |
| 25 | **Cumuls de report figés à la clôture** (`account.account.deferral`) et FEC qui calcule les à-nouveaux | Exercices clos réellement immuables. Lyvre fait déjà une clôture provisoire puis définitive avec à-nouveaux. Le modèle Tryton est une approche alternative plutôt qu'un écart. | https://foss.heptapod.net/tryton/tryton/-/tree/branch/default/modules/account |

### Points où Lyvre est en avance (pour mémoire)
- Plan associatif ANC 2018-06 et plan SCI : Tryton n'a qu'un PCG « entreprise » ancien, sans 86/87, fonds dédiés ou comptes 19.
- Adhérents, dons, reçus fiscaux Cerfa, bénévolat valorisé, clôture associative (fonds dédiés, affectation du résultat), registre des parts et comptes courants d'associés.
- Mode recettes/dépenses simplifié, synchronisation Qonto et HelloAsso, OCR des factures d'achat, prévisionnel de trésorerie et tableau de bord d'impact. Tryton exige un comptable formé et une installation PostgreSQL et Docker conséquente.
- Ergonomie : le client sao est générique (formulaires et listes générés), et aucun assistant métier n'y est orienté association.

### Idées concrètes à reprendre pour Lyvre (par ordre de rapport intérêt / coût)
1. Lettrage 411/401 avec proposition automatique et passage en perte ou profit des écarts (modèle `reconciliation` : un numéro, des lignes, une somme nulle).
2. États de période `open`/`closed`/`locked` par mois.
3. Codes de déclaration TVA calqués sur la CA3 (table `tax_code` agrégeant base et taxe), plus la TVA sur les encaissements.
4. Charges et produits constatés d'avance depuis la ligne de facture (`defer_from`/`defer_to`).
5. Immobilisations à amortissement linéaire mensuel ou annuel, créées depuis la facture d'achat.
6. Import CAMT.053, et règles de rapprochement par expression régulière avec groupe `invoice` ou référence structurée.
7. Relances à niveaux (délai, modèle de courriel, frais).
8. Prélèvements SEPA pain.008 avec mandats (RUM, date de signature, FRST/RCUR).
