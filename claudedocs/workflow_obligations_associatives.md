# Workflow — Obligations associatives (lots A → C → B → D)

> Statut (2026-10-23) : **lots A, B, C et D réalisés** (main local, non poussé) ; plan
> terminé côté logiciel. En attente côté utilisateur : relecture des reçus face aux Cerfa officiels
> (point ouvert 2, US-B1), passage du FEC de test dans
> « Test Compta Demat » (US-A1), relecture de l'affectation SCI 455x par l'expert-comptable, accord
> pour migrer les vraies bases (elles sont à `9c41b7e2d5a8` : migrations tenant jusqu'à
> `f6b1d4e8a207` (11 migrations), plus `seed_meta.py` pour la méta-base : `instance_memberships`, colonne `instances.bookkeeping`). Travail parallèle : cadrage de la base documentaire et de
> l'assistant dans [`doc/base_documentaire/`](../doc/base_documentaire/README.md) (autre session).
>
> Plan initial du 2026-10-22. Sources : [`besoins_obligations_associatives.md`](besoins_obligations_associatives.md)
> (OA1–OA14), [`design_obligations_associatives.md`](design_obligations_associatives.md) (D1–D22,
> validé implicitement par le passage au workflow). Exécution : `/sc:implement`, phase par phase,
> sur `main` local non poussé.

## 1. Règles communes à toutes les phases

- **Recette d'une phase** : migration (tenant Alembic ou méta `seed_meta`) → services → API →
  tests pytest → écrans SPA (+ Vitest) → E2E si parcours → contrôle Chrome sur les copies du
  serveur 5001 → docs (`routes`, `models`, `services`, guide utilisateur) → commit local → mémoire.
- `make check` et `make e2e` verts à chaque fin de phase ; aucun push sans accord.
- **Sécurité des données** : essais uniquement sur les copies du serveur 5001 (sauvegarde
  `*.before-<phase>.db` avant chaque migration) ; vraies bases jamais migrées par l'outil ; Qonto
  SCI en lecture seule.
- **Contrôle d'accès** (dès A.1) : toute nouvelle route d'écriture est couverte par un test
  « expert-comptable → 403 ».
- Notifications (`sync_jobs`) pour tout traitement long (génération de reçus, envoi d'emails).

## 2. Dépendances

```
A.1 Rôles ─┬─► A.2 Structure + statut d'exercice ─► A.3 Validation + FEC ─► A.4 Assistant 1-6
           │                                                               │
           │                                         A.5 Ouverture, extournes, affectation ◄┘
           │                                         A.6 Fonds dédiés (minimal) ─► C.5
           └─► (toutes les phases : contrôle d'accès)
C.1 Projets ─► C.2 Budget ─► C.3 Suivi + CdR projet ─► C.4 Prévisionnel ─► C.5 Fonds dédiés × projets
B.1 Tiers + paramètres ─► B.2 Émission + PDF ─► B.3 Lot, email, annulation, état annuel
D.1 Caisse (les deux modes) ─► D.2 Mode + catégories + menus ─► D.3 Recettes / dépenses ─► D.4 États ─► D.5 Bascule
```

C.4 utilise les caisses si D.1 est fait ; sinon banques seules, caisses ajoutées en D.1.

## 3. Lot A — Clôture, FEC, rôles

### Phase A.1 — Rôles et accès par instance (D1, D2)

| Étape | Tâche |
|---|---|
| A.1.1 | Méta : table `instance_memberships`, reprise idempotente dans `seed_meta` (admin si `is_admin`, sinon `treasurer`) |
| A.1.2 | `tenant.py` : `g.instance_role`, refus des instances non attribuées ; `session` : instances accessibles, `role`, `permissions` |
| A.1.3 | API : `before_request` lecture seule pour `accountant` (liste blanche) ; `instance_admin_required` (intégrations, accès) |
| A.1.4 | API membres : liste, ajout (compte existant ou créé), rôle, retrait, garde « dernier admin » |
| A.1.5 | Front : `useCan`, bandeau « Lecture seule », masquage des actions sur tous les écrans existants ; écran **Configuration › Accès** |
| A.1.6 | Tests : matrice rôle × (lecture, écriture, admin) sur un échantillon de routes de chaque module + test générique « toute route non-GET refusée à `accountant` hors liste blanche » |

**✅ CP A.1** : un expert-comptable ne voit que son instance, consulte tout, ne peut rien modifier
(interface et API) ; aucun utilisateur existant ne perd d'accès sur les copies 5001.
— *Fait (2026-10-22)* : `instance_memberships` + reprise unique ; `app/access.py` ; hook tenant
(`g.instance_role`) ; refus centralisé des écritures pour `accountant` (test sur **toutes** les
routes d'écriture de l'API) ; `instance_admin_required` sur intégrations, Qonto, rapport
d'activité, facteurs d'impact, date de synchro des factures ; API et écran **Accès** ; accès par
instance dans l'écran Utilisateurs ; front : `useCan`, `<Can>`, `writeOnly`, colonne `actions` et
fenêtres de saisie neutralisées en lecture seule, badge « Lecture seule ». Copie 5001 : reprise
appliquée deux fois (seconde sans effet), expert-comptable créé par l'écran Accès et vérifié en
lecture seule dans Chrome. pytest 718, Vitest 78, E2E 17.

### Phase A.2 — Structure et statut d'exercice (D3, D11, reprise §8)

| Étape | Tâche |
|---|---|
| A.2.1 | Migration : table `organization`, `fiscal_years.status` + horodatages, colonnes `journal_entries` (validation, extourne, type d'inventaire), tables `closing_steps`, `closing_events` |
| A.2.2 | Reprise : `closed=True` → `provisional` ; `organization.name` ← libellé d'instance |
| A.2.3 | `ledger` : statut tenu avec `closed` ; contrôles inchangés ; exclusion des sources `OPENING/REVERSAL/ALLOCATION/CLOSING` des suggestions de rapprochement |
| A.2.4 | API + écran **Configuration › Structure** (SIREN, RNA, adresse, objet, signataire) ; Exercices : affichage du statut |

**✅ CP A.2** : migration montée / descendue sur copies ; exercices existants en « clôture
provisoire » ; aucun test existant cassé.
— *Fait (2026-10-22)* : migration `c4e2a7d9b315` (organization, statut et horodatages d'exercice,
colonnes de validation / extourne / inventaire, `closing_steps`, `closing_events`) ; `status` et
`closed` synchronisés à chaque enregistrement (les 11 contrôles existants inchangés) ; bouton
« Clôturer » = clôture provisoire ; écritures de clôture exclues du rapprochement ; API et écran
**Structure** (SIREN avec clé de Luhn, RNA, code postal) ; statut affiché dans Exercices.
Correctif : la redirection vers le choix d'instance passait une URL absolue en `next` (ignorée par
la SPA). Copies 5001 migrées (sauvegardes `*.before-A2.db`), descente testée, reprise d'un exercice
verrouillé testée sur copie jetable. pytest 725, Vitest 78, E2E 17.

### Phase A.3 — Validation et FEC (D5, D6)

| Étape | Tâche |
|---|---|
| A.3.1 | Service `closing.validate(fy)` : numérotation continue par journal (ordre date, id), `validated_at` ; `unvalidate` |
| A.3.2 | Service `fec` : 18 champs, ordre, formats, tiers en compte auxiliaire, nom `<SIREN>FEC<date>`, contrôles |
| A.3.3 | Route Flask de téléchargement ; figeage + SHA-256 à la clôture définitive |
| A.3.4 | Validation externe : FEC d'un exercice de test (base E2E + copie SN) passé dans « Test Compta Demat » ; correction de l'encodage / séparateur au besoin (point ouvert 1) |

**✅ CP A.3** : FEC accepté par l'outil de la DGFiP ; totaux = balance ; refus sans SIREN.
— *Fait (2026-10-22), sauf l'outil de la DGFiP* : service `fec` (validation, contrôles, génération,
relecture interne, figeage SHA-256), numérotation à la clôture provisoire, API de contrôle, route de
téléchargement (tous rôles), fenêtre « FEC » dans Exercices ; E2E (SIREN → clôture provisoire →
FEC) sur un exercice ancien ajouté à la base E2E. Données réelles (copie SN, exercice 2025) : 105
écritures, 210 lignes, débit = crédit = 21 255,50 €, relecture conforme ; fichier remis à
l'utilisateur pour « Test Compta Demat » (application de bureau de la DGFiP, non lancée ici).
pytest 734, Vitest 78, E2E 18.

### Phase A.4 — Assistant de clôture, étapes 1 à 6 (D4, D7)

| Étape | Tâche |
|---|---|
| A.4.1 | Service `closing` : état des étapes, règles d'enchaînement, audit |
| A.4.2 | Étape 1 `checks` (contrôles recalculés, liens) ; étape 2 `inventory` (408/4686, 418/4687, 486, 487 ; suggestions de factures non parvenues) |
| A.4.3 | Étape 4 `result` (états existants), 5 `fec`, 6 `close` (provisoire : trésorier / admin ; définitive : admin) ; réouverture (admin) |
| A.4.4 | Écran `/fiscal-years/<id>/closing` : stepper, états, motif obligatoire pour « ignorer » |

**✅ CP A.4** : sur une copie 5001, un exercice passe en clôture provisoire puis est rouvert puis
reclôturé avec des numéros identiques ; l'expert-comptable consulte l'assistant sans agir.
— *Fait (2026-10-22)* : service `closing` (contrôles : rapprochements, écritures déséquilibrées ou
hors dates, achats non comptabilisés, factures non réglées (info), 47x non soldés, 512/53 créditeurs ;
inventaire 408/4686, 4687/418/441, 486, 487 en journal OD au dernier jour ; étapes faites / ignorées
avec motif ≥ 5 caractères, « Contrôles » fait refusé s'il reste une anomalie, « FEC » fait exigeant un
essai à blanc propre ; clôture provisoire après les 5 étapes, définitive et réouverture (motif) admin ;
historique `closing_events`). `fec.preview` (point de sauvegarde annulé). Écran
`/fiscal-years/<id>/closing` (liste d'étapes + panneau, historique), bouton « Clôturer… » de la liste.
Suggestions de factures non parvenues non faites (reportées). Copie 5001 : SN 2025 rouvert puis
reclôturé, 105 numéros identiques ; expert-comptable sur la copie SCI : assistant visible, aucune action.
pytest 746, Vitest 78, E2E 18.

### Phase A.5 — Ouverture, extournes, affectation (D8, D9)

| Étape | Tâche |
|---|---|
| A.5.1 | Étape 7 `opening` : création de N+1 proposée, journal AN, à-nouveaux (classes 1-5, résultat 120/129), extournes des écritures d'inventaire ; regénération |
| A.5.2 | Étape 8 `allocation` : décision (organe, date), répartition 110 / 119 / 106 / fonds associatifs ; SCI : 455x (point ouvert 3 à valider avec l'expert-comptable) |
| A.5.3 | Tests : bilan d'ouverture N+1 = bilan de clôture N (y compris après réouverture et regénération) ; extournes ; affectation asso et SCI |

**✅ CP A.5** : sur la copie SN, cycle complet 2025 → 2026 ; bilan 2026 avec soldes d'ouverture ;
E2E « assistant complet » sur la base E2E.
— *Fait (2026-10-23)* : `closing.generate_opening` (exercice suivant créé au besoin, contigu et
ouvert ; à-nouveaux journal AN classes 1-5 + résultat en 120/129, sous-compte 120xxx accepté, à
défaut 12 (plan SCI) ; extournes OD des écritures d'inventaire avec `reverses_entry_id` ;
regénération sans doublon), `allocate` / `cancel_allocation` (organe, date dans N+1, répartition
sur 10x / 11x / 455x totalisant le résultat ; écriture OD dans N+1). Réouverture de N : supprime
à-nouveaux et extournes, refusée si le résultat est affecté ou si N+1 est clôturé. Écritures gérées
par l'assistant (INVENTORY, OPENING, REVERSAL, ALLOCATION) non modifiables ni supprimables ailleurs
(`ledger.delete_entries`, API écritures). Saisie clavier des dates corrigée dans toute la SPA
(plugin dayjs `customParseFormat`). Copie SN : 2025 → 2026, AN-2026-0001 (5121 / 120 : 8 964,00 €),
affectation en 110 (OD-2026-0001), bilan 2026 équilibré avec soldes d'ouverture. Le point ouvert 3
(affectation SCI en 455x) reste à valider avec l'expert-comptable : la répartition est libre.
pytest 753, Vitest 78, E2E 18 (assistant complet).

### Phase A.6 — Fonds dédiés minimal (D10) et clôture du lot A

| Étape | Tâche |
|---|---|
| A.6.1 | Tables `dedicated_funds`, `dedicated_fund_movements` ; étape 3 de l'assistant (dotation 689x/19x, utilisation 19x/789x) |
| A.6.2 | Docs : guide utilisateur « Clôturer un exercice », `routes`, `models`, `services` ; relecture par l'expert-comptable (FEC, affectation SCI) |

**✅ CP lot A** : US-A1, US-A2, US-A3 cochées ; `make check` + `make e2e` verts.
— *A.6 fait (2026-10-23)* : tables `dedicated_funds` / `dedicated_fund_movements` (migration
`d5f3b8e1a426`), service `dedicated_funds` (dotation 689x/19x, utilisation 19x/789x, plafonds,
écritures OD gérées par l'assistant), étape 3 de l'assistant ; guide `doc/cloture.md`, `routes`,
`models`, `services` à jour. US-A2 et US-A3 cochées ; **US-A1 en attente du passage du FEC dans
« Test Compta Demat »** (utilisateur) ; relecture de l'affectation SCI (455x) par
l'expert-comptable à faire. Copies 5001 migrées (`*.before-A6.db`).

## 4. Lot C — Projets, budget, prévisionnel

| Phase | Tâches | CP |
|---|---|---|
| **C.1 Projets** (D12) | Table `projects` ; `project_id` sur `journal_lines`, `purchase_lines`, `rules` ; colonne Projet dans l'éditeur d'écriture, les lignes d'achat, les règles ; action « Ventiler » (découpage de ligne) ; écran **Compta › Projets** | Ventilation conserve l'équilibre et le FEC ; règle qui affecte un projet |
| **C.2 Budget** (D13) | Table `budget_lines` ; grille comptes × mois (regroupements), filtre projet ; copie N-1 (budget ou réalisé) | Saisie et rechargement d'un budget complet |
| **C.3 Suivi** | Service `budget` (prévu / réalisé / écart à date, par préfixe et projet) ; écran de suivi + export tableur ; CdR d'un projet sur une période (PDF / tableur) ; carte au tableau de bord | US-C1 cochée |
| **C.4 Prévisionnel** (D14) | Service 12 mois glissants ; `cash_forecast_items` (récurrence) ; écran **Trésorerie › Prévisionnel** (graphique + tableau) ; alerte de solde négatif au tableau de bord | US-C2 cochée |
| **C.5 Fonds dédiés × projets** | `dedicated_funds.project_id` ; étape 3 de l'assistant proposant le reste non utilisé d'après le réalisé du projet | Assistant sur une subvention affectée à un projet |

**C.1 fait (2026-10-23)** : table `projects` et `project_id` sur `journal_lines`, `purchase_lines`,
`rules` (migration `e7a4c2d9f531`) ; service `projects` (CRUD, totaux, affectation, ventilation) ;
écran Compta › Projets ; colonne Projet dans l'éditeur d'écriture (si l'instance a des projets),
les lignes d'achat et les règles ; affectation / ventilation sur la fiche d'une écriture, y compris
rapprochée (sauf la ligne bancaire). Copie SN 5001 : ligne 607 de BQ-2026-0005 (rapprochée)
ventilée 100,00 € projet / 54,24 € sans projet ; rapprochement conservé ; FEC 2026 à blanc conforme
(débit = crédit). pytest 763, Vitest 78, E2E 19.

**C.2 fait (2026-10-23)** : table `budget_lines` (migration `f2b6d8a3c147`), service `budget`
(grille, enregistrement par périmètre, contrôles de chevauchement, copie N-1 budget / réalisé),
API `/api/v1/budgets/<fy_id>[/copy]`, écran Compta › Budget (annuel / mensuel, sous-totaux, résultat
prévu, colonne des comptes figée). Copie SN 5001 : budget 2026 copié du réalisé 2025, enregistré et
rechargé à l'identique (charges 6 145,75 €, produits 15 109,75 €, résultat 8 964,00 € = résultat
2025). pytest 768, Vitest 78, E2E 20.

**C.3 fait (2026-10-23)** : `budget.tracking` (prévu année / à date, réalisé par préfixe et projet,
écart, hors budget), `projects.statement` (CdR d'un projet sur une période, factures jointes) ; API
`/budgets/<fy_id>/tracking`, `/projects/<id>/statement` ; exports XLSX (`app/views/exports.py`) ;
écrans Suivi budgétaire (graphique, impression) et Compte de résultat du projet (impression PDF) ;
carte Budget au tableau de bord. **US-C1 cochée.** Copie SN 5001 vérifiée (suivi 2026 au 22/10, CdR
« Jardin partagé », carte). pytest 772, Vitest 78, E2E 20.

**C.4 fait (2026-10-23)** : table `cash_forecast_items` (migration `a8c3e5f7b209`), service
`cash_forecast` (soldes hors à-nouveaux + transactions non comptabilisées, factures non réglées,
budget restant hors 68/78, saisies répétées, alerte), API `/api/v1/cash-forecast[/items]`, écran
Banque › Prévisionnel (graphique, tableau, détail d'un mois, saisies), alerte au tableau de bord.
**US-C2 cochée.** Copie SN 5001 : trésorerie 20 473,74 €, mouvements d'octobre à décembre (factures,
budget 2026), aucun budget 2027. pytest 776, Vitest 78, E2E 21.

**C.5 fait (2026-10-23) — lot C terminé** : `dedicated_funds.project_id` (migration `b9d4f6a8c310`),
proposition de dotation / utilisation d'après les charges du projet dans l'étape 3, choix du projet
à la création ou ensuite ; montants des messages au format français. Copie SN 5001 : subvention de
500 € sur « Jardin partagé » (100 € de charges 2026) → dotation proposée 400 €, enregistrée
(OD-2026-0002) puis retirée. US-C1 et US-C2 cochées. pytest 777, Vitest 78, E2E 21.

## 5. Lot B — Reçus fiscaux

| Phase | Tâches | CP |
|---|---|---|
| **B.1 Tiers et paramètres** (D15, D17) | Adresse et nature des tiers (fiche, import existant inchangé) ; table `receipt_settings` ; écran **Configuration › Reçus fiscaux** (éligibilité + avertissement, articles du CGI, comptes de dons, signataire, signature) | Activation par un admin d'instance seulement |
| **B.2 Émission et PDF** (D16, D18) | Tables `receipt_counters`, `donation_receipts`, `donation_receipt_items`, `in_kind_donations` ; candidats par année (lignes 7541 avec tiers non reçues + dons en nature) ; émission unitaire / annuelle ; gabarits particuliers et entreprises (CERFA en vigueur, point ouvert 2) ; PDF figé | Reçus conformes relus face aux modèles ; numérotation sans trou sous concurrence |
| **B.3 Lot, envoi, annulation, état annuel** | Job d'émission en lot et d'envoi email (SMTP, notification de fin) ; annulation + réémission ; état annuel (nombre, montant) ; écran **Dons › Reçus** | US-B1 cochée ; E2E « émettre et télécharger un reçu » |

**B.1 fait (2026-10-23)** : colonnes d'adresse et `person_kind` sur `entities`, table
`receipt_settings` (migration `c1e5a7b9d402`), service `receipts` (paramètres, mentions requises,
déclaration de responsabilité, signature), API `/api/v1/receipts/settings[/signature]` (admin
d'instance ; 404 en SCI), écran Configuration › Reçus fiscaux, adresse et nature dans la fiche du
tiers. Copies 5001 recréées depuis les vraies bases (lecture seule) après le redémarrage, migrées
(8 migrations) ; page vérifiée sur la copie SN. pytest 783, Vitest 78, E2E 22.

**B.2 fait (2026-10-23)** : tables `receipt_counters`, `donation_receipts`, `donation_receipt_items`,
`in_kind_donations`, `journal_lines.entity_id` (migration `d3f7b9c1e504`) ; candidats par donateur
(résolution banque / compte de tiers / choix), dons en nature, émission annuelle ou par don,
numérotation réservée dans la transaction (pas de trou en cas d'échec, testé), PDF figé (SHA-256,
contrôlé au téléchargement) ; écran Dons › Reçus fiscaux ; instance E2E « Asso Dons E2E ».
**Point ouvert 2** : modèles retenus Cerfa n° 11580*05 (2041-RD, particuliers) et n° 16216*01
(2041-MEC-SD, entreprises ; mise en page libre admise par le BOFiP si les mentions y sont) — à
relire face aux formulaires officiels. pytest 790, Vitest 78, E2E 23.

**B.3 fait (2026-10-23) — lot B terminé côté logiciel** : émission et envoi en arrière-plan (jobs
`donation_receipts`, `donation_receipts_send`, notifications), envoi par email avec PDF joint (SMTP
de l'instance), annulation motivée et réémission (`replaced_by_id`), état annuel (rapprochement
dons comptabilisés = reçus + à reprendre, export XLSX), titres de `JobStatus` paramétrables.
US-B1 : état annuel coché ; conformité Cerfa à relire. Pas de migration. pytest 795, Vitest 78,
E2E 23 (émission, PDF, annulation-réémission, état annuel).

## 6. Lot D — Comptabilité simplifiée et caisse

| Phase | Tâches | CP |
|---|---|---|
| **D.1 Caisse** (D22) | `bank_accounts.kind` ; compte 53x ; mouvements de caisse ; « Dépôt en banque » (581) ; contrôles de l'assistant étendus à la caisse ; prévisionnel (C.4) avec caisses | Dépôt d'espèces sans effet sur le CdR |
| **D.2 Mode et catégories** (D19, D21) | Méta `instances.bookkeeping` ; choix à la création d'instance ; table `simple_categories` pré-remplie ; `menu_config` clé `bookkeeping` ; masquage des écrans de partie double en mode simple | Instance simple : aucun écran débit / crédit visible |
| **D.3 Recettes et dépenses** (D20) | Saisie en fenêtre (écriture générée `SIMPLE`) ; catégorisation d'une transaction importée ; règles qui fixent une catégorie | Opérations visibles en partie double après bascule |
| **D.4 États simplifiés** | CdR par catégorie N / N-1 ; situation de trésorerie (cumulée) ; verrouillage d'exercice sans assistant ni FEC | US-D1 (états) cochée |
| **D.5 Bascule en partie double** | Passage `simple → double` (admin global), inverse refusé si écritures non `SIMPLE` ; première clôture en double : à-nouveaux depuis les soldes cumulés | US-D1 cochée ; E2E « saisie simple puis bascule » |

**D.1 fait (2026-10-23)** : `bank_accounts.kind` (migration `e5a9c3d7f106`), service `cash`
(mouvements au journal CA, dépôt en banque par 581 en deux écritures, solde cumulé hors à-nouveaux),
API `/bank-accounts/<id>/cash[/deposit]`, écran de caisse, liste « Comptes et caisses » avec solde,
caisses exclues du rapprochement / OFX / Qonto, contrôle de clôture 58x. pytest 798, E2E 24.

**D.2 fait (2026-10-23)** : `instances.bookkeeping` (méta, `seed_meta.py`), choix à la création
(asso seulement), filtre de menus `bookkeeping` (partie double masquée en mode simple),
`simple_categories` (migration `f6b1d4e8a207`) pré-remplies depuis le plan, écran Configuration ›
Catégories. pytest 802.

**D.3 fait (2026-10-23)** : service `simple_operations` (écritures `SIMPLE`, catégorisation d'une
transaction importée avec rapprochement, modification limitée si rapprochée, liste des recettes et
dépenses), API `/api/v1/simple/...`, écran « Recettes et dépenses » (opérations, relevé à
catégoriser), catégorie dans les règles en mode simple ; instance E2E « Asso Simple E2E ».
pytest 806, E2E 25.

**D.4 fait (2026-10-23)** : `simple_reports` (compte de résultat par catégorie N / N-1, situation
de trésorerie cumulée, verrouillage simple / déverrouillage admin), écran « États », colonne
Verrouillage des exercices en mode simple, `/close` refusé en mode simple ; correctif : deux
catégories par défaut ne partagent plus un compte. US-D1 (états) cochée. pytest 810, E2E 25.

**D.5 fait (2026-10-23) — lot D terminé** : changement de mode par l'administrateur global
(`PATCH /instances/<id>` `bookkeeping` ; simple → double sans reprise, retour refusé si une écriture
a une ligne hors classes 5 / 6 / 7), à-nouveaux de la première clôture en double calculés en cumulé
avec les résultats antérieurs en report à nouveau, bouton sur la fiche d'instance ; E2E « saisie
simple puis bascule ». **US-D1 cochée.** pytest 813, Vitest 78, E2E 25.

## 7. Estimation indicative

| Lot | Phases | Charge |
|---|---|---|
| A | A.1 (2 j) · A.2 (1 j) · A.3 (1,5 j) · A.4 (2 j) · A.5 (1,5 j) · A.6 (1 j) | ≈ 9 j |
| C | C.1 (1,5 j) · C.2 (1 j) · C.3 (1 j) · C.4 (1 j) · C.5 (0,5 j) | ≈ 5 j |
| B | B.1 (1 j) · B.2 (2 j) · B.3 (1,5 j) | ≈ 4,5 j |
| D | D.1 (1 j) · D.2 (1 j) · D.3 (1,5 j) · D.4 (1 j) · D.5 (0,5 j) | ≈ 5 j |

Total ≈ 23,5 jours de développement, hors relectures externes (expert-comptable, outil de la DGFiP).

## 8. Points de contrôle externes

- **Fin de A.3** : FEC passé dans « Test Compta Demat ».
- **Fin de A.5** : l'expert-comptable relit un cycle de clôture (affectation SCI, point ouvert 3).
- **Fin de B.2** : reçus relus face aux modèles CERFA en vigueur.
- **Avant toute mise en production** : migration des vraies bases (méta + chaque instance)
  selon `doc/multi_tenant.md`, après sauvegarde, avec votre accord.
