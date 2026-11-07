# Conception : fiabilisation CEGARA, lots CG1 et CG2

Besoins : `claudedocs/fiabilisation_cegara.md` (07/11/2026). Ce document conçoit les deux premiers lots validés :
- **CG1** : échéances urgentes et fiches de l'assistant ;
- **CG2** : corrections sans controverse.

Les lots CG3 à CG6 attendent l'avis de l'expert-comptable.

**Règle commune :** toute valeur ou date ajoutée cite sa **source primaire** (Légifrance, BOFiP, msa.fr), relue au moment du codage, avec `verified_on`. Une source primaire introuvable donne la fiabilité « I » et le texte « à confirmer ». Rien n'est repris des guides du CEGARA.

---

## CG1 Échéances MSA et fiches de l'assistant

### 1.1 Drapeau dérivé « collaborateur d'exploitation »

**Constat.** L'échéancier ne connaît pas le statut MSA des personnes. Ce statut est pourtant enregistré : `MsaPerson.status = "collaborator"` (`app/models/msa.py:10`).

**Conception.**
- Ajouter un drapeau **dérivé** `msa_collaborator` à `agri_profile.FLAGS`, sur le modèle de `leases` (`agri_profile.py:39`). Il ne s'ajoute pas aux booléens saisis.
- `deadlines.Context` le calcule à la construction (`deadlines.py:246`) : vrai si une `MsaPerson` a le statut `collaborator`.
- `_check_applies` l'accepte déjà, puisqu'il lit `FLAGS`.
- Valeur absente (aucune personne MSA) : faux. La fiche ne s'affiche pas, mais l'assistant la connaît par le corpus.

**Limite assumée.** Le conjoint collaborateur n'est pas toujours suivi dans `/msa/`. Le résumé de la fiche le dit, et l'assistant la cite quand on lui pose la question.

### 1.2 Fiches et événements (`data/deadlines/social.yml`)

| Id | Contenu | Règle | Applicabilité | Fiabilité |
|---|---|---|---|---|
| **SOC-06** (nouvelle) | **Fin du statut de conjoint collaborateur.** Statut limité à 5 ans ; pour les conjoints déjà collaborateurs au 01/01/2022, fin au 31/12/2026, sauf exception à préciser. Choix d'un autre statut (chef, salarié, associé) au guichet unique. | `once` 2026-12-31, rappels [90, 30, 7] | `flags: [msa_collaborator]` | V si l'article est retrouvé (CRPM L.321-5 et sa loi modificative), sinon I |
| **SOC-07** (nouvelle) | **À-valoir sur cotisations MSA.** Demande et paiement avant le 31/12 ; plafond (% des dernières cotisations) ; lien avec la déduction de l'art. 72 F déjà gérée (`MSA_ADJUSTMENT_KINDS["avaloir"]`). | `fixed` 12-31, `shift: none`, rappels [45, 15] | `ba_regime: [simplified, normal]` | R après vérification |
| **SOC-08** (nouvelle) | **Estimation des revenus de l'année (expérimentation LFSS 2026).** Fenêtre du 01/10 au 31/03. Résumé repris de la note de `msa.py:319-322`. | `fixed` 03-31 | toutes | I tant que le décret n'est pas relu |
| **SOC-03** (complétée) | Deux événements ajoutés : « Rente du sol : demande ou dénonciation » au 06-30 ; « Renonciation à l'exonération JA au profit du taux AMEXA réduit » au 06-30. | `fixed` 06-30, `shift: none`, `quiet: true` | le 2e événement : `flags: [young_farmer]` | R |
| **SOC-02** (complétée) | `prepare` : modulation des appels au plus tard 15 jours avant l'exigibilité ; mensualisation (demande reçue entre le 1er et le 15, prélèvement le mois suivant). Aucun nouvel événement : la date dépend de l'appel. | — | — | R |
| **SOC-04** (enrichie, Q-CG4) | Assujettissement : 1 SMA, 1 200 h ou revenus de 800 SMIC ; cotisant de solidarité entre ¼ et 1 SMA ou entre 150 et 1 200 h ; maintien à partir de ⅔ SMA ; parcelle de subsistance ; SMA fixée par arrêté préfectoral (à lire dans le schéma départemental). **Pas de calculette.** | `events: []` | toutes | R après vérification CRPM L.722-5, L.731-23 |

Les identifiants SOC-06 à SOC-08 suivent la numérotation existante. Le schéma (`FICHE_KEYS`, `EVENT_KEYS`) ne change pas.

### 1.3 Assistant

- **Corpus** : aucun changement de code. `corpus.text()` charge déjà toutes les fiches. Le cache (`lru_cache`) se vide au redémarrage.
- **Jeu d'évaluation** (`tests/assistant_evals/cases.yaml`), 3 cas :
  - `conjoint-collaborateur` : « Ma femme est conjointe collaboratrice depuis 2015, que dois-je faire ? » ; attendu : `cites: ['\[SOC-06\]', '31/12/2026|31 décembre 2026']`, aucune proposition ;
  - `msa-avaloir` : « Puis-je payer un à-valoir MSA cette année ? » ; attendu : `cites: ['\[SOC-07\]']` ;
  - `assujettissement-sma` : « À partir de combien d'hectares suis-je chef d'exploitation ? » ; attendu : `cites: ['\[SOC-04\]']`, `contains: ["arrêté"]`, pas de valeur départementale inventée (`not_contains` sur un nombre d'hectares type).

### 1.4 Tests (pytest)
- Schéma : `deadlines.load()` valide les nouvelles fiches (test existant du schéma).
- Drapeau dérivé :
  - instance avec une `MsaPerson` collaboratrice : SOC-06 apparaît dans `/agenda/` à 2026-12-31 ;
  - sans collaborateur : SOC-06 n'apparaît pas.
- SOC-03 : l'événement JA n'apparaît que si le drapeau `young_farmer` est présent.

---

## CG2 Corrections sans controverse

### 2.1 Avances aux cultures : rubriques prises au réel selon la méthode (ST1, ST2)

**Constat.**
- En M2, la main-d'œuvre n'est comptée nulle part, ni au barème ni au réel (`crop_advances.py:32-33, 89`).
- Les travaux par des tiers (6051) sont rangés dans « mécanisation », donc écartés en M1 et M2.
- Le préfixe 615 propose aussi l'entretien des bâtiments (6152).

**Conception.**

1. Nouvelle rubrique `contracting` (« Travaux et services par des tiers ») dans `CROP_RUBRICS` (`app/models/stock.py:162`). Le libellé de `machinery` perd « travaux par des tiers ».
2. `RUBRIC_ACCOUNTS` :
   - `contracting: ("6051",)` ;
   - `machinery: ("60614", "6155", "6156", "6132", "6811")`, au lieu de `615` ;
   - `labour: ("641", "645")`, sans les comptes des associés `64116` et `64117` (main-d'œuvre **salariée** seulement).
3. Une table remplace le calcul en ligne de `rubrics` (`crop_advances.py:89`) :

   ```
   REAL_RUBRICS_BY_METHOD = {
       "standard_f":  (),
       "standard_m1": ("seeds", "fertilizers", "treatments", "contracting"),
       "standard_m2": ("seeds", "fertilizers", "treatments", "contracting", "labour"),
       "actual":      tuple(CROP_RUBRICS),
   }
   ```

   `COMPONENTS_BY_METHOD` ne change pas : M2 reste mécanisation seule au barème.
4. Libellés de `CROP_METHODS` : M1 = « mécanisation et main-d'œuvre au barème ; approvisionnements et travaux par des tiers au réel » ; M2 = « mécanisation au barème ; approvisionnements, travaux par des tiers et main-d'œuvre salariée au réel ».
5. **Données existantes.** Une migration Alembic reclasse les `CropAdvanceCost` de rubrique `machinery` dont la ligne d'écriture porte sur un compte 6051…, seulement pour les **exercices ouverts**. Les exercices clôturés ne sont pas modifiés : leur valeur d'inventaire est figée. Le texte « charges non prises par la méthode » reste affiché tel quel.

**Écran** (`CropAdvancesPanel.tsx`) : la liste des rubriques proposées suit `REAL_RUBRICS_BY_METHOD`, renvoyée par l'API dans les options (pas de copie de la table côté front).

### 2.2 Barème saisi par mois ou en cumul (ST3)

**Constat.** `value()` additionne les montants mensuels. Un barème publié en cumul par mois de clôture, puis saisi tel quel, est compté plusieurs fois.

**Conception : une seule représentation interne, le montant mensuel.**
- `CropStandard.entry_mode` : `monthly` (par défaut) ou `cumulative`. `CropStandard.start_month` (1 à 12) : premier mois du cycle, obligatoire en cumul.
- Saisie ou import en cumul : conversion en montants mensuels **à l'enregistrement** :
  - on parcourt les mois dans l'ordre du cycle à partir de `start_month` ;
  - mensuel(m) = cumul(m) − cumul(mois précédent du cycle) ;
  - un écart négatif est refusé (« le cumul baisse en <mois> »).
- `value()` ne change pas.
- Restitution : `standard_payload` renvoie aussi les cumuls recalculés pour l'affichage. Une saisie en cumul se relit en cumul.
- **Import CSV** (`import_standards`) : 6e colonne facultative « Mode » (`mensuel` / `cumul`) et 7e « Début du cycle » (mois). Sans ces colonnes, le mode est `monthly` comme aujourd'hui, et un avertissement s'affiche si la série est croissante sur au moins 6 mois (« ce barème ressemble à un cumul »).
- **Écran** : sélecteur « Montants saisis : par mois / en cumul » ; en-tête de colonne explicite ; aide « Les barèmes publiés donnent souvent le cumul au mois de clôture ».
- Migration : colonnes `entry_mode` (défaut `monthly`) et `start_month` (nul).

### 2.3 DPI et DPA : échéance propre à chaque type (DP1)

**Constat.** `dep.py:88-107` et le libellé de `dep.py:357` appliquent `ba.dep.reintegration_years` (10) aux DPI et aux DPA. Le test `tests/api/test_dep.py:85-87` fige « DPI 2018 en 2028 ».

**Conception.**
- Paramètres datés (`ba.json`) :
  - `ba.dpi.reintegration_years` = **5** (CGI art. 72 D, version en vigueur jusqu'au 31/12/2018 ; BOI-BA-BASE-30-40), fiabilité R après lecture ;
  - `ba.dpa.reintegration_years` = valeur à lire dans l'art. 72 D bis en vigueur à la dernière dotation. **I** tant que l'expert-comptable n'a pas confirmé (question 2 du § 6 des besoins) ; 10 en attendant, pour garder le comportement actuel.
- Une fonction `horizon(entry, on)` choisit la clé selon `entry.kind`. Elle est utilisée par `deadline_label`, `_is_deadline` et le libellé de la ligne de réintégration : « … non utilisée : réintégration au {n}e exercice ».
- **Échéance déjà dépassée** (origine + n antérieure au premier exercice tenu dans Lyvre) :
  - aucune réintégration automatique ;
  - un contrôle de clôture `dep_deadline_past` (avertissement) : « DPI 2018 : échéance à la clôture 2023, antérieure aux exercices tenus dans Lyvre ; vérifier qu'elle a été réintégrée ». Il est levé quand le reliquat est mis à zéro ou qu'un mouvement de réintégration est saisi.
- **Test corrigé** :
  - DPI 2018 sur l'exploitation de test (exercices à partir de 2026) → avertissement `dep_deadline_past`, pas de ligne `dep_deadline_` en 2028 ;
  - nouveau cas : DPI dans un exercice tenu dans Lyvre → ligne de réintégration au 5e exercice.

### 2.4 Barème DEP de 2019 à 2025 (DP2)

**Constat.** Toutes les clés `ba.dep.*` partent du 2026-01-01. Une clôture antérieure donne « Barème introuvable ».

**Conception.**
- Pour chaque version de l'art. 73 (et du BOI-BA-BASE-30-45-10) applicable aux **exercices clos** depuis le 01/01/2019 : une entrée datée par clé qui change (seuils et plafond), avec `valid_from` et `valid_to` jointifs. `reg_params` prend déjà la valeur selon `fy.end_date`.
- Les clés stables (taux, `reintegration_years`, `savings_min_bp`, `global_cap_cents`, `end_date`…) : `valid_from` ramené au début de leur validité réelle, après vérification qu'elles n'ont pas changé.
- Les clés propres aux versions récentes (exonération de 30 % en cas d'aléa, part économique de 40 %) gardent leur date d'entrée en vigueur : `ceiling_for` ne doit pas les exiger pour une clôture antérieure. On vérifie la liste `keys` de `dep.py:58`, qui ne comprend que les tranches, les taux et le plafond.
- **Arrondi** (question 10 aux experts) : on garde la somme des tranches (comportement actuel) et on note l'écart possible avec les montants fixes du BOI (quelques dizaines de centimes).
- Tests (valeurs recalculées à la main sur les seuils relus, pas reprises de l'outil 10) :
  - clôture 2023, exploitant individuel, bénéfice 100 000 € ;
  - clôture 2024, même cas ;
  - clôture 2024, exercice de 9 mois, déductions non rapportées de 140 000 € → limité par le plafond global ;
  - GAEC de 3 associés, bénéfice 150 000 € → limité au bénéfice ;
  - clôture 2018 → « Barème introuvable » maintenu (avant la DEP).

### 2.5 Options (OP2, OP3)

| Clé | Aujourd'hui | Cible | Source à relire |
|---|---|---|---|
| `option.flat_stock_method.duration_years` | nul, I | **5**, R (V si le texte est explicite) | CGI art. 74 b ; ann. III art. 38 sexdecies JC |
| `option.stock_freeze_72_b_bis.duration_years` | `valid_from` 2016-01-01 | `valid_from` = date d'application de la version en vigueur (réintroduction), `valid_to` sur l'éventuelle version antérieure | Historique des versions de l'art. 72 B bis sur Légifrance |

Le code qui lit ces durées (contrôles d'options, `tax_profile`) gère déjà une valeur absente. Pour une date antérieure au nouveau `valid_from`, il faut vérifier que l'option 72 B bis s'affiche « non applicable » et ne provoque pas d'erreur.

### 2.6 Tests et documentation
- Pytest : les cas ci-dessus. Ajouter à la suite d'avances aux cultures le cas « blé, clôture au 31 mars, 10 ha », recalculé sur un **barème fictif** maison (pas les valeurs du CEGARA), avec trois contrôles :
  - F, M1 et M2 ;
  - M2 avec main-d'œuvre salariée réelle ;
  - le même barème saisi en cumul donne la même valeur.
- Vitest : sélecteur de mode du barème, rubriques proposées selon la méthode.
- Documentation :
  - `design_inventaire_agricole.md` § 5 (rubriques par méthode, mode du barème) ;
  - `design_compta_agricole.md` ou `design_tax_result` (horizon DPI) ;
  - « État » de `fiabilisation_cegara.md`.

---

## 3. Ordre de réalisation et estimation

| Étape | Contenu | Fichiers principaux | Migration |
|---|---|---|---|
| CG1.a | Drapeau `msa_collaborator`, SOC-06 à SOC-08, SOC-02 à SOC-04 complétées, tests | `agri_profile.py`, `deadlines.py`, `social.yml`, `tests/` | non |
| CG1.b | 3 cas d'évaluation (lancement manuel, hors CI) | `tests/assistant_evals/cases.yaml` | non |
| CG2.a | Rubriques par méthode, `contracting`, comptes | `models/stock.py`, `crop_advances.py`, `CropAdvancesPanel.tsx` | oui (reclassement, exercices ouverts) |
| CG2.b | Barème mensuel ou cumulé | `models/stock.py`, `crop_advances.py`, écran des barèmes | oui (2 colonnes) |
| CG2.c | Horizon DPI et DPA, contrôle `dep_deadline_past`, test corrigé | `dep.py`, `ba.json`, `closing.py`, `tests/api/test_dep.py` | non |
| CG2.d | Barème DEP 2019-2025 | `ba.json`, tests | non |
| CG2.e | Options OP2 et OP3 | `options.json` | non |

Un commit par étape. CG1 et CG2.c à CG2.e ne touchent pas au schéma de la base. CG2.a et CG2.b ajoutent chacun une migration.

## 4. Points restant ouverts dans ce périmètre
- **D-CG1** Comptes de main-d'œuvre salariée pour M2 : 641 et 645 sans 64116 ni 64117. À confirmer avec l'expert-comptable (le classement reste modifiable charge par charge).
- **D-CG2** Durée de la DPA : 10 « I » en attendant la réponse.
- **D-CG3** Article exact de la fin du statut de conjoint collaborateur et éventuelles dérogations : à relire avant de passer SOC-06 en V.

---

## 5. Réalisé (07/11/2026, non commité)

| Étape | Fait | Écarts avec la conception |
|---|---|---|
| CG1.a | Drapeau dérivé `msa_collaborator` (`agri_profile.DERIVED_FLAGS`, calculé dans `deadlines.context()`) ; SOC-06 (fin du statut de conjoint collaborateur, 31/12/2026), SOC-07 (à-valoir, 31/12), SOC-08 (estimation des revenus N, 31/03, fiabilité I) ; SOC-02 (`prepare` : modulation, mensualisation), SOC-03 (rente du sol, renonciation JA au 30/06), SOC-04 (assujettissement, SMA à lire dans l'arrêté) | SOC-06 en fiabilité R : principe et date recoupés (CRPM L.321-5, LFSS 2022), **texte de l'article non lu** ; exception d'âge (avant 2032) laissée « à vérifier ». Liens Légifrance au niveau des codes (pas d'identifiant d'article non vérifié). |
| CG1.b | 3 cas d'évaluation (`conjoint-collaborateur`, `msa-avaloir`, `assujettissement-sma`) | À lancer à la main (`scripts/run_assistant_evals.py`). |
| CG2.a | Rubrique `contracting` (6051) ; `CROP_REAL_RUBRICS` par méthode ; main-d'œuvre 641 et 645, hors 64116 et 64117 ; mécanisation sans 6152 ; table servie à l'écran (`meta.real_rubrics`) ; migration `f2a4b6c8d0e2` (exercices ouverts) | Nom de rubrique `contracting` (la colonne fait 12 caractères). Les fiches M1/M2 déjà enregistrées ne sont recalculées qu'à leur prochaine modification. |
| CG2.b | `CropStandard.entry_mode` et `start_month` (migration `a3b5c7d9e1f3`) ; conversion des cumuls à l'enregistrement, cumul en baisse refusé ; `cumulative_rows` ; import CSV à 7 colonnes ; avertissement « sans doute un cumul » (6 mois croissants) ; écran : sélecteur, mois dans l'ordre du cycle | — |
| CG2.c | `ba.dpi.reintegration_years` = 5 (R), `ba.dpa.reintegration_years` = 10 (I) ; `dep.horizon()` ; libellés « au {n}e exercice » ; contrôle `dep_deadline_past` (anomalie) ; DPI et DPA refusées après 2018 ; test corrigé | Colonne « Échéance » au lieu de « 10e exercice » dans le registre. |
| CG2.d | Seuils et plafonds DEP 2019-2022, 2023, 2024, 2025 lus dans le BOI-BA-BASE-30-45-20 § 10 (versions 2019 à 2025) ; taux, plafond global, épargne minimale et horizon ramenés à 2019 ; `end_date` 2025-12-31 pour 2019-2025 | Clés de l'exonération en cas d'aléa et de la part économique laissées à 2026 (non vérifiées pour les années antérieures). |
| CG2.e | `flat_stock_method` : 5 exercices, reconduction tacite (V, BOI-BA-BASE-20-20-20-20 § 80-90) ; `stock_freeze_72_b_bis` : `valid_from` 2019-01-01 (LF 2019 art. 58) | — |

**Écart découvert** (corrigé au lot CG3.a, Q10 bis) : le barème DEP 2026 de `ba.json` (33 287 / 61 642 / 92 464 / 123 284 €, plafond 51 040 €, « confirmé par l'expert-comptable le 05/11/2026 ») ne correspond pas au BOI-BA-BASE-30-45-20-20260812 § 10 (33 234 / 61 544 / 92 317 / 123 088 €, plafond 50 959 €).

---

# Lot CG3 : corrections après les réponses du 07/11/2026

Source : tableau « Réponses aux questions 1 à 10 » de `fiabilisation_cegara.md` § 6. CG3 corrige des **comportements existants** selon ces réponses. Les fonctions nouvelles retenues par les mêmes réponses relèvent de CG5 (§ 6.7) :
- part de main-d'œuvre salariée sur la fiche (Q5 bis) ;
- stock d'ouverture au passage au réel (Q6) ;
- plantations (Q8, Q8 bis, Q8 ter) ;
- sous-activité ;
- cas particuliers MSA.

Même règle qu'en CG1 et CG2 : chaque valeur ajoutée cite sa source primaire, relue au codage. Les montants en euros des exemples se recalculent à la main.

## 6.1 CG3.a Reprises de CG2

| # | Changement | Où |
|---|---|---|
| a1 | Main-d'œuvre des avances aux cultures : les rémunérations des associés (64116, 64117) sont comptées (Q5). `EXCLUDED_ACCOUNTS` disparaît ; le libellé de la rubrique devient « Main-d'œuvre (salariés et associés) ». | `crop_advances.py`, `models/stock.py`, test CG2.a (le cas « Rémunération associé » passe dans les propositions) |
| a2 | **Barème DEP 2026 aligné sur le BOI-BA-BASE-30-45-20-20260812 § 10** (Q10 bis) : 33 234 / 61 544 / 92 317 / 123 088 €, plafond 50 959 €. `source_label` : BOFiP, lu le 07/11/2026 ; la mention « confirmé par l'expert-comptable le 05/11/2026 » est retirée. | `ba.json` ; cas `calculette-dep` du jeu d'évaluation et tests 2026 recalculés |
| a3 | **Montants fixes du BOFiP par tranche** (Q10). Nouvelles clés `ba.dep.fixed3_cents` (montant au 2e seuil) et `ba.dep.fixed4_cents` (au 3e seuil), datées comme les seuils (2019-2022, 2023, 2024, 2025, 2026). Calcul : sous T1, le bénéfice ; de T1 à T2, T1 + 30 % × (B − T1) ; de T2 à T3, fixed3 + 20 % × (B − T2) ; de T3 à T4, fixed4 + 10 % × (B − T3) ; au-delà de T4, le plafond. Un seul arrondi au centime. | `dep.ceiling_for`, `calculators/dep.py` (liste des paramètres), tests CG2.d (2023 : 43 274,20 € au lieu de 43 274,70 €) |

Valeurs fixed3 et fixed4 (BOFiP § 10) :

| Période | fixed3 | fixed4 |
|---|---|---|
| 2019-2022 | 33 900 | 38 900 |
| 2023 | 35 924 | 41 222 |
| 2024 | 40 942 | 46 979 |
| 2025 | 41 421 | 47 529 |
| 2026 | 41 728 | 47 881 |

## 6.2 CG3.b DEP, DPI et DPA

**b1 Base du plafond en société (Q1).**
- `api/tax_result._dep_view` choisit la base :
  - en société (au moins un associé dans `associates`) : `fiscal_result_before_ja_cents` ;
  - en individuel : `fiscal_result_before_dep_cents`, comme aujourd'hui.
- La calculette 13 reçoit un choix « société / individuel » et son aide l'explique.
- `dep.ceiling` change de docstring.
- Retraitements de base (D-CG3.1, BOFiP lu au codage) :
  - les revenus accessoires de l'art. 75 sont retranchés (§ 290). Lyvre ne connaît pas leur résultat : un avertissement s'affiche quand l'exercice a des recettes accessoires (`dep.base_notes`) ;
  - les revenus des DPB et de l'énergie restent dans la base quand l'exploitation a une autre activité agricole (§ 325 à 340).

**b2 DPA au 7e exercice (Q2).** `ba.dpa.reintegration_years` passe à **7**. Fiabilité **I** : l'art. 72 D bis n'a pas pu être relu (Légifrance renvoie une erreur 404).

**b3 Intérêt de retard (Q2, D-CG3.2 : art. 1727).**
- *Corrigé au codage, d'après BOI-BA-BASE-30-45-10 § 330* : la fraction réintégrée est « majorée d'un montant égal au produit de cette somme par le taux de l'intérêt de retard ». L'intérêt porte donc sur la **somme réintégrée** et s'ajoute au résultat. Lyvre le calcule en euros, sans taux d'imposition.
- Paramètre daté `ba.late_interest_monthly_bp` : 40 pb jusqu'au 31/12/2017, 20 pb ensuite.
- Période : du 1er juillet qui suit l'année de la déduction au 30 juin qui suit l'année de la réintégration (convention des outils CEGARA, à valider).
- Lignes `to_validate` du tableau de passage :
  - `dep_interest_{id}` pour les DPI et les DPA à l'échéance ;
  - `dep_shortfall_interest_{id}` pour l'épargne insuffisante, imputée sur les DEP les plus anciennes (le § 330 laisse le choix à l'exploitant).
- La DEP réintégrée normalement au 10e exercice n'en porte pas (BOI-BA-BASE-30-45-30 § 40 et § 50).

**b4 Date limite de l'épargne (Q3).**
- `dep.savings` retient `min(clôture + 6 mois, date de dépôt de la liasse BA)`.
- La date de dépôt est calculée par `deadlines.dates()` sur la règle de l'événement FIS-01, **avec le délai de télédéclaration** (`edi_date`).
- `savings()["deadline_basis"]` indique laquelle des deux s'applique.

**b5 Épargne au-delà de 100 % (Q3 bis).**
- Ligne de passage `dep_excess`, `to_validate: True` : « Épargne supérieure aux déductions non rapportées : réintégration à confirmer ».
- Montant proposé : les DEP antérieures non rapportées (BOI-BA-BASE-30-45-30 § 50). Le BOI-BA-BASE-30-45-10 § 330 parle seulement d'une épargne libre à retirer : le libellé cite les deux, et la ligne reste à valider.
- Le contrôle `dep_savings_above` passe d'information à anomalie.
- Le texte (art. 73) est à relire au codage. S'il ne prévoit rien, la ligne est retirée et la question remontée.

## 6.3 CG3.c MSA

**c1 Triennale (Q4).**
- `comparison()` calcule la moyenne des **revenus** des 3 années, puis `abatement(moyenne, year)` : triennale = moyenne − abattement.
- Il faut `income_cents` sur les 3 lignes d'historique. L'écran de l'historique gagne un champ « Revenu avant abattement ».
- Une année saisie depuis l'avis MSA avec la seule assiette (sans revenu) bascule sur l'ancien calcul (moyenne des assiettes), avec la note « revenu {année} inconnu : moyenne des assiettes ».
- Le formulaire de l'historique accepte un revenu facultatif.

**c2 et c3 abandonnés (décision du 07/11/2026).** Le barème NSA 2026 de la MSA (annexe du 25/02/2026, lue au codage) contredit Q4 bis et Q4 ter :
- le taux de l'AMEXA se lit sur « a, l'assiette sociale des cotisations retenue pour le calcul desdites cotisations » ;
- pour les prestations familiales, « r » est « le montant de l'assiette de cotisations » ;
- un seul barème AMEXA progressif s'applique à tout chef d'exploitation domicilié en France. Le chef à titre secondaire n'a de valeurs propres que pour la retraite de base plafonnée (14,15 %) et l'ATEXA (montants divisés par deux).

L'utilisateur a choisi de **suivre le barème** : le calcul de Lyvre est conservé. Le taux au-delà de 300 % du PASS (6,50 %) passe en V.

**c4 Micro-BA (MS3).**
- `msa.compute` : si le régime BA à la clôture est le micro-BA, renvoyer une `reason`. D'après msa.fr (page micro-BA, 16/03/2026), l'assiette est la moyenne des recettes hors taxes des 3 années précédentes (ou de N-1 sur option) après l'abattement de 87 %.
- L'application de l'abattement de 26 % au micro-BA après la réforme n'est pas établie : Lyvre ne calcule pas l'assiette et renvoie à l'avis MSA.
- La calculette 17 garde la saisie libre.

## 6.4 CG3.d Stocks

**d1 Écrêtement de la méthode forfaitaire (ST4).**
- Nouvelle fonction `stock_inventory.flat_unit(line, fy)`, partagée par l'évaluation comptable (méthode `flat`) et la valeur fiscale (`stock_tax`, méthode `flat`) :
  - valeur unitaire = cours × (1 − décote) ;
  - si la ligne de même clé (`stock_tax.key`) de l'exercice précédent était aussi au forfait, la valeur est bornée entre 80 % et 120 % de sa valeur unitaire.
- **Renonciation à l'écrêtement** : nouvelle option `flat_stock_no_capping` (`tax_profile.OPTIONS`). `options.json` lui donne la même durée que l'option forfaitaire (5 ans, tacite, BOI-BA-BASE-20-20-20-20 § 130).
- Le détail de la ligne affiche « écrêté à +20 % (valeur d'ouverture 1,04) ».
- Test, sur l'exemple des guides recalculé : porcs 1,30 → 1,90 → 1,60 €/kg, décote de 20 % → 1,04 → 1,25 → 1,28.

**d2 Blocage 72 B bis à la première inscription, sorties PEPS (Q7).**
- `stock_tax.frozen()` reconstitue des **couches** d'exercice en exercice depuis la clôture de référence :
  - couche initiale = quantité et valeur fiscale unitaire de référence ;
  - une hausse de quantité ajoute une couche à la valeur comptable unitaire de l'exercice où elle apparaît (première inscription) ;
  - une baisse consomme les couches les plus anciennes (PEPS) ;
  - valeur = somme des couches.
- Le surplus n'est plus revalorisé chaque année. Le test « Cognac » est recalculé sur 2 exercices.

**d3 Option globale, rotation lente seule (Q7 bis).**
- Colonne `StockLine.slow_rotation` (booléen, nul = selon la catégorie : `animals_long` vrai, `animals_short` faux, produits à cocher). Migration.
- Quand l'option 72 B bis est en vigueur :
  - toute ligne à rotation lente prend la méthode fiscale `frozen` (choix ligne par ligne retiré, `manual` reste possible avec un motif) ;
  - une ligne à rotation rapide ne peut pas être bloquée.
- Écran : case « rotation de plus d'un an » sur la ligne.

**d4 Avertissement de minimis (Q7 bis).**
- Paramètre `aid.de_minimis.agri_cap_cents` (règlement UE 1408/2013 modifié par le 2024/3118, montant et période à lire au codage, fiabilité I sinon).
- Contrôle de clôture `stock_freeze_de_minimis` (information) : avantage du blocage (valeur comptable − valeur fiscale) cumulé sur l'exercice et les 2 précédents, comparé au plafond. Le message rappelle que le plafond vaut **toutes aides de minimis confondues**.

**Réalisé (CG3.d, 07/11/2026)** :
- paramètres `stock.flat_capping_bp` (2 000 pb) et `aid.de_minimis.agri_cap_cents` (20 000 € jusqu'au 15/12/2024, puis 50 000 € : règlement UE 2024/3118) ;
- `option.flat_stock_no_capping.duration_years` = 5 (V, BOI-BA-BASE-20-20-20-20 § 130) ;
- `stock_inventory.flat_unit` et `line_key`, couches PEPS dans `stock_tax.frozen` (`layers`), `stock_tax.slow` et `effective_method` ;
- migration `b4c6d8e0f2a4` : les lignes déjà bloquées sont marquées à rotation lente ;
- le contrôle de minimis montre l'**écart de valeur** cumulé (la base de l'avantage), car Lyvre ne connaît pas l'impôt économisé ;
- la mention « règle à valider (Q-S5) » disparaît.

**Non-cumul avec 75-0 B** (non retenu en Q7 bis) : pas de contrôle ajouté. Question **D-CG3.3** : l'interdiction du BOFiP a-t-elle été levée par la LF 2026 ?

## 6.5 CG3.e Options

| # | Changement | Source à lire au codage |
|---|---|---|
| e1 | `ba_normal_option.duration_years` = 2 (Q9) | CGI art. 69 III |
| e2 | `ba_simplified_option.renounce` : version en vigueur (Q9 bis) | CGI art. 69 et 64 bis, BOI-BA-REG-10 |
| e3 | `rsa_option.renounce` = 2 mois avant la fin de la période. Nouvelle forme de règle `{"months_before_end": 2}` dans `tax_profile.renounce_by` | CGI art. 298 bis I ; ann. II art. 260 J |
| e4 | `rsa_fiscal_year` : `duration_years` et `renounce` | CGI art. 298 bis I-1 |
| e5 | `vat_monthly` : durée et renonciation relues | BOI-TVA-SECT-80-30-60-20 |
| e6 | **Délais d'option** : nouvelle famille de paramètres `option.<code>.elect`, règle de la date limite pour opter, affichée dans le formulaire d'option et dans le corpus de l'assistant. Formes de règle : `{"months_after_start": 3}` (IS), `{"with_return": "first"}` (avec la déclaration du premier exercice concerné). | voir ci-dessous |
| e7 | Nouvelles options dans `tax_profile.OPTIONS` (Q9 ter) : `crop_advance_method` (méthode des avances aux cultures), `fuel_flat_74c`, `recurring_expenses_74d`, `income_spread_75_0_a`, `land_on_balance_sheet`, `landlord_vat` | CGI art. 72 A, 74 c, 74 d, 75-0 A, ann. III 38 sexdecies D, art. 260 6° |

**Réalisé (CG3.e, 07/11/2026)**, d'après les textes relus. Les règles qui n'ont pas pu être relues restent sans valeur, en fiabilité I :
- **réel normal** : 2 exercices, reconduction tacite par période de 2 (CGI art. 69 III, impots.gouv.fr ; R) ; renonciation dans le délai de dépôt de la déclaration ;
- **réel simplifié** : 1 an reconduit tacitement, renonciation dans le délai de déclaration de la période précédente (CGI art. 64 bis V, lu sur Légifrance ; V). Le « 1er février » du guide de 2019 est périmé ;
- **délai pour opter au réel (simplifié ou normal)** : dans le délai de déclaration de l'année précédente (art. 69 IV, V), paramètres `option.*.elect` ;
- **RSA** : renonciation par lettre recommandée 2 mois au moins avant l'expiration (BOI-TVA-SECT-80-20 ; R), nouvelle forme de règle `{"months_before_end": 2}` dans `renounce_by` ;
- **`rsa_fiscal_year`** : 5 ans, fiabilité I ;
- **`vat_monthly`** : inchangé, non relu ;
- **6 options ajoutées** au profil fiscal (avances aux cultures, 74 c, 74 d, 75-0 A, terres au bilan, TVA du bailleur) :
  - `crop_advance_method` porte en note les durées de chaque méthode (BOI-BA-BASE-20-20-20-30, version 2019 : M 10 ans tacites, F 3 ans renouvelable une fois, T 3 ans, R irrévocable) ;
  - les 5 autres sont « à vérifier » ;
- **délai d'option IS** : non relu, pas de paramètre ;
- **formulaire d'option** : il affiche la durée, le délai et la renonciation de l'option choisie (`tax_profile.option_rules`).

`income_spread_75_0_a` ne remplace pas la proposition annuelle d'étalement : il trace seulement l'option et son délai. Le lien avec `ba_regimes.spread_*` reste inchangé.

## 6.6 Tests
- **a** : propositions avec 64116 ; DEP 2023, 2024, 2025 et 2026 en montants fixes ; cas `calculette-dep` (62 000 € en 2026).
- **b** :
  - base société avant JA : GAEC dont l'abattement JA réduit le bénéfice → plafond sur la base avant JA ;
  - DPA 2018 → réintégration en 2025 ;
  - date limite de l'épargne pour une clôture au 31/12 (date EDI de mai) et au 30/06 (6 mois) ;
  - épargne au-delà de 100 % → ligne à valider.
- **c** :
  - triennale sur revenus de 0, 0 et 90 000 € → 22 200 € (abattement plafonné de la moyenne) au lieu de 21 636 € ;
  - taux AMEXA lu sur N-1 ;
  - chef à titre secondaire ;
  - micro-BA → `reason`.
- **d** : écrêtement (porcs) ; couches PEPS sur 3 exercices ; option globale ; refus du blocage d'une ligne rapide ; contrôle de minimis.
- **e** : `renounce_by` avec `months_before_end` ; schéma des paramètres `elect` ; nouvelles options dans le profil.
- Jeu d'évaluation : un cas « délai d'option IS » et un cas « intérêt de retard d'une DPA ».

## 6.7 Ordre, migrations, suite

| Étape | Migration | Dépend de |
|---|---|---|
| CG3.a | non | — |
| CG3.b | non | D-CG3.2 pour la valeur de l'intérêt |
| CG3.c | non | barème NSA 2026 sur msa.fr |
| CG3.d | oui (`stock_lines.slow_rotation`) | — |
| CG3.e | non | lectures du CGI |

Un commit par étape. Ensuite, **CG5** (fonctions nouvelles retenues) :
- part de main-d'œuvre salariée sur la fiche (Q5 bis) ;
- stock d'ouverture guidé au passage au réel (Q6) ;
- plantations : choix charges ou 7222 (Q8), annuité entière (Q8 bis), durées proposées (Q8 ter) ;
- sous-activité ;
- cas particuliers MSA ;
- alerte de provision quand le cours du jour est inférieur au prix de revient.

## 6.8 Questions ouvertes de CG3
- **D-CG3.1** ✅ *Lu au BOFiP le 07/11/2026 (voir b1).* Base DEP : faut-il retirer les revenus de l'art. 75, des DPB et de l'énergie, comme l'outil 10 ? À lire au BOFiP, BOI-BA-BASE-30-45-20 § 50 et suivants.
- **D-CG3.2** ✅ *Tranché le 07/11/2026 : art. 1727.* Intérêt des réintégrations : **intérêt de retard de l'art. 1727** (0,40 % puis 0,20 % par mois, sur le supplément d'impôt) **ou intérêt légal** ? La réponse à la question 2 dit « taux légal ». Or le CGI renvoie à l'art. 1727 pour la DEP (art. 73 II) et l'ancienne DPI. À confirmer avant CG3.b.
- **D-CG3.3** ✅ *Tranché au lot CG4.b (07/11/2026)* : le BOI-BA-BASE-20-20-20-40 § 100 interdit le cumul. Lyvre l'avertit dans le profil fiscal et signale une anomalie à la clôture (`freeze_averaging_conflict`), à la demande de l'utilisateur. Une levée par la LF 2026 n'a pas été trouvée.

---

# Lot CG4 : fiches de méthode de l'assistant

Besoins : `fiabilisation_cegara.md` F4 (AS1, AS3). Le corpus de l'assistant (`assistant/corpus.py`, environ 16 000 tokens en cache) ne contient que des échéances, des paramètres et des écrans. CG4 y ajoute des **fiches de méthode** courtes, rédigées par nous. Chacune donne ses sources primaires.

## 7.1 Choix

| # | Choix | Raison |
|---|---|---|
| M1 | Format de fiche de la base documentaire (`doc/base_documentaire/02_corpus_fiches.md` § 2.3) : Markdown à en-tête YAML ; sections « Résumé », « Exemple », « Référence », « Dans le logiciel » ; au plus environ 600 mots | Format déjà décidé pour la base documentaire. Les fiches agricoles en sont la première mise en œuvre. |
| M2 | Emplacement `data/kb/fiches/agri/`, identifiants **`MA-01`…** (méthode agricole), référentiel `agri` | Arborescence cible du § 2.2. Le préfixe `AG` est déjà pris par les lots. |
| M3 | **Tout le texte des fiches en contexte, en cache**, dans une section « Fiches de méthode » du corpus, triée par identifiant. Pas de recherche. | 10 fiches de 500 mots font environ 7 000 tokens, soit un corpus d'environ 23 000 tokens, sous le seuil du § 4 de `design_assistant_agricole.md`. |
| M4 | **Pas de montant, seuil ni taux écrit en dur** : la fiche cite la clé du paramètre daté (`[ba.dep.cap_cents]`) | Une seule source pour les valeurs, déjà datée et sourcée. Les fiches ne périment pas à chaque loi de finances. |
| M5 | Statut `publie` seulement si chaque règle de la fiche a été relue sur sa source primaire (CGI, BOFiP, CRPM, PCG, msa.fr). Sinon `a_confirmer`, et l'assistant le dit. | Même règle que les paramètres (V, R, I). |
| M6 | Aucun texte des guides CEGARA repris. Ils peuvent figurer dans `verifie_par` comme piste, jamais dans `sources`. | Règle AGD16. |

## 7.2 En-tête d'une fiche

```yaml
id: MA-04
titre: DEP — plafond, épargne, réintégrations
referentiels: [agri]
comptes: ["5121"]                         # facultatif
articles: ["CGI art. 73", "BOI-BA-BASE-30-45-20 § 10, 240, 290, 350-380", "BOI-BA-BASE-30-45-10 § 50, 330"]
liens: [https://bofip.impots.gouv.fr/…]   # au moins un lien vers une source primaire
parametres: [ba.dep.band1_cents, ba.dep.fixed3_cents, ba.late_interest_monthly_bp]   # clés citées, vérifiées par le test
echeances: [FIS-01]                       # fiches d'échéances liées, facultatif
mots_cles: [épargne de précaution, plafond, intérêt de retard]
risque: attention                         # aucun | attention | expert
statut: publie                            # brouillon | a_confirmer | publie
verifie_le: 2026-11-07
verifie_par: lecture du BOFiP (lot CG3.b)
ecrans: ["/tax-result/"]
```

## 7.3 Composants

- **`app/services/kb.py`** (nouveau) :
  - `method_fiches()` lit `data/kb/fiches/agri/*.md` (en-tête et corps), trie par identifiant, garde en cache (`lru_cache`) ;
  - `validate()` contrôle :
    - les clés obligatoires ;
    - l'identifiant unique, conforme à `MA-\d\d`, égal au nom du fichier ;
    - la présence des 4 sections ;
    - une longueur de 700 mots au plus ;
    - au moins un lien `https://` de domaine primaire (legifrance, bofip, impots.gouv, msa.fr, service-public, agriculture.gouv, eur-lex, anc) ;
    - l'existence de chaque clé de `parametres` dans `reg_params` et de chaque `echeances` dans `deadlines` ;
    - l'absence de « CEGARA » ou « CEGAO » dans le corps ;
  - les fiches au statut `brouillon` ne sont pas chargées.
- **`assistant/corpus.py`** : nouvelle section « ## Fiches de méthode » après les paramètres. Chaque fiche commence par une ligne `[MA-04] titre — statut, vérifiée le …, sources : …`, suivie du corps. Le texte reste déterministe.
- **`assistant/prompt.py`** : la consigne de citation ajoute les fiches de méthode `[MA-00]`. Nouvelle consigne : « une fiche au statut à confirmer se cite avec cette réserve ; pour un chiffre, cite le paramètre daté, pas la fiche ».
- **Pas d'écran nouveau** dans CG4. L'affichage des fiches dans l'aide de Lyvre (champ `ecrans`) viendra avec la base documentaire.

## 7.4 Les fiches

| Id | Fiche | Contenu (synthèse propre) | Sources primaires à relire | Liens Lyvre |
|---|---|---|---|---|
| MA-01 | Évaluation des stocks selon le régime | Prix de revient, ou cours du jour s'il est plus bas (provision) ; méthode forfaitaire et décote, écrêtement et renonciation ; IS ; changement de régime | CGI art. 72, 74 b ; ann. III 38 sexdecies H, JC ; BOI-BA-BASE-20-20-20-20 | `/inventory/`, option `flat_stock_method` |
| MA-02 | Avances aux cultures | Art. 72 A ; méthodes T, F, M1, M2, R et leurs durées ; rubriques au réel selon la méthode ; barème mensuel ou en cumul ; fermage et frais financiers exclus | CGI art. 72 A ; BOI-BA-BASE-20-20-20-30 | fiche d'avance, barèmes, option `crop_advance_method` |
| MA-03 | Blocage des stocks à rotation lente (72 B bis) | Option globale, rotation de plus d'un an, couches à la première inscription, sorties PEPS, non-cumul avec 75-0 A, de minimis | CGI art. 72 B bis ; BOFiP 72 B bis ; règlement UE 1408/2013 modifié | `/inventory/`, contrôle de minimis |
| MA-04 | DEP | Plafond (base individuelle ou de société, montants fixes, associés, prorata, plafond global) ; épargne de 50 à 100 % et date limite ; utilisation, aléa, 10e exercice ; intérêt de l'art. 1727 | CGI art. 73 ; BOI-BA-BASE-30-45-10, -20, -30 | `/tax-result/`, calculette 13 |
| MA-05 | Anciennes DPI et DPA | Échéances (5e et 7e exercice), intérêt de retard, reprise de l'historique, échéance passée | CGI art. 72 D et 72 D bis (versions 2018) | registre DEP |
| MA-06 | Plantations pérennes | 2346 puis 246 ; coûts de plantation et annexes ; façons culturales en charges ou en 7222 (choix du dossier) ; durées indicatives ; arrachage ; sol d'autrui ; autorisations 2082 ; subvention | PCG titre 6 ; BOI-BA-BASE-20-10-20 ; CGI art. 39 | `/assets/` (biens vivants) |
| MA-07 | Assiette des cotisations MSA | Triennale ou annuelle ; moyenne des revenus puis abattement de 26 % borné ; taux progressifs sur l'assiette retenue ; micro-BA ; rente du sol ; réintégrations (JA, 72 B bis, DJA) | CRPM L.731-14 et L.731-15 ; CSS L.136-4 ; barème MSA 2026 | `/msa/`, calculette 17, SOC-03 |
| MA-08 | Entraide et coût du matériel | Barème d'entraide (avec intérêt du capital) et coût des façons culturales ; recalcul du coût fixe à l'utilisation réelle ; barème départemental à saisir avec son millésime ; compte 472 | BCMA (méthode publiée) ; CGI art. 75 (entraide) ; PCG agricole 472 | calculettes 14 et 22 |
| MA-09 | Contrôle des structures | Autorisation, déclaration, rescrit ; critères nationaux ; seuils régionaux (SDREA) à lire dans l'arrêté ; délais et sanctions | CRPM L.331-1 à L.331-12, R.331-1 à R.331-15 | baux, associés |
| MA-10 | Aide à la restructuration du vignoble | Aide mixte : part d'investissement (131, reprise au rythme de l'amortissement) et indemnité de perte de recette (74) | règlement OCM, décisions FranceAgriMer ; PCG 131 et 74 | `/aids/` (nature mixte) |

Le statut visé pour MA-01 à MA-05 et MA-07 est `publie`, grâce aux sources déjà lues en CG2 et CG3. Pour MA-06, MA-08, MA-09 et MA-10, c'est `a_confirmer` jusqu'à la lecture des sources.

## 7.5 Tests et évaluation
- **pytest** :
  - `kb.validate()` sans problème sur les fiches livrées ;
  - fiche fautive : clé manquante, mot « CEGARA », paramètre inconnu, plus de 700 mots, aucun lien primaire ;
  - le corpus contient `[MA-01]`, son texte est identique sur deux appels ;
  - une fiche `brouillon` n'est pas chargée.
- **Jeu d'évaluation** (lancement manuel, payant), une question par fiche. Exemples :
  - « Comment évaluer mes avances aux cultures en M2 ? » → `[MA-02]`, mention de la main-d'œuvre au réel ;
  - « Mon épargne DEP dépasse mes déductions, que se passe-t-il ? » → `[MA-04]`, réserve « à valider » ;
  - **piège** : « Le guide dit que je dois renoncer au réel simplifié avant le 1er février, c'est juste ? » → cite l'article 64 bis V et le délai de déclaration, ne valide pas le 1er février.
- Coût : le corpus passe d'environ 16 000 à 23 000 tokens en cache. La première question d'une conversation coûte un peu plus, les suivantes très peu (lecture du cache).

## 7.6 Étapes

| Étape | Contenu |
|---|---|
| CG4.a | `kb.py`, validation, section du corpus, consigne de citation, tests ; fiches pilotes MA-04 et MA-02 |
| CG4.b | MA-01, MA-03, MA-05, MA-07 (sources déjà lues) |
| CG4.c | MA-06, MA-08, MA-09, MA-10 (lecture des sources, sinon `a_confirmer`) |
| CG4.d | Questions d'évaluation ; un passage réel sur la base jetable, si l'utilisateur l'accepte (API payante) |

## 7.6 bis Réalisé (CG4.a, 07/11/2026)

- `app/services/kb.py` : chargeur générique `data/kb/fiches/<référentiel>/*.md`, `validate()`, `method_fiches()` et `corpus_text()`.
- Le corpus de l'assistant a une section « Fiches de méthode ». Sa taille passe de 16 100 à 18 100 tokens environ.
- La consigne de citation couvre `[MA-00]`.
- Fiches **MA-02** (586 mots) et **MA-04** (608 mots), publiées. MA-02 s'appuie sur la lecture intégrale du BOI-BA-BASE-20-20-20-30 (version du 03/07/2019), qui confirme les règles des lots CG2.a et CG3.a :
  - M1 et M2 : approvisionnements et travaux par des tiers au réel (§ 70 à 80) ;
  - M2 : main-d'œuvre salariée au réel, associés d'exploitation compris (§ 110) ;
  - M1 : le travail de l'exploitant et des aides familiaux n'est pas compté (§ 100), ce qui justifie la part salariée de CG5.
- Le BOI ne dit pas quelle méthode s'applique sans option. Pour une société à l'IS, son § 5 renvoie à l'art. 38 nonies de l'annexe III.
- 2 questions d'évaluation (`methode-avances-m2`, `methode-dep-epargne-excedentaire`).

## 7.6 ter Réalisé (CG4.b, 07/11/2026)

- **MA-01 Stocks** (557 mots, publiée) : règles générales lues au BOI-BA-BASE-20-20-20-10 (version du 04/07/2018) :
  - prix de revient, ou cours du jour s'il est inférieur, avec provision (§ 90 et § 320) ;
  - coûts standards interdits pour le prix de revient (§ 190) ;
  - cours du jour = prix de vente sur le marché (§ 310).

  Le stock d'entrée au passage du micro-BA au réel n'est **pas** sur ces pages (renvoi au BOI-BA-REG-40, non lu). La fiche le laisse à l'expert-comptable.
- **MA-03 Blocage 72 B bis** (572 mots, publiée) : BOI-BA-BASE-20-20-20-40 (version du 03/07/2019) lu en entier. Il confirme la conception de CG3.d : option globale, rotation de plus d'un an, entrée bloquée à sa valeur d'inscription (§ 60), PEPS admis (§ 70 et 80). Il apporte aussi :
  - **non-cumul avec 75-0 A et 75-0 B** (§ 100). Le contrôle du 75-0 B est ajouté : avertissement dans le profil fiscal, anomalie `freeze_averaging_conflict` à la clôture ;
  - imposition de l'écart à la renonciation (§ 120) ;
  - aide de minimis mesurée par l'économie d'impôt actualisée (§ 200 et 210).
- **MA-05 DPI et DPA** (352 mots) : **à confirmer**, les art. 72 D et 72 D bis n'ont pas été relus.
- **MA-07 Assiette MSA** (420 mots, publiée) : l'ordre « moyenne puis abattement » y est signalé « à valider ».
- Le corpus fait environ 21 300 tokens. 4 questions d'évaluation ajoutées.

## 7.6 quater Réalisé (CG4.c, 07/11/2026)

- **MA-06 Plantations** (à confirmer) :
  - règles comptables relues au PCG 2026 : art. 618-10 (bien vivant immobilisé, coût de production jusqu'à la mise en exploitation), art. 214-12 (début de l'amortissement), art. 312-1 (reprise des subventions) ; comptes 2346 et 246 du règlement ANC 2020-04 ;
  - non relus : doctrine fiscale (façons culturales, durées, sol d'autrui, arrachage, autorisations de plantation). La page BOFiP visée renvoie une erreur 404.
- **MA-08 Entraide** (publiée) : Code rural L.325-1 à L.325-3 (contrat gratuit ; ni TVA, ni CET, ni cotisations) et PCG art. 618-15 (seuls les remboursements de frais sont comptabilisés). La méthode du barème BCMA n'a pas été trouvée : la fiche ne la décrit pas.
- **MA-09 Contrôle des structures** (publiée) : Code rural L.331-1 à L.331-11 relus. Contenu des SDREA et délais d'instruction non relus, donc non cités.
- **MA-10 Aides au vignoble** (à confirmer) : PCG art. 312-1 relu. Conditions de l'aide FranceAgriMer non trouvées. La page de l'aide à l'arrachage définitif 2026 est citée.
- Bilan : 10 fiches, dont 7 publiées et 3 à confirmer (MA-05, MA-06, MA-10). Corpus d'environ 24 000 tokens. 5 questions d'évaluation ajoutées, dont la question piège du « 1er février ».

## 7.6 quinquies Réalisé (CG4.d, 07/11/2026) : passage réel du jeu d'évaluation

- Base jetable (`scripts/assistant_eval_env.py`, instance « essai-agri »), modèle claude-haiku-5-5, une exécution par cas.
- **33 questions sur 33 réussies (100 %)**, coût estimé à 0,068 $.
- Les 11 cas des lots CG1 à CG4 (conjoint collaborateur, à-valoir, SMA, intérêt de retard, option réel normal, 10 fiches de méthode, question piège du « 1er février ») citent la bonne fiche ou le bon paramètre.
- Relecture de trois réponses :
  - 72 B bis : non-cumul avec 75-0 B, avec l'anomalie de clôture rappelée ;
  - entraide : pas de TVA, remboursement de frais seul comptabilisé ;
  - piège : le « 1er février » est déclaré périmé, avec renvoi au délai de déclaration.
- **Remarque d'outillage** : `run_assistant_evals.py` ne charge pas `.env`. Il faut exporter `ANTHROPIC_API_KEY` avant de le lancer, sinon il répond « intégration indisponible ».

## 7.7 Questions
- **D-CG4.1** ✅ *Accepté le 07/11/2026 : chargeur générique, fiches agri seules.* Les fiches de méthode sont-elles réservées aux instances agricoles (référentiel `agri`), ou faut-il préparer dès maintenant les fiches A, C, D et S de la base documentaire avec le même chargeur ? Proposition : chargeur générique, et seules les fiches `agri` livrées dans CG4.
- **D-CG4.2** ✅ *Accepté le 07/11/2026.* Faut-il relire les fiches avec l'expert-comptable avant de les passer en `publie` ? Proposition : `publie` dès que la source primaire est relue, revue par l'expert-comptable à la fin de CG4, le champ `verifie_par` notant qui a relu.

---

# Lot CG5 : fonctions nouvelles retenues

Sources des décisions : réponses Q5 bis, Q6, Q8, Q8 bis et Q8 ter (`fiabilisation_cegara.md` § 6) et périmètre Q-CG3 (stocks, sous-activité, cas particuliers MSA, plantations). Mêmes règles que les lots précédents :
- chaque valeur ajoutée cite une source primaire relue, sinon fiabilité I ;
- aucune écriture n'est passée sans validation de l'utilisateur ;
- un exercice clôturé n'est jamais réécrit.

## 8.1 CG5.a Part de main-d'œuvre salariée des avances aux cultures (Q5 bis)

- **Source** : BOI-BA-BASE-20-20-20-30 § 100, déjà lu. En M1, « le travail de l'exploitant et des aides familiaux n'étant pas pris en considération ». La même logique vaut pour la méthode F, dont le barème suppose une main-d'œuvre salariée.
- **Modèle** : `CropAdvance.salaried_share_bp` (entier de 0 à 10 000, nul = 100 %). Migration.
- **Calcul** : en F et en M1, la composante `labour` du barème est multipliée par la part salariée. En M2 et au coût réel, la main-d'œuvre vient des charges réelles, donc la part ne s'applique pas. Le détail affiche « main-d'œuvre du barème × 40 % (part salariée) ».
- **Écran** : champ « Part de main-d'œuvre salariée (%) » sur la fiche, visible en F et en M1. L'hypothèse du barème reste affichée.
- **Test** : blé, clôture au 31 mars, barème fictif ; F avec une part salariée de 0 % → la composante main-d'œuvre est à 0.

- **Réalisé (07/11/2026)** :
  - `CropAdvance.salaried_share_bp` (migration `c5d7e9f1a3b5`), appliquée à la composante `labour` du barème en F et en M1. En M2, le barème n'a pas de composante main-d'œuvre, donc la part est sans effet ;
  - champ sur la fiche ;
  - fiche MA-02 mise à jour.

## 8.2 CG5.b Alerte de provision des stocks (ST8)

- **Source** : BOI-BA-BASE-20-20-20-10 § 90 et § 320, déjà lus. Quand le cours du jour est inférieur au prix de revient, une provision est constituée.
- **Calcul** : pour une ligne d'inventaire au coût réel ou au barème (pas au forfait, qui exclut la provision, § 50), avec un cours du jour saisi et inférieur à la valeur unitaire, et sans dépréciation saisie :
  - avertissement « Cours du jour inférieur au prix de revient : provision de X € à constater » ;
  - bouton qui remplit `depreciation_cents` avec l'écart, motif « cours du jour < prix de revient ». L'utilisateur valide.
- **Contrôle de clôture** `stock_depreciation_missing` (information), avec le nombre de lignes.

- **Réalisé (07/11/2026)** :
  - `stock_inventory.depreciation_suggestion()` renvoie la provision proposée (`depreciation_suggested_cents` dans les données de la ligne). Elle ne passe pas par les avertissements, pour ne pas compter la ligne « à compléter » ;
  - contrôle `stock_depreciation_missing` ;
  - bouton « Reprendre la provision » dans le formulaire de la ligne ;
  - fiche MA-01 mise à jour.

## 8.3 CG5.c Stock d'ouverture guidé au passage au réel (Q6)

- **Source à relire avant de coder** : BOI-BA-REG-40-10-10 (§ 190 et suivants), BOI-BA-REG-40-10-20, BOI-BA-REG-40-20 et BOI-BA-REG-40-30, cités en renvoi par BOI-BA-BASE-20-20-20-10 § 330. Tant qu'ils ne sont pas lus, la règle d'évaluation reste « à valider ».
- **Déclencheur** : `ba_regimes._first_real_year(fy)`, déjà utilisé pour les créances du passage du micro au réel.
- **Écran Inventaire** de cet exercice : un encadré « Stock d'entrée au passage au réel ». L'utilisateur saisit ou reprend les lignes du stock détenu à la date du changement, avec prix de revient et cours du jour. Lyvre retient la plus petite des deux valeurs, sous réserve de la lecture du BOI.
- **Écriture d'ouverture** proposée en brouillon : débit des comptes de stock (3x), crédit du compte de l'exploitant (108) pour une EI, ou des comptes courants d'associés (455) pour une société. Elle est marquée `SOURCE_OPENING`, pour que la variation de stock de l'exercice parte de ce stock d'entrée.
- **Tableau de passage** : aucune ligne, puisque le stock d'entrée vient réduire la variation de stock.
- **Contrepartie** : compte de l'exploitant (108) pour une EI ; **comptes courants d'associés (455), au prorata des parts**, pour une société (D-CG5.1).

## 8.4 CG5.d Plantations (Q8, Q8 bis, Q8 ter)

1. **Choix du dossier pour les façons culturales des jeunes plantations** (Q8) :
   - drapeau du profil agricole `plantation_costs_capitalized` (oui = coûts de croissance en 7222 ; non = charges) ;
   - le contrôle `living_wip_missing` ne s'affiche que si le drapeau vaut oui ;
   - si le drapeau vaut non, la plantation en cours ne reçoit que ses coûts de plantation, et Lyvre le rappelle sur la fiche.
2. **Annuité entière** (Q8 bis) : `Asset.full_first_year` (booléen), proposé par défaut pour les plantations (comptes 246 et 2346). L'amortissement part du **premier jour de l'exercice** de mise en service, au lieu de la date de mise en service. `plan_bounds()` prend le début de l'exercice qui contient `in_service_date`. Le tableau d'amortissement l'affiche. Migration.
3. **Repères de durée** (Q8 ter) :
   - *révisé (D-CG5.2)* : pas de durée par défaut. Le tableau de l'annexe BOI-ANNX-000100 (première récolte, début de décroissance, par espèce et par conduite) est affiché comme repère pour les vergers.
4. La fiche [MA-06] est mise à jour en conséquence.

- **Réalisé (07/11/2026)**. Source lue avant de coder : BOI-BA-BASE-20-30-10-20 (version du 01/03/2017, § 90 à 190). Il apporte :
  - le coût de la plantation = plants, appropriation des sols, mise en place (§ 100) ;
  - les **façons culturales** (taille, binage, désherbage, traitements, remplacement des plants morts) sont des **avances aux cultures** (§ 170 et 180) ;
  - **vigne : 25 ans** dès la première déclaration de récolte (§ 140 et 150) ;
  - vergers : dès l'exercice de la première petite récolte, sur la durée de production de l'annexe ;
  - investissements annexes sur leur propre durée (§ 160).

  Mise en œuvre :
  - drapeau du profil `plantation_costs_capitalized`, non coché par défaut (conforme au BOFiP). Le contrôle `living_wip_missing` ignore les plantations quand il n'est pas coché ;
  - `Asset.full_first_year` (migration `d6e8f0a2b4c6`), coché par défaut à la création d'une plantation ; `plan_bounds` part du 1er jour de l'exercice de mise en service ;
  - paramètre `assets.plantation.vine.duration_years` = 25 (V) ;
  - référentiel `data/agri_orchard_references.json` (annexe BOI-ANNX-000100, V), servi dans les métadonnées des immobilisations et affiché dans le formulaire ;
  - fiche MA-06 réécrite et **publiée**.

## 8.5 CG5.e Sous-activité (ST9)

- **Source à relire avant de coder** : PCG 2026 art. 213-32 (affectation des frais fixes selon la capacité normale, disponible dans le dépôt) et, pour le fiscal, ann. III art. 38 nonies et BOI-BIC-PDSTK-20-20-10-10 § 240.
- **Calculette 26 « Sous-activité »** :
  - entrées : rendements des 5 dernières années, rendement de l'année, charges fixes de production ;
  - calcul : rendement normal = moyenne des 3 rendements médians ; taux d'activité = rendement de l'année ÷ rendement normal ; charges fixes imputables = charges fixes × taux ;
  - méthode et limites affichées, comme les autres calculettes.
- **Inventaire** : sur une ligne au coût réel ou au barème, champ facultatif « charges fixes de sous-activité écartées », avec le lien vers la calculette. La part écartée reste en charge et ne s'ajoute pas au stock. Aucune écriture propre.

- **Réalisé (07/11/2026)**. Sources relues :
  - PCG 2026 art. 213-32 (capacité normale = production moyenne sur plusieurs exercices ; frais non affectés en charge) et art. 618-13, 2° (applicable aux produits agricoles) ;
  - BOI-BIC-PDSTK-20-20-10-10 § 240 (charges de sous-activité exclues du coût fiscal), applicable au BA par BOI-BA-BASE-20-20-20-10 § 90.

  Aucun texte ne fixe la formule de la capacité normale, ni ne qualifie une baisse de rendement climatique de sous-activité.

  Mise en œuvre :
  - **calculette 26** (`calculators/sous_activite.py`) : moyenne simple par défaut, variante « 3 valeurs médianes sur 5 ans » signalée à valider ;
  - le **champ d'inventaire n'est pas ajouté** : au coût réel, c'est l'utilisateur qui saisit la valeur unitaire, et un second champ risquerait de déduire la sous-activité deux fois. La calculette donne le montant à retirer ;
  - fiche MA-01 complétée.

## 8.6 CG5.f Cas particuliers MSA (MS4)

- **Sources** :
  - barème NSA 2026 de la MSA, déjà lu : assiettes forfaitaires d'installation (600 SMIC AMEXA, retraite de base, PFA et CSG ; 800 SMIC formation ; 1 820 SMIC RCO ; 11,5 % du PASS invalidité) ; collaborateur (retraite de base sur 600 SMIC à 14,87 % ou 13,05 %, RCO sur 1 200 SMIC, ATEXA à un pourcentage de la cotisation du chef) ; cotisant de solidarité (ATEXA forfaitaire) ;
  - à relire : exonération jeune agriculteur (CRPM L.731-13) et ACRE (CSS L.131-6-4).
- **Paramètres** : `msa.install.*_smic`, `msa.collaborator.*` et `msa.solidarity.*` depuis le barème 2026 (fiabilité V), puis `msa.ja.*` et `msa.acre.*` après lecture.
- **Estimation** (`msa_estimate`) :
  - statut `collaborator` couvert : il n'est plus refusé ;
  - « nouvel installé » : assiettes forfaitaires quand il n'y a pas encore de revenu ;
  - exonération JA dégressive et ACRE appliquées à l'estimation, ligne par ligne, avec leur base légale ;
  - cotisant de solidarité : estimation simple (taux sur les revenus N-1, plus l'ATEXA forfaitaire), si le taux est trouvé.
- La **rente du sol** reste un rappel ([SOC-03]) : son calcul demande les revenus cadastraux, hors de Lyvre.

## 8.7 Étapes et migrations

| Étape | Migration | Sources à relire avant | Taille |
|---|---|---|---|
| CG5.a part salariée | oui (`crop_advances.salaried_share_bp`) | — | petite |
| CG5.b alerte de provision | non | — | petite |
| CG5.d plantations | oui (`assets.full_first_year`) | durées (D-CG5.2) | moyenne |
| CG5.e sous-activité | non | PCG 213-32, ann. III 38 nonies | moyenne |
| CG5.c stock d'ouverture au réel | non | BOI-BA-REG-40 | moyenne |
| CG5.f cas particuliers MSA | non | CRPM L.731-13, CSS L.131-6-4 | grande |

Ordre proposé : a, b, d, e, c, f (du plus sûr au plus dépendant des sources). Un commit par étape, avec la fiche de méthode concernée mise à jour (MA-01, MA-02, MA-06, MA-07).

## 8.8 Questions
- **D-CG5.1** ✅ *Réponse du 07/11/2026 : compte courant d'associé (455), réparti selon les parts.* Passage au réel en société : contrepartie de l'écriture de stock d'entrée ?
- **D-CG5.2** ✅ *Sources données par l'utilisateur le 07/11/2026, lues le même jour :*
  - **BOI-ANNX-000100** (annexe « Durée d'amortissement des différentes plantations de vergers », version du 29/09/2014) : 10 espèces de vergers (pommiers, pêchers, poiriers, pruniers, cerisiers, abricotiers, amandiers, noyers, noisetiers, actinidia), 3 modes de conduite. Pour chacun : densité, âge de la première récolte, âge du début de décroissance des rendements. **Aucune durée en années ni aucun taux** ; ni vigne ni asperge.
  - **BOI-BA-BASE-20-30-10-10** (version du 05/08/2026) : les plantations sont des immobilisations amortissables, même sur des terres restées dans le patrimoine privé (§ 100). Leur prix de revient comprend les plants et les frais de plantation « jusqu'à ce que la plantation soit arrivée à un stade de production normale » (§ 120). Les investissements annexes vont à un compte spécial (§ 120). Au passage du micro au réel, les plantations sont reprises à leur valeur nette comptable (§ 130). Renvoi au BOI-BA-BASE-20-30-10-20 § 100 à 160 pour la définition des frais de plantation (à lire en CG5.d).
  - **Conception révisée** : pas de durée par défaut inventée. Le tableau de l'annexe devient un référentiel daté (`data/regulatory/plantation_orchards.json`, fiabilité V), affiché comme repère à la création d'une plantation de verger. L'utilisateur choisit la durée. Pour la vigne et l'asperge : saisie libre, sans repère.
- **D-CG5.3** ✅ *Réponse du 07/11/2026 : commencer par le collaborateur.* Cas particuliers MSA : tout faire, ou commencer par les nouveaux installés et le collaborateur ?
