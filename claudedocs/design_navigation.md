# Conception : navigation, éditions comptables, documents et icônes

Besoins : `claudedocs/besoins_navigation.md` (07/11/2026, réponses Q1 à Q10). Statut : **conception**, à valider avant l'implémentation.

## 1. Existant relevé

| Élément | Où | Constat |
|---|---|---|
| Menus | `app/menu_config.py` (`MENUS`, `build_nav`) | 2 niveaux (menu → `items` + `divider`) ; filtres `charts`, `bookkeeping`, `feature`, `admin_only` ; dropdown vide masqué |
| Sérialisation | `app/api/session.py` `_resolve_nav` | `{key, label, url}` ou `{key, label, items:[…]}` ; pas d'icône |
| Rendu | `frontend/src/app/AppShell/AppLayout.tsx` | `AppShell` Mantine, barre de 240 px, `NavLink` repliables (imbricables), `activeUrl()` choisit l'entrée active |
| Routes | `app/spa_routes.json` (153 routes, partagé Flask et SPA), `frontend/src/app/routes.ts` (`PAGES`) | Une page par endpoint ; `/lettering/`, `/rent-indices/`, `/reports/*` ont chacun leur page |
| En-tête | `components/PageHeader.tsx` | prop `icon` déjà prévue, rarement utilisée |
| Préférences | `usePreferences()` → `PATCH /api/v1/me/preferences` | JSON libre (16 ko), déjà utilisé pour le thème |
| Icônes | `lucide-react` 1.61, 54 fichiers | Pas de plugin SVGR dans Vite |
| SIG | `agri_reports.sig()` + `GET /reports/sig` (`_agri_only`) | Bâtis sur la présentation agricole du compte de résultat (`build_compte_resultat(..., "agri")`) |
| Fichiers | colonnes `*_path` de 12 modèles ; routes de téléchargement par objet (achats, ventes, baux, décomptes, RFA, parts, notes de frais, comptage) | Pas de route pour certains (relevés bancaires, FEC servi par `views/fec`) |

## 2. Structure cible des menus

### 2.1 Format de `menu_config` (rétrocompatible)

```python
{"key": "compta", "label": "Compta", "icon": "calculator", "charts": _ALL, "active": [...], "items": [
    {"key": "entries", "label": "Écritures", "icon": "notebook-pen", "endpoint": "entries.index",
     "also": ["lettering.index"], ...},                        # endpoints qui activent cette entrée
    {"key": "editions", "label": "Éditions comptables", "icon": "file-bar-chart", "endpoint": "reports.index",
     "also": ["reports.balance", "reports.grand_livre", "reports.bilan", "reports.compte_resultat", "reports.sig"]},
    {"key": "fixed_and_stock", "label": "Immobilisations et stocks", "icon": "warehouse", "items": [   # 3e niveau
        {"key": "assets", "label": "Immobilisations", "icon": "building-2", "endpoint": "assets.index", ...},
        {"key": "stock", "label": "Inventaire de clôture", "icon": "boxes", "pictogram": "silo", ...}]},
    ...
]}
```

- **`items` dans un item** = sous-menu (3e niveau au plus). Mêmes filtres. `_clean_items` devient récursif.
- **Sous-menu à une seule entrée visible** : remplacé par cette entrée (hors `agri`, « Immobilisations et stocks » devient « Immobilisations »). Un sous-menu vide est retiré.
- **`icon`** : nom d'icône Lucide (kebab-case). **`pictogram`** : nom d'icône agric, utilisé seulement en pastille (cartes, en-tête de page).
- **`also`** : endpoints rattachés à une entrée sans y figurer (onglets, pages de détail). Ils servent au surlignage et à l'icône d'en-tête.
- `build_nav` et `_resolve_nav` deviennent récursifs. L'API renvoie `icon`, `pictogram` et `also_urls` (règles résolues).

### 2.2 Arbre (référentiel `agri`, partie double ; filtres actuels conservés)

| Niveau 1 | Niveau 2 | Niveau 3 | Icône (pictogramme) |
|---|---|---|---|
| Tableau de bord | | | `layout-dashboard` |
| **Compta** | Écritures (onglets Écritures, Lettrage) | | `calculator` / `notebook-pen` |
| | Éditions comptables (page d'accueil) | | `file-bar-chart` |
| | **Immobilisations et stocks** | Immobilisations ; Inventaire de clôture (agri) | `warehouse` / `building-2`, `boxes` (`silo`) |
| | **Fiscal et social** | TVA ; Remboursement forfaitaire ; E-reporting B2C ; Résultat fiscal ; Cotisations MSA ; Aides et subventions | `landmark` / `receipt-text`, `hand-coins`, `send`, `scale`, `heart-pulse` (`farmer`), `sprout` (`plots-telepac`) |
| | **Paramètres comptables** | Plan comptable ; Journaux ; Exercices ; Catalogue | `settings-2` / `list-tree`, `book-open`, `calendar-range`, `package` |
| **Gestion** (nouveau) | Projets ; Budgets ; Suivi budgétaire ; ─ ; Échéancier ; Activités ; Ventilation analytique ; Marges par activité | | `briefcase` / `folder-kanban`, `piggy-bank`, `gauge`, `calendar-clock`, `tractor`* (`farm`), `split`, `trending-up` |
| Banque | (inchangé) | | `landmark` |
| Achats | (inchangé) | | `shopping-cart` |
| Ventes | Factures, avoirs et devis ; À émettre ; Factures récurrentes ; **Coopératives** ▸ ; Baux et quittances (onglet Indices) | Coopératives : Autofactures reçues ; Décomptes de coopérative | `receipt` ; Coopératives `warehouse` (`barn`) |
| Associés, Tiers, Dons, Odoo, Indicateurs, Imports/Exports | (inchangés) | | icônes Lucide |
| **Documents** (nouveau) | | | `folder-open` |
| Outils, Configuration | (inchangés) | | `wrench`, `settings` |

\* Lucide n'a pas de tracteur : l'icône de menu reste Lucide (`sprout` pour « Activités »), et `tractor` vient d'agric en pastille.

- Ordre de premier niveau (Q6) : Tableau de bord, Compta, Gestion, Banque, Achats, Ventes, Associés, Tiers, Documents, Outils, Configuration. Les menus propres aux associations (Dons, Odoo, Indicateurs) et Imports/Exports gardent leur place relative.
- Les clés `active` des menus de premier niveau sont recalculées (Compta perd projets, budgets, agenda, activités, analytique, marges ; Gestion les reprend).

### 2.3 Continuité des adresses

Aucun endpoint n'est supprimé de `spa_routes.json` :
- **`/lettering/`** ouvre la page Écritures, onglet Lettrage.
- **`/rent-indices/`** ouvre la page Baux, onglet Indices.

`PAGES` associe ces endpoints au même composant que la page parente, qui choisit l'onglet d'après l'endpoint. Les adresses ne bougent pas, les favoris et les liens de l'assistant restent valides. Les `SCREENS` du corpus de l'assistant sont relus : ajout de `/reports/` (Éditions comptables) et de `/documents/`.

## 3. Pages à onglets (N1, N4)

- **`EntriesPage`** (Écritures) : `Tabs` « Écritures » / « Lettrage ». Le contenu de `LetteringPage` passe dans un composant `LetteringPanel`, sans changement de logique. L'onglet suit l'adresse (`/entries/` ou `/lettering/`) ; changer d'onglet change l'adresse (`navigate`, sans recharger). Le mode simple ne voit pas l'onglet Lettrage (partie double seulement, comme aujourd'hui).
- **`LeasesPage`** (Baux et quittances) : onglets « Baux » / « Indices de loyer » sur le même principe, avec `RentIndicesPanel` extrait de `RentIndicesPage`.

## 4. Éditions comptables (N2, Q5)

- **Nouvel endpoint** `reports.index` (`/reports/`), page `ReportsHubPage` : sélecteur d'exercice en tête (repris des éditions), puis une **carte par édition** (pastille d'icône, titre, une phrase, bouton « Ouvrir », export XLSX ou PDF quand il existe). L'exercice choisi passe dans l'adresse (`?fiscal_year=`) de l'édition ouverte.
- **Soldes intermédiaires pour tous les référentiels (Q5)** :
  - `agri` garde `agri_reports.sig()` (présentation agricole) ;
  - les autres référentiels reçoivent un calcul **PCG générique**, `reports.sig_pcg(fy, prev)`, à partir des soldes des comptes de classe 6 et 7 : marge commerciale (707 − 607 ± 6037), production de l'exercice (70 hors 707, 71, 72), consommations en provenance des tiers (60 hors 607 et 6037, 61, 62), valeur ajoutée, EBE (+ 74 − 63 − 64), résultat d'exploitation, résultat courant, résultat exceptionnel, résultat net. Les libellés et la ventilation exacte seront relus sur le PCG 2026 (dans le dépôt) au codage ;
  - pour une association, la ligne des dons et cotisations (754, 756) s'ajoute à la production (règlement ANC 2018-06), à confirmer ;
  - `GET /reports/sig` perd `_agri_only`. Il choisit le calcul selon `Instance.chart`, et l'export XLSX suit.

## 5. Icônes et rail (I1 à I7)

### 5.1 Icônes Lucide
- Fichier `frontend/src/app/navIcons.ts` : table **explicite** nom → composant (`import { Calculator, … } from "lucide-react"`), pour n'embarquer que les icônes utilisées. Un nom inconnu ne plante pas : pas d'icône, et un avertissement en développement. Un test vérifie que chaque `icon` de `menu_config` est dans la table.

### 5.2 Pictogrammes agric
- Script `scripts/import_agric_pictograms.py` : il lit les SVG choisis dans `~/projects/agric/glyphs/` (liste fermée d'une trentaine), en extrait le `viewBox` et les `path`, et génère `frontend/src/components/pictograms.generated.ts` (`{name: {viewBox, paths}}`). Le fichier généré est commité, avec l'en-tête de licence MIT et l'origine. Pas de dépendance npm, pas de `dangerouslySetInnerHTML`.
- Composant `<Pictogram name="cow" />` : SVG `fill="currentColor"`, `aria-hidden`. Composant `<IconTile icon? pictogram? color?>` : pastille de 40 px (rayon 10), fond teinté (`lichen` clair ou `sauge`), icône de 22 px. Il sert aux cartes et aux en-têtes. `pictogram` l'emporte sur `icon` dans une pastille.
- « À propos » (`openSourceVendors.ts`) : ajout d'agric (Ekylibre, MIT).

### 5.3 Menu latéral et rail
- `AppLayout` : chaque `NavLink` reçoit `leftSection={<NavIcon name={icon} size={18} />}`.
- **Rail** : bouton de bascule en bas de la barre. La largeur passe de 240 à 64 px. Chaque menu devient une icône avec `Tooltip` (libellé) et un `Menu` flottant pour ses sous-menus (2e et 3e niveaux). La préférence `nav_rail: true/false` est stockée via `usePreferences`. Sur mobile, le tiroir reste en pleine largeur et le rail est ignoré.
- Accessibilité : en rail, `aria-label` sur chaque bouton et `aria-current` conservé. Les menus flottants se parcourent au clavier (Mantine `Menu`).

### 5.4 En-têtes de page
- `PageHeader` : sans prop `icon`, il cherche l'entrée de menu de la page courante (`useNavEntry()` : endpoint, sinon `also`) et affiche son icône (Lucide) ou sa pastille (agric si `pictogram`). Les pages qui passent déjà une `icon` gardent la leur. Rien à modifier page par page.

### 5.5 Cartes et tuiles
- **Éditions comptables** : `IconTile` par édition.
- **Outils** : catégories de calculettes (`calculators.CATEGORIES`) avec un pictogramme par catégorie (élevage `cow`, cultures `wheat`, semis `seeding`, fertilisation `fertilization`, pulvérisation `sprayer`, récolte `harvester`, chantiers et matériel `tractor`, irrigation `water` (Lucide `droplets`), énergie (Lucide `zap`), réglementaire (Lucide `scale`)…). Table dans `navIcons.ts`.
- **Documents** : un `IconTile` par type de document.
- **Tableau de bord** : les raccourcis existants reçoivent leur `IconTile`. Pas de refonte du contenu.

## 6. Documents (N6, lecture seule)

### 6.1 Service `app/services/documents.py`
Registre de **sources**. Chacune décrit un type de document et sait lister ses fichiers sans les copier :

```python
Source(kind="purchase", label="Factures d'achat", icon="shopping-cart", charts=ALL, bookkeeping=("double",),
       query=lambda: Purchase.query.filter(Purchase.attachment_path.isnot(None)),
       row=lambda p: Doc(name=p.attachment_name, date=p.issue_date, size=p.attachment_size, mime=p.attachment_mime,
                         path=p.attachment_path, party=p.entity name, origin_url="/purchases/<id>", fy=…),
       can=lambda user: role allows purchases read)
```

Sources de la première version (colonnes existantes) :
- pièces d'achat ;
- PDF de ventes, et pièces reçues (`received-file`) ;
- reçus fiscaux (asso) ;
- relevés bancaires ;
- décomptes de coopérative (agri) ;
- quittances, aperçus, pièces signées et courriers de révision des baux ;
- pièces des mouvements de parts ;
- pièces des notes de frais ;
- feuilles de comptage d'inventaire (agri) ;
- attestations RFA (agri) ;
- FEC des exercices.

Logo et signature (paramètres) sont exclus. Les pièces Qonto et Documenso distantes sont hors périmètre (Q4).

### 6.2 API
- **`GET /api/v1/documents?kind=&fiscal_year=&q=&page=`** :
  - liste paginée (50), triée par date décroissante ;
  - `facets` : nombre de documents par type et par exercice ;
  - chaque document : `{kind, kind_label, name, date, size, mime, party, fiscal_year, origin: {label, url}, file_url, preview}`.
- **`file_url`** : la **route de téléchargement existante** de la source quand elle existe (droits déjà en place), sinon une route générique `GET /api/v1/documents/<kind>/<id>/file`. Elle vérifie le droit de la source, puis sert le fichier avec `send_file` en `inline` pour l'aperçu.
- **Droits** : une source n'est listée que si le rôle courant peut lire l'objet d'origine (mêmes contrôles que sa page). Pas de lien public, pas de jeton.
- **Performance** : une requête par source filtrée (exercice, recherche sur le nom et le tiers), fusion et tri en mémoire, puis pagination. Volumes attendus : quelques milliers de lignes. À revoir s'ils dépassent 10 000.

### 6.3 Page `DocumentsPage` (`/documents/`, endpoint `documents.index`)
- Colonne de gauche : arbre **Type › Exercice** (`facets`), avec les compteurs.
- Au centre : tableau (nom, type avec icône, date, tiers, taille, lien « Ouvrir la fiche »), recherche et filtres dans l'adresse.
- À droite, ou en tiroir sur mobile : **aperçu** PDF (`<iframe>` sur `file_url`) ou image, bouton « Télécharger ».
- État vide : `IconTile` et une phrase par type (« Aucune pièce d'achat pour cet exercice »).

## 7. Tests
- **`menu_config`** :
  - visibilité par référentiel et par mode, pour les 4 référentiels × 2 modes ;
  - un sous-menu à une entrée remplacé par l'entrée, un sous-menu vide retiré ;
  - chaque `endpoint` existe dans `spa_routes.json`, chaque `icon` dans `navIcons`, chaque `pictogram` dans le fichier généré.
- **`session`** : nav récursive avec `icon`, `pictogram` et `also_urls`.
- **Vitest** :
  - 3e niveau rendu et ouvert quand la page active en fait partie ;
  - rail (info-bulle, menu flottant, préférence) ;
  - onglets Écritures/Lettrage et Baux/Indices selon l'adresse ;
  - page d'accueil des éditions (exercice transmis) ;
  - Documents (arbre, filtre, aperçu).
- **pytest** :
  - `sig_pcg` sur un jeu de comptes (association, société) ;
  - `GET /reports/sig` pour chaque référentiel ;
  - documents (sources, droits par rôle, pagination, route générique refusée sans droit) ;
  - anciennes adresses servies par la bonne page.

## 8. Lots

| Lot | Contenu | Dépend de |
|---|---|---|
| **NV1** Structure des menus | Format à 3 niveaux, `icon`/`pictogram`/`also`, nouvel arbre (Compta rangée, Gestion, Coopératives, Immobilisations et stocks, entrée Documents masquée jusqu'à NV5), API récursive, rendu imbriqué, `SCREENS` de l'assistant | — |
| **NV2** Onglets | Écritures/Lettrage, Baux/Indices, anciennes adresses | NV1 |
| **NV3** Éditions comptables | Page d'accueil `/reports/`, SIG PCG générique pour tous les référentiels | NV1 |
| **NV4** Icônes et rail | `navIcons`, import des pictogrammes agric, `IconTile`, icônes du menu, rail, en-têtes automatiques, cartes (Outils, tableau de bord), « À propos » | NV1 |
| **NV5** Documents | Service, API, page, entrée de menu | NV1, NV4 (tuiles) |

Un commit par lot, avec les tests. Aucune migration de base (le rail est une préférence JSON).

## 9. Questions
- **D-NV1** SIG d'une association : faut-il intégrer les dons et cotisations (754, 756) à la production, ou les montrer à part ? Proposition : à part, sous la valeur ajoutée.
- **D-NV2** Rail : replié par défaut sur les écrans de moins de 1 280 px de large ? Proposition : non, déplié par défaut, choix de l'utilisateur mémorisé.
- **D-NV3** Documents : afficher aussi les FEC générés (fichiers techniques) ? Proposition : oui, dans un type « Exports réglementaires ».

## 10. Réalisé

**NV1 (07/11/2026, commité 37002cf).**
- `menu_config` :
  - 3e niveau (`items` dans un item), filtrage récursif ; un sous-menu vide est retiré, un sous-menu à une entrée est remplacé par cette entrée ;
  - `icon` sur chaque menu et sur les nouvelles entrées, `pictogram` sur stock, MSA, aides, activités et coopératives ;
  - `endpoints()` pour les tests.
- Nouvel arbre : Compta (Écritures, Lettrage, Éditions comptables ▸, Immobilisations et stocks ▸, Fiscal et social ▸, Paramètres comptables ▸), menu **Gestion** placé avant Banque, **Coopératives** ▸ sous Ventes.
- Adaptations provisoires :
  - « Éditions comptables » reste un **sous-menu** jusqu'à la page d'accueil de NV3 ;
  - Lettrage et Indices de loyer restent des entrées jusqu'aux onglets de NV2.
- API `session` : `nav` récursive avec `icon` et `pictogram`. Le champ `also` n'est pas encore utile (il le sera avec les onglets de NV2).
- Interface :
  - types récursifs et `navLinks()` (recherche rapide, entrée active) ;
  - barre latérale sur trois niveaux, groupe de la page courante ouvert d'office ;
  - icônes Lucide via `app/navIcons.tsx`, une avance sur NV4.
- Questions D-NV1 à D-NV3 : propositions retenues par défaut, faute de réponse.

**NV2 (07/11/2026, commité a4e5980).**
- Solution plus simple que la conception (§ 3) : les pages restent distinctes, avec leurs adresses et leur logique. Une barre d'onglets commune (`components/PageTabs.tsx`, `ENTRY_TABS`, `LEASE_TABS`) relie Écritures et Lettrage, ainsi que Baux et quittances et Indices de loyer. Cliquer sur un onglet change l'adresse, sans recharger.
- Menu : les entrées Lettrage et Indices de loyer disparaissent. `also` (`lettering.index`, `rent_indices.index`) est servi par l'API sous la forme `also_urls`. `activeUrl()` surligne l'entrée porteuse sur la page de l'onglet.
- Recherche rapide : les onglets restent trouvables (« Compta › Écritures » pour Lettrage).

**NV3 (07/11/2026).**
- **Soldes intermédiaires de gestion pour tous les référentiels** (Q5), dans `services/sig.py` :
  - `agri` garde la présentation agricole (`agri_reports.sig`) ;
  - les autres référentiels suivent le tableau usuel du système développé du PCG de 1982, que le PCG 2026 ne reprend plus. L'écran le précise (`meta.method`) ;
  - la marge commerciale porte sur 707 et 7097 moins 607, 6087, 6097 et 6037 ; la production sur 70 (hors marchandises), 71 et 72 ; les consommations sur 60, 61 et 62 (hors marchandises) ;
  - viennent ensuite la valeur ajoutée, les subventions (74), les impôts (63), le personnel (64) et l'EBE ;
  - pour une association, les cotisations, dons, legs et mécénat (753 à 756) apparaissent à part avant l'EBE (D-NV1) ;
  - les résultats d'exploitation, courant, exceptionnel et net viennent du compte de résultat du référentiel (`agri_reports.result_rows`, partagé).
- **Page d'accueil des éditions** `/reports/` (`ReportsHubPage`, API `GET /api/v1/reports/`) :
  - une carte par édition : pastille d'icône, titre, phrase, exports (CSV et ODS du compte de résultat, classeur des états agricoles) ;
  - l'exercice choisi en tête est transmis par `?fy_id=`.
- **Menu** : « Éditions comptables » redevient une entrée simple (`reports.index`). Son champ `also` couvre les cinq états, pour la mise en surbrillance.
- **Assistant** : `/reports/` est ajouté aux écrans du corpus, et le libellé des Écritures mentionne l'onglet Lettrage.
- **Tests** :
  - pytest : `tests/test_sig.py` (SIG du PCG pour asso, sci et société ; API), plus les adaptations de `test_agri_reports`, `test_menu_config` et `test_simple_mode` ;
  - Vitest : `ReportsHubPage.test.tsx` ;
  - résultats : 1719 pytest et 305 Vitest passent.

**NV4 (07/11/2026).**
- **Icônes Lucide** : toutes les entrées de `menu_config` ont désormais une icône (33 ajoutées). `app/navIcons.tsx` est une table explicite, qui couvre aussi les catégories de calculettes (`TOOL_CATEGORY_ICONS`).
- **Pictogrammes agric** : `scripts/import_agric_pictograms.py` génère `components/pictograms.generated.ts`, commité avec la mention MIT.
  - Liste fermée de 29 pictogrammes.
  - Polygones et rectangles convertis en tracés.
  - Formes blanches transformées en découpes (masque SVG), formes `fill:none` ignorées.
- **Composants** :
  - `Pictogram` (SVG en `currentColor`, `aria-hidden`) ;
  - `IconTile` : pastille teintée ; le pictogramme l'emporte sur l'icône.
- **En-têtes de page** : sans `icon`, `PageHeader` affiche la pastille de l'entrée de menu de la page (`useNavEntry`, qui tient compte des onglets `also_urls`) ; `icon={null}` n'en met aucune. `activeUrl` est passé dans `api/session.ts`.
- **Rail** :
  - un bouton en bas de la barre la fait passer de 240 à 72 px ;
  - chaque menu devient une icône avec une info-bulle ; ses sous-menus s'ouvrent en menu flottant, les sous-menus du 3e niveau y deviennent des sections ;
  - le choix est mémorisé dans la préférence `nav_rail` ;
  - sur mobile, le tiroir reste déplié.
- **Cartes** :
  - éditions comptables ;
  - catégories de calculettes : pictogrammes agric pour les sujets agricoles ;
  - tuiles de chiffres du tableau de bord.
- **« À propos »** : les crédits d'icônes (Lucide sous ISC, agric sous MIT) sont ajoutés sur la page elle-même (`AboutPage.tsx`) ; `openSourceVendors.ts` est le comparatif des logiciels.
- **Tests** :
  - pytest : icône sur chaque entrée, pictogrammes existants, une pastille par catégorie ;
  - Vitest : `IconTile.test.tsx`, plus le rail dans `AppLayout.test.tsx`.
