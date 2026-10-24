# Conception — Lot F : fiabilité comptable (validation, verrouillage, lettrage, CCA/PCA, immobilisations, reprise)

> Statut : **validée** (24/10/2026 : Q-F1 brouillard, Q-F2 année de 360 jours selon Ekylibre, Q-F3 réglage).
> **Lot F réalisé (F1 à F6, 24/10/2026).** F6 : import FEC sans fichier conservé côté serveur (le fichier est renvoyé à l'import, analyse sans effet) ; lettrage repris avec son code d'origine quand il est libre ; tableur : écritures en brouillard dans l'exercice ouvert de leur date. F5 : pas d'export tableur du registre ni de l'annexe (API JSON seulement) ; la sortie est refusée si les dotations de l'exercice sont déjà passées (les retirer d'abord) ; prix de cession par facture de vente : rattachement `sale_id` par l'API. F4 : période des lignes d'écriture saisissable par l'API seulement (pas encore dans le formulaire de saisie) ; avoirs non proposés. F3 : à-nouveaux détaillés ligne par ligne (y compris les lignes d'un lettrage partiel, sans regroupement), reste éventuel « non détaillé » ; codes partiels en minuscules ; comptes SCI de l'écart : 671 / 7718 (pas de 658 / 758 dans le plan SCI) ; liste des comptes : tous les comptes lettrables mouvementés, même entièrement lettrés. F2 : routes `/fiscal-years/<id>/period-lock` (`/lock` existait pour la comptabilité simplifiée) ; les écritures de l'assistant de clôture (`MANAGED_SOURCES`) échappent toujours au verrou (pas de contexte `closing`). Écarts : route de validation `POST /entries/validation` (`/entries/validate` existait : validation à blanc du formulaire) ; la réouverture d'une clôture provisoire annule le lot `closing` s'il est le dernier (les écritures validées avant la clôture le restent).
> Besoins : `claudedocs/besoins_comparatif_oss.md` § 3 (E2, E3, E1, E9, E8, E5) et décisions CO1–CO13.
> Suite : validation, puis `/sc:implement F1`.

## 1. Choix structurants

| # | Choix | Raison |
|---|---|---|
| F-C1 | **Une garde unique dans la session SQLAlchemy** (`before_flush`, module `app/services/ledger_guard.py`) refuse toute création, modification ou suppression interdite d'écriture ou de ligne : écriture validée, date verrouillée | Les écritures sont créées par `ledger.post_entry` seul, mais modifiées ou supprimées à une dizaine d'endroits (encaissements, règlements d'achat, mode simplifié, clôture, projets) : une garde au flush les couvre tous, même les futurs. Même principe que `_sync_status_and_lock` des exercices |
| F-C2 | **Validation par lots** (`validation_batches`) : chaque action « Valider » numérote à la suite, par journal et par exercice ; la dévalidation ne porte que sur le **dernier lot** | Numérotation continue sans trou ; les numéros déjà attribués ne changent jamais (critère « FEC identique avant / après la clôture provisoire ») |
| F-C3 | Correction d'une écriture validée = **contrepassation** ; les services qui régénèrent une écriture (facture d'achat modifiée, encaissement défait, écriture de règle remplacée) passent par `ledger.replace_entry` : mise à jour sur place si brouillard, **contrepassation + nouvelle écriture** si validée | L'utilisateur garde ses gestes habituels ; l'intangibilité est tenue en dessous |
| F-C4 | **Historique par instantanés** : après chaque flush qui touche une écriture, son état complet (en-tête + lignes) est enregistré (`entry_events`) ; l'écran montre la différence entre deux instantanés consécutifs | Pas besoin de reconstituer l'état « avant » ; capte aussi les chemins hors `ledger` |
| F-C5 | **Date de verrouillage par exercice** (`fiscal_years.locked_until`) ; la clôture provisoire la porte au dernier jour | Un seul repère, lu par la garde ; pas de périodes mensuelles (E9.4) |
| F-C6 | Pièces reçues dans une période verrouillée : **décalage automatique** à la première date ouverte (CO8) pour les écritures **automatiques** (synchronisations, règles, encaissements rapprochés) ; refus avec date proposée pour une **saisie** | Une synchronisation ne bloque jamais ; une saisie manuelle reste maîtrisée par l'utilisateur |
| F-C7 | **Lettrage** = table `letterings` + `journal_lines.lettering_id` ; colonne lettrable sur le compte ; les pièces de Lyvre (ventes, achats) se **relettrent par document** (fonction idempotente appelée après chaque encaissement / règlement) | Le lettrage suit les paiements existants sans nouveau geste ; idempotent = pas de dérive |
| F-C8 | **À-nouveaux détaillés** pour les comptes lettrables : une ligne AN par ligne (ou groupe partiel) non lettrée, reliée à sa ligne d'origine (`carried_from_line_id`) | Lettrage inter-exercices (E1.5) ; le relettrage par document suit la chaîne |
| F-C9 | **Rôles de comptes** (`account_roles` : rôle → compte) pour les comptes que Lyvre choisit seul (écart de lettrage, dotations, cessions, CCA / PCA…), valeurs par défaut par référentiel dans `data/account_roles.json`, modifiables par l'administrateur | N5 : pas de numéro codé en dur hors paramétrage ; l'expert-comptable valide une table, pas du code |
| F-C10 | Amortissements **calculés, pas stockés** (tableau recalculé) ; seules les **dotations passées** sont enregistrées et figées (`asset_depreciations`) ; le reste du plan se recalcule à partir d'elles | Comme Ekylibre (`planned_depreciations` recalculées, dotations comptabilisées verrouillées) |
| F-C11 | Méthodes et calendrier **repris d'Ekylibre** (`app/models/fixed_asset.rb`) : linéaire, dégressif (coefficient fiscal), non amortissable ; **année de 360 jours, mois de 30 jours** ; dotation d'un exercice = arrondi(base × jours cumulés / jours du plan) − cumul précédent | Usage fiscal (Q-F2) ; méthodes éprouvées dans Ekylibre ; somme des dotations = base exactement (N1) |
| F-C12 | Le mode simplifié n'a **ni validation ni lettrage** (pas de FEC) ; il a le **verrouillage** et le **registre** des immobilisations sans écritures | N2, CO13 (Q8-3) |

## 2. Données (base de l'instance)

Une migration par sous-lot (N4). Les vraies bases restent migrées avec accord, à la mise en production.

### 2.1 Validation et historique (F1)

**`validation_batches`**

| Colonne | Type | Rôle |
|---|---|---|
| `id` | PK | |
| `fiscal_year_id` | FK | |
| `kind` | String(12) | `manual` (sélection), `until` (jusqu'à une date), `closing` (clôture provisoire), `auto` (pièces émises), `lock` (verrouillage), `import`, `migration` |
| `until_date` | Date NULL | pour `until` / `lock` |
| `entries` | Integer | nombre d'écritures validées |
| `user_id` | Integer NULL | utilisateur de la méta-base |
| `at` | DateTime | |
| `undone_at`, `undone_by`, `undo_reason` | NULL | dévalidation (admin, motif) |

**`journal_entries`** (colonnes ajoutées) : `validation_batch_id` (FK NULL). `validation_number` et
`validated_at` existants gardent leur sens ; une écriture est **validée** si `validation_number` est
renseigné.

**`entry_events`**

| Colonne | Type | Rôle |
|---|---|---|
| `id` | PK | |
| `entry_id` | Integer NULL (pas de FK : survit à la suppression) | |
| `fiscal_year_id` | Integer | filtre |
| `reference` | String(50) | lisible après suppression |
| `action` | String(12) | `create`, `update`, `delete`, `validate`, `unvalidate`, `reverse` |
| `snapshot_json` | Text | en-tête + lignes (compte, libellé, débit, crédit, projet) après l'action ; dernier état pour `delete` |
| `user_id` | Integer NULL | `g.user` si requête, sinon NULL (tâche de fond : `source` de l'écriture) |
| `origin` | String(40) | point d'entrée (`api:entries.update`, `job:qonto_sync`, `service:sale_settlement`…) |
| `at` | DateTime | |

Pas d'instantané pour les seules modifications de colonnes « libres » (F-C1 : `project_id`,
`entity_id`, `lettering_id`).

### 2.2 Verrouillage (F2)

**`fiscal_years`** : `locked_until` (Date NULL), `lock_before_close` (Date NULL : date à rétablir si la
clôture provisoire est rouverte).

**`lock_events`** — non : les changements de date sont journalisés dans `closing_events` (étape
`lock`, action `advance` / `rewind`, motif), table existante.

### 2.3 Lettrage (F3)

**`accounts`** : `lettrable` (Boolean, défaut faux). Migration : vrai pour les comptes dont le code
commence par `40`, `41`, `42`, `43`, `441`, `45`, `467`, `468` (les comptes de TVA `445` ne sont pas
lettrables). Modifiable sur la fiche du compte (administrateur).

**`letterings`**

| Colonne | Type | Rôle |
|---|---|---|
| `id` | PK | |
| `account_id` | FK accounts | |
| `code` | String(4) | `A`…`Z`, `AA`…`ZZ`, `AAA`… ; unique par compte ; **minuscules** si partiel (convention FEC courante) |
| `partial` | Boolean | solde non nul |
| `balance_cents` | Integer | débit − crédit des lignes (0 si complet) |
| `lettered_on` | Date | `DateLet` du FEC (date de la dernière ligne) |
| `origin` | String(12) | `document` (vente / achat), `auto` (proposition acceptée), `manual`, `import`, `reversal` |
| `document_type`, `document_id` | NULL | `sale` / `purchase` pour le relettrage par document |
| `gap_entry_id` | FK NULL | écriture d'écart (E1.4) |
| `user_id`, `created_at` | | |

**`journal_lines`** (colonnes ajoutées) : `lettering_id` (FK NULL, index), `carried_from_line_id`
(FK NULL : ligne d'à-nouveau → ligne d'origine).

**`account_roles`** (F-C9, créée en F3, complétée ensuite) : `role` (PK, String), `account_id` (FK).
Rôles F3 : `lettering_gap_expense`, `lettering_gap_income`.

### 2.4 Charges et produits constatés d'avance (F4)

- `purchases.service_start`, `purchases.service_end` (Date NULL) ; `sales` les a déjà.
- `journal_lines.service_start`, `journal_lines.service_end` (Date NULL) pour une écriture saisie.
- `journal_entries.source_ref` des écritures d'inventaire proposées : `cca:purchase:<id>`,
  `pca:sale:<id>`, `cca:line:<id>` (évite les doublons ; la proposition déjà passée est grisée).
- Rôles : `prepaid_expense` (486), `deferred_income` (487) — aujourd'hui dans `INVENTORY_KINDS`.

### 2.5 Immobilisations (F5)

**`assets`**

| Colonne | Type | Rôle |
|---|---|---|
| `id` | PK | |
| `parent_id` | FK assets NULL | composant d'un bien (E8.2) ; le bien parent n'a pas de plan propre s'il a des composants |
| `label` | String(200) | |
| `account_id` | FK | compte 2x |
| `depreciation_account_id` | FK NULL | 28x (déduit du 2x : `28` + suite du code, sinon rôle) |
| `expense_account_id` | FK NULL | dotation (rôle `depreciation_expense`, 6811) |
| `acquired_on` | Date | date d'acquisition (point de départ du dégressif) |
| `in_service_date` | Date NULL | mise en service (point de départ du linéaire) ; vide = en cours |
| `acquisition_cents` | Integer | valeur d'origine HT (ou TTC si non assujetti) |
| `residual_cents` | Integer | valeur résiduelle (défaut 0) |
| `method` | String(10) | `linear`, `regressive` ou `none` (terrain, non amortissable) |
| `duration_months` | Integer NULL | affichée aussi en taux (100 / années) |
| `fiscal_coefficient` | Numeric NULL | dégressif : 1,25 (3-4 ans), 1,75 (5-6 ans), 2,25 (plus de 6 ans), proposé selon la durée |
| `waiting_account_id` | FK NULL | 23x tant que l'immobilisation est en cours |
| `prior_depreciation_cents`, `prior_as_of` | NULL | reprise d'un tableau existant (E8.3) |
| `project_id` | FK NULL | |
| `purchase_line_id` | FK NULL | pièce d'origine |
| `status` | String(10) | `waiting` (en cours, 23x), `in_use`, `depreciated`, `sold`, `scrapped` |
| `disposal_date`, `disposal_price_cents`, `disposal_entry_id`, `sale_id` | NULL | cession / rebut (E8.5) ; facture de vente de cession |
| `notes` | Text | |

**`asset_depreciations`** : `asset_id`, `fiscal_year_id`, `started_on`, `stopped_on`, `days` (base 360),
`amount_cents`, `entry_id` (écriture de dotation de l'exercice, source `DEPRECIATION`, gérée par
l'assistant) ; unique `(asset_id, fiscal_year_id)`. Une ligne par exercice (Lyvre n'a pas de périodes
mensuelles ; Ekylibre propose aussi mensuel et trimestriel).

Rôles : `depreciation_expense` (6811), `disposal_book_value` (675), `disposal_proceeds` (775),
`disposal_receivable` (462), `assets_in_progress` (23).

### 2.6 Reprise (F6)

- **`account_mappings`** : `source_code` (unique), `account_id` — correspondances mémorisées.
- **`import_profiles`** : `name`, `kind` (`csv`, `xlsx`), `columns_json` (colonne → champ), `options_json`
  (séparateur, format de date, décimales).
- **`journal_entries.source`** : `FEC_IMPORT`, `SHEET_IMPORT` ; `source_ref` = `EcritureNum` d'origine.

## 3. Règles

### 3.1 Garde (F-C1)

Au `before_flush`, pour chaque `JournalEntry` / `JournalLine` nouveau, modifié ou supprimé :

| Cas | Refus (`LedgerGuardError`, API 409) |
|---|---|
| Écriture **validée** (numéro déjà enregistré en base) modifiée ou supprimée | Sauf colonnes de validation dans un contexte de validation / dévalidation |
| Ligne d'une écriture validée ajoutée, supprimée ou modifiée | Sauf colonnes libres : `project_id`, `entity_id`, `lettering_id` |
| Date (ancienne **ou** nouvelle) ≤ `locked_until` de l'exercice | Sauf écritures de l'assistant de clôture (`MANAGED_SOURCES`) dans le contexte `closing` |
| Exercice clos (`closed`) | Comportement actuel conservé |

Contextes (`ledger_guard.context("closing" | "validation" | "import")`, `contextvars`) : seuls les
services concernés les ouvrent ; aucune route ne les expose. Codes d'erreur API : `entry_validated`,
`period_locked` (avec `first_open_date`).

Conséquences sur l'existant :

- `projects.split_line` est **refusé** sur une écriture validée (il change les lignes, donc le FEC) ;
  l'affectation d'un projet reste possible. La ventilation sans toucher aux lignes viendra avec
  l'analytique multi-axes (E10, lot V). → point d'attention § 9.
- `sale_settlement` (« Défaire »), `purchase_settlement` (remplacement d'une écriture de règle),
  `purchase_posting` (facture modifiée), `simple_operations` (mode simplifié : jamais validé) passent
  par `ledger.replace_entry` / `ledger.remove_entry` (F-C3).
- `closing.reopen` ne dévalide plus : il rétablit `locked_until` à `lock_before_close` ; les écritures
  validées le restent (dévalider = action séparée, § 3.2). `generate_opening` refuse de regénérer des
  à-nouveaux **validés** ou **verrouillés** (message : dévalider le dernier lot ou déverrouiller).

### 3.2 Validation (E2)

- **Numérotation** : `next = max(validation_number du journal dans l'exercice) + 1`, attribuée dans l'ordre
  `(entry_date, id)` des écritures du lot. `fec.validate` devient « valider ce qui reste » (lot `closing`)
  et ne renumérote plus rien ; `fec.build` ne renumérote plus.
- **Valider** : une écriture, une sélection, « tout jusqu'au JJ/MM/AAAA » (trésorier, administrateur).
  Refus si une écriture du lot est déséquilibrée ou hors exercice (liste).
- **Pièces émises (CO7)** : `sale_issue` valide l'écriture de la facture / de l'avoir dans la même
  transaction (lot `auto`, un lot par jour et par exercice pour ne pas multiplier les lots). Les
  encaissements restent en brouillard (défaisables) jusqu'à validation.
- **Dévalider** : administrateur, motif obligatoire, **dernier lot non annulé** de l'exercice seulement ;
  refusé si l'exercice est clos définitivement, si une ligne du lot est lettrée avec une ligne
  validée hors du lot (délettrer d'abord), ou si une date du lot est verrouillée.
- **Contrepasser** (`ledger.reverse(entry, on_date, reason)`) : écriture inverse au journal d'origine,
  libellé « Contrepassation de <réf.> — motif », `reverses_entry_id`, datée du jour (ou date choisie
  non verrouillée, exercice ouvert). Effets :
  - ligne bancaire rapprochée : la transaction est **dérapprochée** (redevient à rapprocher) ;
    l'écriture d'origine et sa contrepassation sont exclues des propositions de rapprochement ;
  - lignes lettrées : délettrées, puis chaque ligne d'origine lettrée avec sa ligne inverse
    (`origin = reversal`) sur les comptes lettrables ;
  - document lié (achat) : l'écriture du document est remise à vide ; le document repasse
    « à comptabiliser » ; les ventes émises se corrigent par **avoir** (contrepassation refusée, message
    actuel `SALE_LOCKED_MESSAGE`).
- **Rappel** (E2.6) : tableau de bord et contrôles de clôture affichent le nombre d'écritures en
  brouillard, et celles de plus de 3 mois (CO13, Q2-2).

### 3.3 Verrouillage (E3)

- **Avancer** `locked_until` : trésorier ou administrateur ; la fenêtre de confirmation liste les
  écritures en brouillard ≤ date, qui sont **validées** dans le même geste (lot `lock`) ; refus si l'une
  est déséquilibrée.
- **Reculer** : administrateur, motif, journalisé (`closing_events`). Ne dévalide rien.
- Clôture provisoire : `lock_before_close = locked_until`, puis `locked_until = end_date`.
- **Décalage automatique (CO8)** : `ledger.post_entry(..., auto_date=True)` pour les sources
  automatiques (Qonto, OFX + règles, encaissements et règlements rapprochés, échéances préparées) :
  si la date est verrouillée, `entry_date = locked_until + 1 jour` (exercice suivant si besoin),
  description préfixée « [pièce du JJ/MM/AAAA] ». Aucun exercice ouvert après la date : l'erreur
  remonte dans le résumé de la synchronisation (notification), la pièce reste « à comptabiliser ».
- Saisie, encaissement à la main, modification : refus `period_locked` avec `first_open_date` ;
  l'écran propose la date.

### 3.4 Lettrage (E1)

- **Lettrer** un ensemble de lignes d'un même compte lettrable : solde nul → complet (code majuscule,
  `lettered_on` = date de la dernière ligne) ; solde non nul → **partiel** (code minuscule) ;
  |solde| ≤ seuil (réglage `organization.lettering_gap_cents`, 1 € par défaut) → proposition d'**écart** : écriture OD (rôles `lettering_gap_expense` / `_income`), ligne d'écart
  incluse, lettrage complet.
- **Délettrer** : supprime le lettrage (et contrepasse l'écriture d'écart si validée, sinon la
  supprime).
- **Par document** (`lettering.sync_sale(sale)`, `sync_purchase(purchase)`) : lignes 411 / 401 de
  l'écriture de la pièce (ou leurs lignes d'à-nouveau, via `carried_from_line_id`) + lignes de
  tiers des écritures d'encaissement / de règlement + avoirs liés ; relettrage complet ou partiel.
  Appelée par `sale_settlement`, `purchase_settlement`, `sale_issue` (avoir), et à la reprise (E1.8).
- **Propositions** sur un compte : (1) même montant opposé et même référence de pièce, (2) même
  montant opposé et même tiers, dates les plus proches, (3) combinaisons de 2 à 4 lignes du même
  tiers dont la somme est nulle (bornée à 200 lignes non lettrées, 2 s maximum).
- **À-nouveaux (F-C8)** : pour chaque compte lettrable, une ligne AN par ligne non lettrée (montant,
  libellé et tiers d'origine, `carried_from_line_id`) et une ligne par lettrage **partiel** (solde du
  groupe) ; les autres comptes gardent un solde global. Les lignes d'origine lettrées ne sont pas
  reprises. Le FEC de N+1 remplit `CompAuxNum` pour ces lignes.
- **FEC** : `EcritureLet` = code, `DateLet` = `lettered_on` ; `TIERS_PREFIXES` étendu aux comptes
  lettrables rattachés à un tiers (`entities.account_code`).
- Validation : le lettrage n'est pas une modification de l'écriture (colonne libre) ; une ligne
  validée se lettre et se délettre (E2.7).

### 3.5 Charges et produits constatés d'avance (E9)

À l'étape « inventaire » de la clôture, bloc **Propositions** :

- sources : factures d'achat comptabilisées (période du document, sinon période de l'**abonnement**
  rattaché : échéance → échéance suivante − 1 jour), factures de vente émises (`service_start` /
  `service_end`), lignes d'écriture de classe 6 / 7 avec période ;
- montant = arrondi(montant HT de la charge ou du produit × jours après `end_date` ∩ période / jours de
  la période), par compte de charge / produit ;
- l'utilisateur coche, corrige le montant, puis « Passer les écritures » : `closing.add_inventory`
  existant (kind `prepaid_expense` / `deferred_income`, `source_ref` du document) ; l'extourne au
  1er jour de N+1 existe déjà.
- Exemple de contrôle : 1 200 € du 01/07 au 30/06, clôture au 31/12 → 1 200 × 181 / 365 = 595,07 €.

### 3.6 Immobilisations (E8)

Méthodes et calendrier repris d'**Ekylibre** (`FixedAsset#depreciate!`, `FixedAsset.duration`).

- **Jours (base 360)** : chaque mois compte 30 jours ; un jour 31, ou le dernier jour du mois, compte
  pour 30. Durée entre deux dates (incluses) : `30 − jour_début + 1` + 30 par mois plein + `jour_fin`
  (même mois : `jour_fin − jour_début + 1`). Le plan couvre `durée en mois × 30` jours.
- **Linéaire** : départ à la **mise en service** ; dotation de l'exercice = arrondi(base × jours 360
  cumulés jusqu'à la fin de l'exercice / jours 360 du plan) − cumul antérieur (dont
  `prior_depreciation_cents`). La dernière dotation solde exactement la base.
- **Dégressif** : départ au **1er jour du mois d'acquisition** ; taux = (100 / années) × coefficient
  fiscal ; chaque exercice : restant × max(taux dégressif, taux linéaire sur les années restantes) ×
  jours 360 de l'exercice / 360, plafonné au restant (bascule automatique en linéaire quand il
  devient plus fort, comme Ekylibre). Proposé seulement si l'exercice est **soumis à la TVA ou à
  l'impôt** (association fiscalisée) ; sinon masqué (CO13).
- **Non amortissable** (`none`) : terrain, œuvre d'art, immobilisation financière.
- **Composants** (E8.2) : un bien (immeuble de la SCI) a des composants (terrain `none`, gros œuvre,
  toiture, installations…) avec leur propre méthode et durée ; le bien est la somme de ses composants.
- **En cours** (`waiting`, 23x) : travaux ou bien non encore utilisé ; pas de dotation ; la **mise en
  service** passe 23x → 2x (écriture OD) et ouvre le plan.
- **Création** : depuis une ligne de facture d'achat au compte 2x ou 23x (bouton « Créer
  l'immobilisation », proposé à la comptabilisation), à la main, ou par reprise (cumul à une date).
- **Dotations** : sous-étape de l'inventaire « Amortissements » : tableau des dotations de l'exercice,
  « Passer » = une écriture OD (source `DEPRECIATION`, ajoutée à `MANAGED_SOURCES`), une ligne par
  composant (6811 / 28x), projet de l'immobilisation ; regénérée tant que l'exercice est ouvert. Les
  dotations passées sont figées (F-C10) : modifier la base ou la durée recalcule seulement la suite
  du plan (révision du plan, comme Ekylibre).
- **Cession / rebut** (comme le `FixedAssetBookkeeper` d'Ekylibre) : dotation complémentaire jusqu'à
  la date de sortie, puis écriture de sortie : 2x au crédit (valeur d'origine), 28x au débit (cumul),
  675 au débit (valeur nette comptable). **Prix de cession** : par une **facture de vente** de Lyvre
  (ligne au 775, `sale_id`), ou, vendu hors Lyvre, écriture 462 / 775. Comptes par rôle.
- **États** : registre (filtre état, compte, projet), tableau de l'annexe (valeurs brutes et
  amortissements : début, augmentations, diminutions, fin), tableau d'amortissement d'une fiche ;
  exports XLSX (`app/views/exports.py`).
- **Mode simplifié** : registre et tableau, sans dotations ni écritures.
- **SCI à l'IR** (Q8-4) : option `organization.depreciation_enabled` (défaut **vrai** pour une
  association, **faux** pour une SCI) ; faux = registre seul, comme le mode simplifié.
- Contrôles (tests) : mise en service le 15/03, 5 ans, clôture au 31/12 → 1re dotation = base × 286 /
  1 800 ; somme des dotations = base ; dégressif 5 ans (coefficient 1,75) : 35 % puis bascule en
  linéaire la 4e année.

### 3.7 Reprise (E5)

- **Import FEC** (assistant en 3 temps, comme l'import des associés) :
  1. **Lecture** : séparateur tabulation ou `|`, encodage UTF-8 / ISO-8859-15 / Windows-1252 détecté,
     18 colonnes (montants `Debit`/`Credit` ou `Montant`/`Sens`), contrôles (équilibre par
     `EcritureNum`, dates dans l'exercice) ;
  2. **Correspondances** : comptes absents → créer (rattaché à sa classe, `lettrable` selon le
     préfixe) ou correspondre (`account_mappings`) ; journaux absents → créer ; tiers par
     `CompAuxNum` / `CompAuxLib` → entité retrouvée (code de compte, nom) ou créée ;
  3. **Import tout-ou-rien**, deux modes :
     - **historique** : exercice créé s'il manque, écritures importées (source `FEC_IMPORT`,
       `source_ref` = `EcritureNum`), validées (lot `import`), lettrages repris (`EcritureLet`),
       exercice **clôturé provisoirement** avec `locked_until = end_date` ; à-nouveaux de N+1
       générés par l'assistant habituel ;
     - **soldes d'ouverture** : seules les classes 1 à 5 au dernier jour sont reprises en à-nouveaux
       du premier exercice Lyvre, détaillées par ligne non lettrée pour les comptes lettrables.
- **Import tableur** (CSV / XLSX) : colonnes associées une fois (profil mémorisé), regroupement en
  écritures par numéro de pièce (ou date + libellé), mêmes contrôles et même tout-ou-rien ; écritures
  en brouillard.
- Critère : FEC exporté par Lyvre → import historique dans une base vide → balance et états
  identiques (test automatisé sur la base E2E).

## 4. Services (backend)

| Module | Rôle |
|---|---|
| `ledger_guard.py` (F1) | Garde `before_flush`, contextes, `LedgerGuardError`, instantanés `after_flush` → `entry_events` |
| `ledger.py` (F1, F2) | `replace_entry`, `remove_entry`, `reverse`, `post_entry(auto_date=)`, `first_open_date(fy)` |
| `validation.py` (F1) | `validate(entries|until, kind)`, `undo_last_batch(fy, reason)`, `draft_counts(fy)` ; `fec.validate` délègue |
| `period_lock.py` (F2) | `advance(fy, date)`, `rewind(fy, date, reason)`, aperçu des brouillards à valider |
| `lettering.py` (F3) | `letter(lines)`, `unletter(lettering)`, `proposals(account)`, `sync_sale`, `sync_purchase`, `reprise()`, `next_code(account)` |
| `account_roles.py` (F3) | `account_for(role)`, défauts par référentiel (`data/account_roles.json`), écran de réglage |
| `prepaid.py` (F4) | `proposals(fy)`, `post(fy, selection)` |
| `assets.py` (F5) | `schedule(asset)`, `depreciation_lines(fy)`, `post_depreciation(fy)`, `dispose(asset, …)`, `register()`, `annex_table(fy)` |
| `fec_import.py`, `sheet_import.py` (F6) | lecture, analyse, correspondances, import |

Modifiés : `fec.py` (validation non renumérotante, lettrage, AN détaillés), `closing.py` (verrou,
propositions CCA/PCA, dotations, AN détaillés, réouverture), `sale_issue.py`, `sale_settlement.py`,
`purchase_posting.py`, `purchase_settlement.py`, `simple_operations.py`, `projects.py`, `rules_engine.py`
(auto_date), `qonto_sync.py` / `purchase_sync.py` (auto_date, erreurs dans le résumé).

## 5. API (préfixe `/api/v1`)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/entries/validate` | `{ids}` ou `{fiscal_year_id, until}` → lot |
| GET | `/fiscal-years/<id>/validation-batches` | lots (dernier annulable) |
| POST | `/fiscal-years/<id>/validation-batches/last/undo` | admin, `{reason}` |
| POST | `/entries/<id>/reverse` | `{date, reason}` |
| GET | `/entries/<id>/history` | instantanés et différences |
| GET / POST | `/fiscal-years/<id>/lock` | état, aperçu ; `{until}` avancer ; `{until, reason}` reculer (admin) |
| GET | `/lettering/accounts` | comptes lettrables avec solde non lettré |
| GET | `/lettering/accounts/<account_id>/lines` | `?state=open|lettered|all&entity=` |
| POST | `/lettering` | `{line_ids, gap: bool}` |
| DELETE | `/lettering/<id>` | délettrer |
| GET | `/lettering/accounts/<account_id>/proposals` | propositions |
| GET / PUT | `/account-roles` | rôles de comptes (admin) |
| GET / POST | `/fiscal-years/<id>/closing/prepaid` | propositions CCA/PCA ; passer la sélection |
| GET / POST | `/assets`, `/assets/<id>` (GET, PATCH, DELETE) | fiches (suppression si aucune dotation) |
| GET | `/assets/<id>/schedule` | tableau d'amortissement |
| POST | `/assets/<id>/dispose` | `{date, price, kind}` |
| POST | `/purchases/<id>/lines/<line_id>/asset` | créer depuis une ligne d'achat |
| GET / POST | `/fiscal-years/<id>/closing/depreciation` | dotations de l'exercice ; passer |
| GET | `/assets/register`, `/fiscal-years/<id>/assets/annex` | états (+ XLSX par `exports`) |
| POST | `/imports/fec/analyze`, `/imports/fec` | analyse ; import `{mode, mappings}` |
| POST | `/imports/sheet/analyze`, `/imports/sheet` | idem, avec profil |
| GET / PUT | `/account-mappings`, `/import-profiles` | correspondances et profils mémorisés |

Droits : l'expert-comptable consulte tout (historique, lots, lettrage, registre) ; dévalider, reculer le
verrou, rôles de comptes, imports : **administrateur de la structure** (N3) ; le reste : trésorier.

## 6. Écrans (SPA)

- **Écritures** : colonne « État » (Brouillard / n° de validation), filtre, sélection → « Valider (n) »,
  bouton « Valider jusqu'au… » ; fiche : badge validée, boutons Modifier / Supprimer masqués,
  « Contrepasser » (fenêtre date + motif), onglet **Historique** (différences colorées).
- **Exercices** : date de verrouillage, « Verrouiller jusqu'au… » (aperçu des brouillards validés),
  « Déverrouiller » (admin, motif) ; lots de validation avec « Annuler le dernier lot » (admin).
- **Saisie / encaissement** : message `period_locked` avec « Utiliser le JJ/MM » (première date ouverte).
- **Compta › Lettrage** (`/lettering/`) : liste des comptes lettrables (solde non lettré), écran d'un
  compte dans l'esprit du rapprochement : lignes non lettrées, sélection au clavier (Espace), total
  sélectionné en direct, « Lettrer » (Entrée), propositions à accepter, onglet Lettrées (délettrer).
- **Fiche d'un tiers** : solde non lettré par compte, lien vers son lettrage.
- **Clôture › Inventaire** : blocs « Propositions de charges / produits constatés d'avance » et
  « Amortissements » (tableau, Passer / Recalculer).
- **Compta › Immobilisations** (`/assets/`) : registre, fiche (composants, tableau d'amortissement,
  cession), bouton depuis une facture d'achat.
- **Imports › Reprise FEC / tableur** : assistant 3 étapes (lecture, correspondances, import).
- **Configuration › Comptes par défaut** : rôles de comptes (admin).
- **Tableau de bord** : écritures en brouillard de plus de 3 mois (trésorier).

## 7. Sous-lots

| Lot | Contenu | Migration | Dépend de |
|---|---|---|---|
| **F1** | Garde, lots de validation, numérotation non renumérotante, historique, contrepassation, `replace_entry` dans les services, validation d'office des ventes, écrans Écritures / Exercices ; reprise : lot `migration` (écritures déjà numérotées, écritures VE émises) | `validation_batches`, `entry_events`, `journal_entries.validation_batch_id` | — |
| **F2** | Verrouillage, décalage automatique, messages et écrans | `fiscal_years.locked_until`, `lock_before_close` | F1 |
| **F3** | Lettrage (manuel, propositions, écart, par document, reprise), AN détaillés, FEC, rôles de comptes | `accounts.lettrable`, `letterings`, `journal_lines.lettering_id`, `carried_from_line_id`, `account_roles`, `organization.lettering_gap_cents` | F1 |
| **F4** | Propositions CCA / PCA | `purchases.service_*`, `journal_lines.service_*` | F2 |
| **F5** | Immobilisations, dotations, cessions, états | `assets`, `asset_depreciations`, `organization.depreciation_enabled` | F1, F3 (rôles) |
| **F6** | Import FEC (historique, soldes) et tableur | `account_mappings`, `import_profiles` | F1, F3 |

Indépendant, quand les identifiants du bac à sable SuperPDP seront disponibles : **validation Factur-X**
(E29.1b) — intégration SuperPDP minimale (OAuth2 identifiants client, sonde, `POST /validation_reports`),
bouton « Vérifier » sur une facture émise, test d'intégration marqué (désactivé sans identifiants).

## 8. Tests

- Garde : chaque chemin d'écriture existant (saisie, règle, encaissement / défaire, règlement d'achat,
  remplacement d'écriture de règle, mode simplifié, projets, clôture, associés, caisse) tenté sur une
  écriture validée puis dans une période verrouillée → 409 ou contrepassation attendue ; test
  « toutes les routes » comme celui des droits de l'expert-comptable.
- Numérotation : validations successives + clôture provisoire → numéros inchangés ; FEC identique
  avant / après ; dévalidation du dernier lot seulement.
- Contrepassation d'une écriture rapprochée : transaction à rapprocher, aucun orphelin.
- Lettrage : loyer encaissé par virement rapproché → lettré sans action ; facture de décembre impayée,
  clôture, à-nouveaux, encaissement en janvier → lettrée ; écart de 0,40 € ; FEC `EcritureLet`/`DateLet`.
- CCA : 181 / 365 ; abonnement annuel rattaché.
- Amortissements (base 360) : mise en service le 15/03, 5 ans → 286 / 1 800 la 1re année, somme = base ;
  dégressif avec bascule ; composants ; en cours puis mise en service ; cession par facture de vente.
- Reprise : aller-retour FEC (export → import historique → même balance, mêmes états).
- E2E : un parcours par sous-lot (valider puis contrepasser ; verrouiller ; lettrer ; CCA à la clôture ;
  immobilisation ; import FEC).

## 9. Risques et points d'attention

| Risque | Parade |
|---|---|
| Une garde au flush peut casser un chemin oublié (tâche de fond qui échoue) | Test « tous les chemins » (§ 8) ; erreurs de la garde remontées dans le résumé des synchronisations ; F1 livré avant tout le reste |
| Ventilation par projet refusée sur une écriture validée | Assumé jusqu'à l'analytique multi-axes (E10) qui sortira la ventilation des lignes ; message clair (« ventilez avant de valider ») |
| Volume de `entry_events` (synchronisations) | Instantané seulement si l'écriture change ; purge non prévue (quelques Mo par an) |
| Propositions de lettrage par combinaisons coûteuses | Bornées (§ 3.4) |
| Données réelles : écritures déjà numérotées (SN 2025) | Migration : un lot `migration` par exercice numéroté ; les numéros existants ne changent pas |
| Comptes par défaut (écart, 675 / 775 / 462, 6811) | Table de rôles relue par l'expert-comptable avant la mise en production |

## 10. Questions — réponses du 24/10/2026

| # | Question | Réponse |
|---|---|---|
| Q-F1 | Encaissements et règlements créés par Lyvre | **Brouillard** (défaisables tant que non validés ni verrouillés) |
| Q-F2 | Prorata temporis | **Année de 360 jours**, méthodes d'Ekylibre (linéaire, dégressif, non amortissable ; § 3.6) |
| Q-F3 | Seuil d'écart de lettrage | **Réglage** de la structure, 1 € par défaut |
