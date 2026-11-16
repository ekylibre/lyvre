# Conception : lot AG2, TVA agricole

> **Statut** : **validée** (04/11/2026). Q-V1 : créance du remboursement forfaitaire en **44583**. Q-V2 : secteur non agricole **après AG8**. Q-V3 : ligne 31 en **saisie libre**. Q-V4 : 3520 en **état récapitulatif**. Q-V5 : prestations intracommunautaires en **ligne 02** (§ 10).
> **AG2.a réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/fr_calendar.py` : Pâques, fériés légaux, jour ouvré suivant, n-ième jour ouvré après une date ;
> - `vat_period` à deux valeurs (`monthly`, `quarterly`) ; l'**annuel** viendra avec la CA12A (AG2.b) ;
> - moteur de la CA3 découpé par période, avec les clés `AAAA-MM` et `AAAA-Tn`, le libellé « T3 2026 », le report du crédit de période en période, et l'échéance trimestrielle le 5 du **deuxième** mois après le trimestre, reportée au jour ouvré ;
> - **remboursement 3519** : case 26, minimum 760 € (150 € sur la dernière période de l'année), plafonné au crédit, débit 44583 dans la liquidation ; `vat_returns.refund_cents` (migration `d4e6a8c0b2f3`) ;
> - changement de rythme refusé si l'exercice a des déclarations ;
> - écrans : bouton « Trimestrielle (CA3) » sur les exercices, colonne « Période », saisie du remboursement sur la fiche.
>
> Écart avec la conception : le moteur reste celui de la CA3, sans paramètre de formulaire. La généralisation viendra avec la CA12A, qui en a l'usage.
>
> Tests : `tests/api/test_vat_quarterly.py` (13 tests), `frontend/src/features/vat-returns/vatQuarterly.test.tsx` ; tests de la CA3 mensuelle inchangés et au vert.
>
> **AG2.b réalisé (04/11/2026, non commité)**. Contenu :
> - `data/ca12a/2026.json` : 44 lignes du 3517-AGR-SD (cerfa 10968*28), codes de case, correspondance des codes de TVA, reversement en ligne 14 ;
> - moteur **paramétré par formulaire** : `form_spec(année, formulaire)`, `form_for(jour)`, et le formulaire porté par chaque déclaration et son report de crédit ;
> - `vat_period = annual`, réservé aux exploitations ; période civile (clé `AAAA-A`) ou exercice si l'option `rsa_fiscal_year` est enregistrée (clé `AAAA-MM-A`, CA12AE) ;
> - échéances : 2e jour ouvré après le 1er mai pour la CA12A, 5e jour du 5e mois pour la CA12AE ;
> - calcul des lignes 15 à 46 : crédit antérieur en 19, acomptes en 25, lus dans les déclarations `ACOMPTE` ; remboursement du cadre VII, borné à la ligne 44 (sans seuil pour l'excédent) ; conseil des 4/5 ; ligne 31 en saisie libre ;
> - liquidation : 44581 crédité des acomptes, 44583 pour le remboursement ; pour une CA12A civile d'un exercice décalé, les brouillards des deux exercices sont validés ;
> - écrans : bouton « Annuelle (CA12A) », nom du formulaire, saisie de la ligne 31, acomptes imputés.
>
> Écarts avec la conception :
> - **ligne 10 (cessions d'immobilisations) non alimentée** : une ligne de taxe ne sait pas que sa vente porte sur une immobilisation. Une cession taxée part en 04 et se reclasse sur TeleDEC ; il faudra un code de TVA dédié ;
> - la ligne 31 n'a pas d'écriture : la taxe se comptabilise à part ;
> - le jeu d'essai A ne sert pas de test de la CA12A, car le FEC importé n'a pas de codes de TVA. Le test porte sur un jeu calculé à la main.
>
> Tests : `tests/api/test_vat_ca12a.py` (7 tests).
>
> **AG2.c réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/vat_installments.py` : la période annuelle se découpe en blocs de trois mois, chacun avec un acompte dû à la première date du calendrier `vat.rsa.installment_calendar` (5/2, 5/5, 5/8, 5/11) après sa fin, reportée au jour ouvré. CA12A : 5 mai, 5 août, 5 novembre, 5 février N+1 ; exercice juillet-juin : 5 novembre, 5 février, 5 mai, 5 août ;
> - référence : lignes 15, 17, 21 et 23 de la CA12A immédiatement précédente, sinon saisie sur l'exercice (`fiscal_years.vat_reference_cents` et `vat_reference_assets_cents`, migration `e5f7b9d1c3a4`) ; sans référence, nouvel assujetti : montant libre et rappel des 70 % ;
> - acompte proposé ⌈ ligne 23 × 20 % ⌉ à l'euro ; un autre montant, y compris 0 pour une suspension, demande un motif, conservé dans la déclaration ;
> - alerte si la TVA nette de l'année, extrapolée depuis les écritures à date (au moins un mois), dépasse de plus de 30 % les acomptes enregistrés et à venir, quand un acompte a été réduit (paramètre `vat.rsa.installment_tolerance_bp`) ;
> - cycle : enregistrer dans l'ordre (déclaration `ACOMPTE`, écriture D 44581 / C 44551 en brouillard), payer (écriture validée, **pas de verrouillage**), annuler le dernier ; une CA12A validée fige ses acomptes. L'aperçu de la CA12A signale les acomptes échus non enregistrés ;
> - API `GET /vat-returns/installments?period=`, `PUT /vat-returns/installments/reference`, `POST /vat-returns/installments` ; paiement et annulation par les routes existantes ;
> - écran : panneau « Acomptes (3525 bis) » sous la liste des déclarations en mode annuel (référence, dispense, montant calculé, TVA estimée, enregistrer, payé, annuler).
>
> Écarts avec la conception :
> - **dispense : ligne 23 + ligne 17**, et non « 23 − 17 ». L'impôt « avant déduction de la TVA sur immobilisations » ajoute cette TVA à l'impôt net. Calcul exact sur la CA12A précédente : max(15 − 21 + 17, 0). **À valider** ;
> - le montant de l'acompte reste calculé sur la ligne 23, comme prévu. Si le 1/5 se calcule lui aussi avant déduction des immobilisations (lecture possible de l'art. 1693 bis I), il suffit de changer la base. **À valider** ;
> - pas de colonne `extra_json` : le motif et le montant proposé sont conservés dans `boxes_json` de la déclaration d'acompte ;
> - CA12AE d'un exercice qui ne commence pas un 1er janvier, avril, juillet ou octobre : rattachement calculé, à vérifier sur le tableau du BOFiP.
>
> Tests : `tests/api/test_vat_installments.py` (8 tests), `frontend/src/features/vat-returns/vatInstallments.test.tsx` (2 tests).
>
> **AG2.d réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/vat_books.py` : **livre des ventes**, une ligne par pièce et par code de vente (`V…`) datée de la période, avec sa catégorie (ligne 01, 02, 03, 04, 5A, 5C, 09), sa base, sa taxe et le client ; totaux par ligne ;
> - **livre des achats** : tous les achats de la période, codés ou non (comptes 20, 21, 23, 60 sauf 603, 61, 62), une ligne par pièce et par nature (immobilisations, autres) ; TVA déductible (44562 pour les immobilisations, autres 4456 sinon), TVA autoliquidée, mention « non déductible » ; totaux, dont le HT sans TVA déductible ;
> - **contrôle croisé** quand la période est celle de la CA12A (validée ou calculée) : ventes = lignes 01 à 09 en base et en taxe, ligne par ligne ; TVA déductible = 17 + 18 − 14 (les avoirs reçus vont en ligne 14) ;
> - API `GET /vat-books/sales` et `/vat-books/purchases` (`?period=` ou `?start=&end=`, défaut : période annuelle en cours) ; exports `/vat-books/<sales|purchases>.xlsx` et `.pdf` (A4 paysage, contrôle en fin de livre) ;
> - écran Compta › Déclarations de TVA › **Livres** (`/vat-returns/books`) : bascule Ventes / Achats, période, totaux, contrôle, exports ; bouton « Livres de TVA » sur la liste des déclarations.
>
> Écarts avec la conception :
> - un **onglet** était prévu ; c'est une page liée depuis la liste, à cause des routes de la SPA ;
> - les écritures d'à-nouveaux, de clôture, d'affectation, d'inventaire, d'extourne, d'amortissement et de liquidation de TVA sont exclues des livres ;
> - le contrôle ne vaut que pour la période annuelle exacte de la CA12A. En CA3, ou sur une période libre, les livres s'affichent sans contrôle ;
> - la TVA autoliquidée d'une pièce mixte est rattachée aux immobilisations si la pièce en contient, sinon aux autres achats.
>
> Tests : `tests/api/test_vat_books.py` (5 tests), `frontend/src/features/vat-returns/vatBooks.test.tsx` (2 tests).
>
> **AG2.e réalisé (04/11/2026, non commité)**. Contenu :
> - données (migration `f6a8c0e2d4b5`) : `simple_categories.rfa_rate`, `products.rfa_rate`, `entities.rfa_buyer`, tables `rfa_attestations` (une par client et par année, pièce jointe rangée sous `uploads/<instance>/rfa/`) et `rfa_claims` (une par année, bases figées) ;
> - `app/services/rfa.py` : recettes des comptes 70 de l'année civile ; classe de taux d'un compte par sa catégorie de recettes, sinon par les produits du catalogue s'ils concordent, sinon par une proposition (produits animaux et animaux : 5,59 % ; transformés, travaux à façon, entraide : exclus ; végétaux : à choisir, car céréales et légumes diffèrent) ; type de client saisi ou déduit de la fiche (régime de TVA, SIREN, numéro de TVA) ;
> - forfait = bases × taux de l'année, arrondi à l'euro ; contrôles : attestation manquante ou écart de plus de 1 % (clients assujettis en France), ventes sans classe (bloquant), ventes sans client, régime du profil fiscal différent, seuil de 46 000 € sur la moyenne de N-1 et N, × associés d'un GAEC ;
> - dépôt à partir du 1er janvier N+1, échéance le 31/12/N+1 ; en partie double, écriture D 44583 / C 741 à la date de dépôt (pas d'écriture en comptabilité simplifiée : le remboursement s'y saisit en recette à l'encaissement) ; annulation tant que le remboursement n'est pas reçu ; « remboursement reçu » ;
> - API `/rfa/<année>`, `/rfa/accounts/<id>/rate`, `/rfa/buyers/<id>`, `/rfa/<année>/attestations/<tiers>` (JSON ou multipart), `/rfa/<année>/declare` (POST, DELETE), `/rfa/<année>/refunded` ; exports `/rfa/<année>.xlsx` et `.pdf` (état récapitulatif, Q-V4) ;
> - écran Compta › **Remboursement forfaitaire** (`/rfa/`, plan agricole, partie double et comptabilité simplifiée).
>
> Écarts avec la conception :
> - **classes de taux par compte de vente**, pas par ligne de facture : les lignes du grand livre ne portent pas le produit. Un compte qui mêle les deux taux doit être scindé ;
> - **partie double : ventes comptabilisées**, pas encaissements. Un avertissement demande de corriger les factures non encaissées au 31/12 et les encaissements de factures antérieures. En comptabilité simplifiée, ce sont bien des encaissements ;
> - **taux connus à partir de 2026 seulement** (`vat.rfa.rate_*_bp`, valables du 01/01/2026, fiabilité A). Une demande sur les ventes 2025 est bloquée tant que les taux 2025 ne sont pas saisis, avec leur source, dans Administration › Paramètres réglementaires. **À valider** ;
> - pas de règle bancaire « DGFIP » proposée : le virement se rapproche à la main sur 44583 ;
> - **jeu d'essai D non utilisable pour le 3520** : ventes 2025 sur les marchés, sans client, donc à des particuliers. Le test porte sur un jeu calculé à la main (forfait 781 €).
>
> Tests : `tests/api/test_rfa.py` (7 tests), `frontend/src/features/rfa/rfa.test.tsx` (1 test).
>
> **Besoins** : `claudedocs/compta_agri.md`, lot AG2 (AG2.1 à AG2.7).
> **Socle** : la CA3 du lot T (`app/services/vat_return.py`, `data/ca3/2026.json`, `vat_returns`) et le lot AG1 (plan `agri`, profil fiscal daté, paramètres réglementaires).
>
> **Formulaires lus** le 04/11/2026 (texte extrait du PDF, comme pour la CA3) :
> - **3517-AGR-SD**, millésime 2026, cerfa 10968*28 : https://www.impots.gouv.fr/sites/default/files/formulaires/3517-agr-sd/2026/3517-agr-sd_5292.pdf
> - sa notice : https://www.impots.gouv.fr/sites/default/files/formulaires/3517-agr-sd/2026/3517-agr-sd_5406.pdf
>
> Le 3520-SD n'existe qu'en millésime 2025, PDF non lu à ce jour (Q-V4). Le 3525 bis n'est pas publié en ligne : c'est un bulletin prérempli par le SIE.

---

## 1. Ce que dit le formulaire 3517-AGR (CA12A / CA12AE)

| Cadre | Lignes (code de case) | Usage dans Lyvre |
|---|---|---|
| I. Impôt brut, opérations non taxées | 00 achats en franchise (0037), 01 exportations (0032), 02 autres non imposables (0033), 03 livraisons intracommunautaires (0034), 3B (0029), 3C importations (0052), 3D acquisitions intracommunautaires (0055), 2A (0047) | Bases depuis les codes `V_EXP`, `V_EXO`, `V_UE_B`, `V_UE_S` |
| I. Opérations taxées (base et taxe) | **04 20 % (0207), 5A 10 % (0151), 5C 5,5 % (0105)**, 06 2,1 % DOM (0100), 07 8,5 % (0201), 08 anciens taux (0900), 09 taux particuliers (0950), I1 à I6 importations, 9B énergie, **9C services d'un non-établi (0044)**, **10 cessions d'immobilisations (0970)**, 11 livraisons à soi-même (0980), 12 autres (0981), **13 acquisitions intracommunautaires (0031)**, **14 TVA à reverser (0600)**, 4B (0602), **15 total brut** | Même correspondance codes → cases que la CA3 ; la ligne 10 est propre à la CA12A (cession d'un bien immobilisé) |
| II. Impôt déductible | **17 immobilisations (0703), 18 autres biens et services (0702)**, **19 crédit antérieur (0058)**, 20 compléments (0059), 2B (0603), 20A coefficient, **21 total** | 44562 → 17 ; 44566 → 18 ; 19 = ligne 38 de la CA12A précédente, ou solde d'ouverture 44567 |
| III. Impôt net | **23 TVA due (8900)** ou **24 crédit (0705)** ; **25 acomptes versés (0018)** ; **28 solde dû**, **29 excédent de versement**, **30 solde excédentaire (0020)** | 25 = acomptes de l'année enregistrés dans Lyvre (§ 4) |
| IV. Taxes assimilées | 31 taxe sur le chiffre d'affaires des exploitants agricoles (4220), redevances, accises… ; total reporté ligne 40 | Ligne 31 seule, en saisie (Q-V3) ; les autres hors périmètre |
| V. Accise sur les énergies | X, Y, Z, M (dont ZB gazole non routier agricole) | Hors périmètre AG2 (saisie manuelle sur TeleDEC) |
| VI. Récapitulation | 36 crédit, 37 remboursement demandé (8002), 38 crédit à reporter (8003), 39 TVA nette due (8901), 40 taxes assimilées, 41 total à payer (9992) | Calculé |
| VII. Remboursement | 42 crédit remboursable (≥ 150 €), 43 excédent de versement (remboursable sans seuil), 44 maximum, 45 demandé, 46 reportable | Proposé (§ 3.4) |

**Règles de la notice reprises** :
- arrondi à l'euro de la TVA due par taux, et de la TVA déduite par ligne ;
- acomptes au moins égaux à **1/5 de la ligne 23** de la déclaration précédente ;
- **dispense d'acomptes** si la taxe due de l'année précédente, avant déduction de la TVA sur immobilisations, est inférieure à 1 000 € ;
- crédit remboursable à partir de 150 €, excédent de versement remboursable sans condition de montant ;
- conseil de la notice : rembourser l'excédent tout de suite s'il dépasse les 4/5 de la ligne 23.

---

## 2. Choix structurants

| # | Choix | Raison |
|---|---|---|
| V1 | **Un seul moteur de déclaration**, paramétré par formulaire : `vat_return.compute(form, start, end)`. La CA3 reste ce qu'elle est ; la CA12A lit `data/ca12a/<année>.json`, au même format que `data/ca3` | Les deux formulaires partagent les codes de TVA, l'arrondi, la liquidation et le verrouillage |
| V2 | **`fiscal_years.vat_period`** accepte `monthly`, `quarterly`, `annual` (CA12A), et reste nul quand Lyvre ne prépare pas la TVA. Pour une exploitation, la valeur est **proposée** depuis le régime de TVA daté du profil (AG0) | Une seule source pour le moteur et le menu (déjà piloté par `vat_period`) ; le profil reste la référence fiscale, un contrôle signale l'écart |
| V3 | **Les acomptes sont des déclarations** : `vat_returns.form = "ACOMPTE"`, une par échéance (3525 bis), avec leur écriture | Même cycle (calculé, validé, déclaré, verrouillé) ; la ligne 25 de la CA12A se calcule depuis ces lignes |
| V4 | **RFA hors du moteur de TVA** : une exploitation au remboursement forfaitaire n'a ni TVA collectée ni TVA déductible. Le 3520 est un état sur les **ventes encaissées**, avec sa propre table de demandes (`rfa_claims`) | Le forfait se calcule sur des recettes, pas sur des lignes codées ; il marche aussi en comptabilité simplifiée (micro-BA) |
| V5 | **Calendrier français des jours ouvrés** (`app/services/fr_calendar.py` : fériés fixes et mobiles, « n-ième jour ouvré après ») | « 2e jour ouvré après le 1er mai » (CA12A, liasse) ; repris par l'échéancier (AG9) |

---

## 3. CA12A (AG2.3)

### 3.1 Données : `data/ca12a/2026.json`

Même structure que `data/ca3/2026.json` :
- `sections` : lignes dans l'ordre du formulaire, avec `line`, `code`, `label`, `with_base` et `total` ;
- `codes` : code de TVA → ligne et colonne ;
- `deductible_lines` : 17 pour 44562, 18 pour 44566.

**Correspondances** :
- V20 → 04, V10 → 5A, V55 → 5C ;
- V21 (2,1 %) → 09 en métropole, 06 dans les DOM. Le choix se fait selon la structure ; seule la métropole est traitée en AG2 ;
- V_EXP → 01 ; V_EXO → 02 ; V_UE_B → 03 ; V_UE_S → 02 (prestations intracommunautaires, à valider : Q-V5) ;
- AL_S → 9C ; AL_B → 13 ; AL_I* → I1 à I6 ;
- cession d'immobilisation : un code `V20_IMMO` (nouveau, vente d'un bien de classe 2) → 10 ;
- avoirs reçus → 14.

### 3.2 Période et échéance

- **CA12A** : année civile, du 01/01 au 31/12.
  - Exercice comptable civil : la période est l'exercice lui-même.
  - Exercice décalé sans option : la CA12A porte quand même sur l'année civile. Elle couvre alors deux exercices, et le moteur lit les lignes par date, pas par exercice.
- **CA12AE**, si l'option « TVA sur l'exercice » est enregistrée (code `rsa_fiscal_year`, ajouté aux options d'AG0.2) : la période est l'exercice.
- **Échéance** : 2e jour ouvré après le 1er mai de N+1 (CA12A), ou avant le 5e jour du 5e mois après la clôture (CA12AE). Ce sont des paramètres datés : `vat.ca12a.deadline_rule` et `vat.ca12ae.deadline_rule`.

### 3.3 Calcul

`compute("CA12A", start, end)` reprend `compute` de la CA3 avec la spécification du formulaire, puis :
- **ligne 19** : ligne 38 de la CA12A précédente (déclarée), à défaut le solde d'ouverture de 44567 ;
- **ligne 25** : somme des acomptes **validés** de la période (§ 4) ;
- **lignes 28 à 30**, puis cadre VI (36 à 41) et cadre VII (42 à 46).

La **ligne 31** (taxe sur le chiffre d'affaires des exploitants agricoles) est une saisie libre sur la déclaration (Q-V3).

### 3.4 Validation, liquidation, remboursement

- **Liquidation** : même écriture que la CA3, en brouillard jusqu'au dépôt.
  - Elle solde les comptes 4457x / 4456x des lignes déclarées.
  - Elle **solde 44581** (acomptes versés) pour le montant de la ligne 25.
  - Le solde dû va en 44551, le crédit en 44567, l'arrondi en 658 / 758.
- **Remboursement demandé** (lignes 37 et 45) : saisi à la validation, plafonné à la ligne 44.
  - Seuil : ligne 42 si elle atteint au moins 150 € (paramètre `vat.rsa.refund_min_annual_cents`) ; ligne 43 sans seuil.
  - Écriture : débit 44583 « remboursement demandé », crédit 44567.
  - L'**alerte de la notice** est reprise : excédent supérieur aux 4/5 de la ligne 23 → « remboursement immédiat conseillé ».
- **Déclarée** : verrouillage de la période (lot F2), comme la CA3.

### 3.5 Exports

PDF et XLSX dans l'ordre du formulaire, avec les codes de case pour TeleDEC (mêmes gabarits que la CA3).

---

## 4. Acomptes du RSA, 3525 bis (AG2.2)

### 4.1 Échéancier

Quatre acomptes par période annuelle :
- **CA12A** : les 5 mai, 5 août et 5 novembre de N, puis le 5 février de N+1 ;
- **CA12AE** : les mêmes jours, calés sur l'exercice, selon le tableau du BOFiP (paramètre `vat.rsa.installment_calendar`).

**Montant de référence** : la ligne 23 de la CA12A précédente, ou une **saisie** (`fiscal_years.vat_reference_cents`) pour la première année dans Lyvre. La dispense se lit sur la ligne 23 moins la ligne 17 (TVA sur immobilisations) de la déclaration précédente, ou sur une saisie.

| Cas | Proposé |
|---|---|
| Référence avant immobilisations < 1 000 € (paramètre `vat.rsa.installment_exemption_cents`) | « Dispensé d'acomptes » : aucun acompte, tout se paie avec la CA12A |
| Sinon | Montant = ⌈ référence × 20 % ⌉ à l'euro (`vat.rsa.installment_share_bp`) |
| Modulation (réduction, suspension) | Montant saisi, avec motif. **Alerte** si la TVA estimée de l'année (lignes codées à date, extrapolées) dépasse de plus de 30 % les acomptes versés et à verser : risque d'intérêt de retard et de majoration (art. 1731) |
| Nouvel assujetti | Montant saisi ; rappel « au moins 70 % de l'impôt réel du trimestre » (art. 1693 bis II) |

### 4.2 Cycle et écritures

Un acompte est une déclaration de forme `ACOMPTE`, avec sa période (le trimestre), son échéance et son montant.
- **Valider** : écriture débit **44581** « acomptes, régime simplifié », crédit **44551** « TVA à décaisser » (journal OD, source `VAT_RETURN`, en brouillard).
- **Déclarer** (paiement fait sur l'espace professionnel) : le prélèvement de la DGFiP se rapproche de 44551, comme le solde d'une CA3.

Les acomptes **ne verrouillent pas** la période : la CA12A annuelle reste à faire.

---

## 5. RSA en CA3 trimestrielle ou mensuelle (AG2.4)

- **`vat_period = quarterly`** : `periods()` découpe en trimestres. L'échéance est le **5 du deuxième mois après le trimestre**, soit les 5 mai, 5 août, 5 novembre et 5 février, reportée au jour ouvré (paramètre `vat.rsa.quarterly_due_day`, valeur 5). La conception disait d'abord « le 5 du mois qui suit » : corrigé en AG2.a. La règle « CA3 trimestrielle agricole » reste à confirmer sur le BOFiP (§ 8 des besoins) ; elle ne change rien au calcul.
- **`vat_period = monthly`** : rien ne change par rapport au lot T.
- **Remboursement de crédit** (3519), pour toutes les structures et pas seulement les exploitations :
  - à la validation d'une CA3, on peut saisir un remboursement, qui remplit la case **26** ; la case 27 devient alors 25 − 26 ;
  - seuils : **760 €** pour un trimestre ou un mois, **150 €** sur la déclaration de décembre ou du 4e trimestre (paramètres `vat.rsa.refund_min_period_cents` et `refund_min_annual_cents`) ;
  - écriture : débit 44583, crédit 44567 ;
  - l'écran rappelle qu'il faut joindre le formulaire 3519 sur l'espace professionnel.
- **Conseil d'option** : l'assistant (AG9) le reprendra ; il est dès maintenant affiché sur l'écran des acomptes.
  - Condition : un crédit de TVA de l'année en cours (immobilisations, investissement) d'au moins 760 € sur un trimestre.
  - Message : « Le régime des acomptes ne permet aucun remboursement en cours d'année ; l'option pour la CA3 trimestrielle (5 ans) le permet. »

---

## 6. Remboursement forfaitaire agricole, 3520 (AG2.1)

### 6.1 Données

| Élément | Où | Rôle |
|---|---|---|
| Classe de taux d'une vente | `products.rfa_rate` et `simple_categories.rfa_rate` : `high` (5,59 %), `low` (4,43 %), `excluded`, ou nul | Lait, œufs, volailles, animaux de boucherie, céréales, oléo-protéagineux → `high` ; autres produits → `low` ; ventes par moyens commerciaux, produits transformés, animaux vivants vendus à des particuliers → `excluded`. Proposé par les catégories agricoles (AG1.e) et modifiable |
| Client éligible | `entities.rfa_buyer` : `professional` (assujetti en France, attestation), `eu` (livraison intracommunautaire : relevé de factures), `export` (copie de la déclaration d'export), `none` (particulier) | Déduit à la première saisie (SIREN, numéro de TVA, pays : `vat_codes.guess_regime`), modifiable |
| Attestation d'achats | `rfa_attestations` : client, année, montant attesté, pièce jointe, reçue le | Une par client et par année ; l'état signale les manquantes |
| Demande | `rfa_claims` : année des ventes, montants par taux, forfait, statut (préparée, déposée, remboursée), déposée le, écriture | Une par année |

### 6.2 Calcul

**Recettes de l'année civile retenues** :
- les **encaissements** des ventes, c'est-à-dire les lignes de produit des recettes en mode simple ou des règlements de factures en partie double ;
- de clients `professional`, `eu` ou `export` ;
- ventilées par classe de taux.

Le **forfait** est le total des bases de chaque classe multiplié par son taux (paramètres `vat.rfa.rate_high_bp` et `vat.rfa.rate_low_bp` de l'année des ventes), arrondi à l'euro.

**Contrôles** :
- attestation absente ou montant attesté différent des ventes de Lyvre (écart de plus de 1 %) ;
- vente sans classe de taux ;
- client sans type.

**Seuil** : si la moyenne des recettes des deux années civiles dépasse 46 000 € (`vat.rfa.threshold_cents`, multiplié par le nombre d'associés d'un GAEC), alerte « passage obligatoire au régime simplifié agricole » à compter du 1er janvier suivant.

### 6.3 Écritures et échéance

- **Dépôt** : écriture débit **44583** (Q-V1), crédit **741 Remboursement forfaitaire de TVA**. L'encaissement du remboursement solde la créance (règle bancaire « DGFIP » proposée au rapprochement).
- **Échéance** : 31/12 de N+1 (`vat.rfa.deadline_rule`), avec une alerte « dépôt conseillé avant le 1er mars ».
- **Export** : état récapitulatif PDF et XLSX (clients, ventes par taux, attestations) pour remplir le 3520 ; liste des attestations à joindre.

---

## 7. Livres de TVA du RSA (AG2.5)

**Livre des ventes** (période au choix, par défaut l'année de la CA12A) :
- les lignes de produit et de taxe codées, par catégorie : exonéré, intracommunautaire, export, taxable par taux ;
- base et taxe, date, pièce, tiers ;
- totaux par catégorie, égaux aux lignes 01 à 13 de la CA12A, ce que le contrôle vérifie.

**Livre des achats** :
- **tous** les achats, y compris ceux qui n'ouvrent pas droit à déduction : lignes de charge et d'immobilisation, qu'elles soient codées ou non ;
- ventilés entre immobilisations (classe 2) et autres ;
- avec la taxe déductible (44562, 44566) ou la mention « non déductible ».

**Restitution** : écran Compta › Déclarations de TVA › Livres, et exports XLSX et PDF.

---

## 8. Secteur non agricole (AG2.7)

Une exploitation au RSA qui a une activité non agricole (gîte, transformation commerciale, négoce) déclare celle-ci séparément : en CA3, trimestrielle depuis la suppression du régime simplifié d'imposition en 2027.

**Proposition (Q-V2)** : reporter AG2.7 après les **activités** d'AG8. Le secteur se déduira de l'activité de chaque ligne (attribut « secteur de TVA » de l'activité), et deux déclarations de formes différentes coexisteront sur la même période (`vat_returns.form` est déjà dans la clé d'unicité).

---

## 9. Données, API, écrans

**Migrations tenant** :
- `fiscal_years.vat_reference_cents` ;
- `products.rfa_rate`, `simple_categories.rfa_rate`, `entities.rfa_buyer` ;
- tables `rfa_attestations` et `rfa_claims` ;
- `vat_returns.refund_cents` (remboursement demandé) et `vat_returns.extra_json` (saisies libres : ligne 31, motif de modulation).

**Nouveaux codes de TVA** : `V20_IMMO` (cession d'immobilisation, CA12A ligne 10).

**Paramètres** (`data/regulatory/vat_agri.json`, en plus de ceux d'AG1.a) : `vat.ca12a.deadline_rule`, `vat.ca12ae.deadline_rule`, `vat.rsa.installment_calendar`, `vat.rsa.quarterly_due_day`, `vat.rfa.deadline_rule`.

**API** (préfixe `/api/v1`) :

| Route | Rôle |
|---|---|
| `GET /vat-returns?form=` | Périodes selon `vat_period` : mois, trimestres, ou année et ses acomptes |
| `GET /vat-returns/<form>/<période>` | Aperçu calculé (formulaires CA3, CA12A, ACOMPTE) |
| `POST /vat-returns/<form>/<période>/validate`, `/declare`, `DELETE` (annulation) | Cycle commun ; `refund_cents`, `installment_cents` et `motive` dans le corps |
| `GET /vat-books/sales`, `/vat-books/purchases`, `?start=&end=`, exports `.xlsx` / `.pdf` | Livres |
| `GET /rfa/<année>`, `PUT /rfa/attestations/<entity>/<année>`, `POST /rfa/<année>/declare` | Remboursement forfaitaire |

**Écrans** :
- **Compta › Déclarations de TVA** (existant), selon `vat_period` : liste des mois ou des trimestres, ou bien l'**année** avec la CA12A et ses 4 acomptes (montant proposé, dispense, modulation). Fiche de la CA12A dans l'ordre du formulaire, cadre VII compris. Onglet **Livres**.
- **Compta › Remboursement forfaitaire** (exploitations au RFA, `vat_regime = rfa`) : année, ventes par client et par taux, attestations (dépôt de pièce), forfait, alerte de seuil, dépôt.
- **Exercices** : `vat_period` gagne « trimestrielle » et « annuelle (CA12A) » ; la valeur est proposée depuis le régime de TVA du profil.

---

## 10. Décisions de validation (04/11/2026)

- **Q-V1 → 44583** pour la créance du remboursement forfaitaire.
- **Q-V2 → après AG8** : AG2.f reporté, le secteur sera un attribut de l'activité.
- **Q-V3 → saisie libre** de la ligne 31.
- **Q-V4 → état récapitulatif** pour le 3520, sans reproduire ses cases.
- **Q-V5 → ligne 02** pour les prestations intracommunautaires.

Texte des questions, pour mémoire :

- **Q-V1 Compte de la créance de remboursement forfaitaire** en attendant le versement : **44583** « remboursement de taxes demandé » (proposition, comme les crédits de TVA), **4487** « produits à recevoir de l'État », ou **468** ?
- **Q-V2 Secteur non agricole (AG2.7)** : le reporter après les activités (AG8), comme proposé, ou le traiter dès AG2 par une liste de comptes « non agricoles » ?
- **Q-V3 Ligne 31, taxe sur le chiffre d'affaires des exploitants agricoles** (art. 302 bis MB) : saisie libre (proposition), ou calculée sur le chiffre d'affaires avec des paramètres datés (taux national et taux départemental à fournir) ?
- **Q-V4 3520-SD** : le millésime 2026 n'est pas publié. On s'en tient à un **état récapitulatif** (clients, ventes par taux, forfait) qui sert à remplir le formulaire (proposition), sans reproduire ses cases tant qu'elles ne sont pas vérifiées ?
- **Q-V5 Prestations de services intracommunautaires** (`V_UE_S`) sur la CA12A : ligne 02 « autres opérations non imposables » (proposition), comme la CA3 actuelle qui les porte en E2 ? La CA12A n'a pas de ligne dédiée.

---

## 11. Sous-lots

| Sous-lot | Contenu | Livrable vérifiable |
|---|---|---|
| **AG2.a** Calendrier et moteur | `fr_calendar` ; `vat_period` à 3 valeurs ; moteur paramétré par formulaire (CA3 inchangée, tests existants au vert) ; CA3 trimestrielle ; remboursement 3519 (case 26) | Une CA3 trimestrielle et son échéance (5 mai, 5 août, 5 novembre, 5 février) ; un remboursement de 760 € demandé |
| **AG2.b** CA12A | `data/ca12a/2026.json` vérifié sur le formulaire ; calcul (19, 25, 28 à 30, VI, VII) ; liquidation (44581) ; exports | La CA12A du dossier fictif A, égale à un calcul de référence ; liquidation équilibrée |
| **AG2.c** Acomptes | Forme `ACOMPTE`, montant proposé, dispense, modulation et alerte de 30 %, écritures | Les 4 acomptes de A ; dispense sous 1 000 € |
| **AG2.d** Livres | Livres des ventes et des achats, contrôle croisé avec la CA12A, exports | Totaux du livre = lignes de la CA12A |
| **AG2.e** Remboursement forfaitaire | Classes de taux, types de client, attestations, demande, écritures, alerte de seuil, état | Le 3520 du dossier D (micro-BA, RFA) |
| AG2.f (reporté, Q-V2) | Secteur non agricole | — |

**Ordre** : a → b → c → d, et e en parallèle de b (indépendant du moteur).

---

## 12. Tests

- **Calendrier** : 2e jour ouvré après le 1er mai (5/5/2026, 4/5/2027), jours fériés mobiles, report des samedis et dimanches.
- **Moteur** : la suite CA3 existante reste au vert ; CA12A sur un jeu calculé à la main (taux 20, 10 et 5,5 %, immobilisation, autoliquidation, avoir reçu, crédit antérieur, 4 acomptes) ; cadre VII (150 €, excédent sans seuil, conseil des 4/5).
- **Acomptes** : 1/5 arrondi à l'euro supérieur ; dispense calculée avant TVA sur immobilisations ; alerte de 30 %.
- **CA3 trimestrielle** : découpage, échéance, report du crédit de trimestre en trimestre, remboursement (760 €, plafond).
- **Remboursement forfaitaire** : forfait par taux, exclusions, attestations manquantes ou divergentes, seuil de 46 000 € multiplié par les associés d'un GAEC, écriture 741.
- **Livres** : un achat non déductible figure au livre des achats ; les totaux du livre égalent les lignes de la CA12A.
- **Jeu d'essai** : la CA12A de l'exploitation A (réel simplifié) et le 3520 de D, à relire par l'expert-comptable (AGD5).
