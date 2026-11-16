# Conception : lot AG7, cotisations MSA des non-salariés agricoles

> **Statut** : **validée** (05/11/2026, AGD24). Réponses de l'expert-comptable aux questions du § 9 :
> - **Q-M1** : corrections du § 2 acceptées. La DEP reste déductible au social. JA, 72 B bis et 72 F sont réintégrés. Les cotisations et la CSG ne sont pas déduites. La DJA est exclue. Les anciennes DPI et DPA ne sont pas réintégrées, faute de texte.
> - **Q-M2** : en société, les cotisations personnelles d'un associé sont **débitées de son compte courant 455**. Elles ne sont donc pas des charges de la société, et rien n'est à réintégrer au niveau de la société. Le registre des appels de l'associé est relié aux écritures de son 455.
> - **Q-M3** : les bornes (1,76 % et 130 % du PASS) portent sur le **montant de l'abattement**. Si le revenu est nul ou déficitaire, **l'abattement plancher s'applique** (1,76 % du PASS) et creuse le déficit social.
> - **Q-M4** : DJA déduite automatiquement depuis le dossier d'aide `dja`.
> - **Q-M5** : la rente du sol est un **simple rappel** (option, dates, formule). Pas de saisie des revenus cadastraux.
> - **Q-M6** : l'estimation des cotisations ligne par ligne est faite **dès AG7** (sous-lot AG7.e, barème NSA 2026 en paramètres datés). Elle est indicative.
> - **Q-M7** : CSG non déductible retenue sur les appels **exigibles dans l'exercice**, en engagement, avec une charge à payer à la clôture.
> - **Q-M8** : l'exploitant saisit les assiettes des années antérieures depuis ses avis MSA, y compris celles de 2023 et 2024 reconstituées par la caisse.
>
> Conséquences sur le reste du document :
> - **§ 3** : la réintégration des cotisations 646 ne concerne que l'EI. En société, les sommes passent en 455 et non en charges.
> - **§ 3** : en cas de déficit, l'assiette vaut revenu − abattement plancher.
> - **§ 3** : la rente du sol n'est pas calculée.
> - **§ 6** : en société, écriture D 455 de l'associé / C 512, sans 646. La ligne CSG du résultat fiscal ne vaut que pour l'EI. Pour un associé, la déductibilité de ses cotisations personnelles sur sa quote-part est seulement affichée, **à valider**.
> - **§ 7** : estimation dans AG7.e.
>
> **AG7.a réalisé (05/11/2026, non commité)**. Contenu :
> - tables `msa_people` (exploitant suivi : statut, option d'assiette), `msa_bases` (assiette par année, source `lyvre` ou `entered`) et `msa_adjustments` (lignes saisies) ; migration `b6c8d0e2f4a6` ;
> - paramètres `data/regulatory/msa.json` : PASS 2026, taux de 26 %, plancher et plafond, taux de CSG et de CRDS ;
> - `app/services/msa.py` :
>   - exploitants suivis : l'exploitant de l'EI, ou les associés exploitants, dont la fiche est créée d'office ;
>   - passage du résultat fiscal à l'assiette :
>     - réintégrations : JA de l'exploitant, stock bloqué (lignes `frozen`), cotisations 646 moins la ligne CSG du résultat fiscal (EI seulement) ;
>     - déduction de la DJA : part d'exploitation l'exercice de la décision, et reprises 139 ;
>     - lignes saisies (à-valoir 72 F, autres avec motif) ;
>   - abattement borné, plancher aussi en cas de déficit ;
>   - assiette enregistrée dans l'historique une fois le résultat fiscal figé ;
> - API :
>   - `/fiscal-years/<id>/msa` ;
>   - `…/msa/adjustments` (POST, DELETE) ;
>   - `PATCH /msa/people/<id>` ;
> - export `/fiscal-years/<id>/msa.xlsx` ;
> - écran Compta › **Cotisations MSA** (`/msa/`).
>
> Écarts et points à valider :
> - **PASS retenu** : celui de l'année de cotisation (N+1). S'il n'est pas encore publié, le dernier PASS connu est retenu, avec une alerte ;
> - **DJA en société** : répartie comme le résultat, et non attribuée au seul associé JA ;
> - **revenus antérieurs à 2025** : pas de calcul, l'assiette est à saisir (AG7.b) ;
> - **membres de la famille non participants** et **dividendes** : non traités.
>
> Tests : `tests/api/test_msa.py` (5), `frontend/src/features/msa/msa.test.tsx` (1).
>
> **AG7.b réalisé (05/11/2026, non commité)**. Contenu :
> - `msa.history`, `msa.comparison` et `msa.save_base` / `delete_base` :
>   - les assiettes saisies (`entered`) sont modifiables ; celles calculées à la clôture (`lyvre`) ne le sont pas (409) ;
>   - **comparaison** pour l'année de cotisation C = N + 1 : assiette annuelle (revenus N) contre moyenne des revenus N, N − 1 et N − 2, avec les années manquantes, l'écart, la plus basse et l'assiette retenue selon l'option ;
>   - **option** : délai d'option au 30/06 de C ; si l'option annuelle est en vigueur, fin de l'engagement de 5 ans et dénonciation au 30/11 (6 ans sans nouvelle option ensuite) ;
>   - **notes** : revenus d'avant 2025 reconstitués par la caisse, à saisir depuis l'avis ; expérimentation sur l'assiette N pour les cotisations 2027 et 2028 ;
> - API `PUT` et `DELETE /msa/people/<id>/bases/<année>` ; l'option se modifie par `PATCH /msa/people/<id>` (AG7.a) ;
> - écran : bloc « Assiette des cotisations C » et historique saisissable par exploitant (`MsaOptionPanel.tsx`) ;
> - fiche **SOC-03** complétée : dénonciation au 30/11, durée, rente du sol, sources MSA, fiabilité R.
>
> Écart : la moyenne triennale est un arrondi de la moyenne des trois assiettes après abattement, comme le décrit la MSA (abattement appliqué à chaque année reconstituée). À valider.
>
> Tests : `tests/api/test_msa.py` (+1), `msa.test.tsx` (complété).
>
> **AG7.c réalisé (05/11/2026, non commité)**. Contenu :
> - table `msa_calls` (migration `c7d9e1f3a5b7`) : appel par exploitant et par année de cotisation, avec :
>   - nature, exigibilité, montant, assiette de l'avis ;
>   - détail : cotisations, CSG déductible, CSG non déductible et CRDS, tiers ;
>   - marque « estimé » ;
>   - débit bancaire rapproché ; écriture (réservée à AG7.d) ;
> - `app/services/msa_calls.py` :
>   - **saisie** : le détail doit égaler le montant ; les cotisations sont déduites quand elles manquent ;
>   - **estimation du détail** : CSG et CRDS = taux × assiette retenue (historique, selon l'option), au prorata des appels saisis pour l'année ;
>   - **paiements** : débits de J − 15 à J + 30 (MSA ou montant égal d'abord), un débit par appel ;
>   - **mensualités** : 11 × 1/11 des appels de l'année précédente, le 5 de janvier à novembre ; jour et mois à corriger d'après la caisse ;
>   - **rappel de modulation** : écart de plus de 20 % entre l'assiette de l'avis et l'assiette retenue, demande au plus tard 15 jours avant l'exigibilité ;
>   - **alerte** : appel échu depuis plus de 30 jours sans paiement rapproché ;
> - API `/msa/calls` :
>   - GET `?year=`, POST, PATCH, DELETE ;
>   - `/monthly`, `/<id>/estimate`, `/<id>/candidates`, `/<id>/payment` ;
> - écran : bloc « Appels de cotisations » de la page MSA (`MsaCallsPanel.tsx`).
>
> Écarts et points à valider :
> - les montants des appels de l'échéancier (SOC-02) ne sont pas alimentés par le registre ; le rapprochement de l'échéancier reste indépendant de celui du registre ;
> - le seuil de 20 % pour le rappel de modulation est à valider ;
> - calendrier des mensualités (5 janvier → 5 novembre) supposé.
>
> Tests : `tests/api/test_msa.py` (+2), `msa.test.tsx` (complété).
>
> **AG7.d réalisé (05/11/2026, non commité)**. Contenu :
> - `app/services/msa_ventilation.py` :
>   - **EI** :
>     - ligne `msa` du résultat fiscal : CSG non déductible et CRDS des appels exigibles dans l'exercice, marquée « à valider » si un détail est estimé ;
>     - alertes : appels sans détail ; doublon avec une ligne CSG saisie ;
>     - **charge à payer** des appels non réglés au dernier jour (débit absent ou postérieur), D 646 / C 4311, écriture d'inventaire repérée `msa_accrual`, passée ou supprimée depuis l'écran ;
>   - **société** : rien en charge ; par associé, appels, part déductible (cotisations et CSG déductible) et CSG non déductible, à valider ;
>   - **contrôles de clôture** :
>     - `msa_646` : 646 ≠ appels de l'exercice ;
>     - `msa_register` : 646 sans appel ;
>     - `msa_accrual` : charge à payer à passer (anomalie) ;
>     - `msa_455` : paiement d'un associé non passé en 455 ;
> - l'assiette (AG7.a) retranche du 646 la CSG reprise du registre comme la ligne saisie ;
> - API `/fiscal-years/<id>/msa/ventilation` (GET) et `/msa/accrual` (POST, DELETE) ; bloc « Ventilation de l'exercice » de la page MSA.
>
> Écarts : quand la ligne CSG vient du registre, la ligne saisie d'AG6 n'est pas supprimée d'office ; une alerte demande de la supprimer.
>
> Tests : `tests/api/test_msa.py` (+2), `msa.test.tsx` (complété).
>
> **AG7.e réalisé (06/11/2026, non commité) — AG7 terminé (a à e)**. Contenu :
> - barème NSA 2026 de la MSA en paramètres datés dans `data/regulatory/msa.json`, valables du 01/01 au 31/12/2026, fiabilité A, sauf le taux AMEXA au-delà de 300 % du PASS (I) :
>   - SMIC horaire ;
>   - AMEXA (T1 à T5, et taux au-delà de 300 % du PASS) ;
>   - invalidité (1,1 %, minimum 11,5 % du PASS) ;
>   - IJ 250 € ;
>   - retraite de base plafonnée (17,15 % ou 14,15 %) et déplafonnée (0,72 %), minimum 600 SMIC ;
>   - prestations familiales (jusqu'à 3,10 %) ;
>   - ATEXA par catégorie A à E ;
>   - RCO 4 % (minimum 1 820 SMIC) et RCO complémentaire (1 % à 3 %) ;
>   - VIVEA 0,61 %, entre 0,17 % et 0,89 % du PASS ;
>   - FMSE 20 € ;
> - colonne `msa_people.atexa_category` (migration `d8e0f2a4b6c8`) ;
> - `app/services/msa_estimate.py` : estimation ligne par ligne sur l'assiette retenue pour l'année de cotisation (AG7.b) ;
>   - couvre les chefs à titre principal et à titre secondaire, pas le collaborateur ;
>   - si le barème de l'année de cotisation n'est pas publié, le dernier barème connu est appliqué, avec une alerte ;
> - bloc « Estimation des cotisations » par exploitant sur la page MSA, avec le choix de la catégorie ATEXA.
>
> Écarts et points à valider :
> - **AMEXA au-delà de 300 % du PASS** : lecture retenue, 8,5 % jusqu'à 300 % puis 6,5 % sur la part au-delà ;
> - **non comptés** : exonération JA (65 % à 15 % sur 5 ans), cotisations complémentaires par production (FMSE, InterApi, Val'hor), membres de la famille, invalidité du chef à titre secondaire ;
> - **PASS et SMIC** : ceux de l'année de cotisation.
>
> Tests : `tests/api/test_msa.py` (+2), `msa.test.tsx` (complété).
>
> Sources lues le 05/11/2026 :
> - textes officiels sur Légifrance :
>   - LFSS 2024 art. 18 ;
>   - LFSS 2025 art. 13 ;
>   - CSS L.136-3, L.136-4, R.136-2, D.136-5 ;
>   - CRPM L.731-14 à L.731-16, D.731-24, D.731-26, R.731-58 à R.731-67 ;
>   - décrets 2024-688 et 2025-708 ;
> - pages de msa.fr listées dans `claudedocs/compta_agricole/msa/lien_msa.md` ;
> - publications MSA : barème NSA 2026, notice de la déclaration des revenus 2025, FAQ du webinaire du 14/04/2026, note de la MSA Auvergne, informations 2026 de la MSA Nord-Pas-de-Calais.
>
> Les deux PDF déposés dans `claudedocs/compta_agricole/msa/` portent sur les cotisations des **salariés** (taux AT, taux sur salaires au 01/07/2026). Ils sont hors du périmètre d'AG7, la paie étant exclue, et sont ignorés par git (AGD16).

---

## 1. Ce qui existe et ce qui manque

**Ce qui existe déjà :**
- **Résultat fiscal par associé (AG6)** : `tax_result.view(fy)` donne :
  - le résultat fiscal après les lignes de passage (stocks, abattage 75-0 D, 73 A, 75-0 A, plus-values, saisies) ;
  - les lignes JA (`source = young_farmer`) et DEP (`source = dep`) ;
  - la répartition par associé exploitant (droits aux bénéfices, ou pleine propriété et usufruit).
- **Stocks** : `stock_tax` distingue le stock bloqué 72 B bis (méthode `blocked`) dans l'écart de valeur fiscale.
- **Aides (AG3)** : registre des dossiers d'aide, dont la DJA (dossier `dja`, part d'exploitation en 744 et part d'investissement en 131/139).
- **Échéancier (AG9a)** :
  - fiche SOC-02, appels de cotisations datés par caisse (`agenda.msa.calls.<caisse>`), avec rapprochement des prélèvements bancaires (organisme MSA dans `payees.yml`) ;
  - fiche SOC-03, option pour l'assiette annuelle au 30/06 ;
  - profil agricole : caisse MSA et case « cotisations mensualisées ».
- **Comptes et règles** : 646 (cotisations personnelles de l'exploitant), 6451 (cotisations MSA des salariés), 4311 (MSA) ; règle d'imputation « Cotisations MSA » vers 646.
- **CSG non déductible** : saisie à la main dans le résultat fiscal (Q-F2, ligne `csg`).

**Ce qui manque :**
- l'assiette sociale de l'année, par exploitant ;
- l'historique des assiettes, pour comparer moyenne triennale et assiette annuelle ;
- le registre des appels reçus, avec leur détail (cotisations, CSG déductible et non déductible, CRDS, contributions pour des tiers) ;
- la ventilation comptable et fiscale des sommes payées.

## 2. Corrections au cadrage (compta_agri.md § AG7.1 et audit § 5)

D'après les textes en vigueur, deux points du cadrage sont **faux** :

| Élément | Cadrage | Textes en vigueur | Source |
|---|---|---|---|
| **DEP** (art. 73) | réintégrée | **reste déductible** (« à l'exception de la déduction pour épargne de précaution ») | notice MSA des revenus 2025 ; page MSA « Réforme de l'assiette sociale » (« ce qui ne change pas ») |
| Abattement JA (73 B) | réintégré | réintégré | CSS R.136-2 (décret 2025-708) |
| Blocage des stocks (72 B bis) | réintégré | réintégré | CSS R.136-2 |
| À-valoir social (72 F) | réintégré | réintégré | CSS R.136-2 |
| Provision 73 A (vaches) | — | **applicable** au social | notice MSA |
| Cotisations sociales personnelles et CSG déductible | réintégrées « à valider » | **non déduites** : l'assiette se calcule sur les charges « à l'exclusion des cotisations et contributions sociales » ; l'abattement de 26 % remplace leur déduction | page MSA « Réforme » ; notice MSA |
| Étalement 75-0 A | — | suivi au social | L.136-4 ; notice MSA |
| DJA | — | **exclue** de l'assiette | L.136-4 I A 1° |
| Différentiel d'indemnité d'abattage, sommes exonérées 75-0 D | — | exclus | L.136-4 I A 2° et 4° |
| Plus-values et moins-values à long terme | — | non prises en compte | L.136-4 I A |
| Plus-values à court terme exonérées (151 septies) | — | exclues | L.136-4 I A 3° (LFSS 2025) |
| Anciennes DPI / DPA | réintégrées | **non citées** par R.136-2 | à valider (Q-M1) |

Le cadrage sera corrigé à la validation.

## 3. Assiette sociale d'une année (AG7.1)

**Calcul pour l'exploitation**, sur l'exercice clos dans l'année N :

1. Partir du **résultat fiscal** de l'exercice, après JA et DEP (AG6).
2. **Réintégrer** :
   - l'abattement JA (lignes `young_farmer`) ;
   - la déduction du stock bloqué 72 B bis (part `blocked` de l'écart de stocks) ;
   - l'à-valoir social 72 F (ligne saisie, Lyvre ne le suit pas) ;
   - les **cotisations sociales personnelles** comptabilisées (646), moins la CSG et la CRDS non déductibles déjà réintégrées au fiscal (ligne `csg`), pour ne pas compter deux fois.
3. **Déduire** la DJA comprise dans le résultat : part d'exploitation de l'aide `dja` en 744, et reprise 139/747 du dossier `dja`.
4. **Laisser en l'état** ce qui est déjà neutre au fiscal et au social :
   - DEP ;
   - 73 A ;
   - 75-0 A ;
   - 75-0 D ;
   - plus-values à long terme ;
   - plus-values à court terme exonérées.

On obtient le **revenu professionnel avant abattement**.

**Par exploitant** :
- la base de l'exploitation est répartie avec la même clé que le résultat fiscal (`tax_result.shares`) ;
- les éléments personnels sont rattachés à leur associé : JA de l'associé JA, cotisations 646 de l'associé (Q-M2).
- En EI, il n'y a qu'un exploitant, l'exploitant de la structure.

**Abattement de 26 %** (CSS L.136-3 III, D.136-5) :
- montant = 26 % du revenu ;
- **le montant de l'abattement** est borné entre 1,76 % et 130 % du PASS (845,86 € et 62 478 € en 2026). C'est la lecture de D.136-5 ; la page MSA parle d'un « abattement proportionnel plafonné », sans plus de précision (Q-M3).
- Revenu nul ou déficitaire : l'abattement plancher s'applique (1,76 % du PASS) et creuse le déficit social (Q-M3).

**Option rente du sol** (D.731-24) :
- déduction de 4 % × M × RCd / (RCt − RCd), et au moins 304,90 € ;
- l'assiette est alors majorée des loyers des terres et bâtiments mis à disposition ;
- **rappel seulement** : option, dates et formule ; pas de saisie des revenus cadastraux (Q-M5).

**Hors champ :**
- micro-BA : l'assiette sociale est l'assiette fiscale, déjà donnée par le récapitulatif micro-BA d'AG1.d (rappel affiché) ;
- dividendes et comptes courants au-delà de 10 % : sociétés à l'IS, hors BA ;
- membres de la famille non participants d'une société à l'IR (règle de 2014) : avertissement seulement.

**Paramètres datés** dans `data/regulatory/msa.json`, sources Légifrance et barème MSA 2026 :
- `msa.pass_cents` = 4 806 000 ;
- `msa.base.abatement_rate_bp` = 2600 ;
- `msa.base.abatement_floor_pass_bp` = 176 ;
- `msa.base.abatement_ceiling_pass_bp` = 13000 ;
- `msa.csg.deductible_bp` = 680, `msa.csg.non_deductible_bp` = 240, `msa.crds_bp` = 50 ;
- `msa.rent.floor_cents` = 30490, `msa.rent.rate_bp` = 400.

## 4. Moyenne triennale ou assiette annuelle

**Règles :**
- Assiette par défaut : moyenne triennale. Les cotisations de l'année C portent sur les revenus de C−1, C−2 et C−3 (L.731-15 I).
- Option pour l'assiette annuelle (revenus de C−1) :
  - à demander **au plus tard le 30 juin** de C ;
  - vaut 5 ans, reconduite tacitement ;
  - dénonciation au plus tard le 30 novembre ;
  - pas de nouvelle option pendant 6 ans après une dénonciation (D.731-26, L.731-15).
- **Transition** :
  - 2026 : moyenne de 2023, 2024 et 2025 ;
  - 2027 : moyenne de 2024, 2025 et 2026 ;
  - les revenus 2023 et 2024 sont reconstitués par la caisse (« super brute » puis abattement), sans démarche de l'exploitant.
- **Expérimentation 2027-2028** (LFSS 2026 art. 16) : assiette sur l'estimation des revenus de l'année en cours, à demander entre le 01/10 et le 31/03. Lyvre la signale seulement.

**Dans Lyvre :**
- **historique des assiettes** par exploitant et par année :
  - calculé par Lyvre pour les exercices tenus dans Lyvre ;
  - **saisi** pour les années antérieures ou reconstituées (montant de l'avis MSA, avec une note) ;
- **comparaison** pour l'année de cotisation qui suit la dernière clôture :
  - assiette annuelle (C−1) contre moyenne (C−1, C−2, C−3) ;
  - écart et sens (« l'option annuelle réduirait l'assiette de X € ») ;
  - rappel de l'engagement de 5 ans et des délais ;
- **option en vigueur** par exploitant : triennale ou annuelle depuis une date. Elle sert à afficher l'assiette qui servira aux cotisations, et à rappeler la dénonciation.
- La fiche **SOC-03** est complétée (dénonciation au 30/11, sources officielles).

## 5. Appels de cotisations et paiements (AG7.2)

**Ce qui existe :** les dates des appels par caisse, et leur rapprochement avec la banque, sont déjà dans l'échéancier (SOC-02).

**Ce qu'ajoute AG7 :**
- un **registre des appels** par année et par exploitant, saisi depuis l'avis d'appel ou le relevé de compte MSA :
  - nature : 1er appel, 2e appel, solde, mensualité, appel unique, régularisation ;
  - date d'exigibilité ;
  - montant total ;
  - détail :
    - cotisations ;
    - CSG déductible ;
    - CSG non déductible et CRDS ;
    - contributions pour des tiers (VIVEA, FMSE…), facultatif ;
  - **proposition du détail** quand l'avis ne le donne pas : CSG et CRDS = taux × assiette des contributions de l'année, mise à l'échelle de l'appel (« estimé ») ;
- **paiements** :
  - le prélèvement rapproché dans l'échéancier est relié à l'appel ;
  - sinon, rattachement manuel à une écriture 4311 ou 646 existante ;
- **mensualisation** (case du profil) : 1/11 des cotisations de l'année précédente tant que le montant définitif n'est pas connu (R.731-62 s.). Lyvre propose les mensualités, à corriger ;
- **modulation** : rappel 15 jours avant chaque appel, si l'assiette calculée par Lyvre s'écarte de plus de 20 % de l'assiette qui sert à l'appel (seuil à valider).

## 6. Ventilation comptable et fiscale (AG7.3)

**Écritures** :
- en EI, l'appel est passé D 646 / C 4311 et le paiement D 4311 / C 512 : c'est la pratique de la règle d'imputation actuelle. Lyvre ne réécrit pas les écritures existantes ; il contrôle que le total 646 de l'exercice correspond aux appels de l'exercice ;
- en société, les cotisations personnelles des associés exploitants sont soit portées en 646 (avec un sous-compte par associé), soit débitées de leur compte courant 455 (Q-M2).

**Résultat fiscal** :
- la ligne `csg` (CSG non déductible et CRDS) est **proposée** depuis le registre, avec le total des appels de l'exercice en engagement (Q-M7). Elle reste modifiable et remplace la saisie manuelle d'AG6 ;
- l'à-valoir 72 F reste une ligne saisie.

**Clôture** :
- **charge à payer** pour la part non réglée des appels de l'exercice (solde de décembre, pour un exercice décalé) : D 646 / C 4311 par `add_inventory`, avec un motif ;
- **contrôle** : 646 comptabilisé ≠ total des appels de l'exercice.

## 7. Estimation des cotisations

Le cadrage exclut le « calcul définitif des cotisations ». Le barème NSA 2026 de la MSA est pourtant lisible :
- AMEXA dégressive par tranches de PASS ;
- IJ 250 € ;
- invalidité ;
- retraite de base plafonnée et déplafonnée ;
- RCO 4 % avec la RCO additionnelle ;
- ATEXA forfaitaire par catégorie ;
- PFA dégressive ;
- CSG et CRDS 9,7 % ;
- formation.

**Proposition** : une **estimation indicative**, ligne par ligne, sur l'assiette retenue, marquée « à titre indicatif ». Elle irait dans **AG12, calculette 17** (« Cotisations MSA 2026 »), avec des paramètres `msa.rate.*` datés. Elle ne serait pas dans AG7, qui garde l'assiette et le suivi des appels réels (Q-M6).

## 8. Données, API, écrans

**Tables** (migration tenant) :
- `msa_people` : exploitants suivis.
  - Champs : associé (nul en EI), statut (chef d'exploitation à titre exclusif ou principal, à titre secondaire, collaborateur), option d'assiette (`triennial | annual`), option depuis le, rente du sol (oui/non).
  - En EI, une seule ligne, créée d'office.
- `msa_bases` : assiette par exploitant et par année de revenus.
  - Champs : `year`, `source` (`lyvre | entered`), `income_cents` (avant abattement), `abatement_cents`, `base_cents`, `detail_json` (réintégrations et déductions), note.
  - Figée avec le résultat fiscal à la clôture.
- `msa_calls` : registre des appels.
  - Champs : `person_id`, `year`, `kind`, `due_on`, `amount_cents`, `contributions_cents`, `csg_deductible_cents`, `csg_crds_non_deductible_cents`, `third_party_cents`, `estimated`, `deadline_state_id` (lien avec l'échéancier), `journal_entry_id`, note.
- Revenus cadastraux de la rente du sol : dans `detail_json` de l'année (RCd, RCt, loyers), saisis.

**Service** `app/services/msa.py` :
- `base(fy)` : calcul du § 3, par exploitant ;
- `history(person)` ;
- `comparison(person, year)` ;
- `calls(year)` et `propose_split(call)` ;
- `csg_line(fy)`, pour le résultat fiscal ;
- `accruals(fy)` ;
- `checks(fy)`.

**API** :
- `/api/v1/fiscal-years/<id>/msa` (GET) ;
- `/msa/people` ;
- `/msa/bases/<person>/<year>` (PUT pour une saisie) ;
- `/msa/calls` (CRUD, rattachement d'un paiement) ;
- export XLSX de l'état d'assiette.

**Écran** Compta › **MSA** (`/msa/`), réservé aux instances agricoles, avec trois onglets :
- **Assiette** :
  - tableau de passage par exploitant, du résultat fiscal à l'assiette ;
  - abattement ;
  - comparaison triennale / annuelle ;
- **Historique** : assiettes par année, saisies ou calculées ;
- **Appels** :
  - registre, paiements rapprochés ;
  - mensualisation ;
  - CSG non déductible envoyée au résultat fiscal.

Lien depuis la page Résultat fiscal et depuis la fiche SOC-02 de l'échéancier.

## 9. Questions

- **Q-M1 Corrections du § 2** : d'accord pour corriger le cadrage d'après les textes ?
  - DEP **déductible** au social ;
  - JA, 72 B bis et 72 F **réintégrés** ;
  - cotisations personnelles et CSG non déduites ;
  - DJA exclue.

  Et les anciennes DPI / DPA, que R.136-2 ne cite pas : à réintégrer ou non ?
- **Q-M2 Cotisations des associés en société** : les cotisations personnelles de chaque associé exploitant sont-elles passées en **646 avec un sous-compte par associé** (c'est le cas d'un des dossiers réels), ou débitées de son **compte courant 455** ? Lyvre doit savoir les retrouver pour les réintégrer à l'assiette de chacun.
- **Q-M3 Abattement** :
  - les bornes de D.136-5 (1,76 % et 130 % du PASS) portent-elles bien sur le **montant de l'abattement** ?
  - En cas de déficit : assiette nulle, sans abattement ?
- **Q-M4 DJA** : la déduire automatiquement de l'assiette depuis le dossier d'aide `dja` (part 744 de l'exercice et reprise 139/747), comme proposé ?
- **Q-M5 Rente du sol** : la gérer dans AG7 (revenus cadastraux et loyers saisis), ou l'afficher comme simple rappel ?
- **Q-M6 Estimation des cotisations ligne par ligne** : dans AG12 (calculette 17, proposition), ou dès AG7 ?
- **Q-M7 CSG non déductible au résultat fiscal** : quel exercice retenir ?
  - les appels **exigibles dans l'exercice**, en engagement, comme proposé, avec une charge à payer à la clôture ;
  - ou les sommes **payées** dans l'exercice ?
- **Q-M8 Historique** : pour la moyenne triennale, l'exploitant saisit-il les assiettes des années antérieures à Lyvre depuis ses avis MSA, y compris les revenus 2023 et 2024 reconstitués par la caisse ?

## 10. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG7.a** | Paramètres `msa.*` ; exploitants suivis ; assiette de l'exercice par exploitant (§ 3) ; écran Assiette et export | AG6 |
| **AG7.b** | Historique, option d'assiette, comparaison triennale / annuelle, transition 2026-2027, fiche SOC-03 complétée | AG7.a |
| **AG7.c** | Registre des appels, détail proposé, liens avec l'échéancier et les paiements, mensualisation, rappel de modulation | AG7.a |
| **AG7.d** | Ventilation : ligne CSG du résultat fiscal (EI), charge à payer à la clôture, contrôles 646 ou 455 / appels | AG7.c |
| **AG7.e** | Estimation indicative des cotisations ligne par ligne (barème NSA 2026 : AMEXA, IJ, invalidité, retraite de base, RCO, ATEXA, PFA, CSG/CRDS, formation ; assiettes minimales) | AG7.a |

Ordre proposé : a → b ∥ c → d ; e après a.
