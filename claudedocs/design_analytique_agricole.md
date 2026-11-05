# Conception : lot AG8, analytique par activité et marges

> **Statut** : **validée** (06/11/2026, AGD25). Réponses de l'expert-comptable aux questions du § 11 :
> - **Q-A1** : ventilation dans une table à part, au moyen d'une **clé de répartition** (par exemple la surface : une charge ou un produit se répartit selon la surface de chaque activité).
> - **Q-A2** : la campagne est l'année de récolte, **mais certaines activités sont décalées**. Ce sont les dates théoriques de début et de fin de la production dans Lexicon qui la déterminent.
> - **Q-A3** : **atelier puis activité**. Par exemple, l'atelier « vaches laitières » regroupe les activités lait, génisses de 1 an, génisses de 2 ans et veaux.
> - **Q-A4** : classification du **RICA** (dossier `claudedocs/compta_agricole/RICA/`, hors git).
> - **Q-A5** : **toutes les aides par activité**, couplées comme découplées.
> - **Q-A6** : pourcentage, surface et marge brute pour commencer ; des clés alimentées par Ekylibre viendront ensuite.
> - **Q-A7** : saisie à revoir avec les éléments ci-dessus. Le champ des éditeurs devient « **Affectation analytique** » : une activité ou une clé.
> - **Q-A8** : références plus tard.
> - **Q-A9** : l'analytique est **aussi en comptabilité simplifiée et au micro-BA**.
>
> **AG8.a réalisé (06/11/2026, non commité)**. Contenu :
> - extrait Lexicon `data/analytic/lexicon_productions.json` : 473 productions, version 2026.10.07.1, CC-BY-SA 4.0 cité. Il est généré par `scripts/build_lexicon_productions.py` depuis le paquet public et reprend le nom français, la famille, l'usage, les dates de cycle (MM-JJ et décalage d'année), l'unité et la durée de vie ;
> - tables `workshops`, `activities`, `campaigns` et `activity_productions` (migration `e9f1a3b5c7d9`) ;
> - `app/services/analytic.py` :
>   - référentiel ;
>   - **campagne d'une date** : première campagne dont le cycle se termine à cette date ou après ; une date entre deux cycles va donc sur la campagne suivante ;
>   - reprise des dates, de l'unité et du cycle depuis Lexicon (modifiables ensuite) ;
>   - mesures par campagne, totaux par unité, reprise des mesures de la campagne précédente ;
> - API :
>   - `/workshops` (GET `?campaign=`, POST, PATCH, DELETE) ;
>   - `/activities` (POST, PATCH, DELETE) ;
>   - `PUT /activities/<id>/campaigns/<année>` ;
>   - `POST /campaigns/<année>/copy-measures` ;
>   - `/lexicon/productions` ;
> - écran Compta › **Activités** (`/activities/`), dans tous les modes de tenue des instances agricoles.
>
> Écarts : deux familles de Lexicon absentes du formulaire public sont ajoutées, `energy_production` et `environmental_service`. Les unités `unity`, `square_meter` et `cubic_meter` sont gardées.
>
> Tests : `tests/api/test_analytic.py` (4), `activities.test.tsx` (1).
>
> **AG8.b réalisé (06/11/2026, non commité)**. Contenu :
> - tables `analytic_keys`, `analytic_key_members`, `analytic_allocations` et `analytic_rules` (migration `f0a2b4c6d8e0`) ;
> - `app/services/analytic_allocation.py` :
>   - **lignes concernées** : classes 6 et 7, hors écritures d'ouverture, de clôture, d'affectation et de stock, et hors 603, 713, 67, 77 et 69 ;
>   - **résolution** : ventilation saisie, sinon règle de compte (préfixe le plus long) ;
>   - **clés** :
>     - surface ou effectif sur la campagne de chaque activité membre (déduite des dates), avec une alerte si la mesure manque ;
>     - pourcentages ramenés à 100 ;
>     - marge brute différée à AG8.e ;
>     - contrôle des unités ;
>   - **ventilation saisie** sur une ou plusieurs cibles, total ≤ 100 %, campagne facultative ; retrait de la ventilation ;
>   - **couverture** des charges et des produits ;
>   - **suggestions de règles** : compte dont le libellé contient le nom d'une seule activité ;
> - API :
>   - `/analytic-keys` et `/analytic-rules` ;
>   - `/fiscal-years/<id>/analytic/unallocated` (`?account=`, `?all=1`) ;
>   - `/fiscal-years/<id>/analytic/allocations` (POST) et `/allocations/clear` ;
> - écrans :
>   - Compta › **Ventilation analytique** (`/analytic/`) : comptes à ventiler, lignes, affectation en masse, règle pour tout le compte, suggestions ;
>   - bloc « Clés de répartition et règles de compte » sur la page Activités.
>
> Écarts :
> - la ventilation d'une ligne disparaît si l'écriture est modifiée, ses lignes étant recréées ; à reprendre si besoin ;
> - les clés en pourcentages se créent par l'API seulement, l'écran ne les propose pas encore ;
> - la règle par catégorie simple passe par le compte de la catégorie : une règle sur ce compte.
>
> Tests : `tests/api/test_analytic.py` (+1), `analytic.test.tsx` (1), `activities.test.tsx` (complété).
>
> **AG8.c réalisé (06/11/2026, non commité)**. Contenu :
> - migration `a1b3c5d7e9f1` :
>   - `analytic_target` (« activity:ID » ou « key:ID ») sur `purchase_lines`, `rules` et `aids` ;
>   - `activity_id` sur `stock_lines`, `stock_lots`, `crop_advances` et `assets` ;
> - **grand livre** : une ligne d'écriture peut porter une clé `analytic`. `post_entry` et `update_entry` créent alors sa ventilation à 100 % (comptes 6 et 7 concernés seulement), avec l'origine fournie ;
>   - les ventilations suivent la ligne en cascade (relation ORM) ;
>   - les orphelines laissées par des suppressions en masse sont purgées avant chaque état ;
> - **sources** :
>   - écriture saisie : champ `analytic` de la ligne, validé, réaffiché en modification ;
>   - lignes d'achat (origine `purchase`) ;
>   - règles bancaires, en partie double comme en comptabilité simplifiée (origine `rule`) ;
>   - opérations simples (origine `simple`), remplacée à la modification ;
>   - versements d'aide (origine `aid`, affectation du dossier) ;
> - **fiches** : `activity_id` sur les lignes d'inventaire, les lots, les avances aux cultures et les immobilisations (API), pour l'état des marges ;
> - API `/analytic-targets` ;
> - composant `AnalyticSelect` / `ActivitySelect`, présent dans :
>   - l'éditeur d'écriture (colonne « Analytique » sur les lignes 6 et 7) ;
>   - les lignes d'achat ;
>   - le formulaire des règles ;
>   - les opérations simples ;
>   - la fiche d'aide ;
>   - la fiche d'immobilisation ;
>   - la ligne d'inventaire.
>
> Écarts :
> - les produits à recevoir d'aide (`add_inventory`) ne reprennent pas l'affectation du dossier : à ventiler ou à couvrir par une règle de compte ;
> - l'activité des lots et des avances aux cultures se saisit par l'API seulement pour l'instant ;
> - la ventilation saisie d'une écriture modifiée est conservée seulement si l'éditeur la renvoie (affectation unique à 100 %) ; une ventilation multiple est perdue à la modification.
>
> Tests : `tests/api/test_analytic.py` (+1), `analyticSelect.test.tsx` (1).
>
> **AG8.d réalisé (06/11/2026, non commité)**. Contenu :
> - classes de marge `data/analytic/margin_classes.yml`, d'après la méthodologie du RICA et son questionnaire 2024, transposées au plan agricole ; préfixe le plus long :
>   - ventes, autres produits, aides ;
>   - variation des stocks de produits ;
>   - achats d'animaux (60117, déduits de la production) ;
>   - charges spécifiques végétaux (60111, 60112, 60113, 60615) et animaux (60114, 60115, 60116, 6134) ;
>   - 6051 rangé selon la famille de l'atelier ;
>   - structure : le reste de 60 à 66 et 68 ;
> - `app/services/analytic_margins.py` :
>   - **lignes ventilées** (AG8.b et AG8.c) réparties par les clés sur la campagne de chaque activité ;
>   - **variation des stocks** par activité : lignes d'inventaire de l'exercice moins celles de l'exercice précédent ; les approvisionnements passent en charges dans la classe de leur compte d'achat ;
>   - **amortissements** : dotations des fiches rattachées à l'activité, à la place des lignes de l'écriture de dotation ;
>   - production, charges opérationnelles, **marge brute** et marge par unité, structure directe, résultat ; totaux par atelier (mesure si l'unité est unique) ; non affecté ;
>   - lignes affectées à une clé « marge brute » mises de côté pour AG8.e ;
> - API `/fiscal-years/<id>/activity-margins?campaign=` ; exports `activity-margins.xlsx` et `.pdf` (paysage) ;
> - écran Compta › **Marges par activité** (`/activities/margins`).
>
> Écarts :
> - la vue « par campagne » filtre les productions de l'exercice choisi, sans additionner deux exercices : à reprendre si l'on veut la campagne complète d'un exercice décalé ;
> - le rapprochement avec le résultat comptable et le figement à la clôture sont reportés à AG8.e ;
> - les lignes de l'écriture de dotation restent proposées sur l'écran « À ventiler » alors que la marge les ignore.
>
> Tests : `tests/api/test_analytic.py` (+1), `margins.test.tsx` (1).
>
> **AG8.e réalisé (06/11/2026, non commité) — AG8 terminé (a à e)**. Contenu :
> - colonne `activities.distribution_key_id` (clé de répartition d'une activité auxiliaire) et table `analytic_snapshots` (migration `b2c4d6e8f0a2`) ;
> - `analytic_margins` :
>   - **clé « marge brute »** : les lignes mises de côté sont réparties au prorata des marges brutes positives des membres, avant les auxiliaires ;
>   - **auxiliaires** :
>     - le résultat de chaque auxiliaire est réparti sur les activités principales par sa clé (surface, effectif, pourcentages ou marge brute), sur la campagne de clôture des bénéficiaires ;
>     - colonnes « Auxiliaires » et « Résultat » (après répartition) ;
>     - une auxiliaire sans clé garde son résultat, avec une alerte ;
>   - **rapprochement** : résultat comptable = activités + non affecté + hors analytique + écart de méthode, l'écart venant des stocks pris sur l'inventaire et des amortissements pris sur les fiches ;
>   - **figement** : l'état est figé au premier calcul après la clôture définitive (vue complète) et recalculé si l'exercice est rouvert ;
>   - **contrôles de clôture** (information), seulement si des activités existent :
>     - couverture des charges ou des produits sous 80 % ;
>     - activité principale sans mesure ;
>     - clé incomplète ;
>     - auxiliaire sans clé ;
> - écrans :
>   - clé de répartition des auxiliaires sur la page Activités ;
>   - colonnes, rapprochement et repère « figé » sur la page des marges ;
>   - exports XLSX et PDF complétés.
>
> Écart : le seuil de couverture (80 %) est arbitraire et à valider.
>
> Tests : `tests/api/test_analytic.py` (+1), `margins.test.tsx` et `activities.test.tsx` (complétés).
>
> Cadrage : `compta_agri.md` § AG8, AGD7 (activité, et non projets) et AGD8 (compatibilité avec Ekylibre, connecteur AG11).
>
> Sources :
> - modèle Ekylibre : `audit_ekylibre_lexicon.md` § 1.6 ;
> - Lexicon, jeu `productions` (version 2026.10.07.1, CC-BY-SA 4.0, Ekylibre SAS), table `master_productions` : `reference_name`, `activity_family`, `specie`, `usage`, `started_on`, `stopped_on` (dates théoriques sur l'année 2000, par exemple blé tendre d'hiver du 2000-10-01 au 2001-08-31, vache laitière du 2000-09-01 au 2001-08-31), `life_duration`, `support_unit` (hectare ou head) ;
> - RICA : méthodologie Agreste « Chiffres et données » n° 14 de septembre 2025 (définitions) et questionnaire 2024 (feuillets 9 et 10, comptes) ;
> - jeu d'essai C (fictif) : ateliers Isacompta à plusieurs niveaux avec leur surface.

---

## 1. Ce qui existe et ce qui manque

**Ce qui existe déjà :**
- **Projets** (`journal_lines.project_id`) : axe unique des associations et des sociétés, avec ventilation par découpage des lignes. Il est conservé tel quel et reste distinct (AGD7).
- **Plan agricole** :
  - ventes par production : 7011 végétaux, 7012 produits animaux, 7014 animaux ;
  - approvisionnements : 60111 à 60117 ;
  - travaux incorporés à la production : 6051 ;
  - eau d'irrigation : 60615 ;
  - locations d'animaux : 6134 ;
  - variations de stock : 603x et 713x ;
  - aides : 742 à 745.
- **Comptabilité simplifiée** : chaque opération génère une écriture en partie double (`source='SIMPLE'`). L'analytique par ligne d'écriture y fonctionne donc aussi.
- **Inventaire (AG4)** : lignes de stock, avances aux cultures, lots d'animaux.
- **Aides (AG3)** : dossiers.
- **Biens vivants (AG5)** : immobilisations par lot.

**Ce qui manque :**
- le référentiel ateliers, activités, campagnes et mesures ;
- les clés de répartition ;
- la ventilation des lignes ;
- la marge par activité et par atelier.

## 2. Choix structurants

1. **Axe séparé des projets** (AGD7).
2. **Trois niveaux** :
   - l'**atelier** (« Vaches laitières », « Grandes cultures ») regroupe des activités ;
   - l'**activité** (« Lait », « Génisses 1 an », « Blé tendre d'hiver ») est rattachée à une production Lexicon et a ses dates théoriques ;
   - la **production** est l'activité sur une campagne. Elle porte la mesure (surface ou effectif).
3. **La campagne suit les dates théoriques de l'activité** (Q-A2).
   - La campagne est l'année de fin du cycle (année de récolte).
   - Une ligne datée du 15/10/2025 sur le blé d'hiver (cycle du 01/10 au 31/08) va sur la campagne 2026.
   - Une ligne d'élevage laitier (cycle du 01/09 au 31/08) datée du 15/09/2026 va sur la campagne 2027.
4. **Ventilation par clé de répartition, dans une table à part** (Q-A1). Une ligne est affectée :
   - soit à **une activité** ;
   - soit à **une clé**, qui la répartit sur plusieurs activités selon :
     - la **surface** ou l'**effectif** des productions de la campagne ;
     - des **pourcentages** saisis, ramenés à 100 ;
     - la **marge brute** ;
     - plus tard, des clés alimentées par Ekylibre (Q-A6).
   
   La clé est **calculée au moment de l'état**, avec les mesures connues : un changement de surface se répercute sans reventiler. Les écritures, la balance et le FEC ne sont jamais touchés, et l'on peut ventiler après la validation ou la clôture.
5. **Affectation par défaut, puis saisie**. Ordre de priorité :
   1. ventilation saisie sur la ligne ;
   2. ligne d'achat, règle bancaire ou opération simple qui l'a créée ;
   3. règle de compte ou de catégorie simple.
   
   Le reste est « non affecté ».
6. **Marge calculée, sans écriture**, figée à la clôture. Les classes de charges suivent le **RICA** (Q-A4).
7. **Tous les modes de tenue** (Q-A9) : partie double, comptabilité simplifiée et micro-BA, avec un contenu de marge adapté (§ 7).

## 3. Ateliers, activités, campagnes, productions (AG8.1)

**Atelier** :
- nom ;
- **famille** d'activités de Lexicon : `plant_farming` (culture de plantes), `animal_farming` (élevage), `vine_farming` (viticulture), `wine_making` (vinification), `processing` (transformation), `service_delivering` (prestations), `tool_maintaining` (entretien d'outils), `administering` (administration) ;
- **code analytique Isacompta** : texte court, repris des enregistrements ANA (AG10.7) ;
- ordre d'affichage.

Une exploitation de grandes cultures peut n'avoir qu'un atelier « Grandes cultures ». Les niveaux intermédiaires d'Isacompta (céréales) sont des ateliers, ou bien ils se fondent dans l'atelier.

**Activité** :
- atelier ;
- nom ;
- **production Lexicon** facultative (`reference_name`), qui donne :
  - les dates théoriques (`started_on` / `stopped_on`, ramenées au jour et au mois) ;
  - l'unité (`hectare` ou `head`) ;
  - le cycle : annuel, ou pérenne si `life_duration` est renseignée ;
- **nature** : principale, auxiliaire (matériel, bâtiments, charges communes, réparties ensuite) ou autonome (hors répartition) ;
- **dates de cycle** : reprises de Lexicon et modifiables (jour et mois de début, jour et mois de fin) ; par défaut l'année civile ;
- code Isacompta ;
- archivée.

**Campagne** : une année, créée à la demande.

**Production** (activité × campagne) :
- **mesure** : surface en hectares ou effectif en têtes ;
- source de la mesure : saisie, puis Telepac ou RPG plus tard ;
- note.

**Liste des productions Lexicon** : `data/analytic/lexicon_productions.json`, extrait de `master_productions`. Il reprend le nom français, la famille, l'usage, les dates, l'unité et la durée de vie, avec la version, la source et la licence CC-BY-SA citées. Un script le régénère depuis le paquet public.

## 4. Clés de répartition (AG8.1 et AG8.2)

**Clé** :
- nom (« Surface des céréales », « Toutes cultures », « Atelier lait ») ;
- **base** :
  - `surface` ou `headcount` : mesure de la production de chaque activité membre, sur la campagne de la ligne ;
  - `percentage` : parts saisies, ramenées à 100 ;
  - `gross_margin` : marge brute positive de chaque membre ;
- **membres** : une liste d'activités, avec leur part si la base est `percentage`.

**Répartition des activités auxiliaires (AG8.2)** :
- chaque activité auxiliaire désigne une clé ;
- son résultat (charges moins produits) est réparti sur les activités principales par cette clé, dans l'état des marges.

**Contrôles** :
- membre sans mesure pour une clé à la surface ou à l'effectif ;
- clé sans membre ;
- unités mêlées (hectares et têtes) dans une même clé à la mesure.

## 5. Affectation des lignes (AG8.1, suite)

**Lignes concernées** :
- en partie double : les lignes des classes 6 et 7 de l'exercice, sauf les écritures de clôture. Les variations de stock (603, 713) sont traitées au § 7 ;
- en comptabilité simplifiée et au micro-BA : les lignes de classe 6 et 7 des opérations.

**Table `analytic_allocations`** :
- ligne d'écriture ;
- **cible** : une activité, ou une clé ;
- **campagne** facultative : déduite des dates de l'activité si elle est vide ;
- part en points de base : 10 000 pour une seule cible, ou plusieurs lignes dont le total fait 10 000 au plus ;
- origine : `manual`, `purchase`, `rule`, `simple`, `account`.

**Valeurs par défaut** :
- **règles de compte** : préfixe de compte vers une activité ou une clé. Lyvre les propose à partir des libellés des sous-comptes (7011x « Ventes de blé » donne l'activité « Blé ») ;
- **catégories simples** : catégorie vers une activité ou une clé ;
- **lignes d'achat, règles bancaires et opérations simples** : champ « Affectation analytique » (activité ou clé), à côté du projet ;
- **aides (Q-A5)** : affectation du dossier d'aide (activité ou clé), reprise sur la ligne de 74x du versement et sur le produit à recevoir ;
- **lignes d'inventaire, avances aux cultures, lots d'animaux, biens vivants et immobilisations** : activité, utilisée par l'état des marges (§ 7).

**Écran « À ventiler »** :
- lignes non affectées de l'exercice, groupées par compte ;
- affectation en masse à une activité ou une clé ;
- création d'une règle de compte depuis la sélection ;
- **taux de couverture** : part des produits et des charges affectés.

**Éditeur d'écriture** : champ « Affectation analytique » sur chaque ligne de classe 6 ou 7, pour les instances agricoles.

## 6. Classes de charges et de produits (RICA, Q-A4)

Fichier `data/analytic/margin_classes.yml`, par préfixe du plan agricole. Les définitions sont celles de la méthodologie du RICA ; les comptes sont ceux du questionnaire, transposés au plan agricole.

| Classe | Définition RICA | Comptes du plan agricole |
|---|---|---|
| **Charges spécifiques végétaux** (opérationnelles) | engrais et amendements, semences et plants, produits phytosanitaires, travaux pour cultures, eau d'irrigation | 60111, 60112, 60113, 6051 (activité végétale), 60615, et la part de 6031 qui correspond à ces stocks |
| **Charges spécifiques animaux** (opérationnelles) | aliments du bétail, produits vétérinaires, honoraires vétérinaires, travaux pour élevage, locations d'animaux, et produits de reproduction | 60114, 60115, 60116, 6051 (activité animale), 6134, sous-compte vétérinaire du 6226 s'il existe |
| **Achats d'animaux** | déduits de la production (« production de l'exercice nette des achats d'animaux ») | 60117 |
| **Charges de structure** | autres charges courantes : carburants, emballages, eau hors irrigation, énergie, entretien, fermages, locations de matériel, assurances, honoraires, impôts, personnel, cotisations de l'exploitant, amortissements, charges financières | reste des classes 60 à 66 et 68 |
| **Produits** | ventes, production stockée et immobilisée, travaux et autres produits, **aides** (742 à 745), indemnités | 70 à 75 et 79 |
| **Hors analytique** | exceptionnel, impôt sur les bénéfices, participation | 67, 77, 69 |

Le compte 6051 est commun aux cultures et à l'élevage dans le plan agricole. Il est rangé selon la famille de l'atelier de l'activité affectée.

## 7. Marge par activité et par atelier (AG8.3)

Pour chaque production (activité × campagne), puis en total par atelier :

| Bloc | Contenu |
|---|---|
| Production | ventes et autres produits affectés ; **variation des stocks** des lignes d'inventaire de l'activité (stock final − stock initial : récoltes, animaux, avances aux cultures) ; production immobilisée (72) ; **aides** affectées ; moins les **achats d'animaux** |
| Charges opérationnelles | charges spécifiques végétaux ou animaux affectées, et variation des stocks d'approvisionnements affectés |
| **Marge brute** | production − charges opérationnelles ; par hectare ou par tête, avec la mesure de la production |
| Charges de structure directes | charges de structure affectées, et amortissements des immobilisations et biens vivants rattachés à l'activité |
| Part des auxiliaires | répartition du § 4 |
| **Résultat de l'activité** | marge brute − structure directe − part des auxiliaires |

**Selon le mode de tenue** :
- **partie double** : tableau complet ;
- **comptabilité simplifiée** : recettes et dépenses affectées, sans variation de stock ni amortissement (absents de ce mode) ;
- **micro-BA** : recettes affectées, et dépenses affectées si elles sont saisies, à titre de suivi de gestion. L'impôt reste sur l'abattement forfaitaire.

**Rapprochement** : total des activités + non affecté + hors analytique = résultat de l'exercice (ou solde recettes − dépenses en comptabilité simplifiée).

**Campagne ou exercice** :
- l'état se lit par exercice (lignes de l'exercice) ou par campagne (toutes les lignes de la campagne, même sur deux exercices) ;
- il est figé à la clôture de l'exercice ;
- une vue par campagne non terminée est signalée comme provisoire.

**Exports** : XLSX et PDF.

## 8. Données, API, écrans

**Tables** (migration tenant) :
- `workshops` ;
- `activities` ;
- `campaigns` ;
- `activity_productions` ;
- `analytic_keys` et `analytic_key_members` ;
- `analytic_allocations` ;
- `analytic_account_rules`, qui couvre aussi les catégories simples (`simple_category_id`) ;
- colonnes d'affectation (`activity_id` ou `analytic_key_id`) sur `purchase_lines`, `rules`, `aids` ;
- colonne `activity_id` sur `stock_lines`, `crop_advances`, `stock_lots` et `assets` ;
- état figé : `analytic_snapshots`, par exercice.

**Services** :
- `analytic.py` : référentiel, campagnes, résolution de l'affectation, clés ;
- `analytic_margins.py` : marges, répartition des auxiliaires, rapprochement ;
- contrôles de clôture : couverture, clés incomplètes, production sans mesure.

**API** :
- `/api/v1/workshops`, `/activities`, `/campaigns`, `/activity-productions`, `/analytic-keys`, `/analytic-rules` ;
- `/fiscal-years/<id>/analytic/unallocated` ;
- `/analytic/allocations` ;
- `/fiscal-years/<id>/activity-margins?campaign=` (+ `.xlsx`, `.pdf`).

**Écrans** (instances agricoles, tous modes) :
- Compta › **Activités** (`/activities/`) : ateliers et activités, campagnes et mesures, clés, règles de compte ;
- Compta › **Ventilation analytique** (`/analytic/`) ;
- Rapports › **Marges par activité** (`/activities/margins`).

## 9. Compatibilité et suites

- **Ekylibre (AG11)** :
  - correspondances : atelier ≈ regroupement d'activités ; activité ≈ `activity` ; production ≈ `activity_production` ; clé des auxiliaires ≈ `activity_distribution` ;
  - le connecteur apportera des clés calculées (heures de matériel, interventions).
- **Isacompta (AG10.7)** : les ANA hiérarchiques donnent les ateliers et les activités, avec leur surface et leur code.
- **Calculettes (AG12)** : marge brute d'un atelier (21), prix d'équilibre (12), coût de revient d'un matériel (22).
- **Références RICA / Lexicon** : plus tard (Q-A8). Les microdonnées du RICA 2024 sont dans le dossier local, hors git.

## 10. Hors périmètre

- analytique en partie double (classe 9) ;
- coûts complets par intervention (AG11) ;
- budget prévisionnel par activité ;
- références (Q-A8).

## 11. Questions (réponses du 06/11/2026 en tête du document)

- **Q-A1** Ventilation dans une table à part, en pourcentages, ou découpage des lignes ?
- **Q-A2** Campagne de récolte, et règle par défaut pour un exercice décalé ?
- **Q-A3** Groupes d'ateliers sur plusieurs niveaux ?
- **Q-A4** Classification des charges opérationnelles ?
- **Q-A5** Aides découplées ?
- **Q-A6** Clés des auxiliaires ?
- **Q-A7** Champ dans les éditeurs, plus l'écran « À ventiler » ?
- **Q-A8** Références ?
- **Q-A9** Périmètre : partie double seulement ?

## 12. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG8.a** | Ateliers, activités (production Lexicon, dates de cycle), campagnes, productions et mesures ; extrait Lexicon en données ; écran Activités | — |
| **AG8.b** | Clés de répartition (surface, effectif, pourcentage) ; ventilation des lignes ; règles de compte et de catégorie ; campagne déduite des dates ; écran « À ventiler » et taux de couverture | AG8.a |
| **AG8.c** | Champ « Affectation analytique » dans l'éditeur d'écriture, les lignes d'achat, les règles bancaires, les opérations simples et les aides ; activité sur les lignes d'inventaire, les avances, les lots et les immobilisations | AG8.b |
| **AG8.d** | Marge brute : classes du RICA, variation des stocks par activité, achats d'animaux, aides, par unité, par atelier ; modes simplifié et micro-BA ; exports | AG8.b |
| **AG8.e** | Auxiliaires et résultat de l'activité : clé à la marge brute, répartition, rapprochement, figé à la clôture, contrôles | AG8.d |

Ordre proposé : a → b → (c ∥ d) → e.
