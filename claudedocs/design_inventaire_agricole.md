# Conception : lot AG4, inventaire de clôture (stocks et avances aux cultures)

> **Statut** : **validée** (05/11/2026, AGD21), avec les réponses de l'expert-comptable au § 11 :
> - Q-S1 : écriture à la clôture sans extourne ;
> - Q-S2 : animal acheté en charge (60117) à l'achat, puis en stock à la clôture sur la même variation que les animaux nés sur l'exploitation (713551 / 713552) ;
> - Q-S3 : ordres de grandeur du prix de la viande tirés des cotations hebdomadaires fournies, pour contrôler le cours saisi ;
> - Q-S4 : la méthode forfaitaire peut aussi tenir lieu de valeur comptable au réel simplifié ;
> - Q-S5 : sans réponse, l'excédent et les sorties du stock bloqué restent à valider avant la mise en production de la valeur fiscale ;
> - Q-S6 : avances aux cultures au coût standard selon la méthode du guide CEGARA (barème par ha cumulé par mois, variantes F, M1, M2) ;
> - Q-S7 : coût réel saisi ;
> - Q-S8 : lots d'animaux avec entrées et sorties dès AG4 ;
> - Q-S9 : aide de Lexicon reportée.
>
> **AG4.a réalisé (05/11/2026, non commité)**. Contenu :
> - `data/agri_stock_accounts.yml` (11 catégories, comptes et variations du § 3, méthodes permises, compte d'achat de repère), `data/agri_price_references.yml` (fourchettes de la semaine 44 de 2026), `data/regulatory/stock.json` (décotes forfaitaires 20 % et 30 %, fiabilité R) ;
> - tables `stock_settings`, `stock_standards`, `stock_lines`, `stock_count_files` (migration `b4c6d8e0f2a3`) ;
> - `app/services/stock_inventory.py` :
>   - classement d'un compte de stock (préfixe le plus long) et variation proposée ;
>   - méthodes coût réel saisi, coût standard (barème, avertissement si l'unité diffère), prix de détail moins la décote de la catégorie, forfaitaire comme valeur comptable (option `flat_stock_method` à la clôture, sinon avertissement) ;
>   - refus du prix de détail et du forfaitaire pour les approvisionnements, les marchandises et les avances aux cultures ;
>   - contrôle de vraisemblance du cours (moins de la moitié ou plus du double de la fourchette) ;
>   - dépréciation avec motif obligatoire, plafonnée à la valeur ;
>   - stocks initiaux (soldes des comptes 31, 32, 33, 35 et 37 de l'exercice) sans ligne signalés ;
>   - repère du coût réel : charges de l'exercice sur le compte d'achat correspondant ;
>   - reprise de l'exercice précédent (quantités à zéro), import CSV ou XLSX tout ou rien, barèmes ;
>   - exercice clôturé figé ; plan agricole en partie double seulement ;
> - API `/fiscal-years/<id>/stock` (vue, lignes, réglages, reprise, import, feuilles de comptage) et `/stock-standards` ;
> - écran Compta › **Inventaire de clôture** (`/inventory/`), menu masqué au micro-BA.
>
> Écarts avec la conception :
> - les fourchettes de cours sont en données, sans import d'un nouveau fichier de cotations (format des cotations à figer d'abord) ;
> - la date du comptage est enregistrée par l'API, pas encore saisissable à l'écran ;
> - colonnes des lots, des avances aux cultures et de la valeur fiscale ajoutées dans leurs sous-lots.
>
> Tests : `tests/api/test_stock_inventory.py` (10 tests), `frontend/src/features/stock/inventory.test.tsx` (1 test).
>
> **AG4.b réalisé (05/11/2026, non commité)**. Contenu :
> - tables `stock_lots` et `stock_lot_movements`, colonnes `stock_lines.lot_id`, `heads`, `gap_reason` (migration `c5d7e9f1a3b4`) ;
> - `app/services/stock_lots.py` :
>   - lot sur 3112 ou 3113 (espèce, catégorie d'âge, destination, poids moyen) ;
>   - mouvements datés en têtes : naissance, achat (ligne d'achat facultative), vente (vente facultative), mort, passage dans un autre lot (paire sortie / entrée supprimée ensemble), sortie vers les immobilisations ;
>   - mouvements d'un exercice clôturé figés ;
>   - effectif d'ouverture = effectif compté à la clôture précédente, sinon un mouvement « effectif d'ouverture » (refusé s'il existe un comptage précédent) ;
>   - effectif théorique = ouverture + entrées − sorties de l'exercice ;
> - ligne d'inventaire d'un lot : compte et libellé repris du lot, une ligne par lot et par exercice ; effectif compté ; quantité = têtes, ou têtes × poids moyen pour une valeur au kg ; écart avec le théorique signalé tant qu'il n'a pas de motif ; lot repris avec l'exercice précédent ;
> - API `/stock-lots[/<id>]`, `/stock-lots/<id>/movements[/<id>]` (`?fiscal_year_id=` pour les effectifs) ;
> - écran : panneau « Lots d'animaux » dans le groupe Animaux de l'inventaire (ouverture, entrées, sorties, théorique, compté), fiche du lot en tiroir avec ses mouvements ; choix du lot, effectif compté et motif d'écart dans la fiche de ligne.
>
> Écarts avec la conception :
> - les liens vers la ligne d'achat et la vente se font par l'API (identifiants), sans sélecteur à l'écran ;
> - la sortie vers les immobilisations ne crée pas encore l'immobilisation : ce sera AG5.
>
> Tests : `tests/api/test_stock_lots.py` (3 tests, dont la recette des porcelets), `frontend/src/features/stock/lots.test.tsx` (1 test).
>
> **AG4.c réalisé (05/11/2026, non commité)**. Contenu :
> - tables `crop_standards`, `crop_standard_rows`, `crop_advances`, `crop_advance_costs`, colonne `stock_lines.crop_advance_id` (migration `d6e8f0a2b4c5`) ; méthode d'inventaire « fiche d'avance aux cultures » ;
> - `app/services/crop_advances.py` :
>   - fiche (production, surface, implantation, campagne, cycle) qui crée et tient sa ligne 31151 / 31141 (variation 713312 / 713311), une nouvelle fiche à chaque clôture ;
>   - **coût standard** : barème de l'exploitation par ha, par composante et par mois calendaire, cumulé du mois d'implantation au mois de clôture (12 mois au plus, avertissement au-delà), × surface ; variantes F, M1 et M2 ; en M1 et M2, approvisionnements au coût réel ; hypothèse de main-d'œuvre du barème affichée ;
>   - **coût réel 72 A** : lignes d'écriture de l'exercice proposées par rubrique (60112, 60111, 60113, 641, 6051, 60614, 615, 6132, 6811 ; à-nouveaux et clôture exclus), quote-part par culture, une ligne jamais répartie au-delà de 100 % ; charges saisies par rubrique ; fermage, assurance et frais généraux jamais proposés ;
>   - barèmes : saisie (grille 12 mois × 3 composantes) et import CSV (Production ; Année ; Composante ; Mois ; Montant), tout ou rien ;
>   - la ligne d'inventaire d'une fiche ne se modifie que par la fiche (sauf la dépréciation) ;
> - API `/fiscal-years/<id>/crop-advances` (POST), `/crop-advances/<id>` (GET, PUT, DELETE), `/crop-advances/<id>/costs[/<id>]`, `/crop-standards[/<id>]`, `/crop-standards/import` ;
> - écran : panneau « Avances aux cultures » du groupe Végétaux en terre (fiche en tiroir : méthode, barème, charges cochées avec quote-part, charges saisies) et éditeur des barèmes par ha.
>
> Écarts avec la conception :
> - les charges sont proposées depuis les **lignes d'écriture** (factures d'achat comprises, une fois comptabilisées), pas depuis les lignes de facture : une charge n'est jamais comptée deux fois ;
> - main-d'œuvre limitée aux salaires (641) ; la règle pour l'exploitant seul reste à confirmer (§ 11, « Reste à confirmer »).
>
> Tests : `tests/api/test_crop_advances.py` (3 tests, dont les deux recettes du § 13), `frontend/src/features/stock/cropAdvances.test.tsx` (1 test).
>
> **AG4.d réalisé (05/11/2026, non commité)**. Contenu :
> - source d'écriture gérée `STOCK` (hors livres de TVA, **non extournée** à l'ouverture) ;
> - `app/services/stock_entry.py` :
>   - écriture OD au dernier jour : pour chaque compte de stock, annulation du solde avant écriture (D variation / C 3x, ou l'inverse pour un solde créditeur), puis constatation du stock final des lignes (D 3x / C variation, par couple compte et variation) ;
>   - un compte de stock sans ligne est ramené à zéro sur sa variation par défaut ;
>   - dépréciations : reprise du solde créditeur des 39x (D 39x / C 78173), dotation des lignes (D 68173 / C 391, 392, 393, 395 ou 397 selon le compte) ;
>   - refusée si une ligne n'a pas de valeur ; repassée en remplaçant la précédente ; annulable tant que l'exercice est ouvert et l'écriture non validée ;
>   - « à repasser » quand l'inventaire a changé depuis l'écriture (comparaison des soldes par compte) ;
> - `data/agri_stock_accounts.yml` : préfixes de repli 31 (6031), 33 (7133) et 35 (7135) pour les dossiers repris qui tiennent ces comptes sans détail ;
> - contrôles de clôture : stocks à l'ouverture sans inventaire, inventaire saisi sans écriture, inventaire modifié depuis l'écriture (**anomalies**) ; comptes de stock sans ligne, lignes à compléter, mouvements de comptes de stock hors de l'écriture et des à-nouveaux (**informations**) ;
> - API `POST / DELETE /fiscal-years/<id>/stock/entry` ; état de l'écriture dans la vue de l'inventaire ; export `/fiscal-years/<id>/stock.xlsx` (lignes, contrôles, totaux, stock initial, variation) ;
> - écrans : bandeau « Écriture de stock » sur l'inventaire (état, stock initial et final, variation, Passer, Repasser, Annuler, XLSX) et panneau identique dans Clôture › Inventaire.
>
> Écarts avec la conception :
> - le stock initial annulé est le **solde du compte avant l'écriture** (à-nouveaux et mouvements de l'exercice), comme le journal KF ; un compte de stock mouvementé en cours d'exercice est signalé, sans être retraité ;
> - pas encore de valeur fiscale dans l'export : AG4.e.
>
> Tests : `tests/api/test_stock_entry.py` (4 tests, dont la recette du dossier fictif A : sans son journal KF, les stocks finaux saisis redonnent les soldes des comptes 31111, 31114, 31115, 3113, 31, 35511, 35513).
>
> **AG4.e réalisé (05/11/2026, non commité) — lot AG4 terminé (a à e)**. Contenu :
> - colonnes `stock_lines.fiscal_method`, `fiscal_value_cents`, `fiscal_reason` (migration `e7f9a1b3c5d6`) ;
> - `app/services/stock_tax.py`, valeur fiscale par ligne :
>   - **valeur comptable** par défaut ;
>   - **forfaitaire** (option `flat_stock_method` à la clôture, hors approvisionnements et avances aux cultures) : cours × (1 − 20 % ou 30 %) ; égale à la valeur comptable si la ligne est déjà au forfaitaire ;
>   - **stock bloqué** (option `stock_freeze_72_b_bis` à la clôture, produits et animaux) : valeur unitaire fiscale de la ligne de même clé (compte et lot, ou compte et production) à la dernière clôture avant l'option ; quantité bloquée = plus petite des quantités de référence, des exercices intermédiaires et de l'exercice ; surplus à la valeur comptable ; avertissement « à valider (Q-S5) » sur chaque ligne ;
>   - **valeur saisie** avec motif obligatoire ;
>   - écart fiscal par ligne et total, sans écriture (`stock_tax.totals`, lu par AG6.3) ;
> - contrôles de clôture : option en vigueur sans méthode fiscale choisie, valeurs fiscales incomplètes (informations) ;
> - export XLSX : méthode fiscale, valeur fiscale et écart par ligne ; valeur fiscale totale et écart dans les totaux ;
> - écran : colonne « Valeur fiscale » et total fiscal avec l'écart quand une option est en vigueur ; choix de la méthode fiscale dans la fiche de ligne.
>
> Écarts avec la conception :
> - la règle du stock bloqué (Q-S5) reste une proposition, signalée sur chaque ligne : à confirmer avant la mise en production ;
> - la clé de rapprochement entre exercices est le compte et le lot, ou à défaut le compte et la production (sinon le libellé) : une ligne renommée perd sa référence.
>
> Tests : `tests/api/test_stock_tax.py` (3 tests), `frontend/src/features/stock/inventory.test.tsx` (1 test de plus).
>
> **Besoins** : `claudedocs/compta_agri.md`, lot AG4 (AG4.1 à AG4.7). Réponse d'expert du § 8 : décote forfaitaire de 20 %, et de 30 % pour les bovins et la viticulture ; reproducteurs immobilisés s'ils restent durablement.
> **Sources lues le 05/11/2026** :
> - CEGARA, « Guide pratique — Études de coûts standards — Avances aux cultures », décembre 2016 (PDF fourni, hors git, AGD16) : méthode seulement, aucune valeur reprise ;
> - compta-online, « Comptabilisation des animaux » (modifié le 17/09/2018) : achat d'animaux en charge, stock et variation 713 à la clôture ;
> - cotations hebdomadaires de la viande, semaine 44 du 26/10 au 01/11/2026 (`COT-VIA-cotations_csv-A26-S44.zip`, fourni, hors git) ;
> - Recueil PCG 2026, titre 5 (art. 618-13 et 618-14, p. 241-242 ; plan agricole, p. 632-634) ; `audit_reglementation.md` § 2.4 (CGI art. 72 A, 72 B bis, 74 b ; annexe III art. 38 sexdecies, **à vérifier sur Légifrance avant citation**).
> **Socle** :
> - plan `agri` (comptes 31 à 39, 603, 713, 68173, 78173) ;
> - écritures d'inventaire de la clôture (`closing.add_inventory`) ;
> - options fiscales datées (`stock_freeze_72_b_bis`, `flat_stock_method`) ;
> - pièces jointes (`attachments`) ;
> - jeu d'essai A (stocks de produits, aliments, engrais, porcelets).
>
> **Hors lot** : biens vivants immobilisés (AG5) ; tableau de passage fiscal (AG6.3), qui reprendra l'écart de valeur fiscale calculé ici ; provision 73 A pour les vaches (AG6).

---

## 1. Constats

### 1.1 Ce que dit le PCG agricole

- **Art. 618-13** :
  - **coût standard** : on peut le calculer par barèmes, sans comptabilité analytique, en tenant compte des capacités normales de production ;
  - **prix de détail** : cours du jour à la clôture, s'il est un bon indicateur du prix final, **moins une décote adaptée à chaque catégorie** ; réservé aux produits qui ont atteint un stade commercialisable ;
  - ces adaptations valent seulement pour les **produits finis et en-cours nés de l'activité agricole**.
- **Art. 618-14** :
  - **avances aux cultures** : façons culturales évaluables au coût standard ;
  - **prix de détail interdit** ;
  - dépréciation selon le prix, les perspectives de production (intempéries, maladies) et de vente.
- **Plan agricole** :
  - 3111x approvisionnements ;
  - 3112 et 3113 animaux, cycle long et cycle court ;
  - 31141 et 31151 avances aux cultures ; 31142, 31152, 31148 et 31158 pépinières et autres végétaux ;
  - 3311x et 3312x en-cours ;
  - 3511x produits intermédiaires ; 3551x produits finis ;
  - 39x dépréciations ;
  - variations : 6031, 6032, 6037, et 713311 / 713312, 71351, 71355, 713551 à 713554.
  - **Le titre 5 ne dit pas quelle variation correspond à chaque compte de stock** : la correspondance du § 3 est une proposition (Q-S2).

### 1.2 Ce que font les dossiers réels (jeu d'essai A, journal KF au 31/01/2025)

À la clôture, une écriture par compte de stock :
- **annule le stock initial** : D variation / C 3x, pour le montant des à-nouveaux ;
- **constate le stock final** : D 3x / C variation.

Les contreparties observées :
- 3111x en 6031 ; le carburant en 6032 ;
- 3113 (porcelets) en 713 ou 713552 ;
- 3551x (maïs, produits transformés) en 7135.

Rien n'est extourné à l'ouverture : le stock initial reste porté jusqu'à la clôture suivante. C'est l'inventaire intermittent classique.

### 1.3 Ce que Lyvre a déjà

- **Écritures d'inventaire** (charges à payer, produits à recevoir, AG3.c) : datées du dernier jour, **extournées à l'ouverture**. Elles ne conviennent pas telles quelles aux stocks si l'on suit la pratique du § 1.2 (Q-S1).
- **Lignes d'achat** :
  - montant hors taxe, compte, article du catalogue ;
  - **pas de quantité** : un CUMP ou un PEPS ne se calcule pas depuis les factures (Q-S7).
- **Options fiscales** : blocage 72 B bis (5 ans) et méthode forfaitaire 74 b, datées dans le profil fiscal.
- **Micro-BA** : pas d'inventaire (AG4.7).

---

## 2. Choix structurants

1. **Un inventaire par exercice**, fait de lignes de stock : catégorie, compte, libellé, production, quantité, unité, méthode, valeur unitaire, valeur. Il est saisi à l'écran, ou importé depuis un tableur.
2. **Une écriture de stock par exercice**, gérée par Lyvre (source `STOCK`), datée du dernier jour, **non extournée**. Pour chaque compte de stock :
   - D variation / C 3x pour le solde du compte avant l'écriture (stock initial porté par les à-nouveaux) ;
   - D 3x / C variation pour le stock final.
   Elle se regénère tant que l'exercice est ouvert. Elle reste juste après un historique importé, qui n'a pas d'extournes (Q-S1).
3. **La méthode est choisie par ligne**, avec des refus :
   - le prix de détail est interdit pour les avances aux cultures (PCG 618-14) et pour les approvisionnements achetés (PCG 618-13, 4°) ;
   - la méthode forfaitaire est fiscale (§ 6).
4. **Les avances aux cultures** sont une fiche par culture en terre. Ses charges sont prises dans la liste fermée de l'art. 72 A et proposées depuis les achats et les écritures de l'exercice ; l'utilisateur coche et fixe la quote-part. La fiche alimente sa ligne de stock (31141 / 31151).
5. **Deux valeurs par ligne** : comptable et fiscale (forfaitaire, stock bloqué). L'écart par ligne est gardé pour le tableau de passage d'AG6.
6. **Les aides de Lexicon sont des propositions** (prix, rendements) : jamais imposées, toujours sourcées (§ 7).

---

## 3. Comptes de stock et de variation (`data/agri_stock_accounts.yml`)

Proposition (Q-S2). Le compte de variation se change par ligne si besoin.

| Catégorie | Comptes de stock | Variation proposée | Méthodes permises |
|---|---|---|---|
| Approvisionnements | 31111 à 31116 | 6031 | coût réel, coût standard |
| Autres approvisionnements (carburant, emballages) | 32x | 6032 | coût réel |
| Marchandises | 37 | 6037 | coût réel |
| Animaux, cycle long (non immobilisés), nés ou achetés | 3112 | 713551 | coût réel, coût standard, prix de détail, forfaitaire |
| Animaux, cycle court, nés ou achetés | 3113 | 713552 | coût réel, coût standard, prix de détail, forfaitaire |
| Avances aux cultures, cycle long / court | 31141 / 31151 | 713311 / 713312 | fiche culture : coût standard (barème) ou coût réel (72 A) |
| Pépinières, autres végétaux, cycle long / court | 31142, 31148 / 31152, 31158 | 713553 / 713554 | coût réel, coût standard, prix de détail |
| En-cours, cycle long (vins, alcools) | 3311x | 713311 | coût réel, coût standard |
| En-cours, cycle court | 3312x | 713312 | coût réel, coût standard, prix de détail |
| Produits intermédiaires | 3511x | 71351 | coût réel, coût standard, prix de détail |
| Produits finis végétaux | 35511 | 713554 (713553 pour le cycle long) | coût réel, coût standard, prix de détail |
| Produits finis animaux | 35512 | 713552 (713551) | coût réel, coût standard, prix de détail |
| Produits finis transformés | 35513 | 71355 | coût réel, coût standard, prix de détail |

- **Dépréciation** : D 68173 / C 39x (391 pour 31, 393 pour 33, 395 pour 35, 397 pour 37). La reprise de la dépréciation précédente se fait en D 39x / C 78173, dans la même écriture.
- **Animaux achetés** (Q-S2) : l'achat reste une charge (60117) ; à la clôture, l'animal encore présent entre en stock sur la même variation que l'animal né sur l'exploitation (713551 / 713552). Lyvre ne retraite pas l'achat.
- **Reproducteur en stock** (3112 qui restera durablement) : l'alerte relève d'AG5.3.
- Les autres correspondances du tableau sont des propositions, modifiables par ligne.

---

## 4. Inventaire et méthodes (AG4.1, AG4.2)

### 4.1 Ligne de stock

| Champ | Contenu |
|---|---|
| catégorie, compte de stock, compte de variation | proposés depuis le § 3 |
| libellé, production | production Lexicon facultative, pour les prix (§ 7) |
| lot | animaux : espèce, catégorie d'âge, nombre de têtes |
| quantité, unité | t, q, kg, hl, tête, ha, unité |
| méthode comptable | `actual` coût réel saisi, `standard` barème, `retail` prix de détail − décote, `flat` forfaitaire (réel simplifié, Q-S4), `crop_advance` fiche culture, `lot` lot d'animaux |
| valeur unitaire | saisie, ou calculée par la méthode |
| valeur comptable | quantité × valeur unitaire, arrondie au centime ; ou total de la fiche culture |
| dépréciation | montant et motif (prix, intempéries, maladie) |
| valeur fiscale | § 6 |
| notes | |

### 4.2 Méthodes

- **Coût réel** : valeur unitaire saisie. Faute de quantités dans les achats, Lyvre ne calcule ni CUMP ni PEPS ; il affiche à côté le total hors taxe des achats de l'exercice sur le compte de charge correspondant, comme repère (Q-S7).
- **Coût standard** : barème de l'exploitation (`stock_standards` : clé, libellé, unité, valeur, source, année), saisi ou importé d'un tableur (barèmes des chambres ou des instituts). La ligne garde la référence du barème et sa valeur du jour.
- **Prix de détail moins décote** :
  - cours du jour à la clôture (saisi, avec sa source et sa date) × (1 − décote) ;
  - la **décote est fixée par catégorie** pour l'exercice, sans valeur par défaut ;
  - refusé pour les approvisionnements, les marchandises et les avances aux cultures.
- **Contrôle de vraisemblance du cours saisi** (Q-S3) : `data/agri_price_references.yml` donne des fourchettes d'ordre de grandeur, avec leur unité, tirées des cotations de la semaine 44 de 2026. Un cours hors de la fourchette (moins de la moitié ou plus du double) déclenche un avertissement, jamais un refus ; une erreur d'unité est vite repérée (€/kg vif, €/kg de carcasse, €/tête).

  | Catégorie | Unité | Ordre de grandeur (semaine 44/2026) |
  |---|---|---|
  | Porc charcutier | €/kg de carcasse | 1,7 à 1,9 |
  | Gros bovins entrée abattoir (jeunes bovins, vaches, génisses, bœufs) | €/kg net | 5,1 à 8,7 |
  | Bovins maigres (broutards) | €/kg vif | 3,6 à 5,1 |
  | Agneaux de boucherie | €/kg de carcasse | 8,2 à 10,3 |
  | Veaux de boucherie | €/kg de carcasse | 5,4 à 12,6 |
  | Petits veaux de 14 jours à 4 semaines | €/tête | 36 à 306 |

  Le fichier est daté et se met à jour en important un nouveau fichier de cotations. Les céréales n'ont pas de fourchette dans ce fichier.
- **Méthode forfaitaire** (Q-S4) : permise comme valeur comptable quand l'option `flat_stock_method` est en vigueur à la clôture (réel simplifié), aux taux du § 6 ; la valeur fiscale est alors la même.
- **Fiche culture** : avances aux cultures seulement (§ 5).

### 4.3 Feuilles de comptage

- Une ou plusieurs pièces par inventaire : PDF, image ou tableur.
- Elles sont rangées sous `uploads/<instance>/inventaire/<exercice>/` et entrent dans l'archive de l'expert-comptable.

### 4.4 Reprise de l'exercice précédent

« Reprendre les lignes de l'exercice précédent » copie les libellés, les comptes, les méthodes et les lots, avec les quantités à zéro, pour éviter la ressaisie.

---

## 5. Avances aux cultures (AG4.4)

### 5.1 Fiche

Une fiche par culture en terre à la clôture : production, surface en ha, mois d'implantation, campagne de récolte, parcelles en texte libre, cycle court ou long. Elle alimente sa ligne de stock (31141 / 31151). Deux méthodes sont possibles, au choix et constantes d'un exercice à l'autre.

### 5.2 Coût standard (méthode du guide CEGARA, Q-S6)

- **Barème par production** (`crop_standards`) :
  - coût par ha et par mois d'opérations, depuis l'implantation, en trois composantes : approvisionnements (semences, engrais, traitements), mécanisation (heures × coût horaire du matériel) et main-d'œuvre (heures × coût horaire) ;
  - le barème garde son unité (ha), son année, sa source, et l'hypothèse de main-d'œuvre (le guide chiffre 100 % de main-d'œuvre salariée) ;
  - Lyvre ne livre **aucune valeur** : le guide est un document de tiers daté de 2016 (AGD16). L'exploitation saisit ou importe son barème (tableur : production, composante, mois, montant par ha).
- **Variantes** :
  - **F** : approvisionnements, mécanisation et main-d'œuvre ;
  - **M1** : mécanisation et main-d'œuvre, approvisionnements au coût réel (§ 5.3) ;
  - **M2** : mécanisation seule, approvisionnements au coût réel.
  - *Lot CG2.a (07/11/2026, `design_fiabilisation_cegara.md` § 2.1)* : au coût réel, M1 prend aussi les travaux par des tiers (6051, rubrique `contracting`) ; M2 prend en plus la main-d'œuvre salariée (641, 645, hors 64116 et 64117). Table `CROP_REAL_RUBRICS`.
  - *Lot CG2.b* : un barème se saisit par mois ou **en cumul** (premier mois du cycle) ; Lyvre garde le montant du mois.
- **Calcul** : cumul du barème du mois d'implantation au **mois de clôture** inclus, × surface ; les approvisionnements cochés s'ajoutent en M1 et M2.
  - Exemple de forme : un blé semé en novembre, une clôture fin janvier et un barème F cumulé sur novembre à janvier, × 12 ha.
- **Main-d'œuvre** : le barème suppose une main-d'œuvre salariée. Une fiche sans salariés choisit M2, ou retire la main-d'œuvre ; la règle pour l'exploitant seul est à confirmer (§ 11).

### 5.3 Coût réel (liste fermée de l'art. 72 A)

- Rubriques : semences et plants ; engrais et amendements ; produits de traitement ; main-d'œuvre des façons culturales, de l'amendement et des semis ; frais de matériel (carburants, entretien, réparations, amortissements) ; travaux et services par des tiers (lot CG2.a).
- **Propositions** : les lignes d'achat et d'écriture de l'exercice sur les comptes de chaque rubrique (60111, 60112, 60113, 6051, 60614, 615x, 6811x, 641x) sont proposées, l'utilisateur coche et fixe la quote-part (100 % par défaut pour un intrant).
- **Refusés** : fermage, assurance, frais généraux.
- Sert aussi aux approvisionnements des variantes M1 et M2.

### 5.4 Dépréciation et valeur fiscale

- La dépréciation se saisit sur la ligne de stock, avec son motif (art. 618-14 IR3).
- Valeur fiscale = valeur comptable, sauf saisie contraire ; la méthode forfaitaire n'y est pas permise.

### 5.5 Lots d'animaux (Q-S8)

- **Lot** : espèce, catégorie d'âge, destination (vente, engraissement), compte (3112 / 3113), unité de suivi (tête), poids moyen facultatif.
- **Mouvements** datés, en nombre de têtes : effectif d'ouverture (reprise de la clôture précédente), naissance, achat (lien facultatif vers la ligne d'achat 60117), vente (lien facultatif vers la vente), mort, passage dans une autre catégorie d'âge (sortie d'un lot, entrée dans un autre), sortie vers les immobilisations (AG5).
- **Effectif théorique à la clôture** = ouverture + entrées − sorties. L'effectif compté est saisi à l'inventaire ; un écart est signalé avec son motif.
- **Valeur** : effectif compté × valeur par tête, selon la méthode de la ligne (coût réel, standard, prix de détail au kg × poids moyen, forfaitaire).
- Les mouvements ne passent **aucune écriture** : l'inventaire reste intermittent ; ils servent de registre et de contrôle.

## 6. Valeur fiscale (AG4.6)

- **Méthode forfaitaire** (option `flat_stock_method` en vigueur à la clôture, réel simplifié) :
  - valeur fiscale = cours du jour × (1 − décote) ;
  - décote : `stock.flat_discount_general_bp` = 2 000 (20 %) en général ; `stock.flat_discount_cattle_wine_bp` = 3 000 (30 %) pour les bovins et les produits de la viticulture ;
  - les deux paramètres sont datés, avec la fiabilité « R, expert-comptable 04/11/2026 » ;
  - champ : produits finis, en-cours et animaux ; **jamais** les approvisionnements achetés ni les avances aux cultures ;
  - le cours du jour vient de la ligne (prix de détail) ou se saisit.
- **Stock bloqué** (option `stock_freeze_72_b_bis` en vigueur à la clôture) :
  - les lignes bloquées gardent la **valeur unitaire fiscale de la clôture qui précède l'option** ;
  - cette valeur de référence est proposée depuis la ligne de même clé (compte, production, libellé) de cet exercice ;
  - **proposition à valider avant la mise en production** (Q-S5 sans réponse) : les quantités au-delà de la quantité de référence sont évaluées selon la règle normale ; une sortie réduit d'abord la quantité bloquée, qui ne se reconstitue pas. La valeur fiscale reste modifiable par ligne. La règle est à vérifier dans le BOFiP (stocks à rotation lente).
- **Écart** = valeur fiscale − valeur comptable, par ligne et au total. Il est exporté et lu par AG6.3. Aucune écriture.
- Sans option, la valeur fiscale est la valeur comptable.

---

## 7. Aide à la valorisation (AG4.3)

### 7.1 Ce que Lexicon expose (code de `lexicon-rest-api` et de `lexicon` lu le 05/11/2026, API non appelée)

- **Prix** : `GET /production/prices.json?specie=&department=&campaign=&page=`, ouvert sans clé.
  - Lignes les plus récentes d'abord, 150 par page, **sans filtre de date**.
  - Chaque ligne donne le département, l'espèce, la date de début, la campagne, le prix final en EUR par tonne (ou par m³) et un libellé (par exemple « Blé MATIF »).
  - Le département `0` désigne la France.
- **Données réellement chargées** :
  - cours MATIF blé, colza et maïs, mensuels, jusqu'en **décembre 2025** ;
  - prix payés aux producteurs jusqu'en 2021 ;
  - lait jusqu'en juillet 2021 ;
  - **aucun prix de la viande** : les fichiers sont lus, mais jamais versés dans la table des prix.
- **Rendements** (Agreste, q/ha, campagnes 2021 à 2026, 11 grandes cultures, par département) : pas de route de table. On les lit seulement par l'outil MCP `get_crop_figures` (`POST /mcp`, arguments `production`, `department`), ouvert sans clé.
  - Cet outil renvoie aussi au plus 12 prix récents.
  - Il rate les prix régionaux des départements 01 à 09, à cause d'un défaut de codes.
- **Cotations de l'UE** (`eu_market_prices`, céréales) : chargées dans la base, mais **sans route HTTP**.
- **Défauts des données sources** :
  - codes de département non complétés à deux chiffres ;
  - Gironde absente ;
  - noms de régions du lait différents de la table des régions.

### 7.2 Décision : reportée (Q-S9)

Aucune aide de Lexicon dans AG4. Les constats du § 7.1 restent pour une reprise ultérieure, par exemple quand Lexicon publiera des prix à jour. Proposition gardée pour mémoire :


- **AG4.e réduit aux cours MATIF** (céréales, oléagineux) : pour une ligne de stock de blé, colza ou maïs, Lyvre propose le dernier cours national publié **à la date de clôture ou avant**, avec sa date et son libellé, pour le prix de détail ou la méthode forfaitaire.
- **Rendement Agreste** du département (outil MCP) affiché sur la fiche d'avance aux cultures, à titre indicatif.
- **Pas de proposition** pour les animaux, le lait, les légumes ou la viticulture : rien d'à jour n'est publié. Le cours se saisit, avec sa source.
- Si un cours proposé date de plus de 3 mois avant la clôture, Lyvre le signale.
- Ces limites seront signalées à OSFarm (prix de la viande non chargés, codes de département) : c'est une remarque, pas une dépendance du lot (Q-S9).

### 7.3 Principes

Quelle que soit la route :
- le prix ou le rendement proposé s'affiche **à côté** de la saisie, avec sa source, sa date et son unité ; un clic le reprend ;
- rien n'est imposé ni recalculé à l'insu de l'utilisateur ;
- lecture côté serveur avec la clé `LEXICON_API_KEY` (AG3.e), mise en cache par production et par mois ; rien n'est envoyé d'autre que la production, le département et la date.

---

## 8. Écriture d'inventaire (AG4.5)

- Source `STOCK`, gérée (comme les dotations), journal OD, date du dernier jour, **non extournée** (Q-S1).
- Pour chaque compte de stock présent dans l'inventaire ou dont le solde avant écriture n'est pas nul :
  - annulation du stock initial : D variation / C 3x, pour le solde du compte avant l'écriture, hors cette écriture ;
  - constatation du stock final : D 3x / C variation, pour la somme des valeurs comptables des lignes ;
  - le compte de variation est celui des lignes. Une ligne qui change de compte de variation sépare les montants.
- **Dépréciations** : reprise du solde 39x avant l'écriture (D 39x / C 78173), puis dotation de l'exercice (D 68173 / C 39x).
- **Passer, repasser, annuler** tant que l'exercice est ouvert. L'inventaire est **figé** quand l'écriture est validée ou l'exercice clôturé.
- **Contrôles de clôture** (plan agricole, partie double) :
  - compte de stock avec un solde à l'ouverture et aucune ligne d'inventaire, alors que l'écriture n'est pas passée (**anomalie**, comme un inventaire oublié) ;
  - inventaire saisi, écriture non passée (**anomalie**) ;
  - ligne sans valeur, avance aux cultures sans fiche, décote de prix de détail non fixée (**information**) ;
  - mouvement 3x hors de l'écriture de stock et des à-nouveaux (**information** : stock tenu ailleurs) ;
  - option 72 B bis ou forfaitaire en vigueur sans valeur fiscale saisie (**information**).
- **Écran Clôture › Inventaire** : panneau « Stocks » avec le total par catégorie, le lien vers l'écran d'inventaire, et les boutons Passer, Repasser, Annuler.

---

## 9. Données, API, écrans

### 9.1 Tables (base de l'instance)

- `stock_lines` :
  - `fiscal_year_id`, `category`, `account_id`, `variation_account_id`, `label`, `production`, `lot_species`, `lot_age_class`, `heads` ;
  - `quantity` (décimal), `unit`, `method`, `standard_id`, `market_price_cents`, `discount_bp`, `unit_value_cents`, `value_cents` ;
  - `depreciation_cents`, `depreciation_reason` ;
  - `fiscal_method` (none, flat, frozen), `fiscal_unit_value_cents`, `fiscal_value_cents` ;
  - `crop_advance_id`, `notes`, `position`.
- `stock_settings` : `fiscal_year_id`, décotes par catégorie (JSON), `entry_id`, `counted_on`.
- `stock_count_files` : pièces de l'inventaire.
- `stock_standards` : barème de coûts standard.
- `crop_advances` : `fiscal_year_id`, `production`, `surface_ha`, `planted_month`, `campaign`, `cycle`, `plots`, `method` (standard F / M1 / M2, actual), `crop_standard_id`, `notes`.
- `crop_standards` et `crop_standard_rows` : barème par production (unité, année, source, hypothèse de main-d'œuvre) ; montant par ha, par composante (approvisionnements, mécanisation, main-d'œuvre) et par mois depuis l'implantation.
- `stock_lots` : `species`, `age_class`, `destination`, `account_id`, `average_weight_kg`, `active` ; `stock_lot_movements` : `lot_id`, `on`, `kind` (opening, birth, purchase, sale, death, transfer_out, transfer_in, to_fixed_assets), `heads`, `purchase_line_id`, `sale_id`, `counterpart_lot_id`, `note` ; la ligne de stock porte `lot_id` et l'effectif compté.
- `crop_advance_costs` : `crop_advance_id`, `rubric` (72 A), `source` (purchase_line, journal_line, manual), `source_id`, `label`, `base_cents`, `share_bp`, `amount_cents`.

### 9.2 Services

- `stock_inventory.py` : lignes, méthodes, valeurs, reprise de l'exercice précédent, import ;
- `crop_advances.py` : fiches, barèmes et cumul au mois de clôture, propositions 72 A ;
- `stock_lots.py` : lots, mouvements, effectif théorique ;
- `price_references.py` : fourchettes de cours et import d'un fichier de cotations ;
- `stock_entry.py` : écriture, dépréciations, contrôles ;
- `stock_tax.py` : valeur fiscale, écarts ;

### 9.3 API

- `/fiscal-years/<id>/stock` (lignes, réglages, totaux) ;
- `/fiscal-years/<id>/stock/lines[/<id>]` ;
- `/fiscal-years/<id>/stock/copy-previous` ;
- `/fiscal-years/<id>/stock/import` ;
- `/fiscal-years/<id>/stock/files[/<id>]` ;
- `/fiscal-years/<id>/stock/entry` (POST, DELETE) ;
- `/fiscal-years/<id>/crop-advances[/<id>]` ;
- `/crop-advances/<id>/proposals` ;
- `/crop-advances/<id>/costs` ;
- `/stock-standards[/<id>]` et `/stock-standards/import` ;
- `/stock-lots[/<id>]`, `/stock-lots/<id>/movements[/<id>]` ;
- `/crop-standards[/<id>]` et `/crop-standards/import` ;
- `/price-references` et `/price-references/import` ;
- export `/fiscal-years/<id>/stock.xlsx` (état d'inventaire avec valeur comptable, valeur fiscale et écart).

L'expert-comptable lit et exporte, sans écrire.

### 9.4 Écrans

- **Compta › Inventaire de clôture** (`/inventory/?fiscal_year=`), plan agricole, partie double, **masqué au micro-BA** (AG4.7) :
  - onglets par catégorie, totaux comptable et fiscal ;
  - grille de saisie (quantité, unité, méthode, valeur unitaire, valeur) ;
  - fiche « Avance aux cultures » en tiroir ;
  - pièces de comptage ;
  - boutons « Reprendre l'exercice précédent » et « Importer ».
- **Clôture › Inventaire** : panneau « Stocks » (§ 8).
- **Échéancier** : la fiche DIV-03 (clôture et inventaire) renvoie vers l'inventaire.

---

## 10. Ce qui n'est pas dans AG4

- biens vivants immobilisés, lots d'immobilisations, 234 / 724, abattage sanitaire : **AG5** ;
- tableau de passage fiscal, provision 73 A, DEP : **AG6** (AG4 fournit l'écart de valeur fiscale) ;
- **inventaire permanent** (entrées et sorties de stock en cours d'année) : hors périmètre ; l'inventaire reste intermittent ;
- quantités dans les factures d'achat : à ouvrir si Q-S7 le demande.

---

## 11. Questions (posées le 05/11/2026, réponses en tête du document)

- **Q-S1 Écriture de stock.**
  - Proposition : une écriture à la clôture qui annule le stock initial et constate le stock final, **sans extourne à l'ouverture**, comme dans les dossiers réels.
  - Autre choix : écriture du seul stock final, extournée à l'ouverture, comme les autres écritures d'inventaire. Elle donne le même résultat, mais elle est fausse la première année après un historique importé.
- **Q-S2 Contreparties de variation** du § 3, en particulier :
  - avances aux cultures en **713311 / 713312** (en-cours), ou en 7135x ?
  - produits finis végétaux en **713554** (cycle court) par défaut ?
  - animaux nés sur l'exploitation et animaux achetés (60117) sur la même variation **713551 / 713552**, ou les achetés en 6031 ?
- **Q-S3 Décote du prix de détail** (PCG 618-13, 3°) : saisie par catégorie et par exercice, sans valeur par défaut ? Faut-il un plafond, ou un avertissement au-delà d'un taux ?
- **Q-S4 Méthode forfaitaire.**
  - Est-elle seulement une **valeur fiscale** (écart extra-comptable), ou peut-elle aussi tenir lieu de valeur comptable au réel simplifié ?
  - Faut-il étendre le taux de 30 % à d'autres catégories que les bovins et la viticulture ?
- **Q-S5 Stock bloqué (72 B bis)** :
  - les quantités au-delà de la quantité de référence sont-elles évaluées selon la règle normale ?
  - une sortie consomme-t-elle d'abord les unités bloquées ?
- **Q-S6 Avances aux cultures, art. 72 A** :
  - la main-d'œuvre est-elle limitée aux **salariés**, sans rémunération de l'exploitant ?
  - les quotes-parts d'amortissement du matériel sont-elles saisies, ou faut-il une clé (heures, hectares) ?
- **Q-S7 Coût réel** :
  - valeur unitaire saisie, Lyvre ne calculant ni CUMP ni PEPS faute de quantités dans les achats (proposition) ;
  - ou faut-il ajouter les quantités aux lignes d'achat pour calculer le CUMP ?
- **Q-S9 Aide de Lexicon** : faut-il garder AG4.e avec les seuls cours MATIF et les rendements Agreste (§ 7.2) ? Ou le reporter jusqu'à ce que Lexicon publie des prix à jour (viande, lait, légumes) ?
- **Q-S8 Animaux en stock par lot** : espèce, catégorie d'âge et nombre de têtes suffisent-ils ? Ou faut-il l'entrée et la sortie par lot dès AG4, sans attendre AG5 ?

---

## 12. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG4.a** | Comptes du § 3, tables, lignes de stock et méthodes (coût réel, standard, prix de détail avec refus, forfaitaire comptable), barème de coûts standard, fourchettes de cours (§ 4.2), pièces de comptage, reprise de l'exercice précédent, import, écran d'inventaire, masqué au micro-BA | — |
| **AG4.b** | Lots d'animaux : lots, mouvements en têtes, effectif théorique et compté, valeur de la ligne (§ 5.5) | AG4.a |
| **AG4.c** | Avances aux cultures : fiches, coût standard du barème F / M1 / M2 cumulé au mois de clôture, coût réel 72 A proposé depuis les achats et les écritures (§ 5) | AG4.a |
| **AG4.d** | Écriture de stock (`STOCK`), dépréciations 39x / 68173 / 78173, contrôles de clôture, panneau de clôture, export XLSX | AG4.a |
| **AG4.e** | Valeur fiscale (forfaitaire 20 % / 30 %, stock bloqué 72 B bis selon la proposition du § 6), écarts pour AG6 | AG4.d |

Ordre proposé : a → b ∥ c → d → e. L'aide de Lexicon est reportée (Q-S9).

---

## 13. Tests

- **Écriture** (jeu calculé) :
  - engrais : stock initial 6 692,66 € et stock final 4 000 € donnent D 6031 6 692,66 / C 31111 6 692,66, puis D 31111 4 000 / C 6031 4 000 ;
  - repassée : une seule écriture ;
  - après un historique sans extourne : même résultat.
- **Dossier fictif A** (recette) : à partir des à-nouveaux du 01/02/2024, la saisie des stocks finaux du 31/01/2025 redonne, compte par compte, les montants du journal KF (35513, 35511, 3113, 31111, 31114, 31115).
- **Méthodes** :
  - prix de détail refusé sur 31151 et sur 31111 ;
  - décote appliquée par catégorie ;
  - coût standard pris dans le barème.
- **Avance aux cultures** :
  - coût réel : blé semé en octobre, avec semences 2 400 €, engrais 1 800 € (cochés à 100 %) et carburant 3 000 € à 40 % ; valeur 5 400 € en 31151 ; fermage refusé ;
  - coût standard : barème saisi de 100 €/ha en novembre, 20 €/ha en décembre et 30 €/ha en janvier ; implantation en novembre, clôture au 31/01, 10 ha ; variante F → 1 500 € ; variante M2 avec la seule mécanisation du barème, plus les semences au coût réel.
- **Lot d'animaux** : 120 porcelets à l'ouverture, 300 naissances, 280 ventes et 4 morts donnent un effectif théorique de 136 ; 135 comptés signalent un écart d'une tête ; valeur = 135 × valeur par tête.
- **Vraisemblance** : un cours de 170 €/kg pour un porc charcutier est signalé (unité probablement en centimes), et 1,80 € ne l'est pas.
- **Valeur fiscale** :
  - forfaitaire : 100 t de blé au cours de 200 €/t donnent 16 000 € (−20 %) ; bovins −30 % ;
  - refusée sur les approvisionnements ;
  - écart exporté.
- **Dépréciation** : 39x repris puis doté.
- **Droits** :
  - micro-BA : écran masqué, API 404 ;
  - expert-comptable : lecture et export seulement.

### Reste à confirmer

- **Q-S5** (stock bloqué) : excédent sur la quantité de référence et ordre des sorties (proposition au § 6).
- **Main-d'œuvre de l'exploitant dans le coût standard** : le barème du guide suppose 100 % de salariés. Pour une exploitation sans salariés, faut-il imposer M2, ou retirer seulement la main-d'œuvre ?
