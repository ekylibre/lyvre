# Conception : lot AG1, socle de la comptabilité agricole

> **Statut** : **validée** (03/11/2026). Q-A1 : **toujours en engagement**. Q-A2 : 7571/6571 et 7578/6578, en-tête 234. Q-A4 : fichiers + surcharge en méta-base. Q-A5 : sous-comptes de culture repliés. Q-A3 : proposition retenue par défaut, contrôle dès AG1 sur cas sûrs (§ 11).
> **AG1.a réalisé (03/11/2026, non commité)**. Contenu :
> - migration tenant `b2c4e6a8f0d1` : `organization.legal_form_code` et `created_on`, `tax_profiles`, `tax_options`, `simple_categories.excluded_from_micro` ;
> - table `regulatory_values` dans la méta-base (`create_all`) ;
> - paramètres datés `data/regulatory/{ba,vat_agri,options}.json` ;
> - services `reg_params` et `tax_profile` ;
> - API `/tax-profile`, `/tax-profiles`, `/tax-options`, `/regulatory-values` ;
> - onglet Structure › **Fiscalité** pour les plans autres qu'associatif ;
> - page Administration › **Paramètres réglementaires** (lien d'administration).
>
> Écarts avec la conception :
> - une surcharge s'ajoute par `POST /regulatory-values/<clé>` (plusieurs périodes par clé) et se retire par `DELETE /regulatory-values/overrides/<id>` (au lieu de `PUT`) ;
> - les surcharges sont relues à chaque appel, sans cache, puisque plusieurs processus servent l'application ;
> - la proposition Sirene apporte `legal_form_code` et `created_on`, repris seulement s'ils sont vides ;
> - les sources des paramètres pointent sur le CGI (Légifrance), le BOFiP et impots.gouv, avec l'article cité dans `source_label` : les liens d'article ne sont pas vérifiés ;
> - **pas encore d'effet sur `chart = agri`**, qui n'existe qu'à partir d'AG1.b. Les contrôles « régime BA » valent pour toute structure qui en déclare un.
>
> Tests : `tests/test_reg_params.py`, `tests/api/test_tax_profile.py`, `frontend/src/features/organization/FiscalProfile.test.tsx` ; migration essayée sur une copie de base ancienne (`9c41b7e2d5a8`), dans les deux sens.
>
> **AG1.b réalisé (03/11/2026, non commité)**. Contenu :
> - `scripts/build_agri_chart.py`, qui lit le titre 5 du Recueil par lignes reconstituées (PyMuPDF) et les arbitrages `data/regulatory/sources/agri_chart_decisions.yml` ;
> - `data/plan_comptable_agri.json` : 970 comptes, dont 132 ajoutés au PCG 2026 ;
> - `data/agri_pcga1986_map.json` : 90 numéros, issus d'onoma `fr_pcga` → `fr_pcga2023`, plus la décision « 745 reste 745 » ; 19 cibles plus détaillées que le plan sont rabattues sur leur parent ; l'ancien 743 (→ 797, absent du PCG 2026) reste sans correspondance ;
> - `app/services/agri_chart.map_pcga1986` ;
> - `agri` ajouté aux énumérations (provisionnement, amorçage, menus, rôles avec 6578 / 7578 par défaut, Qonto recommandé, contreparties du solde bancaire, libellé du journal des modifications) ;
> - **comptabilité simplifiée ouverte à `agri`** : garde, menus, catégories agricoles avec `excluded_from_micro` ;
> - création d'instance : profil validé avant le provisioning (`app/services/agri_setup.py`), puis forme, régimes datés et premier exercice écrits dans la nouvelle base ; micro-BA → mode simple et exercice civil ;
> - formulaire en 3 blocs numérotés.
>
> Écarts avec la conception :
> - la correspondance PCGA 1986 vient d'**onoma seul**, le CSV Lexicon n'apportant pas les numéros 2023 ; aucune clé OSFarm n'a été nécessaire ;
> - pas de colonne `usage` dans le plan ;
> - `detect_chart` est revu pour les plans inclus l'un dans l'autre ;
> - en attendant AG1.c, le bilan et le compte de résultat d'une instance agri utilisent les modèles `societe` ;
> - les 3 étapes sont des blocs du même formulaire, et non un assistant pas à pas.
>
> Tests : `tests/test_agri_chart.py`, `frontend/src/features/instances/agriCreate.test.tsx` ; provisionnement réel essayé dans le dossier temporaire (970 comptes, détection du plan à la relance).
>
> **AG1.c réalisé (03/11/2026, non commité)**. Contenu :
> - dans `app/services/reports.py` : `BILAN_LAYOUTS["agri"]` (passif sociétés), `["agri_ei"]` (passif entreprise individuelle), choisis par `bilan_layout_key` (forme `EI`) ;
> - `AGRI_CDR_SECTIONS` (art. 121-3), avec le sous-total « Montant net du chiffre d'affaires » et des lignes « dont » (remboursement forfaitaire, travail de l'exploitant, opérations faites en commun) ;
> - `app/services/agri_reports.py` : `sig()` et `living_assets_table()` ;
> - API `/reports/sig` et `/reports/living-assets` (réservées à `agri`), meta `layout` du bilan ;
> - export `/reports/agri-statements.xlsx` (soldes et biens vivants) ;
> - écran Compta › **Soldes intermédiaires** et annexe sous le Bilan ;
> - l'ODS du compte de résultat gère le sous-total du chiffre d'affaires.
>
> Écarts avec la conception :
> - les formules des soldes sont des constantes Python (`agri_reports.SIG`) qui portent sur les lignes du compte de résultat, et non un fichier `data/agri_sig.json` ;
> - lignes ajoutées au modèle, pour le PCG 2026 : « cessions des autres immobilisations » (7578) et « valeur comptable des autres immobilisations cédées » (6578) ;
> - ligne omise : « autres en-cours » du cycle long, sans compte propre ;
> - amortissements et dépréciations des biens vivants répartis seulement s'ils sont en sous-comptes (2841…) ; sinon, une ligne « non répartis » ;
> - pas de PDF du bilan, puisque Lyvre n'en produit pour aucun plan.
>
> Tests : `tests/test_agri_reports.py` (chaque compte compté une fois dans le compte de résultat et le bilan, jeu chiffré, soldes, biens vivants, API, ODS, XLSX) et `frontend/src/features/reports/agriReports.test.tsx`.
>
> **AG1.f réalisé (04/11/2026, non commité)**. Contenu :
> - `scripts/agri_fixtures/` : `anonymize.py`, avec les fichiers réels **en arguments** (aucun nom, SIREN ni motif réel dans le code) ; `vocabulary.py` (productions, familles d'ateliers, gabarits) ; `build_synthetic.py` (D) ; `load.py` ;
> - `tests/fixtures/agri/` (A, B, C, D ; 1,8 Mo) : FEC fictifs, `profile.json`, `expected.json`, ateliers de C ;
> - **contrôle de fuite** bloquant à la génération, et contre-vérification indépendante sur les fichiers réels : seuls du vocabulaire comptable et des noms de cultures subsistent ;
> - test permanent du vocabulaire, sur la sortie seule ;
> - E2E : instances « Exploitation A E2E » et « Exploitation D E2E » (`frontend/e2e/agri.spec.ts`) ;
> - synthèse à relire : `claudedocs/compta_agricole/jeu_essai_valeurs_attendues.md`.
>
> Écarts avec la conception :
> - C garde la clôture au 31/01 de son FEC ; la SAS liée n'est pas reprise (ses écritures `.ISA` ne sont pas lues, seuls les ateliers le sont) ;
> - le lettrage n'est pas repris, la mise à l'échelle des montants ne garantissant pas l'équilibre des groupes lettrés ;
> - un compte sans correspondance de classe 6 ou 7 (ancien 791) va en 658 / 758, et non en 471 ;
> - `expected.json` contient des agrégats par préfixe (résultat, classes, lignes clés), calculés sur le fichier ; les tests y comparent les états de Lyvre ;
> - les exercices suivants (B) sont chargés après les à-nouveaux de l'assistant de clôture, par le même moteur de correspondance que l'import.
>
> Tests : `tests/test_agri_fixtures.py` (8 tests : vocabulaire, chargement de A à D, résultat, lignes clés, bilan équilibré, soldes, exercice suivant de B).
>
> **AG1.d réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/micro_ba.py` : livre des recettes de l'année civile (regroupement par jour des ventes au détail sous le seuil paramétré, recettes exclues repérées, totaux par trimestre) et récapitulatif N / N-1 / N-2 (moyenne, abattement, minimum, seuil, avertissements de fiabilité) ;
> - recettes des années antérieures dans la table `micro_receipts_years` (migration `c3d5f7a9b1e2`), au lieu du champ JSON prévu ;
> - API `/simple/reports/receipts-book`, `/micro-ba`, `/micro-ba/carryover`, réservée à `agri` en mode simple ;
> - export `/simple/reports/receipts-book.xlsx` ;
> - onglets « Livre des recettes » et « Micro-BA » des États simplifiés ;
> - exercice civil exigé au micro-BA (création d'exercice) ;
> - au passage du simple au double pour `agri`, avertissement (régime BA à mettre à jour, art. 72 E bis) ;
> - clôture : 4311 en contrepartie des charges à payer ; types `compensation_debit` / `compensation_credit` (472 → 412 / 402), proposés aux seules exploitations ;
> - contrôles agricoles : 472 non soldé (remplace le contrôle générique « compte d'attente » pour les 472), bien vivant sorti sans 7571 / 6571, biens vivants sans fiche au registre (information).
>
> Écart avec la conception : la mise à jour du régime BA à la sortie du micro-BA reste manuelle (onglet Fiscalité), avec un avertissement.
>
> Tests : `tests/test_micro_ba.py` (11 tests), `frontend/src/features/simple/microBa.test.tsx`, scénario E2E du dossier D étendu.
>
> **AG1.e réalisé (04/11/2026, non commité) : lot AG1 terminé côté logiciel.** Contenu :
> - `scripts/build_agri_categories.py` : jeu « variants » de Lexicon (CSV du dépôt local) et clés d'usage traduites par onoma, rattachées au plan agri ; seuls sont gardés les achats en 60 à 62 et les ventes en 70 ;
> - `data/agri_purchase_categories.json` : 55 catégories, taux de TVA de Lexicon marqués `vat_to_validate` ;
> - **corrections de Lyvre**, explicites dans le script : fermage en 6131, assurance et services bancaires sans TVA, contribution déchets écartée ;
> - `app/services/agri_catalog.seed_catalog()` : les catégories deviennent des **articles du catalogue** (achat, vente ou les deux ; nature « biens » pour 7011 à 7014). Le choix d'un article remplit déjà compte et taux à la saisie : aucun sélecteur nouveau ;
> - le catalogue est rempli à la création d'une exploitation au réel, et par le bouton « Ajouter les articles agricoles » du Catalogue (`POST /products/agri-catalog`, idempotent, un article modifié est conservé) ;
> - `data/rules_agri.yml` : MSA → 646, ASP → 745, FranceAgriMer → 748, fermage → 6131, tiers de type « organisme », sens du montant ; `seed_rules.py agri` ; `RULES_CHARTS` inclut `agri` ;
> - **contrôle du taux à la vente** (exploitation) : alerte sous le taux d'une ligne qui diffère de celui de l'article.
>
> Écarts avec la conception :
> - pas de sélecteur de catégorie dans la ligne d'achat, puisque le catalogue en tient lieu ;
> - le contrôle du taux s'appuie sur l'article de la ligne, et non sur une table `vat.product_category_rates` : c'est plus général, et les vins y sont couverts par leur article ;
> - pas de règle DGFiP (TVA ou impôt : compte indéterminé) ;
> - Lexicon lu dans le dépôt local, sans clé OSFarm.
>
> Tests : `tests/test_agri_catalog.py`, `frontend/src/features/sales/agriVatHint.test.tsx`, E2E étendu (catalogue).
>
> **Besoins** : `claudedocs/compta_agri.md`, lot AG1 du § 7. Il comprend :
> - le profil minimal (AG0.1, AG0.2, AG0.5, AG0.6) ;
> - le référentiel agricole (AG1.1 à AG1.8) ;
> - les trois régimes (AGD1) ;
> - le jeu d'essai fictif (§ 10, AGD2).
>
> **Hors de ce lot** :
> - TVA agricole (AG2) ;
> - aides PAC (AG3) ;
> - inventaire valorisé et biens vivants (AG4, AG5) : AG1 ne pose que les comptes et les états ;
> - fiscalité BA (AG6), MSA (AG7) ;
> - activités (AG8) ;
> - assistant (AG9) ;
> - autofactures et import `.ISA` (AG10).
>
> **Code examiné** : commit `ebdea12`.
>
> **Source réglementaire du plan et des modèles.** On retient le **Recueil PCG du 01/01/2026**, titre 5 (`doc/ref_compta/Recueil-PCG-Janvier-2026-2-.pdf`, art. 111-1 à 132-3). Il contient l'**ANC 2020-04 modifié par l'ANC 2024-07**, aligné sur le PCG 2026. Il remplace le PDF de 2020 fourni (`claudedocs/compta_agricole/Reglt_2020_04…`), qui sert seulement aux commentaires infra-réglementaires.
>
> Le PCG 2026 (art. 618-1 à 618-15) tranche en outre des points du § 8 des besoins :
> - **DPB** : immobilisations incorporelles ; les droits attribués ont une valeur nulle, les droits acquis sont inscrits au prix d'acquisition et amortis sur la durée de perception ; une comptabilité matière est tenue hors bilan (618-2 à 618-5) ;
> - **aides annuelles** : produit à recevoir à la **date limite de dépôt** de la demande (618-6) ;
> - **entraide** : seuls les remboursements de frais vont en charges et produits (618-15) ;
> - **méthodes d'évaluation des stocks et des avances aux cultures** (618-13, 618-14) ;
> - **cessions habituelles de biens vivants en exploitation** (618-11).
>
> Le rattachement **fiscal** des aides reste à valider (AGD5).

---

## 1. Choix structurants

| # | Choix | Raison |
|---|---|---|
| C1 | Nouveau référentiel **`Instance.chart = "agri"`**, au même niveau que `asso`, `sci` et `societe` | Les menus, rôles, états et intégrations sont déjà pilotés par `chart` ; on ajoute une valeur, on ne crée pas de mécanisme |
| C2 | **Plan agri = plan `societe` (PCG 2026) + comptes de l'art. 131-1 du titre 5 du Recueil 2026**, extraits du PDF par script et versionnés (`data/plan_comptable_agri.json`). En cas de conflit de numéro, **le titre 5 l'emporte** (§ 2.2) | Le règlement agricole complète le PCG (art. 111-2) ; même méthode que T1 (`scripts/build_pcg_chart.py`) ; aucune saisie ne dépend de Lexicon (AGD4) |
| C3 | **Le régime BA choisit le mode de tenue** : micro-BA → `bookkeeping = "simple"` ; réel simplifié **et** réel normal → partie double **en engagement** (Q-A1). Le réel simplifié ne diffère qu'au niveau fiscal (liasse 2139, AG6) | Réutilise le mode simple du lot D et la bascule simple → double existante ; aucune base trésorerie à maintenir. C'est la pratique des cabinets constatée dans les FEC réels (401/411 lettrés) |
| C4 | **Profil fiscal daté** dans la base de l'instance : régimes (IR/IS, BA, TVA, base de tenue) par période et options datées | Un régime change en cours de vie (micro → réel, option IS) ; l'assistant (AG9) lira les dates de renonciation |
| C5 | **Paramètres réglementaires** : valeurs datées et sourcées dans `data/regulatory/*.json` (versionnées), **surchargeables** dans la méta-base par l'administrateur | N1 : aucun seuil dans le code ; une valeur annuelle (A) peut être saisie sans livraison |
| C6 | **Régularisations de clôture agricoles** (aides acquises en 441, MSA à payer en 4311, compensation 472 → 402/412) = **écritures d'inventaire** existantes (`closing.INVENTORY_KINDS`), contrepassées à l'ouverture | Le mécanisme (date de clôture, contrepassation automatique, étape « inventaire ») existe déjà |
| C7 | **Correspondance PCGA 1986 → ANC 2020-04** en données (`data/agri_pcga1986_map.json`) dès AG1 | Le jeu d'essai part de FEC Isacompta numérotés en PCGA 1986 (§ 10.1 des besoins) ; elle resservira à l'import (AG10.6) |
| C8 | **Jeu d'essai** : un script d'anonymisation versionné, exécuté hors dépôt sur les données réelles ; seuls les fichiers fictifs sont versionnés | AGD2 ; aucune donnée personnelle dans le dépôt |

```
                 ┌──────────── méta-base ─────────────┐
                 │ instances.chart = "agri"           │
                 │ instances.bookkeeping simple|double│
                 │ regulatory_values (surcharges) C5  │
                 └──────────────┬─────────────────────┘
                                │
  data/ (versionné)             ▼              base de l'instance
  ├ plan_comptable_agri.json ─► seed ──► accounts            ┌─ organization.legal_form_code
  ├ agri_pcga1986_map.json      │                            ├─ tax_profiles (régimes datés)    C4
  ├ regulatory/*.json ─────────►│ reg_params.get(clé, date) ├─ tax_options (options datées)
  ├ agri_purchase_categories.json                            ├─ simple_categories (agri)        C3
  └ account_roles.json (+agri)  │                            └─ journal_entries (inventaire C6)
                                ▼
                  reports.py : BILAN_LAYOUTS["agri"] (EI | société), CDR_SECTIONS["agri"],
                               sig(), living_assets_table()
```

---

## 2. Référentiel « agri » : ce qui change dans le code existant

**`chart` est énuméré à plusieurs endroits.** On ajoute `"agri"` partout, et un test vérifie que les listes concordent.

| Fichier | Modification |
|---|---|
| `app/services/instance_provisioning.py` `CHARTS` | `"agri": "Exploitation agricole (EI, EARL, GAEC, SCEA…)"` |
| `seed_accounts.py` `CHARTS` | `"agri": "plan_comptable_agri.json"`. `detect_chart` : le plan agri contient le plan société, donc il se détecte par ses comptes propres (31111…, 741, 757) ; le cas est couvert par un test |
| `app/menu_config.py` `ALL_CHARTS` | Ajout de `agri`. Les entrées « société » (Associés, Déclarations de TVA) deviennent `["societe", "agri"]` |
| `app/api/instances.py` | `has_associates` coché à la création si la forme est une société (§ 3.1). Le mode **simple** est autorisé pour `asso` **et** `agri` (aujourd'hui `asso` seulement, l. 147 et 202) |
| `app/association_only.py` | Les modules du mode simple (`simple_operations`, `simple_categories`, `simple_reports`) quittent `ASSOCIATION_ONLY_MODULES` pour une garde **« mode simple »** : instance en `bookkeeping = simple`, quel que soit le plan. Reçus, adhérents, bénévolat et Brevo restent réservés aux associations |
| `app/tenant.py` | `is_agri()`, sur le modèle de `is_association()` |
| `data/account_roles.json` | Clé `agri` pour chaque rôle. Exemples : écart de lettrage 658 / 758, arrondi 658 / 758, résultat 120 / 129, compte de l'exploitant 108 |
| `app/services/external_config.py` | `RECOMMENDED["agri"] = ["qonto"]`. Brevo reste réservé aux associations jusqu'à AG9 (résumé du lundi, AGD3) |
| `app/services/bank_balance.py` `COUNTERPARTS` | `agri` : 101 Capital, 108 Compte de l'exploitant, 455 Associés |
| `app/services/assets.py` | Amortissement actif par défaut pour `agri` au réel, et **inactif** au micro-BA (l'abattement de 87 % couvre l'amortissement) |
| SPA | `chart === "societe"` (OrganizationPage) devient « société ou agri » si la forme est une société. Libellés « Exploitations » dans le journal des modifications et dans À propos |

### 2.1 Construction du plan (`scripts/build_agri_chart.py`)

```
entrées :
  data/plan_comptable_societe.json                  (PCG 2026, 837 comptes, déjà versionné)
  doc/ref_compta/Recueil-PCG-Janvier-2026-2-.pdf    titre 5, art. 131-1 (pages 630 à 634 imprimées) :
                                                     extraction PyMuPDF, comme build_pcg_chart.py
  data/regulatory/sources/agri_chart_decisions.yml  arbitrages des conflits (§ 2.2), relus par l'expert-comptable (AGD5)
  API Lexicon /chart_of_accounts (clé OSFarm)       → libellés, colonne fr_pcga (PCGA 1986)
  onoma db/reference.xml (accounts, fr_pcga2023)    → clé `usage` et numéros 2023
sorties :
  data/plan_comptable_agri.json   [{code, label, account_type, is_header, usage?}]
  data/agri_pcga1986_map.json     {"704": "7012", "70117": "7011", "241": "241", …} + _attribution
```

**Règles de construction :**
1. **Union.** On part du PCG 2026 et on ajoute les comptes du titre 5. Quand le même code existe, **le libellé du titre 5 l'emporte** (§ 2.2).
2. **Arbitrages.**
   - Les conflits du § 2.2 sont tranchés dans `agri_chart_decisions.yml`.
   - Tant qu'une décision est `pending`, le script s'arrête sur ce compte et le signale.
   - Les en-têtes sans intitulé dans le texte (234) reçoivent celui de la décision.
3. **Clé `usage`.** C'est la clé onoma (`fertilizer_expenses`…). Champ facultatif, qui sert aux reprises Ekylibre et Isacompta. Il est ignoré par `seed_accounts.py` tant qu'aucune colonne ne le reçoit (pas de migration en AG1).
4. **Attribution.** L'entrée `_attribution` cite Ekylibre SAS, Lexicon et onoma (CC-BY-SA 4.0) dans les deux fichiers dérivés (N5).
5. **Rapport du script.** Il liste les comptes ajoutés, les libellés remplacés et les codes PCGA 1986 sans correspondance, pour relecture.

### 2.2 Conflits entre le PCG 2026 et le titre 5

Constat fait sur les deux textes, le 03/11/2026 :

| Code | PCG 2026 (plan `societe`) | Titre 5, exploitations agricoles | Décision proposée |
|---|---|---|---|
| 741 | Subventions d'exploitation | **Remboursement forfaitaire de TVA** | Titre 5. Les subventions vont en 742 à 748 |
| 742 | Subventions d'équilibre | **Indemnités liées à la production agricole** | Titre 5 |
| 743, 744, 745, 748 | absents | Subventions aux produits, aux structures, au revenu, autres | Ajoutés |
| 757 / 657 | Produits et valeurs comptables des cessions de **toutes** les immobilisations incorporelles et corporelles (PCG 2026 : cessions en exploitation) | Produits et valeur comptable des **biens vivants** immobilisés cédés | **Décidé (Q-A2)** : **7571 / 6571** biens vivants (lignes propres du compte de résultat agricole), **7578 / 6578** autres immobilisations |
| 2341–2347 | 231 et 232 seulement | Listés après 231, mais numérotés 234x | **Décidé (Q-A2)** : en-tête 234 « Immobilisations corporelles en cours : biens vivants » |
| 7012 / 7014 | absents | 7012 **Ventes de produits animaux** (lait, œufs) ; 7014 **Ventes d'animaux** | Titre 5. **Correction** : le compte de résultat agricole porte les « Ventes d'animaux » sur **7014**, pas sur 7012 |

**Format.** `plan_comptable_agri.json` garde le format des autres plans. `seed_accounts.py` lit `code`, `label`, `account_type` et `is_header`, et ignore le reste.

---

## 3. Données (base de l'instance)

Une migration tenant, `a1…_agri_profile`, sans effet sur les instances existantes (N2).

### 3.1 Forme juridique

`organization.legal_form_code` : String(10), nullable.
- **Valeurs** : `EI`, `EARL`, `EARL_U` (unipersonnelle), `GAEC`, `SCEA`, `GFA`, `SARL`, `SAS`, `SA`, `SCI`, `ASSO`.
- **Préremplissage** depuis Sirene, par la catégorie juridique INSEE (`data/insee/categories_juridiques.json`) :
  - 1000 → EI ;
  - 6533 → GAEC ;
  - 6534 → GFA ;
  - 6597 → SCEA ;
  - 6598 → EARL.
  `sirene.py` porte déjà la catégorie ; on ajoute la correspondance.
- **Champ existant** : le texte libre `legal_form` reste pour les mentions légales.
- **Usage** :
  - **choix du passif** : modèle EI ou société (§ 5) ;
  - **contrôles** (§ 3.4) ;
  - `has_associates` pour EARL, GAEC, SCEA, GFA, SARL et SAS.

### 3.2 Régimes datés : `tax_profiles`

| Colonne | Type | Rôle |
|---|---|---|
| `id` | int | |
| `kind` | String(20) | `income_tax` (IR, IS) ; `ba_regime` (micro, simplified, normal) ; `vat_regime` (AG2 : `rfa`, `rsa_installments`, `rsa_quarterly`, `rsa_monthly`, `normal`, `none`) |
| `value` | String(30) | Valeur du régime |
| `start_date` | Date | Effet, en général le premier jour d'un exercice |
| `end_date` | Date, nullable | Nul : en cours |
| `origin` | String(10) | `law` (de plein droit, après dépassement de seuil) ou `option` |
| `note` | String(300) | |

**Contraintes :**
- pas de chevauchement pour un même `kind` (contrôle du service) ;
- `ba_regime` et `income_tax` ne sont requis que pour `chart = "agri"`.

**Lecture** : `tax_profile.current(kind, on=date)`.

En AG1, `vat_regime` est saisissable mais n'a pas encore d'effet. Ce sera le cas en AG2, à partir de `fiscal_years.vat_liable` et `vat_period`, qui restent inchangés.

### 3.3 Options datées : `tax_options`

| Colonne | Type | Rôle |
|---|---|---|
| `code` | String(30) | `ba_simplified_option`, `ba_normal_option`, `is_option`, `averaging_75_0_b`, `stock_freeze_72_b_bis`, `flat_stock_method`, `rsa_option`, `vat_quarterly`, `vat_monthly` |
| `start_date` | Date | |
| `duration_years` | int, nullable | 1, 3 ou 5 ; nul : sans terme |
| `tacit_renewal` | bool | |
| `renounced_on` | Date, nullable | |
| `note` | String(300) | |

**Calcul de la date limite de renonciation.** La règle est lue dans un paramètre réglementaire, par exemple `option.renounce.vat_quarterly` = « avant le 5/2 de la dernière année ». Elle est exposée par l'API. Elle n'est **ni stockée ni utilisée** en AG1 ; elle sert l'assistant en AG9.

### 3.4 Exercice et contrôles

**Pas de base de tenue par exercice** (Q-A1) : en partie double, l'exploitation est toujours tenue en engagement. Le micro-BA reste le seul régime en mode simple.

**Contrôles de cohérence** (AG0.5), au service `tax_profile`. Ils renvoient une erreur `422` avec le champ en cause :
- `ba_regime = micro` refusé si la forme est une société créée après le 01/01/1997, sauf `EARL_U`. La date de création vient de Sirene ou se saisit (`organization.created_on`, ajouté).
- Nombre d'associés du module Associés : GAEC de 2 à 10, EARL de 1 à 10. Alerte seulement, puisque les associés peuvent être saisis après.
- `income_tax = IS` avec `ba_regime` renseigné : refusé, le régime BA n'existe qu'à l'IR.

### 3.5 Catégories du mode simple pour une exploitation

`simple_categories` reçoit une colonne `excluded_from_micro` (bool) : recette exclue du micro-BA (cessions, ICHN, primes d'équipement, remboursements d'entraide).

Les valeurs par défaut sont choisies **selon le plan** : `simple_categories.DEFAULTS` devient `DEFAULTS["asso"]` et `DEFAULTS["agri"]`.

**Recettes** :

| Catégorie | Compte |
|---|---|
| Ventes de produits végétaux | 7011 |
| Ventes de produits animaux (lait, œufs) | 7012 |
| Ventes d'animaux | 7014 |
| Produits transformés | 7013 |
| Travaux à façon | 7041 |
| Aides PAC découplées | 745 |
| ICHN (exclue) | 744 |
| Indemnités d'assurance | 742 |
| Cessions de matériel (exclue) | 7578 |
| Remboursements d'entraide (exclue) | 7088 |
| Autres recettes | 758 |

**Dépenses** :

| Catégorie | Compte |
|---|---|
| Engrais | 60111 |
| Semences | 60112 |
| Phytos | 60113 |
| Aliments du bétail | 60114 |
| Vétérinaire | 60115 |
| Achats d'animaux | 60117 |
| Carburant | 60614 |
| Travaux par tiers | 6051 |
| Fermages | 6131 |
| Locations de matériel | 6132 |
| Entretien | 615 |
| Assurances | 616 |
| MSA de l'exploitant | 646 |
| Impôts | 63 |
| Frais bancaires | 627 |
| Autres | 658 |

Les comptes sont repris de l'ANC 2020-04. AGD5 : liste à relire.

---

## 4. Paramètres réglementaires (AG0.6)

### 4.1 Fichiers versionnés

Les valeurs sont dans `data/regulatory/<domaine>.json`, avec un domaine par fichier : `ba.json`, `vat_agri.json`, `msa.json`, `calendar.json`…

```json
{
  "_comment": "Paramètres réglementaires datés (claudedocs/design_compta_agricole.md § 4).",
  "values": [
    {"key": "ba.micro.threshold_cents", "value": 12920000,
     "valid_from": "2026-01-01", "valid_to": null,
     "source": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI…", "source_label": "CGI art. 69 I (décret 2026-562)",
     "verified_on": "2026-11-03", "reliability": "I",
     "note": "Millésime d'application à valider (120 000 € selon d'autres sources)"},
    {"key": "ba.micro.allowance_bp", "value": 8700, "valid_from": "2016-01-01", "reliability": "R", "…": "…"},
    {"key": "ba.micro.minimum_cents", "value": 30500, "…": "…"},
    {"key": "ba.normal.threshold_cents", "value": 42100000, "reliability": "I", "…": "…"},
    {"key": "ba.gaec.threshold_cents", "value": 51700000, "reliability": "I", "…": "…"}
  ]
}
```

- **Montants en centimes**, taux en points de base, durées en jours ou en années. Les clés sont typées par leur suffixe : `_cents`, `_bp`, `_days`, `_date`, `_rule`.
- **Fiabilité** : `V` vérifiée, `R` règle stable, `A` annuelle, `I` incertaine (légende de `audit_calendrier.md`).

### 4.2 Surcharges (méta-base)

Table `regulatory_values` dans la méta-base (`__bind_key__ = "meta"`, créée par `seed_meta.create_all`).
- **Colonnes** : les mêmes champs, plus `created_by_user_id` et `created_at`.
- **Usage** : l'administrateur de la plateforme y saisit, par exemple, la date limite PAC 2027 dès sa publication, sans livraison.
- **Portée** : commune à toutes les instances, puisque la règle est nationale.

**Exception, le calendrier MSA par caisse.** La clé porte la caisse, par exemple `msa.calls.<caisse>.2027`. Elle est quand même stockée ici : la caisse est un paramètre national à plusieurs valeurs, pas une donnée de l'exploitation.

### 4.3 Service `app/services/reg_params.py`

```python
get(key, on: date) -> Param          # value, reliability, source, verified_on, origin ("file" | "override")
value(key, on: date, default=_RAISE) # raccourci ; MissingParam si aucune valeur ne couvre la date
history(key) -> list[Param]
```

- **Résolution** : la surcharge de la méta-base couvrant la date l'emporte ; à défaut, le fichier ; à défaut, `MissingParam`.
- **Pas de valeur de repli dans le code.** L'appelant décide : afficher « à confirmer » ou bloquer.
- **Cache** : chargement en mémoire au démarrage, invalidé à l'écriture d'une surcharge.

### 4.4 Interface

- **API** : `GET /api/v1/regulatory-values?prefix=ba.` en lecture pour tout utilisateur connecté. `PUT /api/v1/regulatory-values/<key>` réservé à l'administrateur de la plateforme.
- **Écran** « Paramètres réglementaires » (Administration) : liste par domaine, avec la fiabilité en pastille (V vert, R bleu, A orange, I rouge), la source cliquable et la date de vérification. On peut y ajouter une surcharge datée.

---

## 5. États agricoles (AG1.2 à AG1.4)

Dans `app/services/reports.py`, on ajoute des entrées au format existant : tuples `("row", libellé, préfixes, niveau, sens, exclusions)`.

### 5.1 Bilan : `BILAN_LAYOUTS["agri"]` et `BILAN_LAYOUTS["agri_ei"]`

**Choix du modèle** :
- `legal_form_code = EI` : passif « entreprise individuelle » (art. 121-1) ;
- sinon : passif « société ».

`build_bilan(fy, fy_prev, chart)` reçoit une variante. La fonction `bilan_layout_key()` choisit `"agri_ei"` ou `"agri"`.

**Actif**, différences avec le bilan `societe` :

```
ACTIF IMMOBILISÉ
  Immobilisations incorporelles (dont « Fonds commercial et fonds agricole résiduel » 206, 207, 2071)
  Immobilisations corporelles hors biens vivants
    Terrains 211 · Agencements et aménagements fonciers 212 · Améliorations des sols et des milieux 217
    Constructions 213, 214 · ITMO 215 · Autres 218 · En cours 231
  Immobilisations corporelles, biens vivants
    Animaux reproducteurs 241 · Animaux de service 243 · Plantations pérennes 246 · Autres végétaux 247
    Biens vivants en cours 234x (en-tête 234, Q-A2)
  Immobilisations financières (dont participations dans les organismes agricoles 262x, 2672x, 2715, 2723)
  Amortissements et dépréciations 28, 29 (dont biens vivants 284, 294)
ACTIF CIRCULANT
  Biens vivants et en-cours, cycle long
    Animaux 3112 · Avances aux cultures 31141 · Autres végétaux 31142, 31148 · Vins et alcools 3311 · Autres en-cours
  Biens vivants et en-cours, cycle court
    Animaux 3113 · Avances aux cultures 31151 · Autres végétaux 31152, 31158 · En-cours 3312
  Stocks : approvisionnements et marchandises 3111, 32, 37 · produits 35
  Créances : clients 41 (dont soldes de compensation 412) · autres
  …
```

**Passif EI** : capital individuel (101, 108), écart de réévaluation, résultat, subventions d'investissement, provisions réglementées. **Passif société** : modèle `societe`.

Dans les deux modèles, la ligne « Dettes autres fournisseurs : conventions de compte courant » (402, 472) est distincte.

### 5.2 Compte de résultat : `CDR_SECTIONS["agri"]`

Mêmes clés de premier niveau que les autres plans : le tableau de bord continue de fonctionner (docstring de `build_compte_resultat`).

**Produits d'exploitation** :
- ventes de marchandises (707) ;
- **ventes d'animaux hors biens vivants immobilisés** (7014) ;
- autre production vendue (701 hors 7014, 704, 705, 706, 708) ;
- **produits de cession sur biens vivants immobilisés** (7571) ;
- production stockée (713) ;
- production immobilisée : biens vivants (7222, 724) et hors biens vivants (7221) ;
- **production autoconsommée** (73) ;
- indemnités et subventions d'exploitation : 742 à 748 ; le 741 forme une ligne à part, « dont remboursement forfaitaire de TVA » ;
- reprises et transferts ; autres produits (75 hors 757).

**Charges d'exploitation** :
- achats de marchandises ;
- **achats d'animaux** (60117) ;
- approvisionnements (60 hors 60117, 607) ;
- variations de stocks ;
- autres achats et charges externes ;
- impôts ;
- salaires (« dont rémunération du travail de l'exploitant », 64116, 64117) ;
- charges sociales (6451, 646) ;
- dotations ;
- **valeur comptable des biens vivants immobilisés cédés** (6571) ;
- autres charges (65 hors 657).

Les sections financières, exceptionnelles, la participation et l'IS suivent le modèle de l'art. 121-3. Ce modèle **garde** « Produits et charges exceptionnels sur opérations en capital ».

### 5.3 Soldes intermédiaires : `sig(fy, fy_prev, chart="agri")`

**Formules**, en données (`data/agri_sig.json`), sur le principe des correspondances d'Ekylibre réécrites :
- **production de l'exercice** = ventes + production stockée, immobilisée et autoconsommée ;
- **valeur ajoutée** = production − consommations de tiers. C'est la même formule que la VA de la DEP (art. 73 II-2 d), réutilisée en AG6.
- **EBE** = VA + subventions d'exploitation − impôts − charges de personnel ;
- **résultat courant**.

**Affichage** : une page « Soldes intermédiaires » sous Comptabilité, pour `agri` seulement, avec export XLSX.

### 5.4 Annexe : tableau des biens vivants et en-cours (`living_assets_table(fy)`)

| Lignes | Colonnes |
|---|---|
| Cycle long : animaux, végétaux, en-cours | Valeur nette à l'ouverture |
| Cycle court : animaux, végétaux, en-cours | Valeur nette à la clôture |
| Immobilisés : 241, 243, 246, 247 | Variation |

- **Valeurs** : soldes des comptes. Les unités physiques (têtes, hectares) viendront avec l'inventaire (AG4).
- **Restitution** : dans le bilan PDF (annexe) et en écran.

### 5.5 Exports

PDF, XLSX et CSV passent par les mêmes chemins que les autres plans (`report_pdf`, `report_export`). Le libellé du document est « Bilan agricole », « Compte de résultat agricole ».

---

## 6. Les trois régimes (AGD1)

### 6.1 Micro-BA : mode simple

**Création.** `chart = agri` et `bookkeeping = simple` sont choisis ensemble dans l'assistant de création : « Régime BA : micro-BA ».

**Saisie et livre des recettes.**
- Recettes et dépenses : écrans du lot D, avec les catégories agricoles (§ 3.5).
- **Livre des recettes** : nouvel état dans `simple_reports`, avec `GET /api/v1/simple-reports/receipts-book?year=`.
  - Une ligne par encaissement : date, client, libellé, montant, catégorie.
  - **Regroupement facultatif des ventes de 76 € ou moins** par jour. Le seuil est le paramètre `ba.micro.receipts_book.grouping_cents`.
  - Totaux par trimestre et par **année civile**. L'exercice d'un micro-BA est l'année civile ; le contrôle est fait à la création de l'exercice.
  - Exports PDF et XLSX.
- **Récapitulatif micro-BA** :
  - recettes de N, N-1 et N-2, hors catégories `excluded_from_micro` ;
  - moyenne et bénéfice forfaitaire, avec l'abattement et le minimum (paramètres) ;
  - **reprise des années antérieures** à Lyvre par une saisie manuelle des totaux (`simple_report_carryover`, champ JSON de l'exercice).

**Changement de régime.**
- **Micro → réel** : la bascule simple → double existante (lot D.5) devient accessible à `agri`. Le régime BA daté est mis à jour. La réintégration des créances (72 E bis) est **signalée**, puis calculée en AG6.
- **Réel → micro** : refusé dans Lyvre, puisque c'est un cas fiscal rare. Il faut créer une nouvelle instance.

### 6.2 Réel simplifié et réel normal : engagement (Q-A1)

**Tenue identique.** Les deux régimes réels se tiennent comme aujourd'hui dans Lyvre : partie double en engagement, factures en 401/411, lettrage. Ce qui les distingue est seulement fiscal :
- liasse 2139 ou 2143 (AG6) ;
- méthode forfaitaire des stocks, réservée au réel simplifié (AG4).

**Hors périmètre** (Q-A1) : la comptabilité de trésorerie de l'art. 74 et le FEC « trésorerie » (AG10.5 des besoins).

**Comptes propres au réel simplifié.** L'art. 74 c (petits frais en espèces) et le barème carburant relèvent du calcul fiscal (AG6) : AG1 n'en tient pas compte.

### 6.3 Régularisations de clôture agricoles (C6)

Extension de `closing.INVENTORY_KINDS` :

| Type | Compte | Contreparties | Usage |
|---|---|---|---|
| `accrued_income` (existant) | 7xx | 4687, 418, **441** (déjà accepté) | Aides annuelles acquises à la date limite de dépôt et non encaissées (PCG art. 618-6) : saisie manuelle en AG1, proposée en AG3 |
| `accrued_expense` (existant) | 6xx | 408, 4686, **+ 4311** | Cotisations MSA, fermage à payer |
| `compensation_at_close` (nouveau) | 472x | 402 ou 412 | Solde de chaque convention de compte courant (art. 132-1) ; proposé par le contrôle du § 6.5 |

### 6.5 Contrôles propres au plan (AG1.6)

Ils s'ajoutent à `closing.checks(fy)` quand `chart = agri`. Ce sont des anomalies avec motif exigé, sauf mention :
- un compte 24x est soldé dans l'exercice, mais la cession n'est pas passée en 7571 / 6571 ;
- compte 472 non soldé à la clôture. Une action propose le virement vers 402 ou 412 (écriture d'inventaire `compensation_at_close`) ;
- information : solde débiteur en 24x sans immobilisation dans le registre ;

---

## 7. Règles d'imputation et catégories d'achat (AG1.5)

### 7.1 `data/agri_purchase_categories.json`

Généré par `scripts/build_agri_categories.py` depuis l'API Lexicon (`master_variant_categories`, clé OSFarm), versionné, avec attribution CC-BY-SA :

```json
{"categories": [
  {"key": "fertilizer", "label": "Engrais et amendements", "account": "60111", "stock_account": "31111",
   "vat_code": "D20", "source_usage": "fertilizer_expenses"},
  {"key": "animal_food", "label": "Aliments du bétail", "account": "60114", "stock_account": "31114",
   "vat_code": "D10"}
]}
```

**Usage** : le formulaire de ligne d'achat et la catégorisation d'une transaction proposent la catégorie. Choisir une catégorie remplit le compte et le code TVA, qui restent modifiables. Ce n'est qu'une suggestion : rien n'est imposé.

Les codes TVA viennent de `vat_codes.json` (D20, D10, D55). Les taux discutés (engrais en agriculture biologique, animaux) sont marqués `to_validate` (AGD5).

### 7.2 Règles bancaires agricoles

`RULES_CHARTS` passe à `{"asso", "agri"}`, et `seed_rules.py` lit le fichier du plan, `data/rules_agri.yml`. Il ne contient que des libellés génériques, sans tiers réel :

| Libellé contient | Compte |
|---|---|
| `MSA` | 646 |
| `ASP` | 745, à reclasser en AG3 |
| `DRFIP` ou `DGFIP` | 63 ou 445, choisi par le montant |
| `FERMAGE` | 6131 |

### 7.3 Cohérence entre compte de vente et taux

**Contrôle non bloquant** à la saisie d'une vente.
- **Ce qui est contrôlé** : la **catégorie du produit** du catalogue, et non le compte. Le 7013 « produits transformés » mélange des taux : vins à 20 %, fromages à 5,5 %.
- **Table** : `data/regulatory/vat_agri.json`, clé `vat.product_category_rates`. Exemple : « vins et alcools » → 20 % attendu.
- **Affichage** : un écart s'affiche comme une alerte sur la ligne.

**Q-A3 (§ 11)** : faut-il lancer ce contrôle dès AG1 ou attendre la table des taux d'AG2 ? Proposition : dès AG1, sur quelques cas sûrs seulement (vins et alcools à 20 %).

---

## 8. Écrans (SPA)

| Écran | Contenu |
|---|---|
| Création d'instance (existant) | Choix « Exploitation agricole », puis **assistant en 3 étapes** : (1) forme juridique, préremplie par le SIREN ; (2) IR ou IS, régime BA (micro, réel simplifié, réel normal), avec la date d'effet ; (3) date de clôture, avec la mention « les exercices décalés sont courants (31/01, 30/04, 30/06…) ». Le mode simple ou double et la base de tenue s'en déduisent |
| Structure › **Fiscalité** (nouvel onglet, `agri` et `societe`) | Forme ; historique des régimes datés (ajout d'une période, fin de la précédente) ; options datées avec durée, reconduction et date de renonciation calculée ; contrôles AG0.5 affichés en alertes |
| Bilan, Compte de résultat (existants) | Modèles agricoles ; section « Annexe : biens vivants » |
| **Soldes intermédiaires** (nouveau) | § 5.3 |
| Recettes et dépenses, Rapports simplifiés (existants, ouverts à `agri`) | Catégories agricoles ; **Livre des recettes** ; **Récapitulatif micro-BA** |
| Clôture › Inventaire (existant) | Types « MSA à payer » (4311) et « compensation 472 » ; contrôles agricoles (§ 6.5) |
| Administration › **Paramètres réglementaires** (nouveau) | § 4.4 |

Les composants suivent le design system Lyvre : Mantine, palette lichen, ardoise et ocre.

---

## 9. API (préfixe `/api/v1`)

| Méthode et route | Rôle |
|---|---|
| `GET/PUT /organization` (existant) | Ajout de `legal_form_code` et `created_on` |
| `GET /tax-profiles`, `POST /tax-profiles`, `PATCH/DELETE /tax-profiles/<id>` | Régimes datés ; contrôles AG0.5 en 422 |
| `GET/POST /tax-options`, `PATCH/DELETE /tax-options/<id>` | Options ; réponse avec `renounce_by` calculé |
| `GET /reports/sig?fy=` ; `GET /reports/living-assets?fy=` | États § 5.3 et 5.4, avec exports `.xlsx` et `.pdf` |
| `GET /simple-reports/receipts-book?year=&group_small=1` ; `GET /simple-reports/micro-ba?year=` | § 6.1 |
| `POST /closing/<fy>/inventory` (existant) | Nouveaux types du § 6.3 |
| `GET /regulatory-values?prefix=` ; `PUT /regulatory-values/<key>` (administrateur de la plateforme) | § 4 |
| `GET /agri/purchase-categories` | § 7.1 |
| `POST /instances` (existant) | Champs `legal_form_code`, `income_tax`, `ba_regime`, `fy_end` quand `chart = agri` ; crée le profil et le premier exercice |

---

## 10. Jeu d'essai fictif (AGD2)

### 10.1 Chaîne de génération

```
~/projects/cultia_back/doc/spec/import_compta/   (réel, hors dépôt, jamais lu par les tests)
        │
        ▼  scripts/agri_fixtures/anonymize.py  --source <dossier> --out tests/fixtures/agri/
        │   1. lecture des FEC (fec_import.parse) et des .ISA (lecteur minimal : DOS, EXO, CPT, ANA, ECR, MVT)
        │   2. numérotation : PCGA 1986 (8 chiffres) → plan agri, via data/agri_pcga1986_map.json ;
        │      sous-comptes de culture repliés sur le compte ANC (libellé de culture gardé dans EcritureLib)
        │   3. anonymisation (JE1) : tiers → « Fournisseur 001 », « Coopérative A » ; noms et SIREN
        │      supprimés ; libellés → gabarits par compte (« Achat engrais », « Vente maïs ») ; pièces renumérotées
        │   4. montants × coefficient tiré par dossier (graine fixée), arrondis au centime, écritures rééquilibrées
        │   5. dates décalées d'un nombre entier d'années (saisonnalité conservée)
        │   6. contrôle de fuite : aucune chaîne du fichier source de 4 caractères ou plus, hors vocabulaire
        │      comptable (liste blanche), ne doit subsister ; sinon échec
        ▼
tests/fixtures/agri/
  A_earl_porcs_rs/      FEC-<exercice>.txt, profile.json, expected.json
  B_scea_legumes_rn/    deux exercices consécutifs (à-nouveaux)
  C_gaec_ateliers/      FEC + ateliers.json (de l'ANA du .ISA, pour AG8), SAS liée
  D_micro_rfa/          simple_operations.json (synthétique, build_synthetic.py)
```

**Garanties :**
- **Le script ne contient aucune donnée réelle.** La liste blanche ne contient que du vocabulaire comptable ou agricole générique.
- **La sortie est relue avant le commit.** Elle est contrôlée deux fois : par le contrôle de fuite, puis par un `grep` des SIREN connus fait sur place par le développeur, sans les écrire dans le dépôt.

### 10.2 Valeurs attendues et chargement

- **`expected.json`** : balance par classe, totaux du bilan et du compte de résultat agricoles, SIG, livre des recettes (D). Pour JE4, ce sont des valeurs produites puis **relues par l'expert-comptable** (AGD5). Elles ne sont pas recalculées par le code testé.
- **`scripts/agri_fixtures/load.py <dossier> <slug>`** crée une instance `agri` avec le profil de `profile.json`, puis importe le FEC par `fec_import.import_history` ou les opérations simples.
- **E2E** : `scripts/e2e_server.py` crée « Exploitation A E2E » et « Exploitation D E2E » (JE5).

---

## 11. Décisions de validation

- **Q-A1 → toujours en engagement** (03/11/2026). Pas de base trésorerie ; le réel simplifié ne diffère qu'au niveau fiscal.
- **Q-A2 → subdivision** (03/11/2026) :
  - 7571 / 6571 « produits et valeur comptable des cessions de biens vivants immobilisés », portés sur les lignes du compte de résultat agricole ;
  - 7578 / 6578 pour les autres immobilisations (PCG 2026) ;
  - en-tête 234 « Immobilisations corporelles en cours : biens vivants » ;
  - **encore à trancher par l'utilisateur (AGD5) avant AG3** : la ventilation de la DJA (74x et 131) et celle des aides en 742 à 748. Elles n'ont pas d'effet sur le plan d'AG1, puisque tous ces comptes existent.
- **Q-A3 → dès AG1, sur des cas sûrs** (proposition retenue par défaut, faute de réponse contraire) : vins et alcools à 20 %, par catégorie de produit.
- **Q-A4 → fichiers versionnés + surcharge en méta-base** (03/11/2026, C5).
- **Q-A5 → replier** (03/11/2026) : les sous-comptes de culture sont rattachés au compte du titre 5, et la culture est gardée dans le libellé. AG8 en fera des activités (AGD7).

---

## 12. Sous-lots

| Sous-lot | Contenu | Livrable vérifiable |
|---|---|---|
| **AG1.a** Paramètres et profil | § 4 (fichiers, méta, service, API, écran) ; migration `organization.legal_form_code`, `created_on`, `tax_profiles`, `tax_options`, `simple_categories.excluded_from_micro` ; onglet Fiscalité ; préremplissage Sirene ; contrôles AG0.5 | Tests de résolution datée, des surcharges, des contrôles et de la migration (copie de base) |
| **AG1.b** Référentiel | `build_agri_chart.py`, `plan_comptable_agri.json`, `agri_pcga1986_map.json` ; ajout de `agri` aux énumérations (§ 2), test de concordance ; rôles ; création d'instance en 3 étapes | Instance agri créée, plan chargé, menus filtrés (US-A1, première partie) |
| **AG1.c** États | Bilan EI et société, compte de résultat, SIG, annexe ; exports | Égalité avec `expected.json` du dossier A |
| **AG1.d** Régimes | Mode simple ouvert à `agri` (garde, catégories, livre des recettes, récapitulatif micro-BA, bascule vers le réel) ; régularisations de clôture agricoles (§ 6.3) ; contrôles agricoles (§ 6.5) | US-A8 ; clôture du dossier A avec 441, 4311 et 472 soldé, contrepassée à l'ouverture |
| **AG1.e** Règles | Catégories d'achat (Lexicon), `rules_agri.yml`, contrôle des taux | Suggestion de compte et de TVA à la saisie |
| **AG1.f** Jeu d'essai | Anonymisation, génération, A à D, chargement, E2E | Contrôle de fuite au vert ; `expected.json` relus par l'utilisateur |

**Ordre** : a → b → (c ∥ f) → d → e.
- Le jeu d'essai (f) démarre dès que le plan et la correspondance existent (b).
- Les états (c) se testent sur f.

---

## 13. Tests

- **Unitaires** :
  - `reg_params` : bornes de dates, priorité de la surcharge, `MissingParam` ;
  - contrôles de `tax_profile` (chevauchement, micro interdit pour une société créée après 1997, IS avec régime BA) ;
  - `renounce_by` ;
  - détection du plan agri par `seed_accounts.detect_chart`.
- **Plan** : chaque compte de la liste ANC est présent ; aucun code en double ; la correspondance PCGA 1986 couvre tous les comptes des FEC fictifs ; concordance des énumérations de `chart`.
- **États** : bilan équilibré, passif EI ou société, compte de résultat, SIG et annexe égaux à `expected.json` (A, B, C) ; mêmes clés de premier niveau qu'un autre plan (tableau de bord).
- **Régimes** :
  - micro (D) : livre des recettes, regroupement à 76 €, récapitulatif hors recettes exclues ;
  - régularisations : 441, 4311 et compensation 472 → 402/412, contrepassation à l'ouverture ;
  - bascule micro → réel.
- **Garde** : le mode simple est accessible à `agri` ; reçus et adhérents refusés à `agri` (403) ; aucune régression pour `asso`, `sci` et `societe` (suites existantes).
- **Jeu d'essai** : contrôle de fuite sur la sortie, à chaque génération ; chargement des 4 dossiers.
- **E2E** : création d'une exploitation en 3 étapes ; consultation du bilan agricole ; saisie d'une recette au micro-BA et lecture du livre des recettes.

---

## 14. Risques et points d'attention

| Risque | Parade |
|---|---|
| **Fuite de données réelles** dans les fixtures | Contrôle de fuite bloquant (§ 10.1), relecture, aucune source dans le dépôt, `tests/fixtures/agri/` passé en revue au commit |
| Plan agri inclus dans le plan société : `detect_chart` ambigu | Comptes propres à l'agri (31111, 741…) et test dédié |
| Licence CC-BY-SA des dérivés de Lexicon et d'onoma | `_attribution` dans les fichiers ; mention dans À propos ; ne pas mélanger ces fichiers avec des données sous licence incompatible |
| Paramètres incertains (I) utilisés comme certains | `reliability` exposée partout ; une valeur I s'affiche avec une pastille rouge et « à valider » |
| Clé OSFarm nécessaire seulement pour générer les fichiers | Les scripts lisent `LEXICON_API_KEY` dans l'environnement du développeur ; l'application ne l'utilise pas en AG1 |
| Exercices décalés (31/01, 30/04) | Aucune hypothèse d'année civile, sauf au micro-BA (contrôle) ; les fixtures A, B et C sont décalées |
