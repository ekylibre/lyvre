# Conception : lot AG10, e-facturation et pièces agricoles

> **Statut** : **validée** (06/11/2026, AGD27). Réponses aux questions du § 9 :
> - **Q-E1 Plateforme** : **dépôt de fichiers d'abord**. La plateforme de référence est **SUPER PDP** (documentation lue le 06/11/2026, § 11) ; un connecteur viendra plus tard.
> - **Q-E2 RFA** : renvoi à la documentation SUPER PDP. Elle **ne traite pas le RFA** : ni code d'exonération, ni mention, ni règle de réception (§ 11). Le code reste **à sourcer** (norme XP Z12-012) ; Lyvre n'en invente pas (§ 5).
> - **Q-E3 Décomptes** : schéma du § 4 validé. **Ristournes et compléments de prix dans le compte de vente habituel** de la production (70x), dans l'exercice du décompte.
> - **Q-E4 E-reporting** : d'après SUPER PDP (§ 6 et § 11) : données **au jour au moins**, par **catégorie** (TLB1 biens, TPS1 services…) et par **taux** ; paiements pour les seuls services hors option pour les débits ; calendrier tenu par la PA selon le régime de TVA ; ventes à des particuliers facturées transmises comme des factures (note BAR = B2C).
> - **Q-E5 Import `.ISA`** : oui, lecture des exports réels sans copie ni versionnement, extraits fictifs pour les tests ; priorité : écritures, ateliers, affectations, échéances.
> - **Q-E6 Priorités** : ordre proposé retenu (a → b, puis c → d, puis e).
>
> **Cadrage** : `compta_agri.md` § AG10 et US-A10.
>
> **Réglementation** : `compta_agricole/audit_reglementation.md` § 6.3.
> - Réception des factures électroniques obligatoire depuis le 01/09/2026.
> - Émission et e-reporting au 01/09/2027 pour les PME et TPE, soit la quasi-totalité des exploitations assujetties.
> - Autofacturation très courante : coopératives, laiteries, négoce (CGI art. 289 I-2).
>
> **Échéance du lot** : avant le 01/09/2027.

---

## 1. Ce qui existe et ce qui manque

**Ce qui existe déjà :**
- **Émission Factur-X** (`einvoice.py`, module Ventes) :
  - XML CII au profil EN 16931, inséré dans un PDF/A-3 ;
  - motifs d'exonération (`vat_codes.exemption`), dont la franchise en base ;
  - émission par Qonto, qui répond à l'obligation pour une entreprise assujettie (`design_ventes.md`).
- **Achats** : factures fournisseurs reçues par Qonto ou déposées, lecture des PDF (`invoice_reader`), comptabilisation (`purchase_posting`).
- **Import FEC** (`fec_import.py`, lot F6) : plan de correspondance par compte (existant, mémorisé, à créer).
- **Plan agricole** :
  - correspondance PCGA 1986 → ANC 2020-04 (`data/agri_pcga1986_map.json`, `agri_chart.map_pcga1986`, AG1.b), **non branchée sur l'import FEC** ;
  - variations de stock, aides, parts de coopérative (2621).
- **Jeu d'essai** : `scripts/agri_fixtures/anonymize.py` lit déjà les enregistrements ANA d'un export Isacompta (ateliers, unité, surface).
- **Analytique (AG8)** : ateliers, activités, campagnes, mesures. C'est la cible de la reprise des ateliers.
- **TVA agricole (AG2)** : taux 5,5 %, 10 % et 20 %, RFA, CA12A.

**Ce qui manque :**
- **autofactures reçues** enregistrées comme ventes, avec acceptation ou contestation ;
- **décomptes de coopérative** ;
- **mentions agricoles** dans le Factur-X ;
- **e-reporting B2C** ;
- **reprise Isacompta** (`.ISA`) et **correspondance 1986** à l'import FEC.

## 2. Choix structurants

1. **Pas de connecteur de plateforme agréée (PA) dans un premier temps** (Q-E1). Lyvre lit un **fichier de facture électronique** (Factur-X PDF, CII ou UBL XML), déposé à la main ou repris d'une source connectée. La transmission reste celle de la PA de l'exploitation, comme aujourd'hui avec Qonto.
2. **Une autofacture est une vente.** Elle est enregistrée dans le module Ventes, comme une facture émise au nom du producteur par son client.
   - Le client est la coopérative, la laiterie ou le négociant.
   - Le numéro est celui de l'autofacture.
   - Le statut de cycle de vie est porté par la vente : reçue, acceptée, contestée, refusée (codes de la réforme, § 3).
   - **Pas de numérotation Lyvre**, puisque le client numérote.
3. **Un décompte de coopérative est une pièce composée.** Il porte :
   - des **apports**, en ventes 70x par produit ;
   - des **acomptes déjà versés**, imputés sur la créance ;
   - des **compléments de prix** de campagnes antérieures ;
   - des **ristournes** ;
   - des **retenues** : parts sociales (2621), cotisations, frais de collecte, prélèvements interprofessionnels.
   
   Une seule écriture équilibrée par décompte, sur le compte du tiers coopérative (Q-E3).
4. **E-reporting** : Lyvre **prépare** les données de transaction (par jour, catégorie et taux, ventes à des particuliers) et les exporte dans la forme de l'API SUPER PDP. Il ne les **transmet** pas (Q-E1, Q-E4).
5. **Reprise de dossiers** : on **complète** les imports existants plutôt que d'en créer d'autres.
   - FEC : correspondance 1986 et sous-comptes par culture.
   - `.ISA` : nouveau lecteur, qui alimente plan, journaux, écritures, ateliers et ventilations.

## 3. Autofactures reçues (AG10.1)

- **Dépôt** d'un fichier :
  - Factur-X PDF ou XML CII ou UBL ;
  - type de document 389 (autofacture), ou facture dont le **vendeur** est l'exploitation (SIREN de l'organisation).
- **Lecture** :
  - parties ;
  - numéro et date ;
  - lignes (désignation, quantité, unité, prix, taux de TVA) ;
  - totaux ;
  - mentions (« autofacturation »).
  
  Lyvre contrôle la cohérence : somme des lignes, TVA par taux, SIREN du vendeur.
- **Proposition de vente** :
  - le client est retrouvé par son SIREN, ou créé ;
  - chaque ligne reçoit un compte 70x : par la règle « produit → compte » du catalogue, sinon par la correspondance de la désignation avec les activités (AG8), sinon par saisie.
- **Autofacture** : code **389** dans le type de document (BT-3) ; l'émetteur (le client) agit sous **mandat de facturation** du producteur, déclaré à sa PA (SUPER PDP, « Mandat de facturation »).
- **Cycle de vie**, qui suit les statuts de la réforme (codes listés par SUPER PDP) :
  - **acceptée** (`fr:205`) : la vente est comptabilisée ;
  - **contestée** (`fr:207`) : motif saisi, vente en attente, rappel dans l'échéancier ;
  - **refusée** (`fr:210`) : rien n'est comptabilisé ;
  - **encaissée** (`fr:212`) : notée au rapprochement du règlement.
  
  Le statut est **à transmettre par la PA** (pas d'envoi par Lyvre, Q-E1) : Lyvre affiche le code et le motif à reporter.
- **Doublon** : même client et même numéro → refusé.

**Réalisé (AG10.c)** :
- `einvoice_reader.py` : lecture complète CII (seul ou joint au PDF Factur-X) et UBL (`Invoice`) : type BT-3, numéro, dates, parties (SIREN, SIRET, TVA, adresse), lignes (unités UN/ECE usuelles), remises et frais de pied de facture repris en lignes, ventilation de TVA, totaux, notes. XML avec DOCTYPE ou ENTITY refusé, 1 Mo au plus.
- `self_billing.py` :
  - **contrôles bloquants** : type 389, ou vendeur = SIREN de l'organisation ; vendeur ≠ exploitation ; numéro, date, lignes, client ; euros ; somme des lignes = base HT ; bases par taux ; TVA par taux = total de TVA ; HT + TVA = TTC ; doublon ;
  - **avertissements** : SIREN de l'organisation ou du vendeur absent, TVA d'un taux écartée de plus d'un centime, TVA facturée à un exercice non soumis (RFA, franchise : à contester), net à payer différent du TTC (acomptes), aucun exercice ;
  - **compte proposé par ligne** : produit du catalogue de même désignation, sinon même désignation déjà reçue du client, sinon production Lexicon → activité AG8 → sa règle de compte ;
  - **client** retrouvé par SIREN, n° de TVA ou nom, sinon créé ;
  - **vente reçue** : `self_billed`, `source = received`, numéro du client, montants et TVA du fichier (pas de recalcul), sans écriture ; fichier rangé dans `uploads/<instance>/autofactures/AAAA/MM/` ;
  - **cycle de vie** : reçue → acceptée (écriture VE, `fr:205`), contestée (motif obligatoire, `fr:207`), refusée (statut annulée, `fr:210`) ; contestée → acceptée ou refusée ; « encaissée » (`fr:212`) se lit du règlement ;
  - une autofacture reçue ne se modifie pas et ne prend pas de numéro Lyvre ; elle se supprime tant qu'elle est « reçue ».
- Numéro unique par **client** (contrainte `kind, entity_id, number`, migration `e5f7a9b1c3d5`).
- Échéancier : fiche DIV-07 (source `self_billing_disputes`), rappel à l'échéance des autofactures contestées.
- Écrans : Ventes › Autofactures reçues (plan agricole) ; sur la fiche de vente, Accepter, Contester, Refuser, fichier reçu, code de statut à transmettre.
- **Non fait** : avoir reçu sur autofacture (refusé à la lecture, à saisir à la main) ; ventilation analytique de la ligne (AG10.d).

## 4. Décomptes de coopérative (AG10.1, suite)

- Une **autofacture de coopérative** peut être un décompte complet. À défaut, un **décompte papier ou PDF** se saisit avec le même formulaire.
- Les lignes sont **typées** :

| Type | Compte (validé, Q-E3) | Sens dans le décompte |
|---|---|---|
| Apport (vente) | 70x de la production, TVA au taux de la ligne | crédit |
| Complément de prix | 70x de la production, compte de vente habituel (campagne d'origine indiquée) | crédit |
| Ristourne | 70x de la production, compte de vente habituel | crédit |
| Acompte déjà versé | 411 coopérative (imputation) | débit |
| Parts sociales retenues | 2621 parts de coopératives | débit |
| Cotisations, frais, prélèvements | 62x / 63x (compte proposé par la règle) | débit |
| Net à payer | 411 coopérative, puis banque au règlement | — |

- **Exercice** : compléments de prix et ristournes vont dans les ventes de l'exercice du décompte, même s'ils portent sur une campagne antérieure.
- **Activité** : chaque apport peut porter son activité et sa campagne (AG8), ce qui en fait une ventilation analytique de la ligne de vente.

## 5. Factur-X agricole (AG10.2)

- Les taux 5,5 %, 10 % et 20 % des ventes agricoles sont déjà portés par les codes de TVA (AG2).
- **Producteur au RFA** :
  - sa facture porte la mention propre au remboursement forfaitaire agricole et un motif d'exonération (BT-120 libellé, BT-121 code) ;
  - la documentation SUPER PDP ne donne **ni code ni mention** pour le RFA (§ 11). Le code et le libellé deviennent un **paramètre daté** (`data/regulatory/`) **vide tant qu'il n'est pas sourcé** (norme XP Z12-012, BOFiP) ;
  - tant que ce paramètre est vide, Lyvre **ne produit pas** le Factur-X d'un producteur au RFA et le dit, plutôt que d'émettre un code inventé ;
  - le remboursement forfaitaire n'est pas de la TVA facturée.
- **Mentions nouvelles de la réforme** :
  - SIREN du client ;
  - adresse de livraison ;
  - nature de l'opération (biens, services, mixte) ;
  - option pour le paiement de la TVA d'après les débits.
  
  Les champs existent ou sont ajoutés au module Ventes. Le profil Factur-X reste **EN 16931** (BT-24 `urn:cen.eu:en16931:2017`, valeur acceptée par SUPER PDP).
- **Facture à un particulier** : note **BAR** de valeur `B2C` (SUPER PDP la détecte ainsi et en tire l'e-reporting) ; une facture ne mêle pas biens et services.

## 6. E-reporting B2C (AG10.3)

- **Champ** : ventes à des particuliers (vente directe, marchés, paniers).
- **Sources** :
  - ventes du module sans SIREN client ;
  - opérations de recettes de la comptabilité simplifiée dans des catégories « vente directe » ;
  - encaissements de caisse.
- **Ventes facturées** à des particuliers : elles partent comme des factures (note BAR = B2C, § 5) ; la PA en tire l'e-reporting. Lyvre **les exclut** des agrégats pour éviter le double envoi.
- **Agrégat des ventes sans facture**, d'après SUPER PDP :
  - **par jour au moins** (un envoi peut couvrir plusieurs jours, ligne par ligne) ;
  - par **catégorie** : `TLB1` livraisons de biens (cas courant de la vente directe), `TPS1` prestations de services ; `TNT1` et `TMA1` sont listées par l'API, sans usage prévu dans Lyvre pour l'instant ;
  - par **taux** : base hors taxe, TVA ;
  - rôle `SE` (vente), devise EUR.
- **Paiements** : à déclarer pour les **seules prestations de services**, sauf option pour la TVA d'après les débits (CGI ann. II art. 290 A, cité par SUPER PDP). Les ventes de biens agricoles n'en demandent pas.
- **Périodicité** : la PA déclenche les envois (flux 10.3 et 10.4) selon le **régime de TVA** de l'entreprise (`monthly`, `quarterly`, `simplified`, `vat_exemption` chez SUPER PDP ; le RSA agricole correspond à `simplified`). Les données ne doivent pas arriver après la période. Lyvre n'en recalcule pas le calendrier : il signale les jours non exportés.
- **Sortie** :
  - tableau par période, contrôlé avec le chiffre d'affaires de la CA12A ou de la CA3 ;
  - export **JSON** dans la forme de `POST /v1.beta/b2c_transactions` de SUPER PDP (`date`, `category_code`, `currency`, `role_code`, `tax_exclusive_amount`, `tax_total`, `tax_subtotals[]`), et un tableur ;
  - rappel dans l'échéancier : « exporter l'e-reporting » à la fréquence choisie (pas de date réglementaire inventée).

## 7. Reprise de dossiers (AG10.4, AG10.6, AG10.7)

**FEC des cabinets (Isacompta, Agrigest, ISTEA)** :
- **correspondance PCGA 1986** : le plan de correspondance de l'import propose d'abord `map_pcga1986` (comptes sur 8 chiffres, 704x, 7011xxxx, 713xxxxx, 241/242…), puis la correspondance mémorisée ou la création ;
- **sous-comptes par culture** (7011xxxx, 713xxxxx) : proposés comme **activités** (AG8) d'un atelier, avec une règle de compte, à la fin de l'import ;
- tests sur des FEC fictifs en numérotation Isacompta (les FEC du jeu d'essai A, B, C sont déjà au plan actuel).

**Réalisé (AG10.a)** :
- `agri_chart.resolve_pcga1986` (compte du plan, sous-compte replié) et `old_numbering` : la correspondance ne
  s'applique que dans une instance agricole et à un fichier dont les comptes généraux (hors classe 4) sont sur
  8 chiffres à 90 % au moins, pour ne pas renuméroter un FEC déjà au plan actuel (`60112` resterait sinon `60111`) ;
- `fec_import.plan_accounts` : compte renuméroté → correspondance (`60110000` → 60111) ; sous-compte replié →
  sous-compte du compte du plan, qui garde son numéro sans les zéros de fin quand il commence par celui du compte
  (`70117111`, `512001`), sinon le premier numéro libre (`70120700` → 7011001) ; nature du compte parent ;
  correspondances mémorisées (exercice suivant sans création) ;
- `import_activities` : propositions sur les sous-comptes 7011 à 7014 sans règle, production Lexicon rapprochée
  par les mots du libellé (ambiguïté → aucune), activité existante reprise ; création : atelier par famille,
  activité, règle « compte → activité » ;
- API `GET` / `POST /api/v1/imports/activities` (administrateur, instance agricole) ; écran Reprise d'historique :
  avertissement « ancien plan », mention « plan 1986 » par compte, panneau « Activités proposées ».

**Export Isacompta `.ISA`** :
- format de transfert à enregistrements typés (VER, DOS, EXO, JOU, CPT, TVA, ANA, ECR, MVT, AFF, ECH, POI), encodage DOS ;
- le lecteur se construit en lisant les fichiers réels **sans les copier ni les versionner** (comme pour le jeu d'essai). Seuls des extraits **fictifs** servent aux tests (Q-E5) ;
- **apports** :
  - plan et journaux ;
  - écritures et lignes (comme le FEC) ;
  - **sections ANA** → ateliers et activités AG8, avec leur surface sur la campagne ;
  - **ventilations** `ANAMVT` (ligne) et `ANACPT` (compte) → ventilations et règles analytiques ;
  - échéances `ECHMVT` (information) ;
  - codes de TVA (information) ;
- même écran que l'import FEC : analyse, plan de correspondance, import.

**Réalisé (AG10.b)** — disposition relevée sur 4 exports réels lus sur place (aucune copie), décrite dans
`app/services/isa_import.py` :
- les enregistrements `AFF` sont des **lettrages** (`AFFLET`) et `POI` des **pointages** bancaires (`POINTI`), pas des
  affectations analytiques : la ventilation est dans `ANAMVT` (ligne) et `ANACPT` (compte), en ‰ ;
- lecture : écritures `ECR` + lignes `MVT` (débit, crédit, lettre, date), comptes sur 10 caractères ramenés à
  8 chiffres (`6262000000` → `62620000`), tiers alphanumériques en comptes auxiliaires (`401DUPONT`) ; en-têtes
  `ECR` sans journal ignorés. Sur les 4 exports : toutes les écritures et tous les lettrages équilibrés ;
- import par le même chemin que le FEC (`fec_import.analyze / import_history / import_opening` acceptent un lecteur
  et un traitement complémentaire), donc ancien plan agricole (AG10.a), correspondances, tout-ou-rien ;
- analytique (instance agricole) : feuilles de la hiérarchie des sections = activités, **choisies** à l'écran
  (proposées : ventilées, avec surface ou reconnues dans Lexicon) ; section la plus haute = atelier (famille par
  Lexicon, un mot du libellé, sinon « Administration ») ; surface en hectares sur la campagne en cours au milieu
  de l'exercice ; ventilation sur un **regroupement** de sections → clé « surface » sur ses activités ; origine
  « reprise du dossier » ; une section non reprise laisse la ligne à ventiler ;
- non repris : échéances, pointages, codes de TVA (affichés à l'analyse).

## 8. Données et écrans

**Tables** :
- `sales` : colonnes `self_billed` (autofacture), `lifecycle_status`, `lifecycle_reason`, `received_file`.
- `coop_statements` et `coop_statement_lines` : décompte, type de ligne, compte, campagne, activité.
- `ereporting_days` : jour, catégorie, taux, base, TVA, source, état préparé ou exporté.

**Services** :
- `einvoice_reader.py` : lecture CII et UBL, avec la bibliothèque `factur-x` pour l'extraction du PDF ;
- `self_billing.py` ;
- `coop_statements.py` ;
- `ereporting.py` ;
- `isa_import.py` ;
- branchement de `fec_import.plan_accounts` sur `map_pcga1986`.

**Écrans** :
- Ventes › **Autofactures reçues** : dépôt, contrôle, acceptation ou contestation ;
- Ventes › **Décomptes de coopérative** ;
- TVA › **E-reporting** ;
- Import › **Isacompta (.ISA)**, à côté de l'import FEC.

## 9. Questions

- **Q-E1 Plateforme agréée** : quelle PA utilisent les exploitations ciblées (Qonto, une autre) ?
  - Un connecteur est-il attendu dans AG10, pour recevoir les autofactures et transmettre les statuts et l'e-reporting ?
  - Ou commence-t-on par le dépôt de fichiers (proposition), la transmission restant faite dans la PA ?
- **Q-E2 RFA dans le Factur-X** : quel motif d'exonération et quelle mention doit porter la facture d'un producteur au remboursement forfaitaire ?
  - Je ne veux inventer ni le code VATEX ni le libellé ; as-tu une source (BOFiP, norme ou guide de la DGFiP) ?
  - Et pour la réception : un exploitant au RFA est-il tenu de recevoir ses factures par une PA ?
- **Q-E3 Décomptes de coopérative** : le schéma du § 4 te convient-il ?
  - Apports en 70x ; acomptes imputés sur le 411 ; parts sociales en 2621 ; frais en 62x / 63x.
  - Les **ristournes** vont-elles en produit (quel compte) ou en réduction des ventes ?
  - Les compléments de prix d'une campagne antérieure vont-ils dans les ventes de l'exercice ?
- **Q-E4 E-reporting** :
  - périodicité au RSA (mensuelle ?) ;
  - sources des ventes B2C dans Lyvre (ventes sans SIREN, catégories simples de vente directe, caisse) ;
  - format attendu par la PA, à fournir. À défaut, un tableur et un export par période.
- **Q-E5 Import `.ISA`** : puis-je lire les exports réels de `cultia_back` (sans copie, sans versionnement) pour écrire le lecteur, avec des extraits fictifs pour les tests ?
  - Quelles données reprendre en priorité : écritures, ateliers, affectations, échéances ?
- **Q-E6 Priorités** : faut-il tout livrer pour le 01/09/2027, ou prendre l'ordre proposé ?
  - Reprise FEC et `.ISA` d'abord (utile dès maintenant).
  - Puis autofactures et décomptes.
  - Puis Factur-X agricole et e-reporting.

## 10. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG10.a** ✅ | Import FEC : correspondance PCGA 1986, sous-comptes par culture proposés comme activités | AG8 |
| **AG10.b** ✅ | Import `.ISA` : lecteur, plan, journaux, écritures, ateliers ANA vers AG8, affectations, codes TVA | AG10.a |
| **AG10.c** ✅ | Autofactures reçues : lecture Factur-X / CII / UBL, vente proposée, cycle de vie, doublons | — |
| **AG10.d** | Décomptes de coopérative : lignes typées, écriture, activités | AG10.c |
| **AG10.e** | Factur-X agricole (RFA sous réserve du code sourcé, nouvelles mentions, note B2C) et e-reporting B2C (agrégats jour × catégorie × taux, contrôle, export JSON SUPER PDP) | AG10.c |

Ordre retenu (Q-E6) : a → b, puis c → d, puis e.

## 11. Documentation SUPER PDP lue (06/11/2026)

Sources : documentation `https://www.superpdp.tech/documentation/…` (articles « Démarrage rapide », « Calendrier », « Authentification », « Formats de facture », « Synchronisation », « E-reporting », « Mandat de facturation », « FAQ », « API AFNOR ») et référence OpenAPI `https://api.superpdp.tech/openapi/superpdp.json` (version 1.39.0.beta). Rien n'est copié dans le dépôt.

- **Formats** : Factur-X, CII et UBL (France), JSON EN 16931 ; validateur `POST /v1.beta/validation_reports` ; conversion `POST /v1.beta/invoices/convert`.
- **Calendrier France** : réception obligatoire à septembre 2026, émission à septembre 2027.
- **Authentification** : OAuth 2.1 (client credentials, ou authorization code pour un logiciel de gestion) ; bac à sable.
- **Réception** : `GET /v1.beta/invoices` et `GET /v1.beta/invoice_events` avec `starting_after_id` (synchronisation exhaustive).
- **Statuts** `fr:200` à `fr:213` et `fr:501` (déposée, émise, reçue, mise à disposition, prise en charge, approuvée, partiellement approuvée, en litige, suspendue, complétée, refusée, paiement transmis, encaissée, rejetée, irrecevable) ; envoi d'un statut par `POST /v1.beta/invoice_events`.
- **Autofacture** : cas du mandat de facturation (AFNOR XP Z12-014, cas d'usage 19a et 19b ; BOI-TVA-DECLA-30-20-10) ; code 389 en BT-3 ; mandat déposé et vérifié par la PA.
- **E-reporting** : voir § 6 ; API `b2c_transactions`, `b2c_payments`, `ereportings` (aperçu et historique).
- **RFA** : **absent** de la documentation et de l'OpenAPI (aucune occurrence de « agricole », « forfaitaire », « VATEX »). Le motif d'exonération est un champ libre (`exemption_reason`, `exemption_reason_code`).
