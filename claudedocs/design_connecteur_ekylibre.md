# Conception : lot AG11, connecteur Ekylibre

> **Statut** : **validée** (07/11/2026, AGD28). Réponses aux questions du § 9 :
> - **Q-K1 Ventes et achats** : **voie A**. Lyvre tient les factures ; elles vont être **supprimées d'Ekylibre**. AG11.e est sans objet.
> - **Q-K2 API Ekylibre** : elle peut évoluer, mais elle va **changer très fortement** pour devenir le **jumeau numérique de la ferme** (agronomie, traçabilité, équipement, temps de travaux). Le connecteur isole donc la lecture de l'API v2 dans un adaptateur unique (§ 2.6) et n'investit pas dans des évolutions de la v2.
> - **Q-K3 Intervention à plusieurs cibles** : coût réparti **au prorata des surfaces** des cibles.
> - **Q-K4 Inventaire** : préremplissage des quantités à 7 jours près de la date d'inventaire, validé.
> - **Q-K5 Instance d'essai** : `demo.ekylibre-dev.com` pour l'instant (essais manuels ; identifiants hors dépôt). Les tests automatiques restent sur des réponses fictives.
> - **Q-K6 Utilisateur dédié** : non. Le jeton est celui d'un utilisateur existant ; Lyvre permet de le révoquer et ne conserve pas le mot de passe.
> - **Q-K7 Priorités** : a → b → c → d.
>
> **Cadrage** :
> - `compta_agri.md` § AG11 ;
> - **AGD8** : le connecteur fait remonter dans Lyvre les ventes, les achats, les interventions (coûts par activité) et les inventaires ; le modèle d'activité d'AG8 reste compatible avec celui d'Ekylibre ;
> - `design_analytique_agricole.md` § 9 : le connecteur apportera des clés calculées (heures de matériel, interventions) ;
> - Q-A6 : des clés alimentées par Ekylibre viendront après les clés à la surface, au pourcentage et à la marge brute.
>
> **Sources lues le 07/11/2026**, code public `ekylibre/ekylibre` (branche `main`, AGPL-3.0, poussé le 25/10/2026) :
> - `config/routes.rb` (espaces `api/v1` et `api/v2`) ;
> - `app/controllers/api/v2/*` ;
> - `app/views/api/v2/**/*.jbuilder` ;
> - `app/decorators/intervention_costing_decorator.rb` ;
> - `app/services/farm_profiles/*`.
>
> Aucune API n'a été appelée. Rien n'est copié dans le dépôt.

---

## 1. Ce que l'API Ekylibre expose réellement

### 1.1 Authentification (v2)

- **Jeton** : `POST /api/v2/tokens` avec `{email, password}` renvoie `{token}`.
  - Le jeton est celui de l'utilisateur. Il est créé une fois et réutilisé, sans expiration.
  - `DELETE /api/v2/tokens/:token` le révoque.
- **Appels** : en-tête `Authorization: simple-token <email> <jeton>`, ou paramètres `access_email` et `access_token`.
- **Droits** : l'API agit **au nom de l'utilisateur** ; il n'y a pas de portée en lecture seule.
- **Instance Ekylibre** : une URL par exploitation. Les réponses portent l'en-tête `X-Ekylibre-Media-Type: ekylibre.V2`.

### 1.2 Ressources v2 utiles

| Ressource | Contenu (vues `jbuilder`) | Intérêt pour Lyvre |
|---|---|---|
| `GET /api/v2/products/plants` | `id`, `name`, `net_surface_area`, `variety`, **`activity_id`, `activity_name`**, `born_at`, `dead_at`, `production_started_on`, `production_stopped_on` | Activités et **surfaces** par campagne (AG8) |
| `GET /api/v2/products/land_parcels` | parcelle, surface, dates de production | Contrôle des surfaces |
| `GET /api/v2/products/matters` | intrants et produits : `population`, `unit_name`, `variant_id`, `france_maaid` des phytos | **Quantités** en stock à la date de l'appel (AG4) |
| `GET /api/v2/products/equipments` | matériel, `has_hour_counter` | Clés « heures de matériel » |
| `GET /api/v2/interventions` | `id`, `nature`, `procedure_name`, `started_at`, `stopped_at`, `state`, `working_duration`, **`costing`** `{total, inputs, doers, tools, receptions}`, `working_periods`, `parameters` (`role`, `product_id`, `quantity_*`, `working_zone`) | **Coûts par intervention** → par activité (via les cibles) |
| `GET /api/v2/variants` | variantes (`reference_name`, `variety`) | Correspondance des intrants |
| `GET /api/v2/cultivable_zones` | zones cultivables, forme GeoJSON | Plus tard (PAC) |
| `GET /api/v2/farm_profiles/:harvest_year` | assolement N, N-1 et N-2, données climatiques | Plus tard |
| `GET /api/v2/farm_accountancy/:harvest_year` | soldes et ratios de la **comptabilité d'Ekylibre** | Sans objet si Lyvre tient la comptabilité |

### 1.3 Limites constatées

- **Pas de ventes, d'achats, d'écritures ni de stocks valorisés** dans l'API. La v1 n'en a pas davantage : contacts, interventions, problèmes, comptages, Lexicon phyto.
- **Interventions** :
  - pas de filtre de date ni de pagination : la liste renvoie toutes les interventions non rejetées ;
  - le coût est **global** pour l'intervention. La répartition entre cibles (`imputation_ratio`, `activity_productions_interventions_cost`) n'est pas exposée.
- **Stocks** : `population` est la quantité **courante**, pas celle d'une date donnée. Aucune valeur n'est fournie.
- **FEC** : Ekylibre sait exporter un FEC (`app/concepts/fec/`), par l'écran des échanges d'exercice ; ce n'est pas une API. Lyvre sait déjà importer un FEC (lot F6, AG10.a).

## 2. Choix structurants (proposés)

1. **Lecture seule, à la demande.**
   - Lyvre lit Ekylibre et n'y écrit jamais.
   - Une synchronisation se lance depuis l'écran, en tâche de fond (`sync_jobs`). Pas d'appel planifié au départ.
2. **Une écriture comptable ne dépend jamais de l'API au moment de la saisie** (même principe qu'en N6).
   - Ce qui vient d'Ekylibre devient des **référentiels** : activités, surfaces, clés de répartition, quantités de comptage.
   - Ces référentiels sont figés dans Lyvre avec leur date de synchronisation.
3. **L'analytique reste celle d'AG8.**
   - Les coûts d'interventions ne créent pas d'écritures. Ils alimentent des **clés de répartition** (pourcentages calculés, refaits à chaque synchronisation).
   - Ces clés servent aux règles « compte → clé » : intrants, carburant, entretien du matériel, main-d'œuvre.
4. **Intégration « Ekylibre » par instance**, comme les autres (`external_connections`), réservée aux instances agricoles.
   - Clés : `url`, `email`, `token`.
   - Le mot de passe sert une fois à obtenir le jeton et **n'est pas conservé**.
5. **Pas d'utilisateur Ekylibre dédié** (Q-K6) : le jeton est celui de l'utilisateur qui connecte ; l'écran rappelle qui il est et permet de révoquer le jeton.
6. **Adaptateur unique** (Q-K2) : toute la lecture de l'API v2 (chemins, champs des vues `jbuilder`) est dans `ekylibre_client.py`, qui rend des objets Lyvre neutres (production, intervention, matière). Le reste du connecteur n'en dépend pas : quand l'API du jumeau numérique arrivera, seul l'adaptateur changera.

## 3. Activités et surfaces (AG11.b)

- **Lecture** : `products/plants`. Pour chaque plante (production), Lyvre retient :
  - `activity_id` et `activity_name` ;
  - `net_surface_area` ;
  - les dates de production, qui donnent la **campagne** par la règle d'AG8 (`campaign_year`).
- **Correspondance** :
  - nouvelle colonne `activities.ekylibre_id`, à côté d'`isacompta_code` ;
  - une activité Ekylibre est rapprochée d'une activité Lyvre par cet identifiant, sinon par son nom (`import_activities._words`), sinon elle est **proposée** à la création. C'est le même écran que les activités proposées d'AG10.a.
- **Mesures** : surface totale par activité et campagne, enregistrée comme **mesure** de la production de la campagne (`activity_productions.measure`, `measure_source = ekylibre`).
  - Une mesure saisie à la main n'est pas écrasée : l'écart est signalé.
- **Contrôle** : la somme des surfaces est comparée à celle des parcelles (`land_parcels`).

## 4. Clés de répartition depuis les interventions (AG11.c)

- **Lecture** :
  - `interventions`, filtrées dans Lyvre sur l'exercice (`started_at`), `state` différent de `rejected`, `nature = record` ;
  - pour chaque intervention : `costing` (intrants, main-d'œuvre, matériel, réceptions), `working_duration`, et les paramètres de rôle **cible** (`product_id`).
- **Imputation aux activités** :
  - cible → plante → `activity_id` ;
  - si l'intervention a plusieurs cibles, le coût se répartit **au prorata des surfaces des cibles** (Q-K3, faute d'`imputation_ratio` dans l'API).
- **Clés produites** : une par nature de coût, base `percentage`, membres = activités, parts = coûts de l'exercice ramenés à 100.
  - « Intrants (Ekylibre) » ;
  - « Main-d'œuvre (Ekylibre) » ;
  - « Matériel (Ekylibre) » ;
  - « Heures de matériel (Ekylibre) », à partir de `working_duration` des interventions avec matériel.
  
  Chaque clé porte la date de synchronisation et le nombre d'interventions.
- **Usage** : l'utilisateur rattache ses comptes aux clés par les règles d'AG8. Proposition par défaut :
  - 601x et 602x vers « Intrants » ;
  - 6061 et 6155 vers « Matériel » ;
  - 64x vers « Main-d'œuvre ».
  
  Une ligne déjà ventilée garde sa ventilation.
- **Ce que ce n'est pas** : une valorisation comptable des interventions. Les coûts d'Ekylibre sont économiques (prix d'achat des intrants, taux horaires) ; ils ne servent que de **poids**.

## 5. Inventaire (AG11.d)

- `products/matters` donne la **quantité courante** de chaque intrant ou produit, avec son unité et sa variante.
- Lyvre s'en sert pour **préremplir une feuille de comptage** (AG4.3, `stock_count_files`), seulement si la synchronisation est faite **à la date d'inventaire, à 7 jours près** (paramétrable). Sinon, Lyvre affiche l'écart de dates et ne préremplit pas.
- **Correspondance** variante Ekylibre → produit ou article de stock Lyvre : mémorisée à la première synchronisation.
- La **valeur** reste celle des méthodes d'AG4 (coût, cours, coût standard). Ekylibre ne la fournit pas.

## 6. Ventes et achats (sans objet, Q-K1 : voie A)

L'API ne les expose pas. Trois voies :

| Voie | Fonctionnement | Avantages | Limites |
|---|---|---|---|
| **A. Lyvre tient ventes et achats** | factures dans Lyvre (Qonto, Factur-X, autofactures AG10) ; Ekylibre reste l'outil de production | aucune double saisie comptable ; e-facturation déjà en place | les ventes saisies dans Ekylibre ne remontent pas |
| **B. FEC d'Ekylibre** | export FEC périodique dans Ekylibre, puis import dans Lyvre (AG10.a, tout-ou-rien, par période) | aucun développement côté Ekylibre | manuel, par période ; risque de doublon avec les factures saisies dans Lyvre |
| **C. Nouvelle API Ekylibre** | ajout côté Ekylibre de `GET /api/v2/sales`, `/purchases` (et d'un filtre de date sur les interventions) | synchronisation fine, pièces jointes | développement dans Ekylibre (hors de ce dépôt) |

**Retenu : A** (Q-K1). Les factures sont tenues dans Lyvre et vont être supprimées d'Ekylibre. Une exploitation qui a encore des factures dans Ekylibre les reprend une fois par le FEC (AG10.a), sans connecteur.

## 7. Données, services, écrans

**Tables et colonnes** :
- `activities.ekylibre_id` ;
- `activity_productions.measure_source` : nouvelle valeur `ekylibre` ;
- `analytic_keys.source` (`manual`, `ekylibre`), `synced_at` ;
- `ekylibre_variant_links` (variante Ekylibre → article de stock) ;
- curseur de synchronisation (`sync_cursors`, clé `ekylibre`).

**Services** :
- `ekylibre_client.py` : **adaptateur** de l'API v2 (jeton, appels avec un délai d'attente, erreurs lisibles, conversion en objets neutres) ;
- `ekylibre_sync.py` : activités, interventions, matières ;
- `ekylibre_keys.py` : calcul des clés.

**Écrans** :
- Intégrations › **Ekylibre** : URL, email, mot de passe à usage unique, test de connexion, révocation du jeton ;
- Analytique › **Ekylibre** : dernière synchronisation, activités proposées, écarts de surface, clés calculées avec le détail par activité ;
- Stocks › feuille de comptage : bouton « Préremplir depuis Ekylibre ».

**Tests** : réponses JSON **fictives** construites sur les vues `jbuilder` ; aucun appel réel dans les tests.

**Sécurité** :
- le jeton est stocké comme les autres secrets d'intégration ;
- l'URL est contrôlée : `https` seulement, pas d'adresse privée, même règle que les autres intégrations ;
- délai d'attente et taille de réponse bornés.

## 7 bis. Réalisé (AG11.a)

- **Adaptateur** `ekylibre_client.py` : seul module qui connaît l'API v2.
  - Objets neutres `Production`, `Intervention` (coûts par nature, cibles, outils, durée), `Matter`.
  - `obtain_token` et `revoke_token`.
  - `Client` : profil, cultures, interventions, matières.
- **Sûreté** :
  - URL `https` seulement, sans identifiants ;
  - résolution DNS contrôlée : adresses privées, locales, de lien local et réservées refusées ;
  - redirections non suivies, délai de 30 s, réponse de 30 Mo au plus.
- **Intégration** `ekylibre` (instances agricoles), clés `url`, `email` et `token` (secret) :
  - test de connexion par le profil ;
  - connexion par mot de passe **à usage unique** (`POST /api/v1/ekylibre/connect`), qui n'est ni conservé ni renvoyé ;
  - révocation du jeton chez Ekylibre ; le jeton est effacé de Lyvre dans tous les cas.
- **Instantané local** `ekylibre_snapshots` (migration `b8c0d2e4f6a8`), un par type (cultures, interventions, matières), lu en tâche de fond (`sync_jobs`, `POST /api/v1/ekylibre/sync`).
  - La lecture se fait en tout-ou-rien : en cas d'échec, l'instantané précédent reste.
  - Les sous-lots b à d travaillent sur l'instantané.
- **Écran** : Intégrations › Ekylibre › « Connexion et lecture » (se connecter, révoquer, lire Ekylibre, date et volume des données lues).
- **À vérifier sur `demo.ekylibre-dev.com`** :
  - forme JSON de `net_surface_area` (`Measure` sans `as_json` côté Ekylibre ; l'adaptateur accepte un objet `{value, unit}`, un texte avec unité ou une fraction) ;
  - unité de `working_duration`, lue en secondes ;
  - présence de `costing` sur les interventions anciennes.

## 7 ter. Réalisé (AG11.b)

- Lecture des **parcelles** ajoutée à l'adaptateur et à l'instantané (`products/land_parcels`), pour le contrôle des surfaces.
- `activities.ekylibre_id` (migration `c9d1e3f5a7b9`).
- `ekylibre_activities.py`, sur l'instantané :
  - cultures regroupées par activité Ekylibre (sans surface ou sans activité : ignorées) ;
  - rapprochement : `ekylibre_id`, sinon même nom, sinon même production Lexicon ; sinon création proposée (atelier de la famille Lexicon, grandes cultures à défaut) ;
  - campagne d'une culture : celle de sa fin de production (sinon de son début) par la règle de l'activité Lyvre ;
  - surface par campagne reportée en mesure `measure_source = ekylibre`. Une mesure saisie dans Lyvre n'est jamais remplacée : l'écart est compté et signalé. Une saisie postérieure repasse la mesure en « saisie » (`analytic.set_measure`) ;
  - un identifiant Ekylibre ne désigne qu'une activité Lyvre : rattacher ailleurs le retire de l'ancienne ;
  - contrôle : surface des cultures d'une campagne supérieure de plus de 1 % à celle des parcelles (avertissement : dérobées, cultures associées).
- Écran Activités › **Depuis Ekylibre** (`/activities/ekylibre`, bouton sur la page Activités quand l'intégration est active) : cible par activité (existante ou à créer), surfaces par campagne (à reporter, à jour, à mettre à jour, saisie différente), rattachement en lot.

## 8. Hors périmètre

- Écriture vers Ekylibre : comptes, factures, statuts.
- Parcelles, zones cultivables, assolement et données climatiques (`farm_profiles`). Ils seront utiles aux aides PAC (AG3) plus tard.
- Données de traçabilité (registre phyto, plan de fumure), qui restent dans Ekylibre (AGD9).
- Budgets prévisionnels d'Ekylibre (`activity_budgets`).

## 9. Questions

- **Q-K1 Ventes et achats** : quelle voie du § 6 retiens-tu ?
  - A : Lyvre tient les factures.
  - B : FEC d'Ekylibre.
  - A et B : B en secours.
  - C : nouvelle API.
- **Q-K2 API Ekylibre** : peut-on faire évoluer l'API côté Ekylibre ? Par exemple :
  - filtre de date et pagination des interventions ;
  - coûts par cible (`imputation_ratio`) ;
  - ventes et achats ;
  - quantités à une date.
  
  Si oui, je rédige la demande. Sinon, Lyvre s'en tient au § 1.
- **Q-K3 Répartition d'une intervention à plusieurs cibles** : au prorata des surfaces des cibles, faute de mieux ? Ou à parts égales ?
- **Q-K4 Inventaire** : le préremplissage des quantités, à 7 jours près de la date d'inventaire, te convient-il ? Ou faut-il ne rien faire tant que l'API ne donne pas les quantités à une date ?
- **Q-K5 Instance d'essai** : existe-t-il une instance Ekylibre de démonstration (données fictives) avec un utilisateur API, pour vérifier le connecteur à la main ? Les tests restent sur des réponses fictives.
- **Q-K6 Utilisateur dédié** : le jeton est celui d'un utilisateur Ekylibre, avec tous ses droits. Recommandes-tu un utilisateur « Lyvre » dédié, avec des droits réduits côté Ekylibre ?
- **Q-K7 Priorités** : ordre proposé :
  1. a : connexion ;
  2. b : activités et surfaces ;
  3. c : clés depuis les interventions ;
  4. d : inventaire ;
  5. e : ventes et achats selon Q-K1.

## 10. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG11.a** ✅ | Intégration Ekylibre : jeton (mot de passe non conservé), test de connexion, client HTTP borné, tâche de synchronisation | — |
| **AG11.b** ✅ | Activités et surfaces : `ekylibre_id`, activités proposées, mesures par campagne, contrôle avec les parcelles | AG11.a, AG8 |
| **AG11.c** | Clés de répartition depuis les interventions : intrants, main-d'œuvre, matériel, heures ; règles proposées | AG11.b |
| **AG11.d** | Inventaire : feuille de comptage préremplie depuis les matières, correspondance des variantes | AG11.a, AG4 |
| ~~AG11.e~~ | Ventes et achats : sans objet (Q-K1, voie A) | — |
