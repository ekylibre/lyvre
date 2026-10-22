# Design — Obligations associatives : clôture, FEC, rôles, budget et projets, reçus fiscaux, comptabilité simplifiée

> Statut : **proposé** (2026-10-22), à valider. Besoins : [`besoins_obligations_associatives.md`](besoins_obligations_associatives.md)
> (OA1–OA14, FA1–FA9, FB1–FB7, FC1–FC6, FD1–FD6). Ordre des lots : **A → C → B → D** (OA5).
> Cadre technique inchangé : Flask + SQLAlchemy multi-tenant, API `/api/v1`, SPA React + Mantine,
> PDF et fichiers servis par Flask, tâches longues par `sync_jobs` + notifications.

## 1. Constats sur l'existant (à corriger ou à respecter)

| # | Constat | Conséquence pour le design |
|---|---|---|
| C1 | `fiscal_years.closed` est un simple verrou ; `ledger` refuse toute mutation d'un exercice `closed` | Garder ce contrôle central, l'étendre à un statut (D3) |
| C2 | Les états (`reports._sum_accounts`) filtrent par `fiscal_year_id` : **le bilan d'un exercice N+1 n'a aujourd'hui aucun solde d'ouverture** | Les à-nouveaux (D8) corrigent ce manque ; aucun calcul cumulatif à défaire |
| C3 | `journal_entries.reference` (« BQ-2026-0012 ») est attribuée à la création, dans l'ordre de saisie, avec des trous possibles après suppression | Numérotation FEC distincte, attribuée à la validation (D5) |
| C4 | Pas de lettrage des tiers ; rapprochement bancaire = lien transaction ↔ ligne | FEC : `EcritureLet` / `DateLet` vides (autorisé) |
| C5 | `users.is_admin` global ; tout utilisateur voit toutes les instances actives et peut clôturer | Rôles par instance (D1, D2) |
| C6 | `entities` sans adresse ni distinction personne physique / morale | Colonnes d'adresse et de nature (D17) |
| C7 | `bank_accounts` = comptes bancaires seulement (OFX / Qonto) | Nature `bank` / `cash` (D22) |
| C8 | Le tableau de bord calcule le solde bancaire depuis `bank_transactions` (pas les écritures) | Insensible aux à-nouveaux |
| C9 | Le rapprochement propose des lignes du compte 512 de même montant à ±3 jours | Exclure les écritures d'ouverture, de clôture et d'extourne des suggestions (D8) |
| C10 | Tous les comptes nécessaires existent dans le plan asso (19x, 689x, 789x, 53x, 58x, 754x, 110/119/120/129/106, 408/418/468x, 486/487) | Pas de reprise du plan ; plan SCI : vérifier 455 (associés), 53, 58 |

## 2. Décisions de design

| # | Décision |
|---|---|
| **D1** | **Rôles par instance** dans la méta-base : table `instance_memberships(user_id, instance_id, role)`, rôles `admin`, `treasurer`, `accountant`. `users.is_admin` reste l'**administrateur global** (utilisateurs, instances) et vaut `admin` sur toutes les instances. |
| **D2** | **Contrôle côté serveur, une seule règle** : le hook tenant pose `g.instance_role` (403 / choix d'instance si aucun accès) ; un `before_request` de l'API refuse toute écriture (`POST/PUT/PATCH/DELETE`) au rôle `accountant` sauf une liste blanche (préférences, notifications lues, session). Décorateur `instance_admin_required` pour les fonctions d'administration d'instance (intégrations, accès, clôture définitive, réouverture, paramètres des reçus). Le front masque les actions (`useCan`), le serveur fait foi. |
| **D3** | **Statut d'exercice** `fiscal_years.status` ∈ `open` / `provisional` / `closed` (+ `provisional_at`, `closed_at`, `closed_by_user_id`). La colonne `closed` est conservée et tenue à jour (`status != 'open'`) pour que tous les contrôles existants (C1) restent valables. |
| **D4** | **Assistant de clôture** = service `closing` + table `closing_steps(fiscal_year_id, step, state, note, user_id, updated_at)` ; états `todo` / `done` / `skipped` (ignorée avec motif obligatoire). Les contrôles sont **recalculés à chaque affichage** (jamais mis en cache) ; seule la décision de l'utilisateur est stockée. Journal d'audit `closing_events`. |
| **D5** | **Validation et numérotation FEC** : à la clôture provisoire, chaque écriture de l'exercice reçoit `validation_number` (séquence continue **par journal et par exercice**, ordre `entry_date`, `id`) et `validated_at`. Réouverture d'une clôture provisoire : numéros effacés puis réattribués à la clôture suivante. `reference` reste le numéro affiché à l'écran et devient `PieceRef` dans le FEC. |
| **D6** | **FEC** généré par le service `fec` (pas de stockage tant que provisoire) ; à la clôture définitive, le fichier est **figé** dans `instance/uploads/<slug>/fec/` avec son empreinte SHA-256 (`fiscal_years.fec_sha256`). Disponible seulement en partie double (OA14). |
| **D7** | **Écritures d'inventaire** saisies par l'assistant : `source='INVENTORY'`, journal `OD`, datées du dernier jour de N, avec un **type** (`accrued_expense` 408/4686, `accrued_income` 418/4687, `prepaid_expense` 486, `deferred_income` 487). L'**extourne** est générée dans N+1 (1er jour, `source='REVERSAL'`, `reverses_entry_id`). |
| **D8** | **À-nouveaux** : une écriture par exercice N+1, journal **`AN`** (créé au besoin), `source='OPENING'`, datée du 1er jour de N+1 : soldes de tous les comptes de **bilan** (classes 1 à 5) de N, résultat porté sur **120 / 129** en attente d'affectation. Regénérée (suppression + recréation) tant que N+1 n'est pas clôturé et que N repasse en `provisional`. Les sources `OPENING`, `REVERSAL`, `ALLOCATION`, `CLOSING` sont **exclues des suggestions de rapprochement** (C9). |
| **D9** | **Affectation du résultat** : écriture `source='ALLOCATION'` dans N+1 (journal `OD`, date de la décision), solde 120/129 vers 110 / 119 / 106 / fonds associatifs (asso) ou **455x comptes des associés** / 106 / 110 / 119 (SCI) ; organe (`AG` / `assemblée des associés`) et date stockés dans `fiscal_years.allocation_decided_on` / `allocation_body`. |
| **D10** | **Fonds dédiés** (lot A, minimal) : tables `dedicated_funds` (ressource affectée) et `dedicated_fund_movements` (dotation 689x / 19x, utilisation 19x / 789x par exercice, écriture liée). Rattachement à un projet ajouté au lot C (`project_id`). |
| **D11** | **Identité de la structure** dans la base de l'instance : table à une ligne `organization` (raison sociale, SIREN, RNA, adresse, objet, signataire). Utilisée par le FEC (nom du fichier), les reçus, les états. Sauvegardée avec l'instance. |
| **D12** | **Axe analytique unique** (OA11) : table `projects` ; `project_id` nullable sur `journal_lines`, `purchase_lines`, `rules`. La ventilation d'un montant sur plusieurs projets **découpe la ligne** en plusieurs lignes de même compte (aucune table de répartition, le FEC et les états restent inchangés). |
| **D13** | **Budget** : `budget_lines(fiscal_year_id, account_id, project_id, month, amount_cents)` ; `account_id` peut désigner un compte de regroupement (60, 64…) : le réalisé se calcule par préfixe. `month` NULL = montant annuel réparti par douzièmes à l'affichage. |
| **D14** | **Prévisionnel** calculé à la demande (12 mois glissants, OA12), sans stockage : soldes actuels banques + caisses, échéances des factures d'achat et clients non réglées, budget restant à réaliser du mois, saisies manuelles `cash_forecast_items` (avec récurrence mensuelle optionnelle). |
| **D15** | **Reçus fiscaux fondés sur la comptabilité** : un reçu agrège des **lignes d'écriture** de comptes de dons (paramétrables, défaut 7541) **avec tiers**, plus des **dons en nature** saisis à part (valorisation). Pas de source HelloAsso directe : un don HelloAsso doit être comptabilisé (évite double émission et incohérence avec les comptes). |
| **D16** | **Numérotation des reçus** : `donation_receipts.number` = `AAAA-NNNNN` via une table de compteurs `receipt_counters(year, last_number)` incrémentée dans la transaction d'émission ; jamais réutilisé, jamais supprimé ; annulation = statut `cancelled` + motif (+ remplaçant éventuel). |
| **D17** | **Tiers** : colonnes `address_line1`, `address_line2`, `postal_code`, `city`, `country`, `person_kind` (`individual` / `company`) sur `entities` ; obligatoires au moment d'émettre un reçu (contrôle à l'émission, pas à la saisie). |
| **D18** | **PDF des reçus** par weasyprint (gabarits serveur, comme le rapport d'activité) : modèle particuliers (CERFA n° 11580 en vigueur) et modèle entreprises (CERFA en vigueur, n° 16216 à vérifier) ; PDF figé à l'émission dans `instance/uploads/<slug>/recus/AAAA/`. Génération en lot et envoi par email = **job** `sync_jobs` (kind `donation_receipts`) avec notification de fin. |
| **D19** | **Mode de tenue** par instance dans la méta-base : `instances.bookkeeping` ∈ `double` / `simple` (défaut `double`), à côté de `chart` ; pilote menus et fonctions comme le plan comptable. `simple` n'est proposé qu'avec le plan asso. |
| **D20** | **Comptabilité simplifiée = écritures en partie double générées** : une recette ou dépense saisie crée une `journal_entry` à deux lignes (trésorerie 512x / 53x ↔ compte de la catégorie), `source='SIMPLE'`. Le passage en partie double (FD5) consiste à changer `bookkeeping` : **aucune reprise de données**. |
| **D21** | **Catégories** du mode simplifié : table `simple_categories(code, label, kind income/expense, account_id, position, active)`, pré-remplie depuis le plan asso (cotisations 756, dons 7541, subventions 74, ventes 70, achats 60, services 61/62, salaires 64…), modifiable. |
| **D22** | **Caisse** (OA14, les deux modes) : `bank_accounts.kind` ∈ `bank` / `cash` ; une caisse a un compte 53x, pas d'IBAN / Qonto / OFX ; mouvements saisis à la main. **Dépôt d'espèces** = virement interne par **581** (deux écritures, comme le PCG) pour ne pas compter de recette ni de dépense. |

## 3. Modèle de données

### 3.1 Méta-base (`seed_meta`, ALTER idempotents comme `_ensure_column`)

```
instance_memberships
  id PK · user_id FK users · instance_id FK instances · role (admin|treasurer|accountant)
  created_at · created_by_user_id
  UNIQUE(user_id, instance_id)

instances + bookkeeping VARCHAR(10) NOT NULL DEFAULT 'double'
```

Reprise (une fois, idempotente) : pour chaque utilisateur actif × instance active sans
membership : `admin` si `users.is_admin`, sinon `treasurer` (personne ne perd d'accès).

### 3.2 Base de chaque instance (migration Alembic, lot par lot)

Lot A :
```
organization (1 ligne) : name · siren · rna · address_line1/2 · postal_code · city · country
                         purpose (objet) · signatory_name · signatory_title · signature_path · updated_at
fiscal_years + status (open|provisional|closed) · provisional_at · closed_at · closed_by_user_id
             + fec_sha256 · fec_path · allocation_decided_on · allocation_body
             (reprise : closed=True → status='provisional', voir §8)
journal_entries + validation_number INT NULL · validated_at DATETIME NULL
                + reverses_entry_id FK journal_entries NULL · inventory_kind VARCHAR(20) NULL
                INDEX(fiscal_year_id, journal_id, validation_number)
closing_steps : fiscal_year_id FK · step (VARCHAR) · state (todo|done|skipped) · note · user_id · updated_at
                UNIQUE(fiscal_year_id, step)
closing_events : fiscal_year_id · step · action · user_id · at · details_json
dedicated_funds : label · resource_account_id FK accounts · entity_id NULL (financeur)
                  origin_fiscal_year_id · amount_cents · project_id NULL (lot C) · created_at
dedicated_fund_movements : fund_id · fiscal_year_id · kind (allocation|use) · amount_cents · entry_id FK
journals : ajout du journal AN (« À-nouveaux ») à la première ouverture
```

Lot C :
```
projects : name UNIQUE · description · start_date · end_date · manager · archived · created_at
journal_lines + project_id FK NULL · purchase_lines + project_id · rules + project_id
budget_lines : fiscal_year_id · account_id · project_id NULL · month NULL|1..12 · amount_cents
               UNIQUE(fiscal_year_id, account_id, project_id, month)
cash_forecast_items : date · label · amount_cents · bank_account_id NULL · repeat_monthly_until NULL
```

Lot B :
```
entities + address_line1/2 · postal_code · city · country · person_kind (individual|company)
receipt_settings (1 ligne) : enabled · eligibility (general_interest|public_utility|other)
                 · eligibility_detail · rescrit_ref · cgi_articles (200|238bis|978, JSON)
                 · donation_account_prefixes (JSON, défaut ["7541"]) · default_mode (annual)
receipt_counters : year PK · last_number
donation_receipts : number UNIQUE · year · entity_id · person_kind · mode (annual|single)
                    · total_cents · status (issued|cancelled) · cancel_reason · replaced_by_id
                    · pdf_path · pdf_sha256 · issued_at · issued_by_user_id · sent_at · sent_to
donation_receipt_items : receipt_id · journal_line_id NULL · in_kind_id NULL · date · amount_cents
                         · nature (cash|securities|in_kind) · form · payment_method
                         UNIQUE(journal_line_id)  -- une ligne de don ne figure que sur un reçu émis
in_kind_donations : entity_id · date · description · valuation_cents · valuation_method
```

Lot D :
```
simple_categories : code UNIQUE · label · kind (income|expense) · account_id · position · active
bank_accounts + kind (bank|cash) DEFAULT 'bank'
```

## 4. Lot A — Clôture, FEC, rôles

### 4.1 Rôles et accès

- `app/tenant.py` : après la sélection de l'instance, `g.instance_role = membership.role`
  (`admin` pour un administrateur global) ; sans accès → 403 JSON (`no_access`) ou redirection
  vers `/select-instance`. `GET /api/v1/session` : `instances` = instances accessibles seulement,
  `role` et `permissions` (`write`, `instance_admin`, `close_final`).
- `app/api/__init__.py` : `before_request` « lecture seule » (D2), liste blanche :
  `api.update_preferences`, `api.notifications_mark_read`, `api.login/logout/select_instance`.
- `instance_admin_required` remplace `admin_required` sur les intégrations ; `admin_required`
  (global) reste sur utilisateurs et instances.
- Nouvel écran **Configuration › Accès** (admin de l'instance) : liste des membres, ajout par
  email (compte existant, ou création avec mot de passe initial communiqué par l'administrateur),
  changement de rôle, retrait. Garde-fou : impossible de retirer le dernier `admin` d'une instance.
- Palette Ctrl+K, notifications, exports, PDF : soumis au même contrôle d'accès à l'instance
  (lecture autorisée à `accountant`).

### 4.2 Assistant de clôture (8 étapes, OA9)

| # | Étape (`step`) | Contenu calculé | Action / résultat stocké |
|---|---|---|---|
| 1 | `checks` | Transactions banque / caisse non rapprochées ; écritures déséquilibrées ; factures d'achat non comptabilisées ou non réglées ; 47x non soldés ; banque ou caisse créditrice ; écritures hors dates de l'exercice | Chaque anomalie avec lien ; « Continuer quand même » = `skipped` + motif |
| 2 | `inventory` | Écritures d'inventaire déjà saisies (D7) ; suggestions : factures d'achat datées de N reçues après la date de clôture → 408 | Formulaire guidé par type ; liste ; `done` |
| 3 | `dedicated_funds` | Ressources affectées de N (D10) : reçu, utilisé, reste | Dotation 689x / 19x et utilisation 19x / 789x ; `done` ou `skipped` (aucune ressource affectée) |
| 4 | `result` | Bilan et CdR provisoires (états existants), résultat = produits − charges | Lecture ; `done` |
| 5 | `fec` | Contrôles FEC (équilibre, dates, comptes, journaux) ; aperçu des 20 premières lignes | Téléchargement ; `done` |
| 6 | `close` | Rappel des étapes ignorées | Clôture **provisoire** (admin ou trésorier) : numérotation D5, `status=provisional`. Clôture **définitive** (admin) : FEC figé (D6), `status=closed`, irréversible |
| 7 | `opening` | Exercice N+1 (création proposée s'il n'existe pas) | Génère à-nouveaux (D8) et extournes (D7) dans N+1 ; regénérable |
| 8 | `allocation` | Résultat à affecter (120/129 de l'ouverture) | Saisie de la décision (organe, date, répartition) → écriture D9 ; peut être faite des mois plus tard (AG) |

Règles : étapes 1 à 5 tant que N est `open` ; l'ordre est conseillé, pas imposé, sauf `close`
(exige 1 à 5 `done` ou `skipped`), `opening` (exige N au moins `provisional`) et `allocation`
(exige `opening`). Réouverture d'une clôture provisoire (admin) : efface les numéros de
validation, repasse `open`, marque `opening` à refaire ; refusée si N+1 est clôturé.

### 4.3 FEC (FA1, D5, D6)

- Nom : `<SIREN>FEC<AAAAMMJJ>.txt` (date de clôture de l'exercice) ; refus si SIREN absent.
- 18 champs, dans l'ordre : `JournalCode`, `JournalLib`, `EcritureNum`, `EcritureDate`,
  `CompteNum`, `CompteLib`, `CompAuxNum`, `CompAuxLib`, `PieceRef`, `PieceDate`, `EcritureLib`,
  `Debit`, `Credit`, `EcritureLet`, `DateLet`, `ValidDate`, `Montantdevise`, `Idevise`.
- Séparateur **tabulation**, première ligne = en-têtes, dates `AAAAMMJJ`, montants avec virgule
  décimale sans séparateur de milliers, encodage à confirmer par « Test Compta Demat » (D-ouverte 1).
- `EcritureNum` = `validation_number` (D5) ; `PieceRef` = `reference` ; `ValidDate` = `validated_at` ;
  à-nouveaux en premier ; ordre : journal AN puis date, journal, numéro.
- Comptes de tiers 401xxx / 411xxx : `CompteNum` = compte détaillé, `CompAuxNum` / `CompAuxLib`
  = compte et nom du tiers (`entities.account_code`) quand il existe.
- Contrôles avant génération : exercice au moins `provisional` (numéros attribués), écritures
  équilibrées, total débit = total crédit = balance.

### 4.4 API (lot A)

| Méthode | URL | Rôle |
|---|---|---|
| GET / PUT | `/api/v1/organization` | lecture : tous ; écriture : admin instance |
| GET | `/api/v1/fiscal-years/<id>/closing` | état des 8 étapes + données de chaque étape |
| POST | `/api/v1/fiscal-years/<id>/closing/<step>` | `{state: done|skipped|todo, note}` |
| GET | `/api/v1/fiscal-years/<id>/fec/preview` | FEC à blanc (exercice ouvert, savepoint annulé) — étape 5 |
| GET | `/api/v1/fiscal-years/<id>/fec/check` | contrôles + relecture du FEC (exercice clôturé) |
| GET / POST / DELETE | `/api/v1/fiscal-years/<id>/inventory[/<entry_id>]` | écritures d'inventaire |
| GET / POST | `/api/v1/dedicated-funds` · `/api/v1/fiscal-years/<id>/dedicated-funds` | fonds et mouvements |
| POST | `/api/v1/fiscal-years/<id>/close` | `{final: bool}` (final = admin) |
| POST | `/api/v1/fiscal-years/<id>/reopen` | admin, exercice `provisional` |
| POST | `/api/v1/fiscal-years/<id>/opening` | génère / regénère à-nouveaux + extournes |
| POST | `/api/v1/fiscal-years/<id>/allocation` | `{decided_on, body, lines: [{account, amount}]}` |
| GET | `/fiscal-years/<id>/fec` (route Flask, fichier) | tous les rôles |
| GET / POST / PATCH / DELETE | `/api/v1/instances/<id>/members[/<user_id>]` | admin instance |

### 4.5 Écrans (SPA)

- **Compta › Exercices** : statut, bouton « Clôturer » → `/fiscal-years/<id>/closing`
  (assistant : stepper Mantine vertical, chaque étape repliable avec son état).
- **Configuration › Structure** (`organization`) ; **Configuration › Accès** (membres).
- Bandeau « Lecture seule (expert-comptable) » dans l'en-tête ; actions masquées via `useCan`.

## 5. Lot C — Projets, budget, prévisionnel

- Service `budget` : réalisé par compte / préfixe et par projet (requête groupée sur
  `journal_lines` de l'exercice, hors `OPENING`) ; prévu / réalisé / écart à date (mois écoulés).
- Saisie : **Compta › Budget** (grille comptes × mois ou annuel, filtre projet, copie N-1 réalisé
  ou budget N-1) ; **Compta › Projets** (liste, fiche : CdR du projet sur une période, export
  tableur et PDF pour un financeur — réutilise `reports` filtré par `project_id`).
- Affectation à un projet : colonne « Projet » dans l'éditeur d'écriture, les lignes de facture
  d'achat, les règles ; action « Ventiler » qui découpe une ligne (D12).
- **Trésorerie › Prévisionnel** : graphique (Mantine Charts) + tableau mensuel 12 mois, saisie des
  éléments manuels, alerte de solde négatif sur le tableau de bord.
- API : `/api/v1/projects`, `/api/v1/budgets/<fy_id>` (GET / PUT par lot de cellules),
  `/api/v1/budgets/<fy_id>/tracking`, `/api/v1/projects/<id>/statement`,
  `/api/v1/cash-forecast`, `/api/v1/cash-forecast/items`.
- Fonds dédiés (D10) : `project_id` ajouté ; l'étape 3 de l'assistant propose les montants non
  utilisés d'après le réalisé du projet.

## 6. Lot B — Reçus fiscaux

- **Configuration › Reçus fiscaux** (admin instance) : activation, éligibilité (avertissement de
  responsabilité), articles du CGI, comptes de dons, signataire et signature (image).
- **Tiers** : adresse et nature (D17) dans la fiche ; contrôle « reçu impossible : adresse
  manquante » au moment de l'émission.
- **Dons › Reçus** : année civile ; liste des donateurs avec dons non encore reçus (lignes D15 non
  rattachées) ; émission unitaire ou en lot (job, D18) ; envoi email (SMTP existant, job) ;
  téléchargement ; annulation (motif) et réémission ; **état annuel** (nombre, montant, FB7).
- Dons en nature : saisie (description, valorisation, méthode) ; comptabilisation proposée
  (charges / produits ou 86/87 selon le cas) hors reçu.
- API : `/api/v1/receipts/settings`, `/api/v1/receipts?year=`, `/api/v1/receipts/candidates?year=`,
  `/api/v1/receipts/issue` (job), `/api/v1/receipts/<id>/cancel`, `/api/v1/receipts/<id>/send`,
  `/api/v1/receipts/summary?year=` ; PDF : route Flask `/receipts/<id>.pdf`.
- Plan SCI : fonction absente (menus `charts: ["asso"]`).

## 7. Lot D — Comptabilité simplifiée et caisse

- **Création d'instance** : choix `Comptabilité simplifiée` / `Partie double` (asso seulement) ;
  modifiable par l'administrateur global (passage simple → double sans reprise, D20 ; l'inverse
  refusé dès qu'une écriture non `SIMPLE` existe).
- **Menus** (`menu_config`, nouvelle clé `bookkeeping`) : en mode simple, « Recettes et dépenses »,
  « Banque et caisse », « États » (CdR simplifié, situation de trésorerie), budget / projets,
  adhésions, reçus ; masqués : écritures, journaux, plan comptable, balance, grand livre, bilan,
  assistant de clôture, FEC.
- **Recettes et dépenses** : liste filtrable (mois, catégorie, projet, compte), saisie en fenêtre
  (date, libellé, montant, recette / dépense, catégorie, compte de trésorerie, tiers, projet,
  pièce jointe) ; une transaction bancaire importée se « catégorise » en une opération (même
  écran que le rapprochement, simplifié).
- **États** : CdR simplifié = sommes par catégorie (produits / charges N, N-1) ; situation de
  trésorerie = soldes début / fin d'exercice des comptes 512x et 53x, **calculés en cumulé** depuis
  l'origine (pas d'à-nouveaux en mode simple).
- **Caisse** (D22, les deux modes) : `Banque › Comptes` accepte un compte de nature caisse (53x) ;
  écran des mouvements de caisse ; action « Dépôt en banque » (581).
- Exercice en mode simple : verrouillage simple (`status=closed` sans assistant ni FEC).
- Passage en partie double : l'assistant de la première clôture en double calcule les à-nouveaux
  à partir des soldes cumulés (les exercices simples n'en ont pas).

## 8. Reprise de l'existant

- Exercices `closed=True` existants → `status='provisional'` (verrou maintenu ; l'administrateur
  peut les rouvrir ou passer l'assistant pour générer à-nouveaux et FEC). Aucune écriture
  rétroactive automatique.
- Memberships : créés pour tous les couples utilisateur × instance (§3.1).
- `organization` : nom repris de `instances.label`, autres champs vides (SIREN à saisir avant FEC).
- `bank_accounts.kind='bank'` partout ; `instances.bookkeeping='double'` partout.
- Toutes les migrations tenant suivent la boucle documentée (`doc/multi_tenant.md`).

## 9. Tests

- **pytest** : contrôle d'accès (chaque rôle × lecture / écriture / admin, liste blanche,
  instances non attribuées, dernier admin) ; assistant (règles d'enchaînement, réouverture) ;
  numérotation de validation continue ; à-nouveaux (bilan d'ouverture N+1 = bilan de clôture N,
  y compris après réouverture) ; extournes ; affectation (asso, SCI) ; FEC (format, ordre, totaux,
  nom, refus sans SIREN) ; reçus (numérotation sans trou sous concurrence, annulation, une ligne de
  don sur un seul reçu, contrôles d'adresse) ; mode simple (écritures générées, CdR simplifié,
  passage en double) ; caisse et dépôt 581.
- **Validation externe** : FEC d'un exercice de test passé dans « Test Compta Demat » ; reçus
  relus face aux modèles CERFA en vigueur ; relecture par l'expert-comptable.
- **Vitest / E2E** : assistant de clôture complet sur la base E2E ; expert-comptable en lecture
  seule (aucune action visible, 403 si forcée) ; émission d'un reçu ; saisie en mode simple.

## 10. Points ouverts (à trancher en workflow ou en test)

1. Encodage et séparateur exacts du FEC à confirmer avec « Test Compta Demat ».
2. Numéros et versions des modèles CERFA (particuliers, entreprises) à l'implémentation.
3. Plan SCI : comptes des associés (455x) et affectation (D9) à vérifier avec l'expert-comptable.
4. Création d'un compte par l'administrateur d'instance : sans réinitialisation de mot de passe
   par email aujourd'hui, le mot de passe initial est transmis hors application (à améliorer plus
   tard).
