# Besoins : fiabiliser les calculettes, l'assistant et les méthodes agricoles avec les guides du CEGARA

Brainstorm du 07/11/2026, branche `compta-agricole` (après `d44aae9`). Statut : **CG1 et CG2 réalisés le 07/11/2026** (non commités, `design_fiabilisation_cegara.md` § 5) ; CG3 à CG6 à faire.

## 0. Sources et règle d'usage

Dossier `doc/ref_compta/outils cegara/` (hors git depuis le 07/11/2026, règle AGD16) :

| Thème | Guides (PDF) | Outils (classeurs) | Millésime |
|---|---|---|---|
| Stocks, avances aux cultures | `0_guide-complet_2023.pdf` (évaluation des stocks), `livre_stock-2023-2024.pdf` (CEGAO) | outil-01 sous-activité (2025), outil-03 VCI (2018) | 2023-2024 |
| Matériel, entraide | 4 guides « barème BCMA » 2024 (entraide et façons culturales, général et viti-arbo : pas des doublons) | — | 2024 |
| DEP, DPI | — | outil-10 plafond DEP, outil-11 suivi de l'épargne DEP, outil-04 suivi DPI | 2018-2024 |
| MSA | guides cotisations 2024 (+ annexes, formulaires), annexe SMA 2021 | outil-06 cotisations (2012-2025), outil-08 SMA (2017) | 2017-2025 |
| Plantations | viti 2023 et 2024, arbo 2023 et 2024 (retenir les éditions 2024, `_protege`) | — | 2024 |
| Options, délais | `guide-complet.pdf` = guide « Délais » | — | **2019** |
| Foncier | contrôle des structures (exemple du SDREA Nouvelle-Aquitaine) | — | 2023 |

**Règle (reprise d'AGD16, à confirmer) :**
- Ces guides sont des **sources secondaires**. Ils servent à repérer des cas et des écarts, à construire des tests et à faire relire.
- Toute valeur reprise dans `data/regulatory/` cite la **source primaire** indiquée par le guide (CGI, annexe III, BOFiP, CRPM, msa.fr, décret), après vérification.
- Aucun texte, barème ni tableau n'est recopié dans le dépôt ni dans le corpus de l'assistant.
- Les classeurs ne servent **pas d'oracle**. On y a trouvé des erreurs, par exemple :
  - outil-10 : 4e tranche 2024 saisie « 12071 » ; dernière tranche multipliée par 2 au lieu de n associés ;
  - outil-06 : taux AMEXA tirés du revenu N-1 au lieu de l'assiette ;
  - outil-04 : intérêt de retard à 0,40 % périmé.
  Les cas de test sont recalculés à la main d'après la règle, puis vérifiés.
- Les guides datent de 2019 à 2024. La réforme de l'assiette MSA de 2026 et les lois de finances 2025-2026 les rendent **obsolètes pour les valeurs**. Ils restent utiles pour les **méthodes stables**.

## 1. Objectifs

1. **Corriger** les écarts de méthode que les guides révèlent dans le code (§ 2).
2. **Combler** les cas de gestion courants absents (changement de régime, sous-activité, plantations sur sol d'autrui, nouveaux installés MSA…).
3. **Donner à l'assistant une connaissance des méthodes**, et pas seulement des échéances et des paramètres : section « méthodes » du corpus.
4. **Ajouter des tests de non-régression** chiffrés, tirés des exemples des guides, avec leur millésime.
5. **Réduire les paramètres « I » (incertains)** en les confirmant ou en les corrigeant sur la source primaire.

## 2. Constats (relus dans le code le 07/11/2026)

Gravité : 🔴 résultat fiscal ou social faux, 🟠 cas manquant ou contrôle trompeur, 🟡 documentation ou ergonomie.

### 2.1 Stocks et avances aux cultures (AG4)

| # | Constat | Où | Gravité |
|---|---|---|---|
| ST1 | **M2 sans main-d'œuvre** : la main-d'œuvre n'est ni au standard ni au réel en M2. Selon les guides, M2 = mécanisation standard + approvisionnements **et main-d'œuvre salariée au réel**. | `crop_advances.py:32-33, 89` | 🔴 |
| ST2 | **Travaux par des tiers (6051)** rangés en « mécanisation » standard, donc écartés en M1/M2 alors que les guides les prennent au réel. Le préfixe 615 attire aussi l'entretien des bâtiments (6152). | `crop_advances.py:31-32` | 🔴 |
| ST3 | **Barème mensuel ou cumulé** : `value()` additionne les mois. Les guides publient des **cumuls** par mois de clôture, et rien à l'écran ne le précise. Un barème recopié tel quel est compté plusieurs fois. | `crop_advances.py:79`, `CropAdvancesPanel.tsx` | 🔴 |
| ST4 | **Pas d'écrêtement à ± 20 %** dans l'évaluation forfaitaire (de plein droit, sauf renonciation). | `stock_tax.py:140` | 🔴 |
| ST5 | **Pas de stock d'ouverture au passage du micro au réel** (PR, ou CJ s'il est inférieur, à la date du changement) : le premier exercice au réel taxe tout le stock. | `ba_regimes.py` | 🔴 |
| ST6 | **72 B bis** : le surplus est revalorisé chaque année au lieu d'être figé à sa première inscription. L'option se choisit ligne par ligne au lieu d'être globale. Le stock à rotation rapide est accepté. La non-cumulation avec 75-0 B n'est pas contrôlée. | `stock_tax.py:26,104`, `ba_regimes.py:343` | 🔴 |
| ST7 | **Option forfaitaire mal encadrée** : ni le réel simplifié ni l'IR ne sont vérifiés ; durée nulle (5 ans selon les guides) ; pas de gel après renonciation ; permise sur l'en-cours 33x et les plants. | `stock_tax.py:36`, `options.json:157`, `agri_stock_accounts.yml` | 🟠 |
| ST8 | **Pas d'alerte de provision** quand le cours du jour est inférieur au prix de revient, alors que la ligne porte les deux valeurs. | `stock_inventory.py:176-191` | 🟠 |
| ST9 | **Cas absents** : sous-activité (art. 38 nonies ann. III), méthodes T et R, produits de la ferme à 80 % du CJ, durée et irrévocabilité des méthodes d'avance, cumul des cycles longs, décote du prix de détail (38 sexdecies I) non calculée. | — | 🟠 |
| ST10 | **Main-d'œuvre de l'exploitant dans le barème** : les guides la retirent au prorata de la part non salariée. Lyvre n'affiche qu'un libellé `labour_assumption`. | `crop_advances.py:85` | 🟠 |

### 2.2 DEP et DPI (AG6.4, calculette 13)

| # | Constat | Où | Gravité |
|---|---|---|---|
| DP1 | **DPI réintégrée au 10e exercice** comme une DEP. Les guides indiquent le 5e exercice (art. 72 D ancien). Le test fige « DPI 2018 en 2028 ». | `dep.py:88-107`, `tests/api/test_dep.py:85-87` | 🔴 |
| DP2 | **Barème DEP seulement à partir du 01/01/2026** : une clôture 2024 ou 2025 n'a pas de barème. | `ba.json:214+` | 🟠 |
| DP3 | **Base DEP en société** : Lyvre la calcule après l'abattement JA. L'outil-10 la calcule avant l'abattement pour les sociétés. Les retraitements de base (revenus de l'art. 75, DPB, énergie, réintégrations) sont à vérifier. | `tax_result.py:144-152`, `calculators/dep.py:96` | 🔴 (à valider) |
| DP4 | **Date limite de l'épargne** : toujours 6 mois après la clôture, alors que la date de dépôt est plus tôt pour une clôture de novembre ou de décembre. | `dep.py:168` | 🟠 |
| DP5 | **Intérêt de retard non calculé** : il est seulement cité dans le libellé. | `dep.py:362` | 🟠 |
| DP6 | **Pas de suivi pluriannuel de l'épargne en stock** (fourrages, vins, gestion stricte ou souple). | — | 🟡 |

### 2.3 MSA (AG7, calculettes 10 et 17)

| # | Constat | Où | Gravité |
|---|---|---|---|
| MS1 | **Moyenne triennale d'assiettes déjà abattues**, au lieu de (somme ÷ 3) × 74 % avec les bornes. Les résultats diffèrent dès qu'une borne joue. | `msa.py:296` | 🔴 (à valider) |
| MS2 | **AMEXA du chef à titre secondaire** au barème progressif, au lieu d'un taux fixe. | `msa_estimate.py:51-61` | 🟠 |
| MS3 | **Pas de garde-fou micro-BA** (pas d'abattement de 26 %). | `msa.py:170-184` | 🟠 |
| MS4 | **Cas absents** de l'estimation : nouveaux installés (assiettes forfaitaires, exonération JA dégressive), ACRE, collaborateur (refusé), cotisant de solidarité, éléments d'assiette (épargne salariale, revenus de remplacement, indemnité d'abattage), rente du sol calculée. | `msa_estimate.py:85-86` | 🟠 |
| MS5 | **Valeurs 2026 non confirmées par les guides** (ils sont antérieurs à la réforme) : barème AMEXA, retraite de base 17,15 / 14,15 / 0,72 % contre 2,36 % annoncé en 2024, plancher et plafond de l'abattement, ATEXA. | `msa.json` | 🟠 |
| MS6 | **SMA et AMA non calculés** : un résumé seulement. | `social.yml:51-57` | 🟡 |

### 2.4 Plantations pérennes (AG5)

| # | Constat | Où | Gravité |
|---|---|---|---|
| PL1 | **Contrôle « en-cours sans coût de croissance »** signalé chaque année, alors que la pratique fiscale laisse les façons culturales des jeunes plantations en charges. | `living_assets.py:147-150` | 🟠 |
| PL2 | **Plantations sur sol d'autrui** : pas de sous-compte, pas de plafond de durée au bail, pas d'indemnité du preneur sortant. | `living_exits.py:24` | 🟠 |
| PL3 | **Autorisations de plantation (2082, non amortissable)** absentes du plan agricole. | plan agricole | 🟡 |
| PL4 | **Pas de durées indicatives par culture** (vigne 25 ans dès la 3e feuille, annexes 10 ans ; pommier 15, pêcher 12, prunier 25, kiwi 20, asperge 9…), qui reste à saisie libre (Q-B5). | `design_biens_vivants.md:125` | 🟡 |
| PL5 | **Cas non documentés** : arrachage puis replantation, remplacement de plants, surgreffage, aide à la restructuration FranceAgriMer (mixte). | — | 🟡 |

### 2.5 Options fiscales (`options.json`, guide « Délais » 2019)

| # | Constat | Gravité |
|---|---|---|
| OP1 | `ba_normal_option.duration_years` = 1 (I) ; le guide dit **2 ans** (art. 69 III). | 🟠 |
| OP2 | `flat_stock_method.duration_years` nul (I) ; **5 ans tacites** (art. 74 b, ann. III 38 sexdecies JC). | 🟠 |
| OP3 | `stock_freeze_72_b_bis.valid_from` = 2016 ; dispositif **réintroduit par la LF 2019**. | 🟠 |
| OP4 | `ba_simplified_option.renounce` : conflit de date (avant le 1er février ou dans le délai de déclaration) et d'article (64 bis V ou 69 IV). | 🟠 |
| OP5 | `rsa_option.renounce` nul ; le guide donne 2 mois avant l'expiration. `rsa_fiscal_year` n'a pas de paramètre. | 🟡 |
| OP6 | **Délais d'option absents** : option IS (avant la fin du 3e mois), méthode des avances aux cultures, 74 c, 74 d, 75-0 A, terres au bilan, TVA du bailleur rural. | 🟡 |

### 2.6 Entraide et coût du matériel (calculettes 14 et 22)

| # | Constat | Gravité |
|---|---|---|
| EN1 | La calculette 14 ne prend que des tarifs en €/h. Le BCMA donne les outils en **€/ha** (ou €/t, €/voyage) et les tracteurs en €/h. | 🟠 |
| EN2 | La calculette 22 ne distingue ni le **coût d'entraide** (avec intérêt sur le capital, 3,20 % en 2024) ni le **coût des façons culturales** (sans intérêt). Elle n'a pas de résultat « hors chauffeur » comparable au barème. | 🟡 |
| EN3 | Barème BCMA : 846 lignes, mis à jour chaque année, à variantes régionales, droits de reprise inconnus. **Pas de préremplissage** : saisie avec son millésime, comme le veut AGD15. | — |

### 2.7 Assistant (AG9b)

| # | Constat | Gravité |
|---|---|---|
| AS1 | Le corpus (`assistant/corpus.py`) ne contient que des **échéances, des paramètres et des écrans** : **aucune méthode** (stocks, avances, DEP, plantations, MSA). | 🟠 |
| AS2 | Échéances absentes de `social.yml` : **fin du statut de conjoint collaborateur au 31/12/2026** (urgent), à-valoir MSA au 31/12, expérimentation LFSS 2026 (fenêtre du 01/10 au 31/03 ouverte), rente du sol et renonciation JA au 30/06, modulation et mensualisation. | 🔴 (date proche) |
| AS3 | Fiches DEP, DPI, entraide, contrôle des structures et SMA absentes ; un seul cas d'évaluation sur la DEP. | 🟡 |

## 3. Exigences fonctionnelles

### F1 Corrections de méthode (priorité 1, après validation)
- **F1.1** M2 : main-d'œuvre salariée au réel (ST1).
- **F1.2** Avances M1 et M2 : travaux par des tiers (6051) au réel ; préfixe 615 restreint aux matériels (ST2).
- **F1.3** Barème d'avances : choix explicite **mensuel ou cumulé** à la saisie et à l'import, affiché à l'écran ; un barème cumulé donne la même valeur que son équivalent mensuel (ST3).
- **F1.4** Évaluation forfaitaire : écrêtement de ± 20 % de plein droit, avec renonciation tracée comme une option datée (ST4).
- **F1.5** DPI et DPA : échéance propre à chaque type (DPI 5 exercices ; DPA à vérifier) ; signaler les échéances dépassées ; corriger le test (DP1).
- **F1.6** Base DEP en société et retraitements, selon la réponse de l'expert-comptable (DP3).
- **F1.7** MSA : assiette triennale selon la règle validée (MS1) ; taux AMEXA du chef à titre secondaire (MS2) ; refus ou avertissement en micro-BA (MS3).
- **F1.8** 72 B bis : valeur figée à la première inscription, ordre PEPS, option globale, stock à rotation lente seulement, non-cumulation avec 75-0 B (ST6).

### F2 Cas manquants (priorité 2)
- **F2.1** Stock d'ouverture au passage du micro au réel (ST5).
- **F2.2** Alerte et proposition de provision quand le CJ est inférieur au PR (ST8).
- **F2.3** Sous-activité : rendement normal (moyenne des 3 rendements médians sur 5 ans), taux, charges fixes écartées en charge exceptionnelle. Calculette, et usage dans l'inventaire (ST9).
- **F2.4** Méthodes d'avance suivies comme des options : durée, irrévocabilité, restriction de F et T aux exploitants passés du micro au réel simplifié (ST7, ST9).
- **F2.5** Main-d'œuvre de l'exploitant retirée du barème au prorata de la part non salariée (ST10).
- **F2.6** DEP : date limite de l'épargne selon la clôture (DP4) ; calcul de l'intérêt de retard (DP5) ; historique du barème (2019 à 2025) depuis Légifrance (DP2).
- **F2.7** MSA : nouveaux installés, ACRE, collaborateur, cotisant de solidarité, lignes d'assiette typées, calcul de la rente du sol à partir des revenus cadastraux saisis (MS4).
- **F2.8** Plantations : contrôle PL1 nuancé (choix charges ou 7222) ; sol d'autrui (PL2) ; compte 2082 (PL3).
- **F2.9** Calculette 14 : tarif d'outil en €/ha ou €/unité (EN1). Calculette 22 : mode « BCMA » (prix, durée, valeur résiduelle, taux d'intérêt daté sur le capital moyen) et résultat hors chauffeur (EN2).
- **F2.10** Calculette SMA et AMA, **sans table départementale** : l'utilisateur saisit la SMA de son arrêté (MS6).

### F3 Paramètres datés (priorité 1 pour les corrections, 2 pour les ajouts)
- **F3.1** Corriger ou confirmer OP1 à OP5 sur la source primaire ; passer de I à V ce qui est vérifié.
- **F3.2** Ajouter les délais d'option manquants (OP6).
- **F3.3** Durées indicatives des plantations en paramètres « I » (`assets.plantation.*`), proposées par défaut et modifiables (PL4).
- **F3.4** Revérifier les valeurs MSA 2026 de MS5 sur msa.fr et Légifrance.

### F4 Assistant
- **F4.1** Ajouter au corpus une section **« Méthodes »** : fiches courtes rédigées par nous, chacune avec ses sources primaires, sa date de vérification et sa fiabilité. Ce sont des **synthèses** ; aucun texte de tiers n'y est repris.
- **F4.2** Fiches, par priorité :
  1. conjoint collaborateur 2026 ;
  2. évaluation des stocks par régime ;
  3. avances aux cultures (méthodes, options) ;
  4. DEP (base, épargne, intérêt) et DPI résiduelles ;
  5. plantations pérennes ;
  6. assiette MSA et cas particuliers ;
  7. entraide et coût du matériel ;
  8. SMA et AMA ;
  9. contrôle des structures (national, avec renvoi au SDREA) ;
  10. aide à la restructuration du vignoble.
- **F4.3** Échéances AS2 ajoutées à `social.yml` avec leurs événements.
- **F4.4** Le jeu d'évaluation s'étend aux nouvelles fiches (au moins une question par fiche, dont une piège sur une valeur périmée d'un guide 2019).

### F5 Tests de non-régression
Cas recalculés à la main, chacun avec son millésime de paramètres et sa source :

| Cas | Valeur attendue (à recalculer) | Origine |
|---|---|---|
| Écrêtement, porcs à 1,30 / 1,90 / 1,60 €/kg | 1,04 → 1,25 → 1,28 | stocks, ex. p. 3 |
| Décote 38 sexdecies I, vin vrac et bouteilles | 40 % et 36 % ; 3 000 et 16 000 | stocks |
| Blé, clôture au 31 mars, 10 ha, F, M1 et M2, barème mensuel et cumulé | F 6 140 (5 520 sans salariés) ; M1 2 520 + achats ; M2 1 900 + achats et main-d'œuvre | stocks |
| DEP 2023 et 2024, exploitant individuel, bénéfice 100 000 € ; exercice de 9 mois avec plafond global | 43 274,70 ; 47 922,00 ; 10 000 | outil-10 corrigé |
| MSA 2025 (PASS 47 100, SMIC 11,88), assiettes 60 000 / 30 000 / 10 000 | AMEXA 3 900 / 1 255,41 / 0, etc. | outil-06 recalculé |
| Vigne plantée en 2021, valeur nette au 01/01/2025 ; kiwi planté en 2024 | 26 098 ; 30 007 contre 30 008 (arrondi) | plantations |

## 4. Exigences non fonctionnelles
- Chaque correction de méthode cite **l'article** (CGI, annexe, BOFiP, CRPM) dans le code ou dans le paramètre, comme aujourd'hui.
- Aucune valeur des guides n'entre dans `data/regulatory/` sans la source primaire et `verified_on`.
- Les corrections qui modifient un résultat déjà clôturé (DEP, DPI, stocks) affichent l'écart et ne réécrivent pas les écritures validées.
- Le dossier `outils cegara/` reste hors git ; les cas de test ne reprennent que des nombres.

## 5. Critères d'acceptation
- Les constats 🔴 sont soit corrigés et couverts par un test, soit classés « conforme » par l'expert-comptable, avec une note dans § 6.
- `options.json` ne contient plus de durée nulle pour une option connue.
- L'assistant répond juste et cite une source primaire aux questions d'évaluation des nouvelles fiches ; le score global reste au moins à 98 %.
- Pytest et Vitest passent ; les nouveaux cas F5 sont présents.

## 6. Questions ouvertes

### Pour l'expert-comptable
1. **DEP en société** : base avant ou après l'abattement JA ? Retraitements de base (art. 75, DPB, énergie) ?
2. **DPI et DPA** : échéance de 5 exercices pour les DPI, et durée des DPA ? Intérêt de retard : point de départ et taux ?
3. **Date limite de l'épargne DEP** : 6 mois, ou la date de dépôt si elle est plus tôt ? Sanction quand l'épargne dépasse 100 % ?
4. **MSA** : abattement année par année ou sur la moyenne triennale ? Taux AMEXA et prestations familiales fondés sur l'assiette ou sur N-1 ? Valeurs 2026 (MS5).
5. **Avances M1 et M2** : travaux par des tiers au réel ? Main-d'œuvre salariée au réel en M2 ?
6. **Stock d'ouverture au passage au réel** : règle en vigueur après la LF 2020.
7. **72 B bis** : première inscription et PEPS, option globale, plafond de minimis (relevé par le règlement UE 2024/3118 ?).
8. **Jeunes plantations** : façons culturales en charges ou en 7222 ? Choix par dossier ? Mise en service à la 1re récolte ou au 1er jour de l'exercice ?
9. **Options** OP1 à OP5.
10. **Arrondi DEP** : montants fixes du BOI ou somme des tranches ?

### Pour l'utilisateur
- Q-CG1 Ordre des lots : corrections 🔴 d'abord, ou fiches de l'assistant d'abord (l'échéance du conjoint collaborateur tombe le 31/12/2026) ?
- Q-CG2 Faut-il attendre l'avis de l'expert-comptable sur les points 1 à 10 avant de coder, ou corriger tout de suite ce qui n'est pas controversé (ST1, ST2, ST3, DP1, DP2, OP2) ?
- Q-CG3 La sous-activité, les nouveaux installés MSA et les plantations sur sol d'autrui sont-ils dans le périmètre de la première version ?
- Q-CG4 Calculette SMA : la faire (saisie de la SMA) ou s'en tenir à une fiche ?

### Réponses de l'utilisateur (07/11/2026)
- **Q-CG1** : commencer par les échéances (CG1), puis les corrections (CG2).
- **Q-CG2** : corriger tout de suite ce qui n'est pas controversé (ST1, ST2, ST3, DP1, DP2, OP2, OP3). Les 10 questions du § 6 partent en parallèle à l'expert-comptable.
- **Q-CG3** : la première version comprend les stocks (F2.1, F2.2, F1.4, F1.8), la sous-activité (F2.3), les cas particuliers MSA (F2.7) et les plantations (F2.8, F3.3).
- **Q-CG4** : SMA traitée par une fiche de l'assistant seulement ; pas de calculette (F2.10 retirée).

### Réponses aux questions 1 à 10 (utilisateur, 07/11/2026)

| # | Question | Décision | Point à vérifier au codage |
|---|---|---|---|
| 1 | Base DEP en société | **Avant l'abattement JA en société** ; après l'abattement JA en individuel | Retraitements de base de l'outil 10 (art. 75, DPB, énergie) : à relire au BOFiP |
| 2 | DPI et DPA | **DPA réintégrée au 7e exercice** (DPI au 5e, fait) ; **intérêt calculé** à la réintégration, « au taux légal » | Le CGI applique l'intérêt de retard de l'art. 1727 (0,40 %/mois jusqu'au 31/12/2017, puis 0,20 %), pas l'intérêt légal : taux à confirmer |
| 3 | Date limite de l'épargne DEP | **6 mois après la clôture, ou date de dépôt de la déclaration si elle est plus tôt** | Date de dépôt selon la clôture (échéancier fiscal) |
| 3 bis | Épargne au-delà de 100 % | **Réintégration proposée** (ligne à valider) | Montant réintégré : texte à relire (art. 73) |
| 4 | Triennale MSA | **Moyenne des revenus, puis abattement de 26 % borné** | — |
| 4 bis | Base des taux progressifs AMEXA et prestations familiales | **Revenu N-1** | L'analyse du classeur outil-06 y voyait un défaut : à confirmer sur msa.fr |
| 4 ter | AMEXA du chef à titre secondaire | **Taux fixe, paramètre daté** (`msa.amexa.secondary_rate_bp`) | Valeur 2026 à sourcer sur msa.fr |
| 5 | M1 et M2 | Travaux par des tiers et main-d'œuvre au réel confirmés ; **rémunérations des associés (64116, 64117) incluses** dans la main-d'œuvre | Retirer `EXCLUDED_ACCOUNTS` (CG2.a) |
| 5 bis | Main-d'œuvre de l'exploitant dans le barème | **Part de main-d'œuvre salariée saisie** sur la fiche ; composante main-d'œuvre réduite d'autant | — |
| 6 | Passage du micro-BA au réel | **Stock d'ouverture guidé** (PR, ou CJ s'il est inférieur, à la date du changement), écriture d'ouverture | ann. III art. 38 sexdecies D, LF 2020 art. 55 |
| 7 | 72 B bis, valeur | **Première inscription, sorties PEPS** | — |
| 7 bis | 72 B bis, contrôles | **Option globale ; rotation lente seule ; avertissement de minimis** | Non-cumul avec 75-0 B **non retenu** : le BOFiP l'interdit, sauf modification par la LF 2026 (à vérifier) |
| 8 | Façons culturales des jeunes plantations | **Choix par dossier** (charges ou 7222), le contrôle suit le choix | — |
| 8 bis | Mise en service d'une plantation | **1er jour de l'exercice** de la 1re récolte (annuité entière) | — |
| 8 ter | Durées par culture | **Proposées par défaut, modifiables** (paramètres « I ») | — |
| 9 | Option réel normal | **2 exercices** | Lire l'art. 69 III avant de passer en V |
| 9 bis | Renonciation au réel simplifié | **À vérifier au CGI** (art. 64 bis V ou 69 IV), puis appliquer la version en vigueur | — |
| 9 ter | Compléments d'options | **Renonciation au RSA et `rsa_fiscal_year` ; délais d'option (IS, avances, 74 c, 74 d, 75-0 A, terres au bilan, TVA du bailleur) ; option CA3 mensuelle** | Chaque valeur sur sa source primaire |
| 10 | Arrondi DEP | **Montants fixes du BOFiP** par tranche (bases en paramètres) | Bases 2019 à 2026 au § 10 du BOI |
| 10 bis | Barème DEP 2026 | **Aligné sur le BOFiP du 12/08/2026** (33 234 / 61 544 / 92 317 / 123 088 €, plafond 50 959 €) | Remplace la valeur « confirmée le 05/11/2026 » |

## 7. Découpage (validé le 07/11/2026)

| Lot | Contenu | Dépend de |
|---|---|---|
| **CG1** | Échéances urgentes (AS2) et fiche « conjoint collaborateur » | — |
| **CG2** | Corrections sans controverse : ST1, ST2, ST3, DP1, DP2, OP2, OP3, plus les tests F5 correspondants | — |
| **CG3** | Corrections après validation : DP3, MS1, MS2, MS3, ST4, ST6, OP1, OP4, OP5 | questions 1 à 4, 7, 9 |
| **CG4** | Section « Méthodes » du corpus et fiches F4.2 (2 à 10), avec le jeu d'évaluation | CG2, CG3 pour les contenus |
| **CG5** | Cas manquants F2 (changement de régime, provision, sous-activité, options des avances, MSA, plantations) | CG3 |
| **CG6** | Calculettes : 14 en €/ha, 22 en mode BCMA ; durées des plantations (SMA en fiche seulement) | — |
