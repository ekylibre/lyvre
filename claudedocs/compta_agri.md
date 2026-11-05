# Besoins : comptabilité agricole et assistant des démarches dans Lyvre

> **Statut** : audit et expression de besoins (`/sc:brainstorm`, 03/11/2026). Pas de conception ni de code.
> **Objectif** : ajouter à Lyvre la gestion comptable d'une exploitation agricole et un assistant qui guide
> l'agriculteur chaque semaine dans ses démarches (TVA, fiscal, social, PAC).
> **Rapports d'audit** (détail et sources) dans `claudedocs/compta_agricole/` :
> - `audit_reglementation.md` : CGI art. 63-78, ANC 2020-04, TVA agricole, MSA, e-facturation ;
> - `audit_logiciels.md` : 13 logiciels et matrice des fonctionnalités ;
> - `audit_ekylibre_lexicon.md` : ce qu'on peut reprendre d'Ekylibre/onoma et de Lexicon ;
> - `audit_calendrier.md` : calendrier novembre 2026 → décembre 2027, fiches par échéance, règles d'applicabilité.
>
> **Suite** : questions tranchées (AGD1–AGD11, § 9) ; conception du lot AG1 validée (`claudedocs/design_compta_agricole.md`) ; prochaine étape `/sc:implement AG1.a`.

---

## 0. Sources de départ (fournies par l'utilisateur)

**Ressources en ligne**
- https://www.advyse.fr/comptabilite-agricole/
- https://hello.audit-cpa.com/secteur/agriculture/
- https://www.ouvretaferme.org/articles/?category=how-to

**Ekylibre, qui couvre une partie des obligations comptables agricoles**
- https://github.com/ekylibre/ekylibre
- https://ekylibre.org/fr/user-doc/chapitre5/

**Logiciels de compta agricole et concurrence**
- https://www.lafabriquedunet.fr/logiciels/gestion/comptabilite/comptabilite-agriculture (HTTP 403 : seuls des extraits de recherche ont été lus)
- https://fermegestion.fr/comptabilite-agricole.php
- https://www.comptabilite-agriculteur.fr/quel-logiciel-comptable-choisir-pour-gerer-son-exploitation-agricole/
- https://github.com/GMS64260/gleba

**Ressources complémentaires** : `claudedocs/compta_agricole/`
- règlement ANC 2020-04 ;
- CGI art. 63 à 78 (Légifrance, version du 03/11/2026) ;
- article SIC 384 ;
- brochures CSOEC 2026 « obligations comptables » et « quelle société » ;
- guide Isacompta 2024.

**Ressource externe retenue** : Lexicon (https://lexicon.osfarm.org) : API REST, catalogue de 54 jeux, serveur MCP public.

---

## 1. Synthèse de l'audit

### 1.1 Le cadre réglementaire en 6 points

1. **Trois régimes d'imposition (BA) qui changent tout.**
   - **Micro-BA** : moyenne triennale des recettes ≤ 129 200 € HT, abattement de 87 %, livre des recettes seulement.
   - **Réel simplifié** : jusqu'à 421 000 €. **Comptabilité de trésorerie** dans l'année, créances, dettes et stocks à la clôture. Liasse **2139**.
   - **Réel normal** : comptabilité d'engagement, liasse **2143**.
   - Pour un GAEC, les seuils sont multipliés par le nombre d'associés. Les seuils sont révisés tous les 3 ans : en 2026, des sources récentes divergent encore (120 000 / 391 000 € contre 129 200 / 421 000 €). **Ils doivent être des paramètres datés.**
2. **Un plan de comptes et des états propres** (règlement ANC 2020-04, qui complète le PCG).
   - **Stocks** : stocks agricoles détaillés (31111 à 31116), animaux à cycle long ou court (3112/3113), **avances aux cultures** (31141/31151), en-cours et produits (33x, 35x).
   - **Immobilisations** : biens vivants immobilisés (241 reproducteurs, 243 service, 246 plantations, 247 autres végétaux).
   - **Produits** : production autoconsommée (73), subventions d'exploitation détaillées (741 à 748), cession de biens vivants **en résultat d'exploitation** (757/657).
   - **Comptes divers** : conventions d'entraide (472), MSA (4311, 6451).
   - **États** : bilan et compte de résultat agricoles, et un **tableau des biens vivants** en annexe.
3. **Une évaluation spécifique des stocks et du vivant.**
   - Méthodes : coût réel, coût standard (barèmes), prix de détail moins une décote, ou méthode forfaitaire fiscale au réel simplifié.
   - Avances aux cultures : liste fermée des frais (art. 72 A).
   - Inventaire par lots d'animaux.
   - **Double valeur, comptable et fiscale**, en cas de blocage des stocks à rotation lente (72 B bis).
4. **Des dispositifs fiscaux que l'exploitant pilote sur plusieurs années.**
   - **DEP** (épargne de précaution) : barème selon le bénéfice, épargne de 50 à 100 %, réintégration sous 10 ans.
   - **Abattement jeune agriculteur** : 60 mois.
   - **Provision vaches** (73 A).
   - Moyenne triennale et étalement des revenus exceptionnels.
   - **Revenus accessoires** (seuils de 50 % et 100 000 €) : en société civile, un dépassement **impose l'IS**.
   - Plus-values (151 septies) et crédits d'impôt (bio, HVE, remplacement).
5. **Une TVA agricole à part, que la suppression du régime simplifié général au 01/01/2027 ne touche pas.**
   - **Remboursement forfaitaire (RFA)** pour les non-assujettis (seuil 46 000 €) : 3520, compte 741.
   - **Régime simplifié agricole (RSA)** :
     - acomptes au 1/5 de la TVA de l'année précédente les 5/5, 5/8, 5/11 et 5/2 (3525 bis), puis **CA12A** (3517-AGR) annuelle ;
     - sur option quinquennale, CA3 trimestrielle ou mensuelle, avec remboursement de crédit infra-annuel (3519).
   - Livres des ventes et des achats obligatoires.
6. **Social et e-facturation.**
   - **MSA** : l'assiette est réformée en 2026. Elle part du résultat fiscal, réintègre la DEP, l'abattement JA et le blocage des stocks, puis applique un abattement de 26 % encadré par un plancher et un plafond. Option entre moyenne triennale et revenus N-1. Les appels sont fixés par chaque caisse.
   - **E-facturation** : réception obligatoire depuis le 01/09/2026 ; émission et e-reporting au 01/09/2027 pour les exploitations assujetties.
   - **Autofacturation** : coopératives et laiteries émettent souvent les factures au nom du producteur.

### 1.2 Le marché

| Groupe | Logiciels | Forces | Limites |
|---|---|---|---|
| Fiscal complet, pour les cabinets | Isacompta/Agiris (≥ 35 €/mois), Pennylane agri (CA12A, 2139/2143 depuis 02/2026) | Liasse, DEP, simulation MSA | Pensés pour le cabinet, pas pour l'exploitant |
| Écritures générées depuis la ferme (AGPL) | Ekylibre, Ouvretaferme (0–30 € HT), Gleba | Écritures automatiques, FEC, CA3/CA12 (Ouvretaferme) | Pas de liasse, ni de DEP, ni d'échéancier |
| Simples, pour le micro-BA | FermeGestion (9,90 €/mois) | Recettes et dépenses, RFA | Pas de plan de comptes ni de liasse |
| Hors comptabilité | Mes Parcelles, Smag, FarmLEAP, Karnott | PAC, marges, matériel | — |

**Les manques du marché, qui sont des occasions pour Lyvre :**
1. **Aucun échéancier personnalisé** tiré du dossier (régimes, clôture, caisse MSA, aides demandées). Les dates n'existent qu'en PDF ou dans le calendrier générique d'impots.gouv. Aujourd'hui, ce sont des humains qui accompagnent : AFOCG, CER France, cabinets.
2. **Clôture guidée par l'exploitant** : inventaire, avances aux cultures, cheptel, créance PAC 441.
3. **Classement des aides** : classe 74 ou subvention 131, DJA mixte.
4. **Simulations de choix de régime** : micro-BA ou réel, RFA ou RSA, DEP.
5. **Banque automatique** : seuls Isacompta et Ekylibre l'ont. Lyvre a Qonto.
6. **Plusieurs structures dans un même outil** (GAEC, SCI foncière, GFA, association) : personne ne le fait. C'est le cœur de Lyvre.
7. **Assistant IA branché sur les données** : seul Gleba en a un (OpenAI avec MCP), sans fiscal ni social.

### 1.3 Ce que Lyvre a déjà (au commit `ebdea12`)

| Existant | Réutilisation agricole |
|---|---|
| Plans par référentiel (`Instance.chart` : asso, sci, societe), menus filtrés | Nouveau référentiel `agri` |
| Partie double, validation, verrouillage, lettrage, clôture, CCA/PCA, à-nouveaux | Socle commun |
| Mode **simple** recettes/dépenses (`bookkeeping = simple`, lot D), réservé aux associations | Livre des recettes du micro-BA |
| Immobilisations (days360 d'Ekylibre, composants, sortie) | Biens vivants immobilisés |
| Codes TVA par ligne, CA3 mensuelle (`data/ca3`, `vat_return.py`), verrouillage du mois déclaré | CA3 trimestrielle et mensuelle du RSA ; base de la CA12A |
| Moteur de règles (`data/rules.yml`, `rules_engine.py`), Qonto, OFX, rapprochement | Règles d'imputation agricoles, détection des virements ASP et MSA |
| Baux et révision par **indice des fermages** (`rent_revision.py`) | Fermages côté preneur et côté bailleur (SCI, GFA) |
| Projets (`journal_lines.project_id`), budget | Première base de l'analytique par atelier |
| FEC export et import (`fec_import.py`), Factur-X, plateforme agréée Qonto (SuperPDP prévu) | Reprise de dossiers Isacompta/ISTEA ; e-facturation agricole |
| Notifications, tâches en arrière-plan | Rappels de l'assistant |
| Cadrage de l'assistant (`doc/base_documentaire/`, non implémenté) : API Claude, outils qui appellent les services, règles YAML, recherche FTS5 | Base de l'assistant agricole |

**Absent** : stocks et inventaire, TVA hors CA3 (RFA, acomptes, CA12A), liasses BA, profil fiscal de la structure (forme, régimes, options datées), paramètres réglementaires datés, échéancier, assistant.

### 1.4 Ce qu'on reprend d'Ekylibre et de Lexicon

**Ekylibre et onoma** (AGPL-3.0 : on reprend les **méthodes et les données**, on **réécrit** le code) :
- les 85 numéros propres au plan agricole 2023 (`onoma/db/reference.xml`) ;
- **la correspondance entre comptes et postes des états agricoles** et les ratios (EBE, valeur ajoutée) : `config/accountancy/accountancy_mandatory_documents_fr_pcga2023.yml` ;
- le principe « le régime fiscal choisit le plan », qui va dans le profil ;
- l'écriture d'inventaire (comparaison entre le solde du compte 3x et l'inventaire, puis l'écart en 603x ou 71x) ;
- les états des biens vivants ;
- le choix du format du FEC selon le régime ;
- les importeurs de FEC Isacompta, Agrigest et ISTEA.

Ekylibre n'a **ni** RFA, **ni** CA12A, **ni** liasse BA, **ni** valorisation des stocks, **ni** échéancier.

**Lexicon** (API, MCP `POST https://lexicon.osfarm.org/mcp`, accès anonyme limité à 30 requêtes par fenêtre). Licences : données `master_*` en **CC-BY-SA 4.0**, avec attribution et partage à l'identique ; données publiques en Licence Ouverte 2.0.

| Jeu | Usage dans Lyvre |
|---|---|
| `chart_of_accounts` (1 595 comptes, dont 806 propres au plan agricole) | Construction de `plan_comptable_agri.json` (§ 3, AG1) |
| `variants` / `master_variant_categories` | Compte et **taux de TVA par défaut par catégorie d'achat** (engrais, aliments, semences, eau d'irrigation), durées d'amortissement |
| `legal_positions` | Formes juridiques et régimes admis, à la création de la structure |
| `productions`, codes cultures PAC 2017-2026, rendements, prix | Axes « atelier/production », **aide à la valorisation des récoltes en stock** |
| `rica` (ratios par type d'exploitation, OTEX), `budgets` | Références de marges et de ratios pour l'assistant |
| `enterprise_classifications` (NAF → OTEX), `enterprises` (SIRENE) | Typer l'exploitation dès la création (SIRENE déjà utilisé) |
| `cap_beneficiaries` (aides versées par l'ASP) | Contrôle des aides comptabilisées en 74x |
| `fuel_prices` (GNR) | Aide au remboursement de la TICPE |
| `weather`, `phytosanitary` | Contexte de l'assistant (calamités, registre phyto), hors comptabilité |

Absent de Lexicon et **à constituer dans Lyvre** :
- taux de TVA ;
- taux et calendriers MSA ;
- zones ICHN ;
- barèmes de valorisation des animaux ;
- calendrier fiscal BA ;
- seuils.

---

## 2. Objectifs et utilisateurs

### 2.1 Objectifs

- **O1** Tenir dans Lyvre la comptabilité d'une exploitation agricole au micro-BA, au réel simplifié ou au réel normal, à l'IR ou à l'IS, en EI ou en société (EARL, GAEC, SCEA, GFA, SAS).
- **O2** Produire les déclarations (préparées, pas télétransmises) :
  - TVA agricole : 3520, 3525 bis, CA12A, CA3 du RSA, 3519 ;
  - aide à la liasse 2139/2143 et au micro-BA ;
  - aide à l'assiette MSA.
- **O3** Guider la clôture propre à l'agriculture : inventaire, avances aux cultures, cheptel, aides PAC, DEP.
- **O4** Un **assistant hebdomadaire** qui sait ce que l'exploitation doit faire, quand et avec quelles données. Il détecte, prépare et rappelle ; il ne déclare jamais à la place de l'exploitant.
- **O5** Garder l'avantage de Lyvre : plusieurs structures (exploitation, SCI ou GFA foncier, association), banque automatique, coût bas, sources ouvertes.

### 2.2 Utilisateurs

| Rôle | Besoin principal |
|---|---|
| Exploitant en autocomptabilité (public type AFOCG) | Saisie guidée, résumé hebdomadaire, clôture pas à pas, simulations |
| Associé de GAEC ou d'EARL | Quote-part, abattement JA, DEP par associé |
| Expert-comptable ou centre de gestion (accès en lecture ou en révision) | FEC, balance, tableaux de passage, contrôles ; reprise d'un dossier Isacompta |
| Administrateur Lyvre | Paramètres réglementaires annuels (dates PAC, taux, seuils), vérifiés et sourcés |

---

## 3. Exigences fonctionnelles

Numérotation **AGn.m**. La priorité est donnée par la colonne « Lot » du § 7.

### AG0 Profil de l'exploitation et paramètres réglementaires datés

- **AG0.1 Profil fiscal et social de la structure**, avec dates d'effet :
  - forme juridique ;
  - IR ou IS ;
  - régime BA (micro, réel simplifié, réel normal) ;
  - régime de TVA : RFA, RSA avec acomptes, RSA trimestriel, RSA mensuel, plus un secteur non agricole éventuel au réel ;
  - exercice TVA civil ou aligné sur l'exercice comptable (CA12AE) ;
  - comptabilité de trésorerie ou d'engagement ;
  - caisse MSA, option d'assiette MSA, mensualisation ;
  - productions (grandes cultures, élevage par espèce, viticulture, maraîchage, arboriculture, bio) ;
  - demandeur PAC, n° PACAGE ;
  - employeur ;
  - irrigant, zone vulnérable, entrepositaire agréé.
- **AG0.2 Options datées** :
  - liste : RS ou RN sur option, IS, moyenne triennale (75-0 B), blocage des stocks (72 B bis), option RSA, option CA3 trimestrielle ou mensuelle, méthode forfaitaire des stocks ;
  - pour chaque option : date d'effet, durée, reconduction et **date limite de renonciation**, qui alimente l'assistant.
- **AG0.3 Associés** : en plus du module Associés existant, qualité d'exploitant, part des droits aux bénéfices, statut JA (date d'octroi de la DJA), entrée et sortie. Le nombre d'associés exploitants (plafonné à 4) sert de multiplicateur.
- **AG0.4 Profil prérempli à la création** à partir de SIRENE (forme, NAF), des tables NAF → type d'exploitation et formes juridiques de Lexicon, et des comptes eux-mêmes une fois l'historique saisi.
- **AG0.5 Contrôles de cohérence** :
  - micro interdit pour une société créée après 1997, sauf EARL unipersonnelle (69 D) ;
  - micro interdit pour les marchands de bestiaux et la biomasse (69 C, 69 E) ;
  - nombre d'associés compatible avec la forme (GAEC de 2 à 10, EARL de 1 à 10).
- **AG0.6 Paramètres réglementaires datés** :
  - contenu : seuils, barèmes (DEP, abattement JA), taux (RFA, TVA par nature), dates annuelles (date limite PAC, appels MSA par caisse, indice des fermages) ;
  - chaque valeur porte une période de validité, une **source** (URL), une date de vérification et un niveau de fiabilité : V vérifiée, R règle stable, A annuelle, I incertaine ;
  - **aucun seuil dans le code** ;
  - stockés dans des fichiers de données versionnés, à l'image de `data/ca3/2026.json`, avec une surcharge annuelle saisie par l'administrateur.

### AG1 Référentiel « Exploitation agricole » (plan, états, règles)

- **AG1.1 Plan `agri`** = PCG 2026 (référentiel `societe`) + comptes et subdivisions de l'**ANC 2020-04**, liste exhaustive dans `audit_reglementation.md` § 2.2.
  - **Construction** : CSV Lexicon `chart_of_accounts`, numéros 2023 d'onoma, puis vérification ligne à ligne face au règlement.
  - **Clé `usage` onoma** conservée pour les reprises Ekylibre et Isacompta.
  - **Attribution CC-BY-SA** dans le fichier.
- **AG1.2 Bilan agricole** :
  - à l'actif, biens vivants immobilisés et biens vivants et en-cours à cycle long ou court ;
  - au passif, un modèle « entreprise individuelle » (compte de l'exploitant) et un modèle « société ».
- **AG1.3 Compte de résultat agricole** :
  - ventes d'animaux, production stockée et immobilisée, autoconsommation (73), subventions 74x, cessions de biens vivants 757/657, achats d'animaux ;
  - **soldes intermédiaires** : production de l'exercice, valeur ajoutée, EBE (correspondances d'Ekylibre).
- **AG1.4 Annexe** : tableau des biens vivants et en-cours (valeurs nettes à l'ouverture et à la clôture, têtes ou hectares en option).
- **AG1.5 Règles d'imputation agricoles** :
  - dans `rules.yml`, un compte et un code TVA par défaut par catégorie, issus des catégories d'articles de Lexicon. Exemples : engrais → 60111 à 20 %, aliments du bétail → 60114 à 10 %, eau d'irrigation → 60615 à 5,5 % ;
  - avec les catégories Qonto ;
  - **contrôle de cohérence entre compte de vente et taux** (exemple : vin vendu à 5,5 % → alerte).
- **AG1.6 Contrôles propres au plan** :
  - cession d'un bien vivant en 775 au lieu de 757 ;
  - compte 472 (entraide) non soldé à la clôture : solde automatique vers 402 ou 412 ;
  - animal destiné à la vente en 24x.
- **AG1.7 ~~Comptabilité de trésorerie~~** : abandonnée (AGD10). Le réel simplifié se tient en engagement, comme le réel normal. Les régularisations de clôture agricoles (aides en 441, MSA en 4311, compensation 472) passent par les écritures d'inventaire existantes.
- **AG1.8 Micro-BA** : on étend le mode **simple** aux exploitations.
  - Livre des recettes journalier (HT, à l'encaissement).
  - Regroupement des ventes de 76 € ou moins par jour.
  - Totaux par trimestre et par année.
  - Recettes exclues identifiées : cessions, ICHN, primes d'équipement, remboursements d'entraide.
  - Livre des achats si l'exploitation est au RSA.

### AG2 TVA agricole

- **AG2.1 RFA, remboursement forfaitaire (3520)** :
  - ventes éligibles par **acheteur assujetti** et par taux (5,59 % ou 4,43 %, paramètres datés) ;
  - suivi des **attestations d'achats** (pièce jointe par client et par année) ;
  - calcul et état 3520 ;
  - écriture : créance contre 741 ;
  - échéance au 31/12 de N+1, dépôt conseillé avant le 1er mars ;
  - **alerte** quand la moyenne des recettes sur 2 ans dépasse 46 000 € (multiplié par le nombre d'associés en GAEC) : passage obligatoire au RSA.
- **AG2.2 RSA avec acomptes** :
  - acompte minimal = 1/5 de la TVA nette de l'année précédente ;
  - dispense si cette TVA est inférieure à 1 000 € ;
  - échéancier 5/5, 5/8, 5/11, 5/2, avec bulletin **3525 bis** prérempli ;
  - simulation de modulation ou de suspension, avec alerte si l'écart dépasse 30 % ;
  - écriture de l'acompte (44581).
- **AG2.3 CA12A (3517-AGR)** :
  - calculée depuis le grand livre, comme la CA3 actuelle ;
  - CA par taux, TVA sur immobilisations et sur autres biens et services, régularisations, imputation des acomptes, crédit remboursable à partir de 150 € ;
  - **CA12AE** pour un exercice décalé, avec la période intercalaire ;
  - liquidation en brouillard jusqu'au dépôt, puis verrouillage, comme la CA3 ;
  - correspondance entre cases et formulaire datée dans `data/ca12a/<année>.json`.
- **AG2.4 RSA trimestriel ou mensuel** :
  - réutiliser la CA3 et ajouter la **périodicité trimestrielle** (échéance au 5 du mois qui suit le trimestre) ;
  - **3519** pour le remboursement de crédit : 760 € par trimestre ou par mois, 150 € par an ;
  - l'assistant signale l'intérêt de l'option quand l'exploitation investit beaucoup, puisque le régime des acomptes ne permet aucun remboursement en cours d'année.
- **AG2.5 Livres obligatoires du RSA** :
  - livre des ventes : exonéré, intracommunautaire, export, taxable, par taux ;
  - livre des achats : immobilisations ou autres, **y compris les achats sans droit à déduction**.
- **AG2.6 Taux par nature de produit agricole** : table datée (5,5 %, 10 %, 20 %) ; les points discutés sont marqués « à valider » (§ 8).
- **AG2.7 Secteur non agricole** (gîte, transformation, négoce) :
  - TVA de droit commun, CA3 trimestrielle depuis la suppression du régime simplifié en 2027 ;
  - déclarations séparées pour un même dossier.

### AG3 Aides PAC et subventions

- **AG3.1 Registre des aides** :
  - par dossier : campagne, dispositif (aide de base, redistributif, écorégime, couplées animales ou végétales, ICHN, MAEC, bio, aide JA, assurance récolte, FranceAgriMer, région) ;
  - montant demandé, notifié et versé (avance en octobre, solde en décembre) ;
  - **date limite de demande de paiement** (investissements).
- **AG3.2 Classement comptable proposé** : 742 à 748 selon la nature, **131/139 pour les subventions d'investissement** avec reprise au rythme de l'amortissement. **Ventilation de la DJA mixte** (part exploitation, part investissement, prorata). Correspondance « à valider » par un expert-comptable.
- **AG3.3 Rattachement à l'exercice** (AGD19) :
  - au réel, simplifié ou normal (toujours en engagement, AGD10) : produit acquis à la **date limite de dépôt** de la demande de la campagne (PCG art. 618-6) ; à la clôture, la quote-part non encaissée passe en produit à recevoir, **débit 441, crédit 745** ; la règle fiscale suit (CGI art. 38 et 72), et la méthode est permanente ;
  - au micro-BA, à l'encaissement, sans produit à recevoir.
- **AG3.4 Rapprochement bancaire** : un virement ASP, DRFIP ou FranceAgriMer est reconnu (libellé), proposé contre la créance ou le dossier, et le dossier est mis à jour.
- **AG3.5 Contrôle** : montants versés selon le jeu public `cap_beneficiaries` (Lexicon) par SIREN et par année, comparés aux comptes 74x. Information seulement, sans cumul entre années.
- **AG3.6 (option, plus tard)** : import de la déclaration Telepac (îlots, parcelles, cultures) pour l'assolement et l'analytique (modèle des imports Ekylibre v2015 à v2025).

### AG4 Inventaire de clôture : stocks et avances aux cultures

- **AG4.1 Écran d'inventaire** :
  - par catégorie : approvisionnements 3111x, animaux 3112/3113 par lot, avances aux cultures 31141/31151, en-cours 331x, produits 351x/355x ;
  - saisie des quantités, de l'unité et de la valeur unitaire ;
  - **feuilles de comptage jointes**.
- **AG4.2 Méthodes de valorisation par ligne** :
  - coût réel (CUMP ou PEPS) ;
  - coût standard (barème saisi ou importé) ;
  - prix de détail moins une décote par catégorie ;
  - **méthode forfaitaire fiscale** au réel simplifié (taux de décote : paramètre « à valider ») ;
  - **refus du prix de détail pour les avances aux cultures**.
- **AG4.3 Aide à la valorisation** : prix et rendements de Lexicon par production et par département, et cotations UE, proposés et non imposés.
- **AG4.4 Avances aux cultures** :
  - fiche « culture en terre à la clôture » (production, surface, campagne) ;
  - charges rattachées dans la **liste fermée de l'art. 72 A** : semences, engrais, traitements, façons culturales, matériel ;
  - charges proposées depuis les factures d'intrants saisies, que l'utilisateur coche.
- **AG4.5 Écriture d'inventaire** :
  - variation 3x contre 603x (approvisionnements) ou 713x (produits et en-cours) ;
  - **contrepassation ou reprise à l'ouverture** si le stock n'est pas permanent ;
  - dépréciation 39x et 68173 si besoin.
- **AG4.6 Double valeur** : valeur comptable et **valeur fiscale** (stock bloqué 72 B bis, méthode forfaitaire), avec l'écart reporté au tableau de passage fiscal (AG6.3).
- **AG4.7 Au micro-BA** : pas d'inventaire ; l'écran est masqué.

### AG5 Biens vivants immobilisés

- **AG5.1 Immobilisations biologiques** :
  - nature : 241 reproducteurs, 243 service, 246 plantations pérennes (vignes, vergers), 247 autres ;
  - **gestion par lot** : espèce, classe d'âge, nombre de têtes, entrées et sorties partielles.
- **AG5.2 Cycle de vie** :
  - immobilisation en cours (234x) pour un animal ou une plantation en croissance, puis **mise en service** par production immobilisée (7222/724) ;
  - amortissement (2841/68114) et dépréciation (294/68164) ;
  - **cession en 757/657** ;
  - mortalité, sinistre et **abattage sanitaire** (indemnité, exonération 75-0 D avec réinvestissement sous 2 ans).
- **AG5.3 Contrôle** : un reproducteur en stock (3112) dans une structure soumise à l'ANC 2020-04 déclenche une alerte non bloquante. Le choix entre stock et immobilisation a des effets fiscaux à valider (§ 8).

### AG6 Fiscalité BA : résultat fiscal et dispositifs

- **AG6.1 Moyennes et changements de régime** :
  - moyenne triennale des recettes (encaissements pour le micro, créances acquises pour le réel), recettes à façon multipliées par 3, quotes-parts de sociétés (art. 70), multiplicateur GAEC ;
  - **alerte de changement de régime** à N+1 (micro → réel simplifié, réel simplifié → réel normal) ;
  - réintégration des créances au passage du micro au réel (72 E bis).
- **AG6.2 Simulation micro-BA ou réel** : bénéfice forfaitaire (abattement de 87 %, minimum 305 €) comparé au résultat réel estimé, avec la date limite d'option.
- **AG6.3 Tableau de passage** du résultat comptable au résultat fiscal (extra-comptable), avec :
  - DEP, abattement JA, provision 73 A, étalement 75-0 A, écart de stocks (AG4.6) ;
  - quote-part non déductible de la CSG ;
  - **répartition par associé** pour les 2042 C PRO.
- **AG6.4 DEP** :
  - calcul du plafond (barème daté) ;
  - **registre par exercice d'origine** : montant, épargne affectée (compte bancaire « DEP » repéré), utilisations, réintégrations, part exonérée pour aléa ;
  - contrôle du ratio d'épargne (50 à 100 %) ;
  - échéance du 10e exercice ;
  - calcul de la valeur ajoutée sur 3 ou 4 exercices (aléa économique) ;
  - reprise des anciennes DPI/DPA.
- **AG6.5 Abattement jeune agriculteur** (73 B) : 60 mois depuis l'octroi, calcul par tranches, cas de l'exercice d'inscription de la DJA, calcul par associé JA.
- **AG6.6 Provision vaches** (73 A) : registre par exercice, plafond multiplié par le nombre d'associés, minoration sans contrat EGALIM, reprise dans l'ordre d'ancienneté, échéance du 6e exercice.
- **AG6.7 Revenus accessoires** (art. 75) :
  - les comptes ou l'analytique des activités BIC/BNC sont repérés ;
  - ratio sur 3 années civiles TTC (50 % des recettes agricoles, 100 000 €) ;
  - **alerte d'IS de plein droit** pour une société civile ;
  - ventilation BA / BIC.
- **AG6.8 Aide à la liasse** :
  - correspondance entre comptes et cases des **2139 (A à E)** et **2143 (2144 à 2154)**, datée, en données ;
  - export PDF ou tableur à recopier ;
  - **pas d'EDI-TDFC** dans un premier temps ;
  - pour l'IS : liasse 2033 ou 2050 du référentiel société.
- **AG6.9 Plus-values** (151 septies) : régime court terme ou long terme par immobilisation et seuils d'exonération paramétrés. Une simulation suffit.
- **AG6.10 Crédits d'impôt** : bio (ratio de recettes en agriculture biologique), HVE, remplacement pour congés. Montants paramétrés, comptabilisation et répartition par associé.

### AG7 MSA (cotisations des non-salariés)

- **AG7.1 État « assiette sociale »** :
  - résultat fiscal BA, plus les réintégrations (DEP, abattement JA, blocage des stocks, à-valoir) ;
  - abattement de 26 % entre un plancher et un plafond (paramètres datés) ;
  - par associé exploitant ;
  - **comparaison entre moyenne triennale et revenus N-1** pour éclairer l'option.
- **AG7.2 Échéancier MSA paramétré par caisse** : appels provisionnels, solde, mensualisation. Le prélèvement est rapproché de l'échéance.
- **AG7.3 Ventilation des cotisations payées** : part déductible et CSG/CRDS non déductible, comptes 646 ou 6451 et 4311.
- **Hors périmètre** : calcul définitif des cotisations (barème de la caisse) et paie MSA (§ 6).

### AG8 Analytique par atelier et marges

- **AG8.1 Axe « activité »** (AGD7), sur le modèle d'Ekylibre et de Lexicon. Il est **distinct des Projets** existants.
  - **Activité** : famille (`activity_families` : cultures végétales, élevage, viticulture, transformation, services), production de Lexicon (espèce, cycle annuel ou pérenne).
  - **Nature** : principale, auxiliaire ou autonome.
  - **Campagne** : une activité est suivie par campagne (activité × campagne). Une campagne peut chevaucher deux exercices.
  - **Ligne d'écriture** : rattachée à une activité × campagne.
  - **Mesure physique** : surface ou effectif par campagne, qui sert aux ratios par hectare ou par tête.
  - **Code analytique Isacompta** de l'activité, conservé pour les imports `.ISA` (AG10.7) et les échanges avec les cabinets.
- **AG8.2 Répartition des activités auxiliaires** (matériel, bâtiments, charges communes) sur les activités principales, par clé : pourcentage, surface, marge brute. Les pourcentages sont ramenés à 100.
- **AG8.3 Marge brute par atelier** (produits et aides couplées moins charges opérationnelles), par hectare ou par tête, comparée aux références du RICA ou aux budgets types de Lexicon (information).

### AG9 Assistant des démarches (hebdomadaire et conversationnel)

Il s'inscrit dans le cadrage `doc/base_documentaire/` : API Claude, outils qui appellent les services, propositions **en brouillon seulement**.

- **AG9.1 Base d'échéances** :
  - une fiche par échéance (TVA, fiscal, MSA, PAC, filières, baux, sociétés, e-facturation), environ 40 fiches dans `audit_calendrier.md` ;
  - chaque fiche porte : organisme, **règle d'applicabilité** sur le profil AG0, date ou règle de calcul (jours ouvrés, fériés, clôture décalée), données comptables nécessaires, pièces, pénalités, lien officiel, **fiabilité** ;
  - format en données (YAML), versionné.
- **AG9.2 Calcul des dates** :
  - calendrier des jours fériés français et règle de report ;
  - table des dates selon la clôture (liasse à C + 3 mois, plus 15 jours en EDI ; CA12AE le 5 du 5e mois ; AG à C + 6 mois) ;
  - une échéance de fiabilité A **sans paramètre de l'année** affiche la date de repli avec la mention « date à confirmer ».
- **AG9.3 Échéancier de l'exploitation** :
  - vue liste et vue calendrier ;
  - chaque échéance a un statut : à venir, à préparer, prête, faite, en retard ;
  - le passage à « faite » est manuel ou **automatique par rapprochement** : paiement SIE, MSA ou DGFiP reconnu, déclaration Lyvre validée ;
  - export iCal en option.
- **AG9.4 Résumé du lundi**, dans l'application et **par e-mail via Brevo** (AGD3), en 4 blocs :
  1. **En retard**, avec la pénalité estimée ;
  2. **Cette semaine**, avec le montant estimé à partir des comptes et un bouton d'action (« préparer le 3525 bis », « ouvrir la CA12A », « ouvrir telepac ») ;
  3. **À préparer** (J+8 à J+45) : données manquantes détectées, par exemple « inventaire non saisi », « 3 relevés non rapprochés », « attestations RFA manquantes pour 2 clients » ;
  4. **À vérifier cette année** : paramètres annuels non confirmés.
- **AG9.5 Détections automatiques** :
  - changements de régime (RFA → RSA, micro → réel, réel simplifié → réel normal, revenus accessoires → IS) ;
  - crédit de TVA remboursable ;
  - virement ASP non rattaché ;
  - BA estimé supérieur de plus de 10 % à la base du prélèvement à la source (modulation) ;
  - fermage à indexer au 1/10 et avis d'échéance J-15 (Saint-Michel, Saint-Martin) ;
  - échéance d'une DEP, fin de la période JA, Certiphyto à moins de 6 mois de l'expiration ;
  - date limite de renonciation à une option (AG0.2).
- **AG9.6 Checklists guidées** : clôture (J-30 à J+60), campagne PAC (avril–mai), mois fiscal de mai, automne. Chaque étape renvoie vers l'écran Lyvre concerné.
- **AG9.7 Conversation**, proposée comme une **nouvelle intégration « Assistant Claude »** (AGD6). Elle s'active par instance dans les Intégrations, comme Qonto ou Brevo, avec son propre réglage (clé, modèle, quota). Sans l'intégration, l'échéancier et le résumé du lundi (AG9.1 à AG9.6) fonctionnent quand même :
  - questions en langage naturel sur le dossier (« combien dois-je verser le 5 février ? », « dois-je passer au RSA ? ») ;
  - outils en lecture : services de Lyvre (comptes, TVA, échéancier, profil) ;
  - recherche dans la base documentaire (fiches, textes cités, avec citations) ;
  - **MCP Lexicon** en option (prix et rendements, communes, entreprises) ;
  - actions limitées à des **brouillons** (écriture, acompte, checklist cochée) ou à la navigation.
- **AG9.8 Limites affichées** : l'assistant ne télédéclare pas, ne valide ni ne clôture et ne remplace pas l'expert-comptable. Toute réponse qui porte sur une règle de fiabilité I le dit.
- **AG9.9 Démarches hors comptabilité** (PAC, viticulture, eau, phyto, identification animale, nitrates) : **des rappels seulement** (AGD9), sans données à produire ni aide à la préparation. Elles s'activent selon le profil.

### AG10 E-facturation et pièces agricoles

- **AG10.1 Autofactures reçues** (coopérative, laiterie, négoce) via la plateforme agréée :
  - enregistrées comme **ventes** du producteur, avec acceptation ou contestation ;
  - **décomptes de coopérative** : apports, acomptes, compléments de prix, ristournes, parts sociales retenues (2621).
- **AG10.2 Codes TVA agricoles dans Factur-X** : mention « non assujetti, remboursement forfaitaire » pour le RFA.
- **AG10.3 E-reporting B2C** (vente directe, marchés) agrégé par jour et par taux, à préparer pour le 01/09/2027.
- **AG10.4 Reprise de dossiers** : import de FEC Isacompta, Agrigest ou ISTEA par l'import FEC existant, avec une table de correspondance de comptes agricoles.
- **AG10.5 ~~FEC « trésorerie » BA~~** : sans objet (AGD10), le FEC standard suffit.
- **AG10.6 Ancienne numérotation du plan agricole (1986)** : les dossiers des cabinets la suivent encore (§ 10.1).
  - Exemples : 704x pour les ventes d'animaux, 7011xxxx par culture, 713xxxxx par produit, 241/242 pour les reproducteurs adultes et jeunes, comptes sur 8 chiffres.
  - L'import FEC fait **correspondre l'ancienne numérotation à l'ANC 2020-04** grâce à la colonne `fr_pcga` de Lexicon et d'onoma.
  - Les sous-comptes par culture sont conservés et proposés comme axe « atelier ».
- **AG10.7 Import d'un export Isacompta `.ISA`** : format de transfert à enregistrements typés (VER, DOS, EXO, JOU, CPT, TVA, ANA, ECR, MVT, AFF, ECH, POI ; encodage DOS).
  - Il apporte ce que le FEC n'a pas : **les ateliers analytiques avec leur surface** (codes de culture Isacompta, par exemple 11111 « Blé tendre d'hiver », 341 « Luzerne »), les affectations analytiques des lignes, les échéances et les codes TVA.
  - Il alimente AG8 et le profil de l'exploitation.

---

## 4. Exigences non fonctionnelles

- **N1 Seuils, taux et dates en données datées, sourcées et vérifiées** (AG0.6), jamais en constantes. Une revue annuelle (janvier et avril) fait partie de l'exploitation du service.
- **N2 Aucun effet sur les instances asso, sci et societe** ; migrations sans perte. Le référentiel agri s'active par `Instance.chart = "agri"`.
- **N3 Aucune télétransmission** vers la DGFiP, la MSA ou telepac : Lyvre prépare, l'exploitant dépose. C'est dans la continuité de la CA3.
- **N4 Traçabilité** : déclarations et inventaires figés à la validation ; l'assistant conserve ses sources et la version des paramètres utilisés.
- **N5 Licences** :
  - code AGPL d'Ekylibre réécrit, jamais copié ;
  - données CC-BY-SA attribuées et partagées à l'identique dans les fichiers dérivés ;
  - aucun jeu Lexicon réservé ou non commercial embarqué.
- **N6 Lexicon** (AGD4) :
  - API en ligne avec une clé de membre OSFarm, gardée côté serveur ;
  - cache local ;
  - fonctionnement dégradé si le service est indisponible ;
  - référentiels structurants générés puis versionnés dans `data/`, pour qu'aucune saisie ne dépende du service.
- **N7 Assistant** :
  - coût par instance maîtrisé (quota) ;
  - données de l'exploitation envoyées à l'API Claude **seulement si l'intégration est activée** (AGD6, consentement) ;
  - conforme au doc 04 de la base documentaire.
- **N8 Saisie accessible à un non-comptable** : catégories métier avant les numéros de compte, et toujours un compte proposé.

---

## 5. Récits utilisateur et critères d'acceptation

- **US-A1** En tant qu'exploitante en EARL au réel simplifié et au RSA, je crée une instance « Exploitation agricole » et retrouve les comptes 31151, 60111, 741, 745, 757 et les états agricoles.
  *Critère : plan chargé, menus filtrés, bilan et compte de résultat agricoles équilibrés sur un jeu d'essai.*
- **US-A2** Le lundi 2 novembre 2026, mon résumé m'annonce l'acompte de TVA du 5/11 avec un montant de 1/5 de ma TVA nette 2025, le fermage de la Saint-Martin et le solde MSA de ma caisse.
  *Critère : montant égal à la CA12A 2025 / 5 ; pas d'acompte affiché si cette TVA est inférieure à 1 000 € ; date MSA lue dans le paramètre de la caisse, ou « à confirmer » sans lui.*
- **US-A3** En mai, je prépare ma CA12A 2026 depuis la comptabilité ; les acomptes versés sont imputés et le crédit est proposé en remboursement s'il atteint 150 €.
  *Critère : cases égales à un calcul de référence ; liquidation équilibrée ; année verrouillée après le dépôt.*
- **US-A4** Au 31/12, l'assistant de clôture me fait saisir l'inventaire (ammonitrate en stock, blé en avance aux cultures, 12 génisses) et passe les écritures de variation.
  *Critère : prix de détail refusé pour l'avance aux cultures ; variations 603x et 713x justes ; contrepassation à l'ouverture.*
- **US-A5** L'avance PAC reçue le 16/10 est reconnue et rattachée à la campagne 2026 ; à la clôture, le solde non encaissé est constaté en 441.
  *Critère : virement ASP proposé contre le dossier ; créance égale au montant notifié moins le versé.*
- **US-A6** En tant que maraîcher au RFA, je vois mes ventes à des assujettis par taux, je joins les attestations et j'obtiens mon 3520 avant le 31/12.
  *Critère : forfait = ventes éligibles × taux daté ; alerte si la moyenne sur 2 ans dépasse 46 000 €.*
- **US-A7** En tant qu'associé de GAEC, je simule la DEP et l'abattement JA et vois ma quote-part de BA à reporter sur ma 2042 C PRO.
  *Critère : plafonds multipliés par le nombre d'associés exploitants (au plus 4) ; ratio d'épargne contrôlé ; tableau de passage équilibré.*
- **US-A8** En tant qu'exploitant au micro-BA, je tiens mon livre des recettes et Lyvre compare mon forfait à un résultat réel estimé avant la date d'option.
  *Critère : forfait = moyenne sur 3 ans × 13 % (minimum 305 €) ; ICHN et cessions exclues.*
- **US-A9** Je demande à l'assistant « dois-je opter pour la CA3 trimestrielle ? » ; il répond à partir de mes investissements prévus et de ma TVA, cite la règle (remboursement trimestriel à partir de 760 €, option de 5 ans) et la date limite.
  *Critère : réponse citée ; aucune action autre qu'un brouillon ou une navigation.*
- **US-A10** Ma coopérative m'envoie une autofacture par la plateforme agréée ; elle arrive comme une vente, avec les parts sociales retenues.
  *Critère : vente en 7011 ou 7012, 2621 au débit pour les parts sociales, TVA au taux de la ligne.*

---

## 6. Hors périmètre (pour l'instant)

- Télédéclaration : EDI-TVA, EDI-TDFC, telepac, MSA.
- Paie agricole : DSN, TESA, TESA+. On la rappelle seulement.
- Calcul définitif des cotisations MSA.
- Traçabilité culturale : interventions, registre phyto, plan de fumure. Ces données sont dans Ekylibre ou Mes Parcelles ; l'assistant ne fait que rappeler les obligations (AGD9). Le connecteur Ekylibre (AG11) viendra plus tard.
- Stock permanent : l'inventaire de clôture suffit.
- Comptabilité forestière (revenu cadastral).
- Comptes des CUMA et des coopératives elles-mêmes.

---

## 7. Découpage proposé et ordre

| Lot | Contenu | Dépend de | Pourquoi dans cet ordre |
|---|---|---|---|
| **AG1** | Profil minimal (AG0.1, AG0.6) + référentiel agri (plan, états, règles) + **les trois régimes** (AGD1) : micro-BA en mode simple, réel simplifié en trésorerie, réel normal en engagement + jeu d'essai fictif (§ 10) | — | Socle ; sans plan, rien d'autre ne tient |
| **AG2** | TVA agricole : RFA, acomptes, CA12A, CA3 trimestrielle, 3519, livres | AG1, CA3 existante | Échéances trimestrielles toute l'année ; grosse attente du marché |
| **AG9a** | Échéancier et résumé hebdomadaire **sans conversation** : fiches, règles, dates, détections simples, rapprochement des paiements | AG0, AG2 | C'est le différenciateur ; utile même avant la clôture agricole |
| **AG3** | Aides PAC et subventions | AG1 | Avances en octobre et soldes en décembre : à la clôture, c'est déjà nécessaire |
| **AG4 + AG5** | Inventaire, avances aux cultures, biens vivants | AG1, immobilisations existantes | Indispensables à la première clôture au réel |
| **AG6 + AG7** | Résultat fiscal, DEP, JA, 73 A, accessoires, aide à la liasse, assiette MSA | AG4, AG3 | Avant la première liasse (mai) |
| **AG9b** | Intégration « Assistant Claude » : conversation, outils, base documentaire, MCP Lexicon | AG9a, base documentaire lot 2 | S'appuie sur des services déjà fiables |
| **AG8, AG10** | Analytique par activité × campagne, autofactures, e-reporting, FEC trésorerie, reprise Isacompta | AG1 | AG10 avant le 01/09/2027 |
| **AG11** (plus tard) | Connecteur Ekylibre | AG8, AG4 | AGD8 : après les lots précédents |
| **AG12** (feuille de route) | Mini-calculettes agricoles (§ 7 bis) : 21 calculettes (AGD12, AGD13), pour les utilisateurs connectés, sans données en direct | selon la calculette : AG0.6, AG2, AG3, AG5 à AG9 | Brainstorm du 04/11/2026, besoins complets ; chaque calculette peut suivre le lot dont elle dépend |

---

## 7 bis. AG12 Mini-calculettes (feuille de route, brainstorm du 04/11/2026)

**Idée.** Des outils de calcul courts, sur le modèle des calculettes d'Agriia (https://agriia.app/calculettes, 20 outils au 04/11/2026) :
- gratuits ;
- un formulaire de quelques entrées, puis un résultat ;
- **la méthode et ses limites** affichées ;
- les sources officielles citées ;
- un exemple chargeable ;
- le résultat copiable avec sa méthode.

On reprend le concept, pas le contenu ni la présentation du site.

**Ce que Lyvre ajoute** : une calculette peut être **préremplie par la comptabilité** de l'exploitation (recettes, charges, bénéfice, indice du fermage du bail). Elle peut aussi déboucher sur une action : une écriture en brouillon, la révision d'un bail, un rappel de l'échéancier (AG9).

### Exigences proposées

- **C1 Même gabarit pour toutes les calculettes** : entrées, résultat, détail du calcul, « méthode et limites », sources, date de vérification. Les paramètres viennent des **paramètres réglementaires datés** (AG0.6), avec leur pastille de fiabilité, jamais du code.
- **C2 Deux usages** :
  - *libre* : saisie à la main, sans écrire dans la comptabilité ;
  - *préremplie* : valeurs lues dans l'instance, chacune modifiable, avec son origine affichée.
- **C3 Pas d'écriture comptable directe.** Au plus une proposition (brouillon, révision, rappel), que l'utilisateur valide.
- **C4 Copie** du résultat et de la méthode (texte), plus un export PDF facultatif.
- **C5 Accès** : **utilisateurs connectés seulement** (AGD14), dans le contexte d'une instance. Pas de pages publiques.
- **C7 Pas de données en direct** (AGD15) : ni cours du jour, ni prix du GNR, ni météo. Un prix ou un cours se **saisit** dans la calculette (05, 12), avec la date et la source indiquées par l'utilisateur. Les référentiels de Lexicon (RPG, productions) restent utilisables par l'API avec la clé OSFarm (AGD4), comme pour la calculette 04.
- **C6 Assistant** (AG9b) : chaque calculette est aussi un outil que l'assistant peut appeler (« combien vais-je payer de MSA ? »).

### Calculettes d'Agriia relevées (04/11/2026)

La colonne « Lot Lyvre lié » est une proposition. **Décision AGD12 (04/11/2026) : toutes les calculettes sont retenues, sauf 01 (ZNT), 03 (météo), 18 (IFT) et 19 (IFT et moyenne Agreste)**, soit 16 calculettes. La colonne « AG12 » le note.

| # | Calculette (Agriia) | Ce qu'elle calcule | Lot Lyvre lié (proposition) | AG12 |
|---|---|---|---|---|
| 01 | ZNT par produit | Zone non traitée par produit (AMM, e-phy) | — (réglementation phyto) | non |
| 02 | Certiphyto : validité | Fin de validité, fenêtre de renouvellement | AG9 (rappel) | **oui** |
| 03 | Météo agricole | Pluie, vent, gel, delta T sur 7 jours | — | non |
| 04 | Carte RPG 2025 | Parcelles et cultures de la commune | AG8 (activités, surfaces) | **oui** |
| 05 | Prix du gazole et du GNR | Prix, indice GNR, écart de taxe | Gestion (carburant 60614, remboursement de TICPE) | **oui** |
| 06 | Calculatrice agricole | Surfaces, conversions, règle de trois, chantier, semis, prix de l'azote, enrouleur, pluie | Gestion (coûts) | **oui** |
| 07 | Zonages de ma parcelle | Zone vulnérable, BCAE, Natura 2000… | AG9 (rappels réglementaires) | **oui** |
| 08 | Micro-BA ou réel | Moyenne triennale, comparaison des assiettes | **AG6.2**, AG1.d (récapitulatif micro-BA) | **oui** |
| 09 | Solaire sur hangar | Production, puissance, chiffrage au tarif d'achat | Gestion ; revenus accessoires (AG6.7) | **oui** |
| 10 | Exonération TO-DE | Exonération des saisonniers | Social (paie, hors périmètre) | **oui** |
| 11 | Réfaction humidité | Poids retenu, réfaction, séchage | Gestion (ventes en coopérative, AG10.1) | **oui** |
| 12 | Prix d'équilibre blé | Seuil en €/t selon charges et rendement, comparé aux cours | **AG8** (marges par activité) | **oui** |
| 13 | Plafond DEP 2026 | Plafond de la DEP, règle GAEC, épargne | **AG6.4** | **oui** |
| 14 | Barème d'entraide | Coût d'un chantier selon le barème | AG1.d (conventions 472) | **oui** |
| 15 | Réviser son fermage | Nouveau loyer selon l'indice | **Baux existants** (`rent_revision.py`) | **oui** |
| 16 | Aides PAC 2026 | Simulation des aides (DPB, montants) | **AG3** | **oui** |
| 17 | Cotisations MSA 2026 | Estimation des cotisations par ligne | **AG7** | **oui** |
| 18 | Calculette IFT | Indice de fréquence de traitement | — | non |
| 19 | IFT et moyenne Agreste | Comparaison de l'IFT à une moyenne | — | non |
| 20 | Mise à jour du DUER | Document unique à jour ou non | AG9 (rappel) | **oui** |

**Calculettes propres à Lyvre** (AGD13, absentes d'Agriia), préremplies par la comptabilité :

| # | Calculette | Ce qu'elle calcule | Lot Lyvre lié | AG12 |
|---|---|---|---|---|
| 21 | Marge brute d'un atelier | Produits et aides couplées moins charges opérationnelles, par hectare ou par tête | AG8 | **oui** |
| 22 | Coût de revient d'un matériel | Amortissement, frais financiers, entretien, carburant ramenés à l'heure ou à l'hectare | Immobilisations, AG8 | **oui** |
| 23 | Amortissement | Plan linéaire ou dégressif d'un bien, y compris un bien vivant (days360 comme le registre) | Immobilisations, AG5 | **oui** |
| 24 | Remboursement forfaitaire agricole | Forfait sur les ventes à des assujettis, par taux, seuil de 46 000 € sur 2 ans | AG2.1 | **oui** |
| 25 | Acompte de TVA du RSA | 1/5 de la TVA de l'année précédente, dispense sous 1 000 €, intérêt de l'option trimestrielle | AG2.2, AG2.4 | **oui** |

### Questions ouvertes

- **Q-C1 → AGD12** pour le tri (16 retenues) ; **Q-C1 bis → AGD13** : les 5 calculettes propres à Lyvre (21 à 25) sont ajoutées.
- **Q-C2 → AGD14** : utilisateurs connectés seulement.
- **Q-C3 → AGD15** : pas de données en direct ; prix et cours saisis.

### Fiches pratiques pour l'assistant (ajoutées le 04/11/2026)

`claudedocs/compta_agricole/fiches_pratiques/` contient quatre guides PDF d'Agriia, d'octobre 2026, de 8 à 12 pages chacun, ajoutés par l'utilisateur.

| Fiche | Contenu | Usage dans Lyvre |
|---|---|---|
| `calendrier-administratif-2026-2027.pdf` | Échéances de septembre 2026 à août 2027 : PAC, MSA (caisses de Picardie et du Nord-Pas-de-Calais), fermage, impôts, TVA, phyto, nitrates, statut du conjoint ; sources numérotées | Base d'échéances de l'assistant (AG9.1), à recouper avec `audit_calendrier.md` |
| `checklist-pac-telepac-2027.pdf` | Connexion à Télépac, dates 2026 et 2027, préparation, écorégime, montants officiels, BCAE, après le dépôt | Fiches PAC de l'assistant (AG9, AG3), checklist d'avril (AG9.6) |
| `fermage-2026.pdf` | Indice 2026 et série depuis 2015, formule, minima et maxima, dates, règles du Code rural | Révision des fermages (baux, calculette 15), réponses de l'assistant |
| `couts-chantier-2026.pdf` | Barème d'entraide 2025-2026 (Oise) : méthode outil + tracteur ÷ débit + chauffeur ÷ débit, exemples | Calculette 14, conventions d'entraide (472) |

**Règle d'usage (proposée).** Ces guides sont des **sources secondaires** :
- l'assistant et les paramètres réglementaires citent la **source officielle** que chaque fiche indique (Légifrance, impots.gouv.fr, msa.fr, telepac, instruction technique, arrêtés), après vérification ;
- le texte des guides n'est pas recopié dans la base documentaire, puisque ce sont des publications d'un tiers ;
- les PDF restent un dossier de travail local (Q-C4).

**Apports à reporter**, une fois vérifiés sur la source officielle citée :
- **PAC 2027** : date limite de dépôt le **18 mai 2027**, dépôt tardif jusqu'au **14 juin 2027** (instruction technique du 8 juillet 2026), fin du droit à l'erreur le 20 septembre 2027, à confirmer. Cela lève le point 1 du § 4 d'`audit_calendrier.md`.
- **Avances PAC** : la fiche donne « jusqu'à **70 %** » des aides du 1er pilier en 2025 et 2026, alors que l'audit indiquait 75 % : **écart à vérifier**. L'ICHN est à 85 %.
- **MSA** :
  - la DRP est remplacée par le volet social de la déclaration de revenus ;
  - option pour l'**assiette annuelle** au plus tard le **30 juin** (5 ans, reconduite tacitement, effet au 1er janvier) ; dénonciation avant le **30 novembre**, puis **6 ans** d'attente. Cela lève le point SOC-03 de l'audit ;
  - **déduction de la rente du sol** : demande ou dénonciation avant le 30 juin, pour 1 an reconduit tacitement ;
  - modulation des appels 15 jours avant leur exigibilité ;
  - dates des caisses de Picardie et du Nord-Pas-de-Calais : 1er appel exigible le 27 mars et payable le 28 avril, 2e appel exigible le 11 septembre et payable le 13 octobre, solde émis le 16 novembre et payable le 8 décembre.
- **Statut de conjoint collaborateur** (échéance absente de l'audit) : il prend fin le **31 décembre 2026** pour les conjoints affiliés au plus tard le 1er janvier 2022, sauf dérogation. Le choix d'un statut se déclare au guichet unique.
- **Registre phytosanitaire électronique** au 1er janvier 2027 (règlement UE 2023/564, arrêté du 24 décembre 2025). Le papier reste toléré si les traitements sont convertis avant le 31 janvier de l'année suivante. Cela lève le point ENV-03.
- **Nitrates** : campagne culturale du 1er septembre au 31 août ; plan de fumure et cahier pour chaque îlot en zone vulnérable ; 30 jours pour inscrire un épandage.
- **Seuil du micro-BA** : 129 200 € HT pour 2026 à 2028, d'après la loi de finances pour 2026. Cela recoupe le paramètre `ba.micro.threshold_cents`, à passer de I à V après lecture du BOFiP (BOI-BAREME-000044).
- **Indices des fermages de 2015 à 2026** (arrêtés annuels) : ils peuvent préremplir l'historique des indices des baux (`rent_indices`), avec l'arrêté et le JO de chaque année comme source.
- **Taxe foncière refacturée au fermier** : 1/5 à défaut d'accord (Code rural, art. L415-3).

- **Q-C4 → AGD16** : les PDF de tiers de `claudedocs/compta_agricole/` (fiches Agriia, brochures CSOEC, règlement ANC, CGI exporté, article SIC, guide Isacompta) restent **hors git** (`.gitignore`). Seuls nos synthèses et les rapports d'audit sont versionnés.

## 8. Points à faire valider (expert-comptable ou source officielle)

Ils viennent des rapports, où ils sont marqués [À VALIDER] ou [I]. Ils ne bloquent pas le design, car ce sont des paramètres, mais **ils bloquent la mise en production des valeurs**.

Les réponses de l'expert sont visibles via "=>"

1. **Seuils** :
   - millésime d'application des seuils BA (129 200 / 421 000 / 517 000 € contre 120 000 / 391 000 €);
   => 129 200 / 421 000 / 517 000 € à partir du 01/01/2026 - https://chambres-agriculture.fr/actualites/actualite/benefices-agricoles-lactualisation-des-commentaires-fiscaux
   - seuils de l'abattement JA (67 600 € dans le CGI contre 58 552 € pour le CSOEC) ;
   => 67 600 € nouveau plafond depuis 01/01/2026
   - barème de la DEP 2026 et date de fin du dispositif.
   => fin 31/12/2028 - source : https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000051765352
2. **Stocks et biens vivants** :
   - taux de décote de la méthode forfaitaire des stocks ;
   => Taux général de 20 % : S'applique à la généralité des produits finis, des produits en cours de fabrication et des animaux. Taux majoré de 30 % : S'applique spécifiquement aux bovins ainsi qu'aux produits de la viticulture (vins, eaux-de-vie)
   - classement fiscal des reproducteurs (stock ou immobilisation) face à l'obligation comptable ;
   => 
   1. La règle comptable : Le critère d'affectation durableLe Plan Comptable Agricole impose une distinction claire basée sur la destination de l'animal :
    • Immobilisation corporelle (Classe 24) : Un animal reproducteur doit être immobilisé s'il est certain ou quasi-certain qu'il restera durablement dans l'exploitation (plus de 12 mois) pour servir de moyen de production (ex. : taureaux, béliers, étalons, vaches allaitantes, juments poulinières).
    • Stock (Classe 3) : Les animaux destinés à être vendus dans le cycle normal de l'activité (veaux, agneaux, animaux à l'engraissement) ou ceux dont la destination future reste incertaine à la clôture restent en stock.

   2. Comparatif fiscal : Stock vs Immobilisation


    Critère fiscal	Option Stock 🌾	Option Immobilisation 🐂
    Impact sur le résultat annuel	Aucune déduction annuelle. La valeur du stock entre dans le calcul du résultat net fiscal.	Amortissement annuel déductible (linéaire sur 4 à 8 ans selon l'espèce), ce qui réduit directement le bénéfice imposable.
    Valorisation au bilan	Évalué au coût de revient ou via une décote forfaitaire (selon le régime fiscal).	Enregistré à sa valeur d'entrée (prix d'achat + frais) ou à son coût de production (animal né sur l'exploitation).
    Régime fiscal à la revente	Le prix de vente est traité comme un produit d'exploitation classique, imposable à 100 %.	La vente génère une plus-value professionnelle, ouvrant droit à d'importants dispositifs d'exonération.

   - racine 231 ou 234 des en-cours de biens vivants.
   => Pour enregistrer les en-cours de biens vivants (actifs biologiques), c'est le compte 234 « Immobilisations corporelles en cours (biens vivants) » qu'il faut utiliser
   => Le compte 231 est quant à lui réservé exclusivement aux immobilisations corporelles en cours hors biens vivants (par exemple, un bâtiment agricole ou une machine en cours de construction)
3. **Aides et droits** :
   - correspondance entre aides PAC et comptes 742-748 ;
   => • Compte 742 (Subventions d'équilibre) : Il n'est généralement pas utilisé pour les aides PAC courantes. Ce compte sert à éponger un déficit global constaté, une situation plus fréquente dans le monde associatif ou pour des structures publiques locales que dans les exploitations agricoles pour les aides du premier et second pilier. Note : Depuis la réforme comptable, ce compte intègre les anciennes subventions d'équilibre qui étaient logées au compte 7715.
    • Compte 745 (Subventions d'exploitation versées par les organismes internationaux) : C'est le compte historique et privilégié pour la majorité des aides PAC. L'Union Européenne étant un organisme international, les comptables subdivisent ce compte (ex: 7451 pour le découplé, 7454 pour le couplé) pour isoler les différents flux Télépac.
    • Compte 748 (Autres subventions d'exploitation) : Utilisé pour des aides n'entrant pas strictement dans les autres catégories. Il peut servir pour des subventions d'exploitation purement locales, régionales, ou certaines aides d'urgence de l'État (comme le fonds d'urgence en cas de crise sanitaire ou climatique) si elles ne transitent pas par les enveloppes internationales de la PAC.
   - rattachement fiscal (droit acquis).
   => (question reformulée le 04/11/2026 : une aide découplée de la campagne N, soldée en N+1, se constate-t-elle en produit à recevoir à la clôture de N, et la règle fiscale suit-elle ?)
   => Oui. Comptable (PCG) : produit acquis à la date limite de dépôt de la demande (campagne N), quelle que soit la date d'encaissement ; à la clôture de N, débit 441 (ou créance rattachée), crédit 745 pour la quote-part non encaissée. Fiscal (réel normal ou simplifié) : le résultat fiscal suit le résultat comptable (CGI art. 38 et 72), la doctrine rattache l'aide à l'exercice où le droit est acquis ; méthode à tenir de façon permanente. Micro-BA : imposition à l'encaissement, pas de produit à recevoir.
   - *Tranché par le PCG 2026* (art. 618-1 à 618-6, constat de la conception du 03/11/2026) :
     - DPB en immobilisations incorporelles, à valeur nulle s'ils sont attribués, au coût s'ils sont acquis, amortis, avec une comptabilité matière hors bilan ;
     - aides annuelles en **produit à recevoir à la date limite de dépôt** de la demande.
   - Source du plan agricole retenue : Recueil PCG 2026, titre 5 (ANC 2020-04 modifié par l'ANC 2024-07).
4. **Taux de TVA** :
   - animaux de boucherie (5,5 % ou 10 %) ;
   => Le taux de TVA applicable aux animaux de boucherie et de charcuterie dépend de leur destination :
    • Taux réduit de 5,5 % : s'applique aux animaux vivants vendus en vue de la consommation humaine (par exemple, lors de la vente à un abattoir, à une boucherie ou à un industriel de l'agroalimentaire).
    • Taux de 10 % : s'applique lorsque les animaux sont cédés dans le cadre de la production agricole (par exemple, les ventes d'animaux vivants entre exploitants agricoles ou pour l'élevage/reproduction).
   - engrais et phytos utilisables en agriculture biologique ;
   - travaux agricoles ;
   - bois de chauffage ;
   - opérations exclues du RFA.
5. **RSA** :
   - durée de l'option sous 46 000 € ;
   - liste des assujettis obligatoires ;
   - calendrier exact de la CA3 trimestrielle ;
   - secteurs non agricoles après 2027 ;
   - exigibilité de la TVA en comptabilité de trésorerie.
6. **E-facturation** : situation des exploitants au RFA, périodicité de l'e-reporting au RSA.
7. **MSA** : liste exacte des réintégrations, plancher et plafond, transition 2026-2027, date de l'option annuelle, formulaire unique fiscal et social.
8. **Divers** :
   - structure du FEC de trésorerie BA ;
   - usage actuel du formulaire 2342 ;
   - obligation de l'ANC 2020-04 pour une EARL ou une SCEA à l'IS ;
   - CFE des activités accessoires.
9. **Calendrier** : date limite PAC 2027 (le 15/5 est un samedi), DRM, registre phyto électronique, flux d'azote, GNR.

---

## 9. Décisions et questions ouvertes

### 9.1 Décisions du 03/11/2026

- **AGD1 (Q2) Les trois régimes dès le premier lot.** AG1 couvre le micro-BA (livre des recettes en mode simple), le réel simplifié (trésorerie, puis créances et dettes de clôture) et le réel normal (engagement). Le § 7 est mis à jour.
- **AGD2 (Q1) Jeu d'essai fictif construit à partir de comptabilités réelles** (`~/projects/cultia_back/doc/spec/import_compta/`). Voir le § 10. Les données réelles ne sont jamais versionnées dans Lyvre ; seul le jeu fictif l'est.
- **AGD3 (Q4) Résumé du lundi dans l'application et par e-mail via Brevo** (AG9.4). La partie conversationnelle reste une option à activer par instance.
- **AGD4 (Q5) Lexicon par l'API en ligne avec une clé de membre OSFarm.**
  - La clé est configurée côté serveur, dans `.env` ou dans les intégrations. Elle n'apparaît jamais dans le navigateur ni dans les journaux.
  - Données vivantes (prix, rendements, productions, aides versées, MCP de l'assistant) : appel à l'API, avec un **cache local** et un fonctionnement dégradé si le service ne répond pas.
  - Référentiels structurants (plan de comptes, catégories d'achat) : **générés par un script** qui lit l'API, puis versionnés dans `data/` (même principe que `scripts/build_pcg_chart.py`). Une écriture comptable ne doit pas dépendre d'un service externe au moment de la saisie.
  - N6 est précisé dans ce sens.

### 9.2 Décisions complémentaires du 03/11/2026

- **AGD5 (Q3) L'utilisateur valide en tant qu'expert-comptable** les points du § 8, les correspondances de liasse (2139, 2143), la correspondance des aides PAC et le jeu d'essai.
- **AGD6 (Q4 bis) La conversation avec Claude est une nouvelle intégration** (« Assistant Claude »), activée par instance dans les Intégrations (AG9.7, N7). L'échéancier et le résumé du lundi n'en dépendent pas.
- **AGD7 (Q6) L'analytique repose sur la notion d'activité**, comme dans Ekylibre et Lexicon (famille, production, nature, campagne, répartition des auxiliaires), et non sur les Projets existants (AG8.1, AG8.2).
- **AGD8 (Q7) Connecteur Ekylibre : oui, mais plus tard**, en lot AG11 après l'analytique et l'inventaire. Il fera remonter dans Lyvre les ventes, achats, interventions (coûts par activité) et inventaires. Le modèle d'activité d'AG8 doit rester compatible avec celui d'Ekylibre.
- **AGD9 (Q8) Rappels seulement pour les démarches hors comptabilité** (AG9.9).
- **AGD10 (conception, Q-A1) Toujours en engagement** en partie double : le réel simplifié ne diffère qu'au niveau fiscal. AG1.7 et AG10.5 sont abandonnés.
- **AGD12 (04/11/2026) Mini-calculettes** : 16 retenues sur 20 ; 01 (ZNT), 03 (météo), 18 et 19 (IFT) écartées (§ 7 bis).
- **AGD13** : 5 calculettes propres à Lyvre ajoutées (marge brute, coût de revient d'un matériel, amortissement, remboursement forfaitaire, acompte de TVA) ; AG12 compte donc 21 calculettes.
- **AGD14** : calculettes réservées aux utilisateurs connectés.
- **AGD15** : pas de données en direct (cours, GNR, météo) ; valeurs saisies.
- **AGD16** : PDF de tiers hors git ; synthèses et audits versionnés.
- **AGD19 (expert-comptable, 04/11/2026) Rattachement des aides PAC** : au réel, l'aide de la campagne N est un produit de N, acquis à la date limite de dépôt de la demande ; la part non encaissée à la clôture passe en 441 / 745 ; la règle fiscale suit (CGI art. 38 et 72) et la méthode est permanente. Au micro-BA, à l'encaissement (AG3.3).
- **AGD18 (conception AG9a, 04/11/2026)** : `claudedocs/design_echeancier_agricole.md`, validée. Base d'échéances en YAML (`data/deadlines/`), règles déclaratives sans expression évaluée, occurrences calculées et états stockés, TVA et 3520 lus dans le moteur d'AG2 ; résumé du lundi par le SMTP du serveur réglé sur le relais Brevo, commande lancée par un timer du serveur ; paiement reconnu coché automatiquement ; iCal dans AG9a ; destinataires : utilisateurs qui écrivent, abonnés par défaut.
- **AGD17 (conception AG2, 04/11/2026)** : `claudedocs/design_tva_agricole.md`, validée. Créance du remboursement forfaitaire en 44583 ; secteur non agricole (AG2.7) après AG8 ; ligne 31 de la CA12A en saisie libre ; 3520 en état récapitulatif ; prestations intracommunautaires en ligne 02.
- **AGD11 (conception, Q-A2) 757 / 657 subdivisés** : 7571 / 6571 pour les biens vivants, 7578 / 6578 pour les autres immobilisations ; en-tête 234 pour les biens vivants en cours. Source du plan : Recueil PCG 2026, titre 5.
- Conception : `claudedocs/design_compta_agricole.md` (lot AG1, validée le 03/11/2026).
- **AGD23 (conception AG6, 05/11/2026)** : `claudedocs/design_fiscalite_ba.md`, validée. Résultat fiscal et tableau de passage extra-comptable ; répartition sur la pleine propriété et l'usufruit (rien sur la nue-propriété) ; CSG non déductible saisie ; DEP extra-comptable avec compte d'épargne repéré ; barèmes DEP, JA et 73 A de l'audit confirmés ; provision 73 A en 1483 / 6873 / 7873 ; liasse construite depuis les formulaires 2026 fournis (hors git) ; plus-values et crédits d'impôt dans AG6.
- **AGD22 (conception AG5, 05/11/2026)** : `claudedocs/design_biens_vivants.md`, validée. Biens vivants = immobilisations 24x / 234x par lots (composants), sortie partielle au coût moyen ; production immobilisée 7222 (en-cours) et 724 (animal du stock devenu reproducteur) ; dépréciation 294 / 68164 / 78164 par fiche ; mort, sinistre, abattage : valeur nette en 6571, indemnité en 7571 ; durée d'amortissement libre par fiche ; option du profil « reproducteurs maintenus en stock » qui coupe l'alerte.
- **AGD21 (conception AG4, 05/11/2026)** : `claudedocs/design_inventaire_agricole.md`, validée. Écriture de stock à la clôture sans extourne (annulation du stock initial, constatation du stock final) ; animaux achetés en charge puis en stock sur 713551 / 713552 ; cours saisis contrôlés par des fourchettes tirées des cotations de la viande ; méthode forfaitaire admise comme valeur comptable au réel simplifié ; avances aux cultures au coût standard (barème CEGARA, variantes F, M1, M2, cumul au mois de clôture) ou au coût réel 72 A ; coût réel saisi ; lots d'animaux avec entrées et sorties ; aide de Lexicon reportée. Reste à confirmer : stock bloqué 72 B bis (Q-S5), main-d'œuvre de l'exploitant dans le coût standard.
- **AGD20 (conception AG3, 04/11/2026)** : `claudedocs/design_aides_pac.md`, validée (réponses Q-P1 à Q-P7). Registre des dossiers d'aide ; versements comptabilisés par la banque puis rattachés (proposé, confirmé) ; produit à recevoir 441 par dossier à la clôture ; comptes du plan agricole (couplées 743, découplées 745, ICHN/MAEC/bio 744, assurance récolte 742, part d'exploitation de la DJA 744, ventilation saisie) ; reprise 139 / 747 au rythme des amortissements, saisie pour un bien non amortissable, solde repris à la cession ; contrôle Lexicon avec la clé OSFarm du serveur (`LEXICON_API_KEY`).

Il ne reste aucune question ouverte. Les points du § 8 sont à valider par l'utilisateur, en tant qu'expert-comptable, avant la mise en production des valeurs.

---

## 10. Jeu d'essai fictif construit à partir de dossiers réels (AGD2)

### 10.1 Ce que contiennent les dossiers réels

Source : `~/projects/cultia_back/doc/spec/import_compta/`.
- Ces données sont réelles et personnelles : noms, SIREN, tiers.
- Elles sont **lues sur place, jamais copiées ni versionnées dans Lyvre**.
- Le constat ci-dessous ne contient que des agrégats.

| Lot | Contenu | Constats utiles |
|---|---|---|
| 5 FEC Isacompta (3 dossiers, dont 2 avec l'exercice suivant commencé) | Exercices du **01/02 au 31/01** ; de 160 à 7 000 lignes par exercice ; colonnes trésorerie (`DateRglt`, `ModeRglt`) remplies dans un dossier | Numérotation **PCGA 1986 sur 8 chiffres**. Ventes par culture en 7011xxxx à 7014xxxx (maïs semence, maïs doux, asperges, haricots verts, tournesol, pois). Ventes de porcs en 704x. Variations par produit en 713xxxxx et 6031x. Reproducteurs 241/242, plantations 246/2846. Parts de coopératives 2621/2622/2624. Subventions 131/139, 742 (assurance, sinistre), 745. MSA en 646 **par associé**, comptes d'associés 455x. |
| Journaux de ces FEC | Achats, ventes, banque (une ou plusieurs), à-nouveaux, **extournes**, OD, **OD TVA**, stocks, immobilisations, emprunts, et **un journal par coopérative ou négoce** (5 à 6 par dossier) | Les décomptes de coopérative justifient AG10.1. Les extournes confirment la contrepassation à l'ouverture (AG1.7, AG4.5). Le journal OD TVA est mensuel, avec des demandes de remboursement en 44583 : **CA3 mensuelle** à couvrir (option RSA ou réel). |
| 4 exports Isacompta `.ISA` (2 EARL, 1 SARL, 1 SAS) | EARL : exercice du **01/05 au 30/04** ; SARL et SAS : année civile | Records **ANA** : ateliers hiérarchiques avec surface en hectares (grandes cultures, céréales, blé, maïs, fourrages, luzerne, « non affectés »). Ce sont aussi des structures liées (EARL + SARL du même groupe, SAS probablement photovoltaïque) : cas **multi-structures et revenus accessoires**. |
| 8 PDF (plaquettes BA, grands livres) | SCEA au réel simplifié et au réel normal, EARL avec un exercice du 01/11 au 31/10 | Modèle de présentation de la « plaquette BA » d'un cabinet, à comparer aux états agricoles de Lyvre (AG1.2–AG1.4) |
| `cultia_rica_mapping_v1.xlsx` (dossier parent) | Correspondance des comptes vers les variables du RICA | Utile pour les ratios de référence (AG8.3) |

**Conséquences pour les besoins :**
- la reprise d'un dossier passe par la correspondance PCGA 1986 → ANC 2020-04 (AG10.6) ;
- l'import `.ISA` apporte les ateliers (AG10.7) ;
- **les exercices décalés sont la règle**, pas l'exception : 31/01, 30/04, 31/10. L'assistant et les déclarations doivent les traiter dès AG1, notamment la CA12AE.

### 10.2 Exigences sur le jeu d'essai

- **JE1 Anonymisation.**
  - On remplace : noms, raisons sociales, SIREN/SIRET, tiers (CompAuxNum et CompAuxLib), libellés d'écriture nominatifs, références de pièces, IBAN.
  - On garde : la structure des comptes, les journaux types (coopérative → « COOP A »), la saisonnalité et les proportions.
  - Les montants sont multipliés par un coefficient aléatoire par dossier, puis **rééquilibrés par écriture**.
- **JE2 Script de génération** :
  - un script lit les fichiers réels **sur la machine du développeur** et écrit le jeu fictif ;
  - il est versionné, mais **sans aucune donnée réelle** dans ses constantes ;
  - seul le résultat est versionné, dans les fixtures de tests ;
  - le script vérifie qu'aucune chaîne du fichier source (nom, SIREN) ne subsiste.
- **JE3 Exploitations fictives couvrant les régimes (AGD1)** :
  - **A.** EARL de grandes cultures et d'élevage porcin, réel simplifié en trésorerie, RSA avec acomptes, clôture au 31/01 (dérivée du plus gros FEC) ;
  - **B.** SCEA légumes de plein champ et semences sous contrat, réel normal, CA3 mensuelle, coopératives (dérivée des 2 autres FEC, deux exercices consécutifs pour tester les à-nouveaux) ;
  - **C.** GAEC à 3 associés, clôture au 30/04, ateliers avec surfaces, plus une SAS liée (revenus accessoires) (dérivée des `.ISA`) ;
  - **D.** Exploitant au micro-BA et au RFA en maraîchage de vente directe, **entièrement synthétique**, puisqu'aucun dossier réel ne couvre ce cas.
- **JE4 Valeurs attendues** : pour chaque exploitation fictive, un fichier de résultats de référence (balance, bilan et compte de résultat agricoles, TVA de la période, échéancier de l'assistant à une date donnée). Ce fichier sert aux critères des US-A1 à US-A10.
- **JE5 Instances E2E** : une instance par exploitation fictive (comme « Asso Dons E2E »), créée par le jeu d'essai.

