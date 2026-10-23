# Diacamma (Asso / Syndic / Financial) — analyse comparative pour Lyvre

Date d'analyse : 23/10/2026. Sources : site https://www.diacamma.org/, aide en ligne (http://asso.diacamma.org/Docs, http://syndic.diacamma.org/Docs), manuels PDF (https://download.sd-libre.fr/DiacammaAsso.pdf, https://download.sd-libre.fr/DiacammaSyndic.pdf), installeur `scratchpad/diacamma/Diacamma/install.sh`, et code source récupéré (sans exécution) par `git clone --depth 1` des dépôts GitHub `Diacamma2/financial`, `Diacamma2/asso`, `Diacamma2/syndic`, `Lucterios2/contacts`, `Lucterios2/documents`, `Lucterios2/core` dans `scratchpad/research/diacamma-src/` (derniers commits : financial 08/10/2026 « Version 2.7.10 : Python 3.14 », syndic 16/10/2026).
Note : `pip download diacamma-asso` échoue (les paquets diacamma-* ne sont pas résolus sur PyPI par ce nom ; `lucterios` 2.7.9 y est bien publié). Les chemins ci-dessous sont relatifs à `diacamma-src/`.

---

## 1. Technologies

| Élément | Constat | Source |
|---|---|---|
| Langage | Python 3 (testé jusqu'à 3.14) | commit financial 2.7.10 |
| Framework | **Lucterios** (framework maison au-dessus de **Django 5.2**) ; les vues sont des classes `Xfer*` (XferListEditor, XferShowEditor, XferTransition…) décrivant des écrans abstraits, rendus par un client générique | `financial/setup.py`, `core/` |
| Dépendances notables | django-viewflow (workflows FSM : `FSMIntegerField` sur factures, bordereaux…), reportlab + CairoSVG (PDF), APScheduler (tâches planifiées), odfpy/openpyxl/xlrd/pandas (imports-exports CSV/ODS/XLS), waitress (serveur WSGI), PyQt6 (lanceur bureau), `digital_invoice` (Factur-X / UBL), `stripe`, `requests-oauthlib` | PyPI `lucterios` requires_dist, `financial/setup.py` |
| Base de données | SQLite par défaut ; MySQL et PostgreSQL supportés (choix à la création d'instance) | `core/lucterios/install/*` ; install.sh installe `default-libmysqlclient-dev` |
| Front / client | Client web générique (JavaScript, livré par `lucterios-standard`) qui interprète les écrans déclarés côté serveur — pas de SPA dédiée ; lanceur graphique PyQt6 (`lucterios_qt.py`) qui gère les instances et ouvre le navigateur. Icônes Material Design (`mdi:`) | `core/lucterios/install/lucterios_qt.py`, `lucterios_gui.py` |
| Multi-instance | `lucterios_admin.py` : création / mise à jour / archivage d'instances (une instance = une structure, sa base et ses modules) | `core/lucterios/install/lucterios_admin.py`, install.sh |
| Licence | **GPL v3** (et non AGPL : un hébergeur peut modifier sans redistribuer le code) | `financial/LICENSE`, setup.py |
| Déploiement | Installeurs Windows (.exe, Win10+), macOS (.dmg), Linux (`install.sh` : virtualenv dans `/var/lucterios2`, `pip install lucterios lucterios-standard lucterios-contacts lucterios-documents diacamma-asso diacamma-syndic diacamma-financial`, puis script `launch_lucterios.sh`) | install.sh, diacamma.org |
| Hébergement | Pas d'offre SaaS par l'éditeur ; hébergement et support payants via le partenaire **Sleto** (membre CHATONS), tarifs non publiés sur le site ; démos publiques asso.diacamma.org / syndic.diacamma.org ; communauté (forum/wiki) | https://www.diacamma.org/, https://www.sleto.net |
| Localisation | Plans comptables français (PCG général, asso simplifié/complet), belge, marocain | `financial/diacamma/accounting/system/{french,belgium,morocco}.py`, `asso/diacamma/asso/init_*.csv` |

Remarque technique : les montants des lignes d'écriture sont stockés en `FloatField` (`EntryLineAccount.amount`), contre `Decimal` ailleurs (Payoff, Bill) — fragilité d'arrondis que Lyvre n'a pas intérêt à reproduire.

---

## 2. Méthodes et données comptables

### Plan comptable et exercices
- `ChartsAccount(code, name, year, type_of_account, rubric)` : le plan comptable est **dupliqué par exercice** (FK `year`). `type_of_account` ∈ {actif, passif, capitaux, produit, charge, autres}. Le champ **`rubric`** sert à ordonner/regrouper le compte de résultat et à préciser la nature du don sur les reçus fiscaux. Boutons « Initiaux » (plan type), « Importer » (plan N-1), fusion de comptes (`ChartsAccountMerge`), renumérotation propagée aux lignes. (`financial/diacamma/accounting/models.py:768`, `docs/fr/fiscalyear.rst`)
- `FiscalYear(begin, end, status, is_actif, last_fiscalyear, folder, prefix)` : états **en création → en cours → terminé** (`STATUS_BUILDING/RUNNING/FINISHED`). Un exercice est lié à un **dossier du gestionnaire documentaire** où sont archivés les documents officiels (rapports de clôture, reçus, appels de fonds) ; bouton « Contrôle » vérifiant leur présence. Préfixe d'exercice pour la numérotation. (`models.py:300`)
- Clôture : `check_before_close`, `close()`, `finalize_year()` ; toutes les écritures doivent être validées ; génération de l'écriture de résultat et des **écritures de solde des tiers** (`_create_thirds_ending_entry`) ; compte 88999999 « Résultat en instance d'affectation ». Ouverture N+1 : « Report à nouveau » (`run_report_lastyear`, `import_lastyear`) génère et valide l'écriture d'à-nouveaux dans le journal dédié, avec report du détail par tiers (`_create_report_third`), puis « Commencer ». Le journal d'à-nouveaux interdit les comptes de charges/produits. (`accounting/system/default.py`, `docs/fr/fiscalyear.rst`)

### Journaux, écritures et états
- `Journal(name, is_default)` avec 5 journaux système : Report à nouveau, Achats, Ventes, Règlements, Opérations diverses.
- `EntryAccount(year, num, journal, link, date_entry, date_value, designation, costaccounting, close)` : **brouillard** (`close=False`, modifiable/supprimable) → **validée** (`close=True`, numéro `num` et date de validation `date_entry` attribués, intangible). Correction par **contrepassation** (`reverse_entry`, `create_clone_inverse`). Validation par lot (`EntryAccountBatchClose`). (`models.py:1099`, `docs/fr/entity.rst`)
- `EntryLineAccount(account, entry, amount, reference, third, costaccounting, link, multilink)` : montant signé (débit/crédit calculés), tiers et code analytique **par ligne**.
- Aide à la saisie : bouton « Règlement » depuis une écriture de dette/créance → écriture de règlement pré-remplie et **lettrage automatique** ; alerte « vous avez probablement saisi un avoir » sur sens inhabituel.
- **Écritures modèles** `ModelEntry` / `ModelLineEntry` (journal, libellé, analytique, lignes compte/tiers/montant) pour saisie répétitive. (`models.py:1741`)
- **Import d'écritures** CSV/ODS/XLS avec mapping de colonnes et contrôle d'équilibre (`EntryAccountImport`).
- Recherche multicritère avec **critères sauvegardés** (`XferSavedCriteriaSearchEditor`), exports PDF/CSV/ODS de tous les listings.

### Tiers et lettrage
- `Third(contact)` lié à un contact Lucterios (personne physique ou morale), champs personnalisés `ThirdCustomField`, et **plusieurs comptes auxiliaires** par tiers via `AccountThird(third, code)` (client 411, fournisseur 401, salarié, associé…). (`models.py:77, 235`)
- **Lettrage** : `AccountLink(letter, date_max)` ; conditions : même compte de tiers, équilibre débit/crédit, même exercice non clôturé — ou **lettrage inter-exercices temporaire** (suffixe « & », champ `multilink`) régularisé à la clôture/report à nouveau. Filtres écritures « lettrée / non lettrée », grand livre « non lettrées seulement ». Les reçus fiscaux s'appuient sur le lettrage pour prouver le paiement. (`docs/fr/entity.rst`, `models.py:978, 1040`)

### Analytique, budget
- `CostAccounting(name, description, status ouvert/clôturé, last_costaccounting, is_default, year)` : **codes analytiques** (un seul axe, pas de ventilation d'une ligne sur plusieurs codes, d'après la doc), optionnellement **obligatoires** sur toutes les lignes 6/7 ; imputation par lot ; report automatique d'un exercice à l'autre (`create_costs_from_lastyear`) ; rapports analytiques : compte de résultat, grand livre, balance par code, et rapport par période. (`models.py:645`, `views_reports.py:745-973`, `docs/fr/costaccounting.rst`)
- `Budget(year, cost_accounting, code, amount)` : budget **par compte, par exercice ou par code analytique** ; import depuis réalisé N-1 (`BudgetImport`) ; le budget figure dans le bilan, le compte de résultat et les rapports analytiques (réalisé vs prévisionnel). (`models.py:1871`, `views_budget.py`)

### Rapports
Bilan, compte de résultat (ordonné par rubriques, colonne budget), grand livre (général/auxiliaire, filtre non-lettrées), balance (option détail par tiers = balance mixte générale-auxiliaire), listings journal. Les rapports de clôture sont **générés et archivés automatiquement en PDF** dans la GED ; réédition ultérieure avec filigrane « duplicata ». (`docs/fr/reporting.rst`)

### Export légal
Export de l'exercice au **format XML** conforme à la fiche descriptive DGFiP (XSD `french_fichedescriptive_6709.xsd`, mapping `french_accountexport.xml`) via `FiscalYearExport` — équivalent FEC en version XML plutôt que texte. (`accounting/system/french.py:191`, `views_admin.py:255`)

### Règlements, banques, chèques (module payoff)
- `Supporting(third, is_revenu)` : classe abstraite « justificatif payable » héritée par Bill (facture), TaxReceipt, CallFunds, Expense, Owner → **un seul moteur de règlement** pour toutes les créances/dettes ; `total_payed`, `total_rest_topay`.
- `Payoff(supporting, date, amount, mode, payer, reference, entry, bank_account, bank_fee, linked_payoff)` ; modes : espèces, chèque, virement, CB, autre, **prélèvement**, interne ; **répartition d'un paiement multi-justificatifs** par ratio ou par date (`REPARTITION_BYRATIO/BYDATE`) ; frais bancaires imputés automatiquement. (`payoff/models.py:475`)
- `BankAccount(designation, reference/RIB, account_code, bank_journal, temporary_account_code, temporary_journal, fee_account_code)` : **compte d'attente** optionnel (ex. 511 « chèques à encaisser »).
- **Bordereaux de remise de chèques** `DepositSlip(bank_account, date, reference, status)` + `DepositDetail(payoff)` : en création → clôturé (impression officielle, sinon filigrane « NON VALIDÉ ») → validé (crédit constaté ; écriture compte d'attente → banque générée). Sert aussi aux titres type chèques-vacances/bons. (`payoff/models.py:773`, `docs/fr/deposit.rst`)
- `PaymentMethod(paytype, bank_account, extra_data)` : virement, chèque, **Stripe, PayPal, Monetico (CM-CIC), HelloAsso, URL de paiement en ligne** ; liens de paiement insérés dans les courriels de factures/devis ; notification de retour (IPN) qui **crée automatiquement le règlement** ; journal `BankTransaction` des notifications. (`payoff/payment_type.py`, `views_externalpayment.py`)
- **Pas de rapprochement bancaire** ni d'import de relevés (aucune occurrence OFX/CAMT/« rapprochement » dans le code) : le pointage se limite au lettrage des tiers et aux bordereaux.

### Facturation (module invoice)
- `Bill(Supporting)` avec `bill_type` ∈ **panier, devis, commande, facture, avoir, reçu** et `status` FSM ∈ en création, validé, annulé, archivé ; `parentbill` (chaîne devis → commande → facture → avoir), `categoryBill`, `cost_accounting`, `entry`. Comptabilisation automatique à la validation. (`invoice/models.py:941`)
- `CategoryBill` : catégories de facturation avec **numérotation propre et préfixe**, modèles d'impression distincts (pré-vente / soldé), objet+message courriel, moyens de paiement proposés, workflow. (`models.py:788`)
- `Article(reference, designation, price, unit, sell_account, vat, stockable, categories, accountposting)` + `MultiPrice` (**grilles tarifaires selon critère sauvegardé**, ex. tarif adhérent/non-adhérent), `AutomaticReduce` (**remises automatiques** par catégorie, valeur/%, nombre d'occurrences, filtre de clients), `RecipeKitArticle` (**kits/nomenclatures**), `Provider` (références fournisseurs), `AccountPosting` (code d'imputation : compte de vente + analytique + compte de tiers de provision).
- `Vat(name, rate, account)` ; régime TVA « non applicable » / « simple » au niveau de l'exercice (`VAT_ARRANGEMENTS_*`) ; masques 4456/4457/4452. **Pas de déclaration CA3** ni d'état de TVA dédié.
- **Stock** : `StorageArea`, `StorageSheet` (réception/sortie, fournisseur, réf. facture), `ArticleSituation`, `InventorySheet` (inventaire avec régularisation automatique). (`docs/fr/stock.rst`)
- **Facture électronique (réforme 2026)** : génération **Factur-X et UBL** (`invoice/einvoice.py` via `digital_invoice`) ; connecteur **PDP selon l'API AFNOR « flow » + annuaire** (préconfiguré SuperPDP, sinon URL personnalisée) : dépôt de flux, recherche/réception de factures fournisseurs (`ImportEInvoice`), **statuts de cycle de vie CDAR** (refus `EInvoiceRefuseInvoicing`), recherche d'entreprise par SIREN/SIRET dans l'annuaire. (`accounting/einvoicing_flow.py`, `accounting/views_invoicing.py`)
- Espace client : `CurrentBill` / `CurrentCart` — un utilisateur connecté (adhérent) voit **ses factures, les paie en ligne, accepte un devis en ligne** (`InvoiceValidQuotation`) et peut remplir un **panier d'achat** (centrale d'achat). (`invoice/views_summary.py`)
- Statistiques de facturation, contrôle de cohérence facture/comptabilité (`BillAccountChecking`).

### Immobilisations
Aucun module d'immobilisations/amortissements (seules les classes 2/28 existent dans le plan). Côté syndic, `Expense.expensetype` distingue dépense / **avoir**.

---

## 3. Fonctionnalités par domaine

### Contacts (lucterios-contacts)
Personnes physiques/morales, fonctions et responsabilités (`Responsability`), types de structure, **champs personnalisés** sur tout objet, codes postaux, **possessions** (animaux, véhicules… avec champs perso — utile clubs équestres, karting), étiquettes et listings PDF/CSV/ODS, recherches sauvegardées.

### Adhérents, cotisations, saisons, activités, licences (diacamma-asso / member)
- `Season` (courante, découpée en périodes et 12 mois, chevauchement possible), `Period`, `SubscriptionType` (durée annuelle/périodique/mensuelle/calendaire, **articles facturables** liés), `Activity`, `Team` (équipes/cours), `Age` (catégories d'âge), `Document` (**pièces à fournir par saison** : certificat médical, autorisation parentale…) cochées par adhérent (`DocAdherent`).
- `Adherent(Individual)` : numéro, date/lieu de naissance ; gestion **par famille** (structure morale « famille », facture familiale).
- `Subscription(adherent, season, subscriptiontype, bill, begin/end_date, status, prestations)` : états **en attente (demande en ligne à modérer) → en création (devis) → validée (facture) → annulée / radiée** ; chaque cotisation génère un devis puis une facture → la compta est alimentée par la facturation.
- `License(subscription, value, team, activity)` : **numéros de licence fédérale** par activité/équipe.
- `Prestation` / `TeamPrestation` : options (cours, équipes) ajoutées à la cotisation avec leur article et multi-prix.
- **Renouvellement en masse** (même cotisation, même licence) avec envoi des devis par courriel, liste des « cotisations à rappeler », adhérents dont l'adhésion expire dans N jours.
- **Accès adhérent** : création de comptes de connexion par adhérent ou sur demande, groupe de droits « adhérents actifs » retiré si non renouvelé ; demande de cotisation en ligne.
- Statistiques par saison (ville, genre, durée), étiquettes, import d'adhérents (`CommandManager`).

### Événements, examens, stages (event)
`Event(activity, date, date_end, event_type examen/stage-sortie, default_article membre/non-membre, cost_accounting, status)`, `Organizer` (dont responsable), `Participant(contact, article, reduce, bill, degree_result)` ; à la validation, **facturation automatique des participants** et, pour un examen, **mise à jour des grades** `Degree(adherent, degree, subdegree, date, event)` avec `DegreeType`/`SubDegreeType` par activité (arts martiaux, danse, natation…). Statistiques de grades.

### Dons et reçus fiscaux
`TaxReceipt(Supporting)(num, fiscal_year, year, entries, date)` : génération annuelle par tiers à partir des **écritures validées sur les comptes de produits paramétrés, lettrées (donc réglées), réglées dans l'année civile** ; numéro unique par année ; nature du don déduite de la rubrique du compte ; **abandon de frais** et **abandon de revenus/produits** (modes `PAYOFF_MODE_FEE/REVENU`) ; PDF de simulation, validation définitive, envoi par courriel, archivage PDF dans la GED (dossier par année). (`member/models.py:2006`, `docs/fr/taxreceipt.rst`)

### Facturation
Voir §2 : panier → devis → commande → facture → avoir, catégories et numérotations multiples, multi-prix, remises automatiques, kits, stock/inventaire, paiement en ligne, Factur-X/UBL, connexion PDP.

### Documents (lucterios-documents)
GED avec dossiers/sous-dossiers et **droits par dossier**, vignettes, éditeur intégré, historique créateur/modificateur, recherche multicritère, **liens de téléchargement publics** partageables, archivage automatique des documents officiels (rapports de clôture, reçus, appels de fonds, factures).

### Publipostage / mailing (lucterios-mailing)
`Message` à destinataires définis par **requêtes de contacts ré-exécutées à l'envoi**, pièces jointes ou **liens de partage** vers la GED, sortie **courrier PDF personnalisé** ou courriel ; `EmailSent` avec succès/erreur, **suivi d'ouverture** (`nb_open`, `last_open_date`) ; **envoi de SMS** (choix du champ téléphone, compteur de caractères).

### Syndic de copropriété (diacamma-syndic / condominium)
`PropertyLot` (lots, **tantièmes généraux** + clés secondaires via champs perso), `Owner(Supporting)` et `OwnerContact`/`OwnerLink` (indivisaires, locataires…), `Set` = **catégories de charges** (courantes/exceptionnelles, liées aux lots ou non, budget, compte de produit, analytique), `Partition` (répartition par copropriétaire), `RecoverableLoadRatio` (**charges récupérables** par compte, % pour régularisation locative), `CallFunds`/`CallDetail` (**appels de fonds** courants, exceptionnels, avances, emprunts, **fonds travaux ALUR**, appels semestriels récents), `Expense`/`ExpenseDetail`/`ExpenseRatio` (dépenses réparties par tantièmes), `Payment` ; rapports réglementaires **annexes 1 à 4** du décret 2005-240 (état financier, compte de gestion générale, opérations courantes, exceptionnelles) avec budgets N et N+1 ; plan comptable de copropriété (arrêté du 14/03/2005).

---

## 4. Écarts vs Lyvre (ce que Diacamma a et que Lyvre n'a pas, ou fait mieux)

| # | Fonctionnalité Diacamma | Intérêt pour une association / SCI | Source |
|---|---|---|---|
| 1 | **Lettrage des comptes de tiers** (`AccountLink`), y compris inter-exercices temporaire (« & ») régularisé à la clôture ; filtres lettrées/non lettrées ; lettrage automatique au règlement | Savoir quelles factures/cotisations/loyers restent impayés à partir de la compta elle-même ; préalable à des reçus fiscaux fiables et à une balance âgée | `financial/diacamma/accounting/models.py:978,1040`, `accounting/docs/fr/entity.rst` |
| 2 | **Bordereaux de remise de chèques** avec compte d'attente (511), statuts création/clôturé/validé, impression officielle, écriture de virement interne à la validation | Indispensable pour les associations qui encaissent cotisations/dons par chèque (et chèques-vacances, coupons sport) ; facilite le rapprochement remise ↔ relevé | `financial/diacamma/payoff/models.py:773`, `payoff/docs/fr/deposit.rst` |
| 3 | **Brouillard / validation des écritures** avec numérotation définitive à la validation et correction par contrepassation uniquement | Intangibilité des écritures exigée par les règles comptables et attendue par pour un expert-comptable/commissaire aux comptes ; Lyvre gagne à expliciter un état « validé » par écriture, pas seulement à la clôture | `accounting/models.py:1099` (`close`), `docs/fr/entity.rst` « Validation d'écritures » |
| 4 | **Écritures modèles** (`ModelEntry`) et **import d'écritures CSV/ODS/XLS** avec mapping de colonnes | Saisie rapide des écritures répétitives (salaires d'un intervenant, quote-part de charges) et reprise d'historique depuis un tableur ou un autre logiciel | `accounting/models.py:1741`, `views_entries.py:312` |
| 5 | **Plusieurs comptes auxiliaires par tiers** (`AccountThird`) et balance mixte générale-auxiliaire | Un même contact peut être adhérent (411), fournisseur (401) et associé (455) — fréquent en asso comme en SCI (associé qui avance des frais et paie un loyer) | `accounting/models.py:235`, `docs/fr/reporting.rst` « Balance » |
| 6 | **Archivage automatique des documents officiels en PDF** (rapports de clôture, reçus fiscaux, appels de fonds) avec réédition « duplicata » et contrôle de présence | Preuve figée de ce qui a été présenté en AG/envoyé au donateur ; Lyvre génère à la volée sans conserver la version opposable | `docs/fr/reporting.rst`, `FiscalYear.folder` (`models.py:315`), `condominium/docs/fr/report.rst` |
| 7 | **Rubriques de compte de résultat** (`ChartsAccount.rubric`) réutilisées dans les reçus fiscaux (nature du don) | Compte de résultat présenté selon les rubriques voulues par le CA/financeurs ; nature du don renseignée automatiquement sur le Cerfa | `accounting/models.py:790`, `member/docs/fr/taxreceipt.rst` |
| 8 | **Reçus fiscaux générés à partir de la compta lettrée** (écritures validées + réglées dans l'année), **abandon de frais et abandon de revenus** | Garantit qu'un reçu n'est émis que pour un don effectivement encaissé ; l'abandon de frais de bénévoles est un cas très courant | `asso/diacamma/member/models.py:1916-2179`, `member/docs/fr/taxreceipt.rst` |
| 9 | **Gestion des adhérents par saison** : types de cotisation, activités, équipes/cours, catégories d'âge, **licences fédérales**, pièces à fournir par saison, familles, renouvellement en masse, cotisation = devis puis facture | Clubs sportifs/culturels sans HelloAsso ou avec licences fédérales : suivi complet du membre et lien automatique cotisation ↔ facture ↔ règlement ↔ compta | `asso/diacamma/member/models.py:64-1916`, `member/docs/fr/{subscription,renew,config,prestation}.rst` |
| 10 | **Événements/stages/examens** avec facturation automatique des participants (tarifs membre/non-membre) et **suivi des grades** | Stages, sorties, passages de grades : inscription, facture et analytique de l'événement en un geste | `asso/diacamma/event/models.py:124-418`, `event/docs/fr/newevent.rst` |
| 11 | **Espace adhérent/client** : connexion par adhérent, consultation et **paiement en ligne des factures**, acceptation de devis en ligne, demande de cotisation en ligne modérée, panier d'achat | Réduit le travail du trésorier (relances, saisies) ; pour une SCI, accès d'un associé/locataire à ses quittances | `invoice/views_summary.py`, `member/views.py:1679` (`AskAdherentAccess`), `member/docs/fr/config.rst` |
| 12 | **Paiement en ligne natif multi-prestataires** (Stripe, PayPal, Monetico, HelloAsso, URL) avec lien dans le courriel et **création automatique du règlement** au retour IPN | Encaisser factures et cotisations par CB sans ressaisie ; Lyvre n'a que l'import Stancer/HelloAsso a posteriori | `financial/diacamma/payoff/payment_type.py:168-540`, `views_externalpayment.py` |
| 13 | **Répartition d'un paiement sur plusieurs justificatifs** (par ratio ou par date) et frais bancaires imputés automatiquement par compte bancaire | Un virement unique réglant plusieurs factures/cotisations d'une famille ; commissions de prestataires de paiement comptabilisées sans saisie | `payoff/models.py:486-499`, `BankAccount.fee_account_code` |
| 14 | **Facture électronique côté PDP** : connecteur API AFNOR flow + annuaire (SuperPDP ou URL), réception des factures fournisseurs, statuts CDAR (refus), recherche SIREN, émission Factur-X **et UBL** | Obligation de réception au 1er/09/2026 pour toutes les entreprises assujetties (associations fiscalisées, SCI à l'IS/TVA) ; Lyvre produit du Factur-X mais ne dialogue pas avec une PDP | `financial/diacamma/accounting/einvoicing_flow.py`, `accounting/views_invoicing.py:39-473`, `invoice/einvoice.py` |
| 15 | **Chaîne commerciale complète** : panier → devis → **commande** (avec acompte) → facture → avoir ; **catégories de facturation à numérotation/préfixe propres** et modèles d'impression distincts | Séparer les séries (buvette, stages, locations de salle) et gérer des acomptes sur commande | `invoice/models.py:788-978`, `invoice/docs/fr/create_bill.rst` |
| 16 | **Multi-prix par critère** (tarif adhérent / non-adhérent / famille) et **remises automatiques** (ex. 2e enfant –10 %) ; kits d'articles | Tarification sociale ou dégressive appliquée automatiquement, très courante dans les clubs | `invoice/models.py:188-249, 701, 2594` |
| 17 | **Stock et inventaire** (lieux de stockage, bordereaux réception/sortie, situation, inventaire avec régularisation) | Buvette, boutique, centrale d'achat d'équipements ; valorisation des stocks en fin d'exercice (31x/37x) | `invoice/models.py:109, 2324-2790`, `invoice/docs/fr/stock.rst` |
| 18 | **Analytique obligatoire paramétrable**, report des codes d'un exercice à l'autre, **budget par code analytique**, rapports analytiques (CR, grand livre, balance) avec colonne budget | Comptes rendus financiers par projet exigés par les financeurs (CERFA 15059) ; Lyvre a la ventilation multi-ligne (mieux), mais pas l'obligation ni la balance/grand livre par projet | `accounting/models.py:645, 1871`, `views_reports.py:745-973`, `docs/fr/costaccounting.rst` |
| 19 | **GED intégrée** avec droits par dossier et **liens de téléchargement publics** ; pièces jointes de mailing envoyées en liens | Partager PV d'AG, statuts, rapports avec les membres sans compte ; archivage centralisé des pièces | `documents/lucterios/documents/models.py`, `documents/docs/fr/shared_document.rst` |
| 20 | **Publipostage** courriel/courrier PDF/**SMS** sur requêtes dynamiques, rapport d'envoi et **suivi d'ouverture** | Convocations d'AG, relances, communication aux membres depuis l'outil de gestion | `contacts/lucterios/mailing/models.py:96-541`, `mailing/docs/fr/{mailing,sms}.rst` |
| 21 | **Champs personnalisés** sur contacts, tiers, articles, lots ; **possessions** ; recherches sauvegardées réutilisables (filtres de tarifs, remises, mailing) | Adapter l'outil sans développement (n° de licence externe, taille de maillot, cheval possédé…) | `contacts/lucterios/contacts/models.py:46-453, 817` |
| 22 | **Module syndic** : lots et tantièmes, catégories de charges courantes/exceptionnelles, appels de fonds (dont **fonds travaux ALUR**, emprunts, avances), **charges récupérables** par compte, annexes réglementaires 1-4, budgets N/N+1 | Pour une SCI propriétaire d'un immeuble en copropriété ou une asso gestionnaire : la logique **charges récupérables / tantièmes** peut inspirer la régularisation annuelle des charges locatives des baux Lyvre | `syndic/diacamma/condominium/models.py:67-1824`, `condominium/docs/fr/*.rst` |
| 23 | **Statistiques adhérents** (par ville, genre, durée) et de grades | Données demandées par les mairies/fédérations pour les subventions | `member/docs/fr/statistic.rst`, `event/docs/fr/statistic.rst` |
| 24 | **Installation bureau mono-poste** (Windows/macOS/Linux, lanceur graphique) en plus du mode serveur ; plans comptables belge et marocain | Petites associations sans serveur ni hébergeur ; associations hors France | diacamma.org, `core/lucterios/install/lucterios_qt.py`, `accounting/system/` |

### Points où Lyvre est en avance (pour mémoire)
Rapprochement bancaire (import OFX, synchro Qonto, suggestions, règles de catégorisation — **absent de Diacamma**), mode recettes/dépenses simplifié, assistant de clôture complet (CCA/PCA 486/487 avec extourne, fonds dédiés, affectation du résultat), FEC texte, ventilation analytique d'une ligne sur plusieurs projets, prévisionnel de trésorerie 12 mois, bénévolat valorisé (86/87), Cerfa 11580/16216, factures d'achat avec OCR/Factur-X entrant, baux et quittances, registre des parts SCI, rôles par structure dans une seule instance, interface React moderne, montants en Decimal, licence AGPL. Diacamma n'a ni immobilisations, ni déclaration de TVA, ni FEC texte, ni rapprochement bancaire.
