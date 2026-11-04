# Conception : lot AG3, aides PAC et subventions

> **Statut** : **validée** (04/11/2026, AGD20), réponses de l'expert-comptable au § 10 :
> - Q-P1 : plan agricole, couplées en 743 et découplées en 745, sous-comptes facultatifs ;
> - Q-P2 : 744 pour l'ICHN, les MAEC et l'aide bio, 742 pour l'aide à l'assurance récolte ;
> - Q-P3 : part d'exploitation de la DJA en **744**, ventilation saisie ;
> - Q-P4 : décision d'attribution ;
> - Q-P5 : clé OSFarm disponible (`LEXICON_API_KEY` dans `.env`), AG3.e maintenu ;
> - Q-P6 : rattachement proposé puis confirmé ;
> - Q-P7 : reprise saisie pour un bien non amortissable, reprise du solde à la cession.
>
> **AG3.a réalisé (04/11/2026, non commité)**. Contenu :
> - `data/aids/schemes.yml` : 16 dispositifs (comptes AGD20, fait générateur, payeur, versements types, proposition en campagne PAC), contrôlés au chargement ;
> - tables `aids` et `aid_payments` (migration `d0e2f4a6b8c9`), `app/models/aid.py` ;
> - `app/services/aids.py` :
>   - sous-compte proposé (7451…) créé sous son parent à la création du dossier, ou parent gardé ;
>   - fait générateur : date limite PAC de l'année (`agenda.pac.deadline`, `cattle_deadline` pour les aides animales), sinon 15/05 « à confirmer » ; décision saisie ;
>   - montant acquis = notifié, sinon demandé ; reste à percevoir ; statut « attribuée » à la saisie du notifié ;
>   - versements saisis à la main, reversement en négatif ;
>   - alertes : versé au-delà de l'acquis, décision à saisir, ventilation d'une aide mixte, date limite de demande de paiement dépassée ;
>   - nouvelle campagne PAC proposée d'après le profil (drapeaux PAC et JA, productions) ;
> - API `/aids`, `/aids/<id>`, `/aids/<id>/payments`, `/aids/schemes`, `/aids/pac-campaign` (plan agricole, partie double et mode simple) ;
> - écran Compta › **Aides et subventions** (`/aids/`) : liste par campagne, totaux, fiche en tiroir (montants, dates, versements), nouveau dossier, nouvelle campagne PAC.
>
> Écarts avec la conception :
> - tables `aid_assets` et `aid_accruals` créées avec leurs sous-lots (AG3.d et AG3.c), pas dans cette migration ;
> - le compte se modifie par son numéro (pas de sélecteur), le financeur (`funder_entity_id`) par l'API seulement ;
> - la règle bancaire « Aides PAC (ASP) » comptabilise toujours en 745 : le compte du dossier sera proposé au rattachement (AG3.b).
>
> Tests : `tests/api/test_aids.py` (8 tests), `frontend/src/features/aids/aids.test.tsx` (3 tests).
>
> **AG3.b réalisé (04/11/2026, non commité)**. Contenu :
> - `data/aids/payers.yml` (ASP, FranceAgriMer, Région, DDT), mots entiers du libellé ou de la contrepartie, normalisés comme l'échéancier ;
> - `app/services/aid_payments.py` :
>   - candidats d'un crédit : dossiers ouverts avec un reste à percevoir, ceux du payeur reconnu d'abord, puis le reste égal au virement, l'écart, la proximité de l'avance (16/10) ou du solde (1/12) de la campagne ;
>   - rattachement **confirmé par l'utilisateur** (Q-P6), ventilé sur plusieurs dossiers, sans dépasser le montant restant du virement ;
>   - virement libre **comptabilisé** au rattachement s'il est entièrement ventilé : journal BQ, banque au débit, une ligne par compte de dossier ; aide mixte au prorata de la part d'investissement (131 / 744) ; en comptabilité simplifiée, sur la catégorie de recette du compte ou d'un parent (7451 → 745) ;
>   - virement déjà comptabilisé : jamais réécrit, compte différent du dossier signalé ;
>   - détacher un virement (depuis la fiche du dossier) garde son écriture ;
> - API `GET /aids/candidates?bank_transaction_id=`, `POST /aids/link` ;
> - Banque › Transactions : action « Rattacher à une aide » sur un crédit d'un payeur connu ou déjà en partie rattaché, dossiers rattachés sous le libellé ; fenêtre de ventilation (`LinkAidModal`) ;
> - clôture (plan agricole) : contrôle d'information « virements reçus d'un payeur d'aides rattachés à aucun dossier ».
>
> Écarts avec la conception :
> - **DGFiP absente des payeurs** : ses virements sont surtout des remboursements de TVA (44583) ; un virement d'aide de la DGFiP se rattache depuis un autre payeur ou à la main ;
> - un virement d'un payeur inconnu ne montre pas l'action dans Transactions ; il reste rattachable par l'API ;
> - pas de règle bancaire modifiée : la règle « Aides PAC (ASP) » comptabilise toujours en 745 ; dans ce cas l'écart de compte avec le dossier est signalé.
>
> Tests : `tests/api/test_aid_payments.py` (6 tests), `frontend/src/features/aids/linkAid.test.tsx` (1 test).
>
> **AG3.c réalisé (05/11/2026, non commité)**. Contenu :
> - table `aid_accruals` (migration `e1f3a5b7c9d0`) : décision de clôture par dossier et par exercice (montant passé et motif d'écart, ou proposition écartée et son motif) ;
> - `app/services/aid_closing.py` (plan agricole, partie double seulement) :
>   - fait générateur au plus tard à la clôture → **aide à recevoir** = acquis − versé à la clôture, D 441 / C compte du dossier ;
>   - versé avant un fait générateur postérieur à la clôture → **produit constaté d'avance**, D compte du dossier / C 487 ;
>   - aide mixte (DJA) : part d'exploitation seulement (acquis et versé au prorata de la ventilation), sur le compte d'exploitation (744) ;
>   - écritures d'inventaire (`add_inventory`, `source_ref` `aid:<id>` / `aid-deferred:<id>`), donc extournées à l'ouverture ; supprimée depuis la clôture, la proposition revient ; un montant différent du calcul et une proposition écartée demandent un motif (5 caractères) ;
>   - signalés sans écriture : décision non datée, ventilation manquante, versé au-delà de l'acquis ; dossiers soldés ou refusés ignorés ;
> - contrôles de clôture : aides à recevoir non passées ni écartées (**anomalie**), produits perçus d'avance proposés, dossiers à compléter, solde du 441 différent des aides à recevoir passées (**informations**) ;
> - API `GET/POST /fiscal-years/<id>/closing/aids`, `POST /fiscal-years/<id>/closing/aids/dismissed`, `DELETE …/dismissed/<aid_id>` ;
> - Clôture › Inventaire : panneau « Aides et subventions à la clôture » (`AidAccrualPanel`) ;
> - échéancier : règle `lyvre` de source `aids` sur PAC-07 (date limite de la demande de paiement de chaque dossier ouvert, rappels J-60 et J-15, « fait » quand la demande est notée, lien vers la campagne) ; PAC-03 (avance, solde) renvoie vers `/aids/` ;
> - un dossier dont une aide à recevoir est passée ne se supprime plus.
>
> Écarts avec la conception :
> - seuls les dossiers dont la campagne précède ou égale l'année de clôture sont examinés ;
> - le contrôle du 441 compare au total des aides à recevoir passées : l'octroi d'une subvention d'investissement en 441 (AG3.d) le fera apparaître tant que le contrôle n'en tient pas compte (à ajuster en AG3.d).
>
> Tests : `tests/api/test_aid_closing.py` (7 tests), `frontend/src/features/aids/aidAccrual.test.tsx` (2 tests).
>
> **AG3.d réalisé (05/11/2026, non commité)**. Contenu :
> - migration `f2a4b6c8d0e1` : `aids.grant_entry_id`, tables `aid_assets` (immobilisations financées, montant affecté) et `aid_releases` (reprises figées par exercice, reprises saisies) ; sources d'écriture gérées `AID_GRANT` et `AID_RELEASE` (hors livres de TVA) ;
> - `app/services/aid_grants.py` (partie double seulement) :
>   - **octroi** D 441 / C 131 à la date de la décision, avant le premier versement ; les virements rattachés ensuite soldent le 441 (AG3.b adapté) ; annulable tant qu'aucun versement n'est rattaché ;
>   - **immobilisations financées** : total affecté ≤ part d'investissement ; figées dès qu'une reprise est passée ;
>   - **reprise** = affecté × dotation de l'exercice ÷ base amortissable (`assets.schedule`), la dernière solde l'arrondi ; à la cession ou mise au rebut, le reste sur l'exercice de sortie ; écriture OD unique D 139 / C 747 au dernier jour, non extournée, repassable tant que l'exercice est ouvert ;
>   - **bien non amortissable** : pas de reprise calculée ; reprise saisie avec un motif, passée avec l'écriture (Q-P7) ;
>   - **DJA** : sa part d'investissement suit ces règles (octroi, affectation, reprise) ;
>   - annexe : montant, reprises antérieures et de l'exercice, reste (131 − 139), part non affectée signalée ;
> - contrôles : reprise de l'exercice non passée (information) ; le contrôle du 441 compte les octrois restant à percevoir ;
> - API `POST/DELETE /aids/<id>/grant`, `PUT /aids/<id>/assets`, `GET/POST/DELETE /fiscal-years/<id>/closing/aid-releases`, `POST /…/aid-releases/manual`, `DELETE /…/manual/<id>` ;
> - écrans : section « Subvention d'investissement » de la fiche du dossier (octroi, immobilisations financées) ; panneau « Reprise des subventions d'investissement » et annexe dans Clôture › Inventaire.
>
> Écarts avec la conception :
> - l'annexe est dans le panneau de clôture, pas encore dans l'export des états agricoles (XLSX) ni à côté de l'annexe des biens vivants ;
> - pas de rattrapage : une subvention liée à un bien déjà en partie amorti n'est reprise qu'à partir de l'exercice ouvert, et la dernière reprise solde le reste ;
> - octroi refusé si des versements existent déjà : on garde alors la pratique « versement directement en 131 ».
>
> Tests : `tests/api/test_aid_grants.py` (4 tests), `frontend/src/features/aids/grants.test.tsx` (2 tests).
>
> **AG3.e réalisé (05/11/2026, non commité) — lot AG3 terminé (a à e)**. Contenu :
> - API Lexicon lue dans le code de `lexicon-rest-api` (v1.6.2) : `GET /links/enterprises/<siren>.json`, réservée aux membres, clé en `Authorization: Bearer` ; champ `cap-by-year` (FEAGA, FEADER, cofinancé, total, en euros) ; ni filtre par année ni détail par intervention par HTTP. Clé du serveur vérifiée le 05/11/2026 avec un SIREN fictif (404 avec la clé, 401 sans) ;
> - `app/services/lexicon.py` : client (délai 15 s, erreurs 401/403/429/réseau traduites, montants convertis en centimes), configuration `LEXICON_API_KEY` / `LEXICON_URL` (`.env.example`, `doc/docker.md`) ;
> - table `cap_published` (migration `a3b5c7d9e1f2`) : cache par SIREN et par année dans l'instance, jamais cumulé entre années, relu à la demande ;
> - `app/services/aid_cap.py` : pour une année civile, publié contre versements rattachés aux dossiers et mouvements des comptes 74 (sauf 741 et 747) et 131, hors écritures de clôture (inventaire, extournes, à-nouveaux, octrois, reprises) ; écarts en information ;
> - API `GET /aids/cap-check?year=` (cache, lecture de Lexicon au premier appel), `POST /aids/cap-check` (relecture, refusée à l'expert-comptable) ;
> - carte « Montants publiés par l'ASP » sous la liste des dossiers (année de la campagne affichée), masquée sans clé.
>
> Écarts avec la conception :
> - comparaison par **année civile** de paiement côté Lyvre ; l'exercice budgétaire de l'UE (mi-octobre à mi-octobre) n'est pas reconstitué ;
> - pas de détail par aide : Lexicon ne publie par HTTP que les totaux par année et par fonds ;
> - le SIREN de l'exploitation part chez Lexicon (OSFarm) à chaque relecture ; aucune autre donnée n'est envoyée.
>
> Tests : `tests/api/test_aid_cap.py` (4 tests, Lexicon simulé), `frontend/src/features/aids/capCheck.test.tsx` (2 tests).
>
> **Besoins** : `claudedocs/compta_agri.md`, lot AG3 (AG3.1 à AG3.6), décision AGD19 (rattachement), réponses d'expert du § 8 (comptes 742 à 748).
> **Socle** :
> - lot AG1 : plan `agri` (titre 5 du Recueil PCG 2026), mode simple du micro-BA, écritures d'inventaire de la clôture ;
> - immobilisations (lot F5) ;
> - échéancier AG9a : fiches `data/deadlines/pac.yml`, `payees.yml`, rapprochement des paiements.

---

## 1. Constats

### 1.1 Le plan agricole range les aides par nature

Le titre 5 du Recueil PCG 2026 (p. 635), retenu pour le plan `agri` (décision AG1), donne :

| Compte | Libellé (titre 5) |
|---|---|
| 741 | Remboursement forfaitaire de TVA (AG2.e) |
| 742 | Indemnités liées à la production agricole |
| 743 | Subventions aux produits |
| 744 | Subventions aux structures |
| 745 | Subventions au revenu |
| 747 | Quote-part des subventions d'investissement virée au résultat de l'exercice |
| 748 | Autres subventions d'exploitation |
| 131 / 139 | Subventions d'investissement octroyées / inscrites au compte de résultat |
| 441 | État – Subventions et aides à recevoir |

**Écart avec la réponse d'expert du § 8** : cette réponse décrit la numérotation du **PCG général**. Dans ce plan :
- 742 est la subvention d'équilibre ;
- 745 regroupe les subventions des organismes internationaux, subdivisé en 7451 (découplé) et 7454 (couplé).

Le plan agricole donne un autre sens à 742, 743 et 745. Les deux lectures se rejoignent sur un point : **les aides découplées vont en 745**. Elles divergent sur les aides couplées, en 743 dans le plan agricole et en 7454 dans la réponse (Q-P1).

### 1.2 Les dossiers fictifs suivent le plan agricole

Ces dossiers sont dérivés des dossiers réels (AGD2) :
- les virements de l'ASP vont en **745** ;
- les indemnités (sinistre, assurance) vont en **742** ;
- les subventions d'investissement vont en **131 / 139**, et leur reprise en 77 (777 du PCGA 1986, **747** dans le plan agricole) ;
- à la clôture, une écriture d'inventaire (journal EX) passe le reste à recevoir en **D 441 / C 745**. Elle est extournée à l'ouverture.

C'est le mécanisme de l'AGD19, et Lyvre le sait déjà faire :
- `closing.add_inventory(kind="accrued_income", counterpart 441, source_ref=…)` écrit l'écriture ;
- les à-nouveaux l'extournent.

### 1.3 Ce qui existe déjà

- **Mode simple (micro-BA)** : catégories « Aides PAC découplées » (745) et « Aides couplées » (743). Les aides y sont prises à l'encaissement, sans produit à recevoir (AGD19).
- **Règles bancaires** (`data/rules_agri.yml`) : « Aides PAC (ASP) » vers 745 et « Aides FranceAgriMer » vers 748.
- **Échéancier** :
  - PAC-01 : date limite de la demande, paramètre `agenda.pac.deadline` ;
  - PAC-03 : avance et solde ;
  - PAC-06 : fin du plan JA ;
  - PAC-07 : demande de paiement des aides FranceAgriMer et régionales, renvoyée au registre d'AG3.
- **Rapprochement des paiements** d'AG9a :
  - il ne traite que les débits ;
  - le dictionnaire des payeurs (`payees.yml`) ne connaît ni l'ASP, ni FranceAgriMer, ni la Région.
- **Lexicon** : pas de client dans Lyvre. Le jeu `cap_beneficiaries` (aides versées par bénéficiaire et par année, licence LO 2.0) n'est accessible que par l'API ou le MCP d'OSFarm (AGD4).

---

## 2. Choix structurants

1. **Un registre de dossiers d'aide**, distinct des écritures :
   - le dossier porte la campagne, le dispositif, les montants (demandé, notifié, versé) et le compte ;
   - les écritures restent celles de la banque et de l'inventaire.
2. **Les versements continuent de passer par la banque.** Le virement est comptabilisé comme aujourd'hui (règle ou saisie), puis rattaché à un ou plusieurs dossiers. Il ne passe pas par 441 en cours d'exercice : c'est la pratique des dossiers réels. Le PCG (art. 618-6) et l'AGD19 sont respectés à la clôture.
3. **Clôture : un produit à recevoir par dossier.** Montant = montant acquis (notifié, sinon demandé) − versé à la date de clôture, si le fait générateur est dans l'exercice (§ 4). L'écriture passe par `add_inventory`, avec `source_ref = "aid:<id>"` ; elle est donc extournée à l'ouverture.
4. **Les dispositifs sont des données datées** (`data/aids/schemes.yml`) : libellé, pilier, nature, compte proposé, fait générateur, payeur, calendrier type. Les comptes sont des **propositions** (AGD5) ; le dossier garde le compte choisi.
5. **Subventions d'investissement** :
   - octroi en 131 ;
   - reprise annuelle en D 139 / C 747, au rythme de l'amortissement des immobilisations financées, calculée depuis les plans d'amortissement existants ;
   - la DJA « mixte » se ventile en une part d'exploitation et une part d'investissement.
6. **Au micro-BA**, le registre sert au suivi (montants, versements, dates limites) ; il ne produit **aucune écriture** d'inventaire ni de reprise.
7. **Pas de connexion à telepac** : AG3.6 (import de la déclaration) reste hors lot.

---

## 3. Dispositifs et comptes proposés (AG3.2)

`data/aids/schemes.yml`, une entrée par dispositif :

```yaml
- key: basic_income          # aide de base au revenu (DPB)
  label: Aide de base au revenu (DPB)
  pillar: 1
  nature: operating          # operating | investment | mixed
  account: "7451"            # proposé ; créé sous 745 s'il manque
  trigger: pac_deadline      # pac_deadline | decision | payment
  payer: ASP
  payments: [advance, balance]
  reliability: R
```

| Dispositif | Pilier | Compte proposé | Fait générateur | Sûreté |
|---|---|---|---|---|
| Aide de base au revenu (DPB activés) | 1 | 745 → 7451 | date limite PAC | PCG 618-6 |
| Paiement redistributif | 1 | 745 → 7452 | date limite PAC | PCG 618-6 |
| Écorégime | 1 | 745 → 7453 | date limite PAC | PCG 618-6 |
| Aide complémentaire au revenu des jeunes agriculteurs | 1 | 745 → 7454 | date limite PAC | PCG 618-6 |
| Aides couplées animales | 1 | 743 → 7431 | date limite de la demande animale (PAC-02) | validé (Q-P1) |
| Aides couplées végétales | 1 | 743 → 7432 | date limite PAC | validé (Q-P1) |
| ICHN | 2 | 744 → 7441 | date limite PAC | validé (Q-P2) |
| MAEC | 2 | 744 → 7442 | date limite PAC | validé (Q-P2) |
| Aide à la conversion bio | 2 | 744 → 7443 | date limite PAC | validé (Q-P2) |
| Aide à l'assurance récolte | 2 | 742 → 7421 | date limite PAC | validé (Q-P2) |
| Calamités agricoles, indemnités de crise | — | 742 | décision | pratique des dossiers |
| Aides FranceAgriMer d'exploitation, aides régionales d'exploitation | — | 748 | décision | validé (Q-P4) |
| Investissements (PCAE, FEADER, Région, FranceAgriMer) | 2 | 131 | décision | PCG |
| DJA | 2 | mixte : 131 + 744 | décision | validé (Q-P3) |
| Autre | — | saisi | saisi | — |

Les sous-comptes à quatre chiffres ne sont **pas imposés**. Quand le dispositif propose un sous-compte absent du plan de l'exploitation, Lyvre propose de le créer sous son compte parent, ou de garder le parent. Un dossier ouvert garde son compte, même si `schemes.yml` change.

---

## 4. Rattachement à l'exercice (AG3.3, AGD19)

| `trigger` | Date du fait générateur | Montant acquis |
|---|---|---|
| `pac_deadline` | date limite de la demande de la campagne (`agenda.pac.deadline`, ou `small_ruminants_deadline` / `cattle_deadline` pour les aides animales) | notifié, sinon demandé (« estimé avec une fiabilité suffisante », PCG 618-6) |
| `decision` | date de la décision d'attribution saisie sur le dossier | notifié |
| `payment` | date de chaque versement | versé |

À la clôture d'un exercice au réel (partie double), pour chaque dossier d'exploitation :
- **fait générateur dans l'exercice, ou antérieur** : produit à recevoir = acquis − versé au plus tard à la clôture, s'il est positif ;
- **versement reçu avant le fait générateur** (rare : exercice qui se termine entre le versement et la date limite) : signalé, avec une proposition de **produit constaté d'avance (487)** ;
- **versé > acquis** (reversement, pénalité) : signalé, sans écriture ;
- dossier refusé ou clos : rien.

Le panneau « Aides à recevoir » de l'écran Clôture liste ces propositions. Pour chacune, on peut :
- **passer l'écriture**, ou toutes à la fois ;
- **corriger le montant** : un écart avec le calcul demande un motif, conservé ;
- **écarter la proposition**, avec un motif.

Une proposition passée se repère par `source_ref` et n'est pas reproposée. La supprimer depuis la clôture la fait réapparaître.

Contrôles ajoutés à la clôture (`_agri_checks`) :
- dossier de la campagne dont le fait générateur est dans l'exercice, sans produit à recevoir et non soldé (**anomalie**) ;
- solde du 441 différent des produits à recevoir des dossiers (**information**) ;
- versement de l'ASP non rattaché à un dossier (**information**).

Au micro-BA, le panneau et les contrôles sont masqués.

---

## 5. Versements et rapprochement bancaire (AG3.4)

- **Payeurs** : `data/aids/payers.yml`, avec la même normalisation que `payees.yml` :
  - ASP, AGENCE DE SERVICES ET DE PAIEMENT ;
  - FRANCEAGRIMER ;
  - DRFIP, DGFIP ;
  - REGION, CONSEIL REGIONAL ;
  - la règle bancaire `rules_agri.yml` reste celle du compte.
- **Proposition** : un **crédit** d'un payeur, non encore rattaché, est proposé contre les dossiers ouverts de ce payeur :
  - tri par montant restant à percevoir, puis par proximité avec le calendrier type (avance d'octobre, solde de décembre) ;
  - **pas de rattachement automatique** : un seul virement de l'ASP réunit souvent plusieurs aides (Q-P6).
- **Ventilation** : un virement peut se répartir sur plusieurs dossiers (`aid_payments.amount_cents`). La somme ne dépasse pas le montant du virement.
- **Comptabilisation** : si le virement n'est pas encore comptabilisé, le rattachement propose les comptes des dossiers, une ligne par dossier. S'il l'est déjà sur un autre compte (par exemple 745 par la règle, alors que le dossier est en 743), Lyvre le signale sans réécrire l'écriture validée.
- **Saisie manuelle** : un versement sans relevé (compensation, retenue MSA) se saisit sur le dossier, avec sa date et son montant, sans lien bancaire.

Le rapprochement des paiements d'AG9a reste dédié aux débits. Les deux services partagent seulement la normalisation des libellés (`deadlines.normalize`).

---

## 6. Subventions d'investissement et DJA (AG3.2)

### 6.1 Octroi et reprise

- **Octroi** : à la décision, Lyvre propose l'écriture D 441 / C 131 (journal OD, date de la décision). Le versement solde ensuite le 441.
  - La pratique « versement directement en 131 » reste possible : le dossier note alors que l'octroi n'a pas d'écriture.
- **Financement** : le dossier se lie à une ou plusieurs immobilisations (`aid_assets`, montant affecté à chacune). Le total affecté égale le montant de l'aide, ou en reste en dessous avec un avertissement.
- **Reprise** à chaque exercice, pour chaque immobilisation financée :
  - formule : reprise = montant affecté × dotation de l'exercice ÷ base amortissable de l'immobilisation ;
  - les dotations viennent de `assets.schedule`, les dotations figées comprises ;
  - écriture **D 139 / C 747**, datée de la clôture, une par exercice, détaillée par dossier (source `aid_reprise`) ;
  - elle se regénère tant que l'exercice est ouvert, comme les dotations ;
  - la dernière reprise solde l'écart d'arrondi.
- **Immobilisation non amortissable** (terre) : pas de reprise automatique ; une reprise saisie se justifie par un motif (Q-P7).
- **Cession ou mise au rebut** d'une immobilisation financée : la part non reprise est proposée en reprise, sur l'exercice de la cession (Q-P7).
- **Annexe** : tableau des subventions d'investissement (montant, reprises cumulées, reste en 131 − 139), placé à côté de l'annexe des biens vivants.

L'étalement fiscal de la subvention d'équipement suit en principe l'amortissement. Le texte exact (CGI, art. 42 septies) sera vérifié et cité au lot AG6, qui calcule le résultat fiscal.

### 6.2 DJA

- Un dossier `mixed` porte une **part d'investissement** (montant ou pourcentage) :
  - la part d'investissement suit le § 6.1 (131, reprise liée aux immobilisations du plan d'entreprise) ;
  - la part d'exploitation suit le § 4, avec `trigger: decision`, en 744 par défaut (Q-P3) ;
  - la ventilation se fait par **saisie**, pas de prorata calculé, comme validé (Q-P3).
- Versement en deux fractions : à l'installation, puis au contrôle de fin de plan (PAC-06). Chaque fraction se répartit entre les deux parts au prorata de la ventilation.
- L'option fiscale d'étalement de la DJA et l'abattement JA relèvent d'**AG6** (AG6.5). AG3 enregistre seulement la date d'octroi, reprise par le profil (`young_farmer_since`).

### 6.3 Date limite de demande de paiement (AG3.1)

- Chaque dossier d'investissement peut porter une date limite de demande de paiement, et chaque dossier une date de fin d'engagement.
- Ces dates entrent dans l'échéancier avec une nouvelle règle `lyvre.aids` de la fiche PAC-07 :
  - une occurrence par dossier ouvert ;
  - lien vers le dossier ;
  - rappels à J-60 et J-15 ;
  - statut « fait » dès que la demande est notée sur le dossier.

---

## 7. Contrôle avec les montants publiés (AG3.5)

- **Source** : jeu `cap_beneficiaries` de Lexicon, interrogé par SIREN et par année, **sans cumul entre années**.
  - Le client Lexicon est à créer : clé OSFarm côté serveur (`LEXICON_API_KEY`, AGD4) et cache par SIREN et par année.
  - Sans clé, l'écran l'indique et ne fait aucun appel (Q-P5).
- **Comparaison** : pour une année, total publié (FEAGA + FEADER) contre les versements rattachés aux dossiers de cette année de paiement et le solde des comptes 74x et 131 de la période.
  - L'année publiée est une année de paiement, budgétaire de l'UE, pas un exercice ni une campagne : l'écart s'affiche en **information seulement**.
- **Données personnelles** : un exploitant individuel peut y figurer sous son nom. Les montants lus restent dans le cache de l'instance et ne sont jamais versionnés ni journalisés.

---

## 8. Données, API, écrans

### 8.1 Tables (base de l'instance, une migration)

- `aids` :
  - `id`, `scheme`, `label`, `campaign` (année), `funder_entity_id`, `payer` ;
  - `nature` (operating, investment, mixed), `account_id` (74x ou 131), `operating_account_id` (part d'exploitation d'une aide mixte), `investment_share_cents` ;
  - `trigger`, `decision_on`, `requested_cents`, `notified_cents`, `notified_on` ;
  - `payment_request_deadline`, `payment_requested_on`, `commitment_end_on` ;
  - `status` (requested, granted, closed, refused), `notes`, `created_at`, `updated_at`.
- `aid_payments` : `id`, `aid_id`, `paid_on`, `amount_cents` (négatif pour un reversement), `kind` (advance, balance, installment, clawback, other), `bank_transaction_id` (nullable), `created_at`.
- `aid_assets` : `aid_id`, `asset_id`, `amount_cents` (clé unique sur le couple).
- `aid_accruals` : `aid_id`, `fiscal_year_id`, `proposed_cents`, `amount_cents`, `reason`, `status` (posted, dismissed), `journal_entry_id`.

### 8.2 Services

- `app/services/aids.py` : dispositifs, dossiers, montants acquis, reste à percevoir, fait générateur ;
- `aid_payments.py` : candidats, ventilation, comptabilisation proposée ;
- `aid_closing.py` : produits à recevoir, contrôles, reprises, annexe ;
- `lexicon.py` (AG3.e).

### 8.3 API

- `GET/POST /aids` (filtres `campaign`, `status`) ;
- `GET/PUT/DELETE /aids/<id>` ;
- `GET /aids/schemes` ;
- `POST /aids/<id>/payments`, `DELETE /aids/<id>/payments/<pid>` ;
- `GET /aids/candidates?bank_transaction_id=` ;
- `GET /aids/accruals?fiscal_year_id=`, `POST /aids/accruals` (passer, corriger, écarter) ;
- `GET /aids/grants?fiscal_year_id=` (subventions d'investissement, reprises) ;
- `GET /aids/cap-check?year=` (AG3.e).

L'expert-comptable (lecture seule) lit tout et n'écrit rien.

### 8.4 Écrans

- **Compta › Aides et subventions** (`/aids/`, plan agricole), une liste par campagne :
  - colonnes : dispositif, montant demandé, notifié et versé, reste à percevoir, compte, statut ;
  - fiche en tiroir : versements, immobilisations financées, dates limites ;
  - bouton « Nouvelle campagne PAC » : il crée en une fois les dossiers cochés du profil (aide de base, redistributif, écorégime, aides couplées selon les productions, ICHN…).
- **Transactions** : sur un crédit d'un payeur connu, action « Rattacher à une aide », avec la ventilation.
- **Clôture** : panneau « Aides à recevoir » (§ 4) et « Reprises de subventions » (§ 6.1).
- **Échéancier** : dates des dossiers (§ 6.3). PAC-03 renvoie vers `/aids/`.

---

## 9. Ce qui n'est pas dans AG3

- import telepac (AG3.6) et DPB en comptabilité matière hors bilan (PCG 618-5) : les DPB acquis restent des immobilisations incorporelles saisies dans les immobilisations ;
- étalement fiscal de la DJA, abattement JA, réintégrations : AG6 ;
- simulation du montant des aides : calculette 16 d'AG12 ;
- aides hors exploitation agricole (associations) : les fonds dédiés existants.

---

## 10. Questions à valider (expert-comptable, AGD5)

- **Q-P1 Comptes des aides couplées.** Le plan agricole range les aides couplées en **743 « Subventions aux produits »** et les découplées en 745. La réponse du § 8 les met en 7454, sous 745.
  - Proposition : suivre le plan agricole (743 et 745), conformément à la décision AG1 « le titre 5 l'emporte », avec des sous-comptes facultatifs.
- **Q-P2 ICHN, MAEC, aide bio, aide à l'assurance récolte.**
  - Proposition : 744 pour les trois premières (aides liées à la structure ou au territoire), 742 pour l'aide à l'assurance récolte.
  - L'aide à l'assurance récolte pourrait aussi venir en déduction de la prime (616) ou aller en 748.
- **Q-P3 DJA.**
  - Compte de la part d'exploitation : 748 proposé, ou 744 ?
  - Ventilation saisie suffisante, ou faut-il un prorata selon le plan d'entreprise ?
- **Q-P4 Fait générateur des autres subventions d'exploitation** (FranceAgriMer, Région, calamités) : la **décision d'attribution** convient-elle ?
- **Q-P5 Accès à Lexicon** : dispose-t-on d'une clé OSFarm (AGD4) ?
  - Sans clé, AG3.e est reporté ; le MCP anonyme, limité à 30 requêtes, n'est pas prévu pour un service.
- **Q-P6 Rattachement des virements** : proposé puis confirmé (recommandé, car un virement de l'ASP réunit plusieurs aides), ou automatique quand un seul dossier ouvert du payeur correspond au centime près ?
- **Q-P7 Reprise hors amortissement** :
  - subvention d'un bien non amortissable : reprise saisie seulement ?
  - cession d'un bien financé : reprise du solde à la cession ?

---

## 11. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG3.a** | `schemes.yml`, tables, service et API des dossiers, écran `/aids/` (liste, fiche, nouvelle campagne PAC), versements saisis à la main ; plan agricole, partie double et mode simple | — |
| **AG3.b** | `payers.yml`, candidats sur un crédit, ventilation d'un virement, comptes proposés à la comptabilisation, action dans Transactions ; contrôle « versement de l'ASP non rattaché » | AG3.a |
| **AG3.c** | Produits à recevoir à la clôture (`aid_accruals`, `add_inventory`, extourne), produit constaté d'avance signalé, contrôles de clôture ; PAC-03 et règle `lyvre.aids` dans l'échéancier | AG3.a |
| **AG3.d** | Subventions d'investissement : octroi 441 / 131, `aid_assets`, reprise D 139 / C 747 au rythme des amortissements, cession, annexe ; DJA mixte | AG3.a, immobilisations |
| **AG3.e** | Client Lexicon et contrôle `cap_beneficiaries` | Q-P5 |

Ordre proposé : a → b ∥ c → d → e.

---

## 12. Tests

- **Rattachement** (jeu calculé à la main) :
  - exploitation clôturant au 31/01, campagne 2026, demande 18 000 €, avance de 12 000 € le 16/10 ;
  - produit à recevoir de 6 000 € au 31/01/2027 en D 441 / C 7451, extourné au 01/02/2027 ;
  - au micro-BA : aucune proposition.
- **Dossiers fictifs A, B et C** : le reste à recevoir de 745 au 31/01/2025 (A : 10 282,81 €, C : 301,99 €) se retrouve en saisissant les dossiers correspondants. Le jeu d'essai sert de recette, pas de test automatique, faute de dossiers dans les FEC.
- **Ventilation** : un virement de l'ASP de 9 210,18 € réparti sur deux dossiers ; le total ne peut pas dépasser le virement ; détacher rend le virement disponible.
- **Reprise** : subvention de 10 000 € sur un bien de 50 000 € amorti sur 5 ans en linéaire, mis en service le 01/07 :
  - 1re année (6 mois) : reprise de 1 000 € ;
  - années suivantes : 2 000 € ;
  - dernière année : solde ;
  - cession en 3e année : reprise du reste.
- **DJA mixte** : 30 000 €, dont 20 000 € d'investissement ; deux fractions de 24 000 € et 6 000 €, chacune ventilée au prorata.
- **Échéancier** : une date limite de demande de paiement apparaît à J-60 et passe à « fait » quand la demande est notée.
- **Droits** : l'expert-comptable reçoit 403 sur toute écriture.
