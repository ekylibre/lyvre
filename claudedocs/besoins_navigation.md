# Besoins : navigation et UX du menu (brainstorm du 07/11/2026)

Statut : **besoins complets** (réponses du 07/11/2026 au § 6). Étape suivante : conception.

## 1. Constat

- Les menus sont décrits côté serveur dans `app/menu_config.py` (`MENUS`), filtrés par référentiel (`charts`), mode de tenue (`bookkeeping`), option (`feature`) et rôle (`admin_only`). L'interface (`AppShell/AppLayout.tsx`) les affiche dans une **barre latérale** de groupes repliables (`NavLink` de Mantine), qui peuvent s'imbriquer.
- Aujourd'hui, la structure n'a que deux niveaux : menu, puis sous-menus séparés par des traits.
- Le menu **Compta** compte **28 entrées** pour une exploitation agricole (`agri`), et 16 pour les autres référentiels. On y trouve à la fois la saisie, les éditions, la gestion (projets, budgets, analytique), le fiscal et social (TVA, RFA, MSA, résultat fiscal) et le paramétrage (plan comptable, journaux, exercices).
- Aucun écran ne regroupe les **documents** de l'instance. Chaque pièce n'est visible que depuis sa fiche d'origine (facture, relevé, décompte…).

## 2. Demandes de l'utilisateur

| # | Demande |
|---|---|
| N1 | Regrouper **Écritures** et **Lettrage** |
| N2 | Regrouper **Balance, Grand livre, Bilan, Compte de résultat, Soldes intermédiaires de gestion** dans **« Éditions comptables »** |
| N3 | Nouveau menu **« Gestion »** : Projets, Budgets, Suivi budgétaire, Échéancier, Activités, Ventilation analytique, Marges par activité |
| N4 | **Indices de loyer** dans l'écran **Baux et quittances** (plus d'entrée de menu propre) |
| N5 | **Autofactures reçues** et **Décomptes de coopérative** dans un sous-menu **« Coopératives »** |
| N6 | Nouveau menu **« Documents »** : navigateur des documents de l'instance |

## 3. Proposition de menu cible (exploitation agricole, partie double)

Les entrées marquées *(agri)* n'apparaissent que pour ce référentiel, comme aujourd'hui.

```
Tableau de bord
Compta
  Écritures                        ← N1 : page à onglets Écritures | Lettrage
  Éditions comptables              ← N2 : page d'accueil, une carte par édition
      (Balance · Grand livre · Bilan · Compte de résultat · Soldes intermédiaires)
  Immobilisations et stocks ▸      ← Q7 : Immobilisations · Inventaire de clôture (agri)
  ───
  Fiscal et social ▸               ← proposition (§ 6, Q3)
      Déclarations de TVA · Remboursement forfaitaire (agri) · E-reporting B2C (agri)
      Résultat fiscal (agri) · Cotisations MSA (agri) · Aides et subventions (agri)
  ───
  Paramètres comptables ▸          ← proposition (§ 6, Q3)
      Plan comptable · Journaux · Exercices · Catalogue
Gestion                            ← N3
  Projets · Budgets · Suivi budgétaire
  ───
  Échéancier (agri) · Activités (agri) · Ventilation analytique (agri) · Marges par activité (agri)
Banque                             (inchangé)
Achats                             (inchangé)
Ventes
  Factures, avoirs et devis · À émettre · Factures récurrentes
  Coopératives ▸ (agri)            ← N5 : Autofactures reçues · Décomptes de coopérative
  Baux et quittances               ← N4 : onglet « Indices de loyer » dans l'écran
Associés · Tiers · …               (inchangés)
Documents                          ← N6
Outils · Configuration             (inchangés)
```

Résultat pour une exploitation agricole : « Compta » passe de 28 entrées à 6 au premier niveau, dont 3 sous-menus repliables. Un sous-menu qui n'a qu'une entrée visible (par exemple « Immobilisations et stocks » hors `agri`) s'affiche comme une entrée simple.

## 4. Exigences fonctionnelles

### Navigation (N1 à N5)
- **F1 Sous-menus imbriqués** : `menu_config` accepte un 3e niveau (un item qui porte ses propres `items`), avec les mêmes filtres. Un sous-menu vide est masqué, comme un menu vide aujourd'hui.
- **F2 Écritures (N1)** : une seule entrée « Écritures » ; l'écran a deux onglets, **Écritures** et **Lettrage**. L'adresse `/lettering/` ouvre l'onglet Lettrage.
- **F3 Éditions comptables (N2)** : une entrée qui ouvre une **page d'accueil des éditions** : une carte par édition (Balance, Grand livre, Bilan, Compte de résultat, Soldes intermédiaires de gestion), avec une courte description, un lien, et les exports quand ils existent. Exercice choisi en tête et transmis à l'édition ouverte. Chaque édition garde sa page et son adresse. Les **Soldes intermédiaires de gestion** s'ouvrent à **tous les référentiels** (§ 6, Q5), avec la présentation propre à chaque plan (association, SCI, société, agricole) à vérifier en conception.
- **F4 Menu Gestion (N3)** : nouveau menu de premier niveau, entre « Compta » et « Banque ». Les entrées propres à `agri` y gardent leur filtre. Pour une association ou une SCI, Gestion ne contient que Projets, Budgets et Suivi budgétaire.
- **F5 Indices de loyer (N4)** : onglet « Indices de loyer » dans l'écran « Baux et quittances ». L'entrée de menu disparaît. L'ancienne adresse `/rent-indices/` redirige vers l'onglet.
- **F6 Coopératives (N5)** : sous-menu de Ventes, réservé à `agri`.
- **F7 Continuité** :
  - les adresses actuelles restent valides : aucun lien, favori ou lien de l'assistant cassé ;
  - l'onglet actif (`active`) et la mise en surbrillance suivent la nouvelle structure ;
  - un sous-menu s'ouvre de lui-même quand la page courante en fait partie.
- **F8 Assistant** : la carte des écrans du corpus (`assistant/corpus.py`, `SCREENS`) reste juste. Libellés mis à jour si besoin.

### Documents (N6)
- **F9 Inventaire des documents** : liste unique des fichiers stockés pour l'instance, à partir des colonnes existantes (pièces d'achat, PDF de vente, reçus, relevés bancaires, décomptes de coopérative, pièces de mouvements de parts et de notes de frais, feuilles de comptage, justificatifs RFA, FEC, pièces de baux…). Pour chaque document : type, nom, date, taille, exercice, objet d'origine avec son lien.
- **F10 Navigation** : regroupement par **type** et par **exercice** (ou par mois), recherche par nom et par tiers, filtres. Aperçu PDF et image dans l'écran, téléchargement.
- **F11 Droits** : on ne voit que ce que son rôle permet déjà de voir sur la fiche d'origine (pas de nouvelle porte d'accès). Pas de lien public.
- **F12 Périmètre de la première version** : **navigateur en lecture seule** des fichiers déjà stockés dans Lyvre. Hors périmètre : dépôt de documents libres, pièces Qonto et Documenso distantes (versions suivantes).

## 5. Exigences non fonctionnelles
- Accessibilité : navigation au clavier dans les sous-menus, `aria-current` sur l'entrée active (existant), cibles de 44 px.
- Mobile : la barre latérale repliée garde les sous-menus utilisables.
- Tests : `menu_config` (visibilité par référentiel et par mode, sous-menus vides masqués), `AppLayout` (ouverture automatique du sous-menu actif), redirections des anciennes adresses.
- Documents : pas de copie des fichiers. La liste s'appuie sur les tables existantes, et les volumes restent raisonnables (pagination).

## 6. Réponses de l'utilisateur (07/11/2026)

| # | Question | Réponse |
|---|---|---|
| Q1 | Forme du regroupement Écritures et Lettrage | **Une page à onglets** |
| Q2 | Forme des éditions comptables | **Page d'accueil des éditions** (une carte par édition) |
| Q3 | Ranger aussi le reste de Compta | **Oui, deux sous-menus** : « Fiscal et social » et « Paramètres comptables » |
| Q4 | Portée du menu Documents | **Navigateur en lecture** des fichiers stockés |

| Q5 | Soldes intermédiaires de gestion réservés à `agri` ? | **Non** : ouverts à tous les référentiels |
| Q6 | Ordre des menus (Tableau de bord, Compta, Gestion, Banque, Achats, Ventes, Associés, Tiers, Documents, Outils, Configuration) | **Accepté** |
| Q7 | Immobilisations et inventaire | **Ensemble**, dans un sous-menu « Immobilisations et stocks » |
| Q8 | Mariage des icônes Lucide (trait, charte) et agric (pleines) | **Lucide partout ; agric seulement en pastille** (cartes, tuiles, en-têtes de page agricoles) |
| Q9 | Portée de l'iconification | **Menu latéral, cartes et tuiles, en-têtes de page, menu repliable en rail** |
| Q10 | Émojis façon Cultéo | **Non** : icônes vectorielles seulement |

## 7. Iconification (demande du 07/11/2026)

**Références.**
- **culteo.app** : site vitrine où chaque fonction a un pictogramme (des émojis 🌱 🚜 🧺 🌾) au-dessus d'un titre et d'une ligne de description. On retient le principe « pictogramme + titre + phrase » pour les cartes, pas les émojis (Q10).
- **agric** (`~/projects/agric`, jeu d'icônes d'Ekylibre, licence MIT, environ 1 950 icônes) : SVG pleins (`fill="currentColor"`), sprite SVG et carte des glyphes. Pictogrammes agricoles utiles : `cow`, `sheep`, `pig`, `goat`, `horse`, `tractor`, `wheat`, `corn`, `vine`, `grape`, `apple`, `seed`, `seeding`, `fertilization`, `spraying`, `sprayer`, `harvesting`, `harvester`, `silo`, `barn`, `farm`, `farmer`, `land-parcels`, `plots-rpg`, `plots-telepac`, `bee-hive`, `milk`, `tree`, `leaf`.
- **Charte Lyvre** : icônes **Lucide** (déjà `lucide-react`, 54 fichiers l'utilisent), couleur d'action `lichen`, barre latérale sombre de 240 px.

**Exigences.**
- **I1 Menu latéral** : une icône Lucide par menu de premier niveau et par entrée de sous-menu, à gauche du libellé. Le libellé reste toujours visible en mode déplié.
- **I2 Menu repliable en rail** : la barre latérale se réduit à une colonne d'icônes, avec une info-bulle qui donne le libellé. Un sous-menu s'ouvre en menu flottant. Le choix est mémorisé dans les préférences de l'utilisateur. Sur mobile, le tiroir actuel reste.
- **I3 Cartes et tuiles** : pictogramme dans une pastille colorée (rayon de la charte, fond teinté), avec un titre et une phrase. Concerne la page d'accueil des **éditions comptables**, les **catégories de calculettes** (Outils), les **types de documents** (Documents) et le **tableau de bord**. Les sujets agricoles prennent un pictogramme agric : élevage `cow`, cultures `wheat`, semis `seeding`, fertilisation `fertilization`, pulvérisation `sprayer`, récolte `harvester`, matériel `tractor`, parcelles `plots-rpg`, viticulture `vine`…
- **I4 En-têtes de page** : icône à côté du titre de chaque écran, la même que dans le menu. Pastille agric pour les écrans agricoles (inventaire `silo`, activités `farm`, aides PAC `plots-telepac`, biens vivants `cow`, plantations `vine`, coopératives `barn`).
- **I5 Une seule source** : la clé d'icône est portée par `menu_config` (`icon` pour Lucide, `pictogram` pour agric), servie à l'interface, et réutilisée par les en-têtes de page et les cartes.
- **I6 Intégration d'agric** : on embarque seulement les SVG utilisés (pas la police de 1 950 glyphes), sous forme de composants. La mention de licence MIT d'agric est ajoutée à la page « À propos » (`openSourceVendors.ts`).
- **I7 Accessibilité** : icônes décoratives (`aria-hidden`) quand le libellé est visible ; en mode rail, le libellé passe par `aria-label` et l'info-bulle. Contrastes de la charte, thème clair et sombre.
