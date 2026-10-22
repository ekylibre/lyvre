# 3. Règles comptables déclaratives par référentiel

## 3.1 Ce que l'on reprend d'Ekylibre

Ekylibre (`config/accountancy/accountancy_mandatory_documents_fr_{pcg82,pcg2019,pcg2023,pcga,pcga2023}.yml`) décrit chaque état obligatoire par **un fichier YAML par référentiel**. Chaque ligne d'état y est une **expression de préfixes de comptes** :

```yaml
profit_and_loss_statement:
  products_sales: '707 C, - 7097'
  other_products: '75 C, !756'
  wages: '64 D, !645 !646 !647 !648'
balance_sheet:
  entities_state_receivables: '445 F'
  others_debts_state_debts:   '445 E'
```

La syntaxe est interprétée par `Journal.sum_entry_items` (`app/models/journal.rb`) :

| Élément | Sens |
|---|---|
| `707` | tous les comptes commençant par 707 (`LIKE '707%'`) |
| `!756` | exclut les comptes 756* |
| `@512` | compte strict (`= '512'`) |
| `- …` en tête de terme | terme soustrait |
| `,` | sépare des termes additionnés |
| `B` (défaut) | solde débit − crédit |
| `C` / `D` | solde créditeur ou débiteur **du terme**, ramené à 0 s'il est de l'autre sens |
| `E` / `F` | somme des seuls comptes **à solde créditeur** / **à solde débiteur** (ventilation actif/passif des tiers) |

Le référentiel est porté par l'exercice (`FinancialYear#accounting_system`). Le service `AccountancyComputation` charge le fichier correspondant.

**Jugement.** C'est pertinent, et notre code fait déjà la même chose sans le dire. `app/services/reports.py` contient des listes Python `(clé, libellé, préfixes, exclusions)` et des modes `debit | credit | debit_only | credit_only`. Ces modes correspondent à `B`, `−B`, `F` et `E`. Ce qu'on reprend :

- ✅ **un fichier de règles par référentiel**, chargé selon le type de structure (`Instance.chart`) ;
- ✅ la **notation compacte** des comptes (`70 !701 !707`, `@512`) : lisible par un comptable, citable par l'assistant ;
- ✅ les modes **E/F** pour ventiler les comptes de tiers entre actif et passif. C'est déjà notre `_TIERS_SPLIT_EXCLUDE` + `debit_only` / `credit_only`.

Ce qu'on ne reprend pas :

- ❌ l'**expression en une seule chaîne** qui mêle sens, signe et exclusions (`'4096 4097 4098 425 4287 4387, 441 !4419, 443 F, …'`) : impossible à valider par schéma, illisible au-delà de trois termes. On garde des **champs YAML séparés**.
- ❌ la **duplication intégrale par version** (pcga puis pcga2023 : 257 lignes copiées). On garde un référentiel par couche et des **règles datées** (`applicable`).
- ❌ les **totaux codés en dur** dans le code Ruby (`PCGA_ACTIVE_LINES`…). Chez nous, les totaux sont déclarés dans le YAML.
- ❌ la construction SQL par concaténation de chaînes. Notre moteur reste SQLAlchemy (`_prefix_filters`).
- ➕ ajouté : chaque ligne et chaque contrôle **cite une fiche** (`fiche: C-03`). Le logiciel et l'assistant peuvent ainsi expliquer chaque montant.

### Contre-exemple : paperasse

`paperasse/scripts/generate-statements.js` fait l'inverse : la correspondance entre comptes et lignes d'état y est **codée en dur** en JavaScript (`startsWith`). Les défauts relevés (doc 7 §7.5) justifient nos choix :

| Défaut paperasse | Parade chez nous |
|---|---|
| Comptes absents de toute ligne **ignorés sans message** : 42, 46, 47, 4551, 512 créditeur, 44571… | **Contrôle de couverture** dans `kb_check` et à la clôture (CT4) : tout compte qui a un solde est affecté à **une seule** ligne du bilan ou du CDR |
| Ventilation actif / passif limitée à quelques comptes (seul 411 créditeur passe au passif) | Modes `debit_only` / `credit_only` sur tous les comptes de tiers et de trésorerie (= E/F d'Ekylibre) |
| Amortissement apparié par `'28' + compte.substring(1)` (2183 → 28183, hors PCG) | Lignes d'amortissement déclarées avec leurs propres préfixes (`28 29`) |
| Tous les 7x hors 70 en « autres produits d'exploitation », financier et exceptionnel compris | Sections explicites du CDR, une par nature |
| Pas de colonne N-1 | N / N-1 déjà calculés par `reports.py` |

Ce que l'on reprend de paperasse : les **contrôles d'équilibre après génération** (balance équilibrée, actif = passif, résultat du CDR = résultat du bilan). Ils deviennent le contrôle `etats_coherents` (§3.4).

## 3.2 Familles de règles

| Fichier | Contenu | Consommateur actuel ou futur |
|---|---|---|
| `etats.yml` | Bilan, Compte de résultat, CVN (classe 8) : sections, lignes, totaux | `services/reports.py` (remplace `BILAN_LAYOUTS`, `ASSO_CDR_SECTIONS`, `SCI_CDR_SECTIONS`) |
| `controles.yml` | Invariants comptables vérifiés en continu ou à la clôture | `services/closing.py:checks` (étape 1) ; outil `list_checks` de l'assistant |
| `schemas.yml` | Modèles d'écriture paramétrés : fonds dédiés, CVN, virement interne, cotisation, loyer SCI… | Saisie (« partir d'un modèle »), inventaire de clôture, outil `propose_entry` de l'assistant |
| `comptes.yml` | Métadonnées ajoutées au plan : sens normal, libellé spécifique au référentiel, comptes interdits ou facultatifs | Plan comptable (onglet « Règle »), contrôles de sens |
| `correspondance_2072.yml` (SCI) | Compte → ligne de la déclaration 2072 | État « préparation 2072 » (futur), assistant |

## 3.3 `etats.yml` : syntaxe

```yaml
# data/kb/regles/asso_2018_06/etats.yml
compte_resultat:
  - section: produits_exploitation
    libelle: Produits d'exploitation
    sens: credit                         # debit | credit  (défaut de la section)
    lignes:
      - cle: cotisations
        libelle: Cotisations
        comptes: "756"
        fiche: C-06
      - cle: ventes_prestations
        libelle: Ventes de prestations de services
        comptes: "70 !701 !702 !703 !707"
      - cle: dons_manuels
        libelle: Dons manuels
        comptes: "754 !7542 !7543"
        fiche: C-06
  # …
bilan:
  actif:
    - section: ACTIF CIRCULANT
    - ligne: Créances clients, usagers
      comptes: "41"
      mode: debit_only                  # = Ekylibre F
      indent: 1
    - total: TOTAL ACTIF
```

Correspondance exacte avec le code actuel :

| YAML | `reports.py` aujourd'hui | Ekylibre |
|---|---|---|
| `comptes: "70 !701 !707"` | `["70"], ["701", "707"]` (préfixes, exclusions) | `'70 !701 !707'` |
| `sens: debit` | `"debit"` (`_net`) | `B` |
| `sens: credit` | `"credit"` (`_net_credit`) | `- … B` (pas de mise à 0 contrairement à `C`) |
| `mode: debit_only` | `"debit_only"` | `F` |
| `mode: credit_only` | `"credit_only"` | `E` |
| `@512` | *(n'existe pas)* | `@512` : à ajouter au parseur si besoin |

**Migration sans risque.** Un test vérifie que le YAML chargé produit **exactement** les structures Python actuelles (`ASSO_CDR_SECTIONS == load("asso_2018_06").cdr_sections`). Ensuite on remplace les constantes par le chargement. Les états ne bougent pas d'un centime.

Le test existant « chaque compte de classe 6 / 7 est compté une seule fois » (commentaire de `reports.py`) devient un contrôle de `kb_check`. Il s'applique à chaque référentiel et à chaque plan. Il est **étendu au bilan** : chaque compte des classes 1 à 5 doit tomber dans une ligne, ou dans deux lignes exclusives selon le sens du solde (`debit_only` / `credit_only`). C'est précisément le défaut constaté dans paperasse.

Exemple : [exemples/asso/etats.yml](exemples/asso/etats.yml), un extrait fidèle à `ASSO_CDR_SECTIONS`.

## 3.4 `controles.yml` : syntaxe

Un petit nombre de **types** déclaratifs couvre la majorité des invariants. Pour le reste, on nomme un contrôle Python.

| Type | Paramètres | Exemple |
|---|---|---|
| `solde_nul` | `comptes`, `quand: cloture` | comptes d'attente **471 472 473** soldés avant la clôture (`D-04`, PCG art. 1214-47 ; pas tout le préfixe `47`, qui comprend les écarts de conversion 476 / 477) ; virements internes `58` à zéro (`D-05`) |
| `sens_interdit` | `comptes`, `sens: debiteur\|crediteur` | 19x jamais débiteur (`C-03`) ; 191 jamais débiteur (`C-04`) ; 512 créditeur = anomalie |
| `egalite` | `gauche`, `droite` | Σ86 = Σ87 (`C-05`) |
| `sens_anormal` | `comptes`, `sens` | 411 créditeur, 401 débiteur : avoir ou règlement non affecté, gravité `info` (paperasse `closing.md`, contrôle croisé) |
| `variation` | `etat`, `seuil_pct`, `seuil_min` | ligne du CDR qui varie de plus de 10 % **et** de plus de 500 € par rapport à N-1, gravité `info` (paperasse : « investiguer toute variation > 10 % ») |
| `etats_coherents` | — | résultat du CDR = résultat au bilan, actif = passif, couverture complète des comptes, gravité `critique` (paperasse : contrôles du commissaire aux comptes et de `generate-statements.js`) |
| `axe_obligatoire` | `comptes`, `axe: projet` | lignes 194/195/196/689x/789x avec projet (`C-03`) |
| `aucune_ligne` | `comptes`, `sources_ecriture` (valeurs de `JournalEntry.source`) | aucune écriture `OFX_IMPORT` / `QONTO_IMPORT` en classe 8 (`C-05`) |
| `python` | `fonction` | contrôles existants : transactions non rapprochées, écritures déséquilibrées, hors exercice, factures non comptabilisées ; biens du compte 24 non amortis (`C-04`) |

```yaml
# data/kb/regles/asso_2018_06/controles.yml
- id: fonds_dedies_jamais_debiteurs
  type: sens_interdit
  comptes: "19"
  sens: debiteur
  gravite: anomalie            # critique | anomalie | info  (Check.level ; « critique » bloque la clôture provisoire)
  fiche: C-03
  message: "Le compte {compte} des fonds dédiés est débiteur ({solde} €)."
```

Chaque contrôle produit un objet `Check` (`app/services/closing.py`) avec `code = id`, `level = gravite` et un lien. On ajoute le champ `fiche`. Il alimente le bouton « Pourquoi ? » (BD7) et le bouton « Expliquer » (AS8).

**Gravités.** Elles reprennent les trois niveaux de paperasse (🔴 / 🟠 / 🟡) :
- `critique` : bloque la clôture provisoire ;
- `anomalie` : comme aujourd'hui ;
- `info` : signalement simple.

**Contrôles du FEC.** Ils restent dans `app/services/fec.py`, qui couvre déjà presque tout l'« axe 1 » du skill contrôleur fiscal de paperasse (18 champs, équilibre, numérotation continue, dates, champs requis). Deux ajouts (CT2) :
- CompteNum présent dans le plan de l'instance ;
- signalement des montants négatifs, que `verify` accepte aujourd'hui (`-?\d+,\d{2}`).

Exemple : [exemples/asso/controles.yml](exemples/asso/controles.yml).

## 3.5 `schemas.yml` : modèles d'écriture

C'est le pont entre la fiche (« D 6894 / C 194 ») et l'action. Un schéma est **paramétré**, **vérifié** (comptes existants dans le plan de l'instance, équilibre) et **jamais validé automatiquement**.

```yaml
- id: fonds_dedies_report
  libelle: Report en fonds dédiés (subvention non utilisée)
  fiche: C-03
  journal: OD
  quand: cloture                         # suggère la ligne d'inventaire de l'étape 2
  parametres:
    montant: {type: montant, calcul: dedicated_funds.reliquat}   # calcul fait par le logiciel
    projet:  {type: projet, requis: true}
    origine: {type: choix, valeurs: {subvention: "4", contribution: "5", generosite: "6"}}
  lignes:
    - {compte: "689{origine}", debit: montant, projet: projet}
    - {compte: "19{origine}",  credit: montant, projet: projet}
```

Usages :
1. **Saisie** : bouton « Partir d'un modèle » dans le formulaire d'écriture. Seuls les schémas du référentiel de l'instance sont proposés.
2. **Assistant** : l'outil `propose_entry(schema_id, parametres)` renvoie le **brouillon prérempli** à l'UI. L'utilisateur l'ouvre dans le formulaire habituel et valide lui-même.
3. **Clôture** : `inventory_options()` de `closing.py` peut lister les schémas `quand: cloture`.

Le champ `calcul` désigne une **fonction Python enregistrée** (registre fermé). Le modèle ne calcule jamais les montants (AS7).

Exemples : [exemples/asso/schemas.yml](exemples/asso/schemas.yml), [exemples/sci/schemas.yml](exemples/sci/schemas.yml).

## 3.6 `comptes.yml` : métadonnées des comptes

`data/plan_comptable_*.json` ne contient aujourd'hui que `code`, `label`, `account_type` et `is_header`. On garde ces fichiers **inchangés**. Une surcouche par référentiel ajoute :

```yaml
"756":  {sens: crediteur, fiche: C-06, libelle_ref: "Cotisations"}           # ≠ PCG (gains de change)
"657":  {sens: debiteur,  fiche: C-08, libelle_ref: "Aides financières"}      # ≠ PCG (VNC des immobilisations cédées)
"194":  {sens: crediteur, fiche: C-03, axe: projet}
"4681": {fiche: C-06}
"86":   {hors_bilan: true, fiche: C-05}
```

- **`obligatoire`** : pour les comptes du socle, repris du champ `system` (`minimal` / `facultatif`) de `pcg_2026.json` (arrhes/PCG). C'est la distinction entre caractères normaux et italiques de l'art. 1121-1 (fiche A-08).
- **`sens`** : le PDF du plan SCI (`doc/plan-comptable-SCI.pdf`) indique `C` / `D` devant chaque compte. On peut l'extraire automatiquement (`pdftotext -layout`, colonne de tête) pour remplir `sci/comptes.yml`. Pour l'asso, on le déduit de la classe et des fiches.
- **`libelle_ref`** n'écrase pas le libellé de l'instance (modifiable dans l'UI). Il sert à l'assistant et au contrôle de cohérence des libellés à l'import.

## 3.7 SCI : correspondance avec la déclaration 2072

Le plan SCI encode la ligne de la 2072 **dans le libellé**, par exemple `615216 Grosses réparations (ligne 12)`. On l'extrait en donnée explicite. Le fichier [exemples/sci/correspondance_2072.yml](exemples/sci/correspondance_2072.yml) est **généré** depuis `data/plan_comptable_sci.json` : 83 comptes répartis sur les lignes 1, 2, 3, 4, 6, 8, 9, 12, 14, 15, 16, 17, 20a, 20b et 22.

Points relevés :
- le plan SCI n'a **aucun compte de détail en classe 66**, seulement l'en-tête « CHARGES FINANCIÈRES ». Les intérêts d'emprunt ne sont donc ni comptabilisables, ni rattachés à une ligne 2072. Il faut ajouter le compte et vérifier sa ligne sur la notice de l'année. Voir doc 6 §6.5 ;
- la mention « s'il y a un seul immeuble » du PDF implique un **axe immeuble** quand la SCI en détient plusieurs. L'axe « projet » existant (`app/services/projects.py`) peut servir d'axe immeuble pour une SCI. C'est une question ouverte du doc 6.

## 3.8 Chargement et validation

```
data/kb/regles/<ref>/*.yml
      │  scripts/kb_check.py  (make check)
      │    - schéma JSON de chaque famille
      │    - comptes cités ∈ plan du référentiel
      │    - couverture : chaque compte 6/7 compté une fois dans le CDR
      │    - fiches citées existantes et publiées
      ▼
app/services/kb_rules.py  (lot 2)
      load(stack) -> Rules(etats, controles, schemas, comptes)   # cache en mémoire par pile
```

Pile de résolution des règles : identique aux fiches (doc 2 §2.5). Une couche **remplace** une règle du socle de même `id`, ou en **ajoute**. Un exemple de surcharge : le contrôle `pcg2026.cession_immo_657` est remplacé en asso, car 657 y désigne les aides financières.
