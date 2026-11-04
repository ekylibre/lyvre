# Conception — Échéancier et résumé hebdomadaire de l'exploitation (lot AG9a)

> **Statut** : **validée** (04/11/2026). Q-E1 : **SMTP du serveur réglé sur le relais Brevo**. Q-E2 : paiement reconnu **coché automatiquement**, rattachement réversible. Q-E3 : **iCal dans AG9a** (sous-lot e). Q-E4 : utilisateurs **qui écrivent, abonnés par défaut**, désabonnement possible (pas l'expert-comptable en lecture seule).
> Besoins : `claudedocs/compta_agri.md` § AG9 (AG9.1 à AG9.5, AG9.9), US-A2, AGD3, AGD6, AGD9.
> Contenu des échéances : `claudedocs/compta_agricole/audit_calendrier.md` (38 fiches, tableau mois par mois, table des dates selon la clôture).
> Périmètre : **sans conversation**. L'intégration « Assistant Claude » (AG9.7, AG9.8) est le lot AG9b.
>
> **AG9a.a réalisé (04/11/2026, non commité)**. Contenu :
> - `data/deadlines/{tva,fiscal,social,pac,filieres,divers}.yml` : les 38 fiches de l'audit (README), dont 28 avec des dates et 10 d'information seule (TVA-04, FIS-07, SOC-04, PAC-05, PAC-07, ENV-02, ENV-04, ELE-01, DIV-04, DIV-05) ; liens repris de l'audit seulement ;
> - `app/services/deadlines.py` : schéma validé au chargement, conditions (`legal_form`, régimes, `option`, `close`, `flags`, `production`, `company`, `commercial`, `bookkeeping`) à trois valeurs (oui, non, à préciser), dix types de règles de date, exercices prolongés d'année en année ;
> - `data/regulatory/agenda.json` : dates 2026 de l'audit (PAC, aides animales, avance PAC, appels MSA de deux caisses), valables pour l'année ; sans valeur de l'année, repli « date à confirmer » ;
> - profil des démarches `organization.agri_profile` (migration `a7b9d1f3e5c6`, `app/services/agri_profile.py`), API `GET`/`PUT /agri-profile` (administrateur de l'instance), `GET /deadlines` (fiches et applicabilité du jour) ; onglet **Structure › Activités et démarches** (exploitations).
>
> Écarts et points à valider :
> - le **lundi de Pentecôte est férié** dans `fr_calendar` : le solde d'IS du 15/5/2027 (samedi) tombe au **18/5/2027**, la date limite PAC de repli 2027 aussi ; l'audit marque ce traitement par la DGFiP [I] ;
> - les dates calculées depuis la clôture sont **reportées au jour ouvré** (15/8/2026 → 17/8), ce que la table § 3.4 de l'audit ne montre pas ; l'AG et le dépôt au greffe ne sont pas reportés ;
> - le dépôt au greffe est placé à C + 7 mois (un mois après une AG tenue à la date limite) ;
> - date de la 2042 (FIS-02, FIS-08) et DRP (SOC-01) : pas de paramètre 2026 dans l'audit, repli au 31/05 et au 01/06, « à confirmer » ;
> - appels MSA : deux caisses seulement (Nord-Pas-de-Calais, Côtes normandes, sans le 1er appel) ; les autres prennent le repli (30/04, 15/10, 10/12) ;
> - la dénonciation des options (CA3 trimestrielle avant le 5/2…) viendra des dates limites de renonciation du profil fiscal (détections, AG9a.c), pas des fiches.
>
> Tests : `tests/test_deadlines.py` (14 tests, dont la table § 3.4 sur six clôtures), `frontend/src/features/organization/agriActivities.test.tsx`.
>
> **AG9a.b réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/agenda.py` : occurrences des fiches applicables sur une fenêtre (J-90 à J+400 par défaut), statut (faite, ignorée, prête, en retard, cette semaine, à préparer, à venir), montant quand Lyvre le connaît ; les règles `lyvre` lisent `vat_return.periods` (CA3, CA12A), `vat_installments.schedule` (acomptes : montant enregistré, sinon proposé ; rien en cas de dispense) et `rfa_claims` (3520 au 31/12 de N+1) ;
> - états enregistrés : table `deadline_states` (migration `b8c0e2a4f6d7`), clé fiche#événement + date + période ; « ignorée » demande un motif ; une échéance suivie par Lyvre ne se marque pas à la main ;
> - API `GET /agenda?from=&to=` (occurrences, fiches, questions), `POST /agenda/states`, `DELETE /agenda/states/<id>` ;
> - écran **Compta › Échéancier** (`/agenda/`) : liste par blocs, calendrier mensuel (grille maison, Mantine n'en fournit pas), filtre par domaine, fiche en tiroir (organisme, à préparer, pénalités, liens, fiabilité, « date à confirmer », action Lyvre), bandeau des démarches à préciser renvoyant vers Activités et démarches.
>
> Écarts :
> - une fiche dont l'applicabilité dépend d'une réponse manquante ne produit **aucune occurrence** : elle apparaît seulement dans les questions, une fois ;
> - les échéances de TVA n'existent que si l'exercice déclare dans Lyvre (`vat_period`) : un profil au RSA sans exercice paramétré n'affiche pas de CA12A (signalement prévu avec les détections, AG9a.c) ;
> - les événements « discrets » (acompte du PAS, avance PAC, fin des corrections PAC…) ne figurent pas dans le bloc « À venir » de la liste, mais restent dans le calendrier.
>
> Tests : `tests/api/test_agenda.py` (4 tests, dont US-A2 : acompte du 5/11 à 1 001 € « cette semaine » le 02/11/2026), `frontend/src/features/agenda/agenda.test.tsx`.
>
> **AG9a.c réalisé (04/11/2026, non commité)**. Contenu :
> - `data/deadlines/payees.yml` : motifs de libellé par organisme (DGFiP/SIE/SIP, MSA, Douane, Agence de l'eau), comparés en majuscules sans accents ni ponctuation, mot entier (« SIE » ne reconnaît pas « SIEMENS ») ; libellé et contrepartie ;
> - événements de paiement marqués `payment: true` : CA12A, acomptes de TVA, CA3, acompte et solde d'IS, CFE, TFNB, appels MSA ;
> - `agenda.match_payments` : à l'ouverture de l'échéancier, rattache les débits de J-10 à J+10, égaux à 5 % près au montant estimé (sans estimation : libellé et date seuls) ; un débit et une échéance ne servent qu'une fois, montant le plus proche puis date la plus proche ; état `done`, `origin = bank`, fait le jour du débit ;
> - détacher un paiement laisse un état `unlinked` : l'échéance redevient à faire et n'est plus rapprochée automatiquement ; le rattachement à la main (`GET /agenda/candidates`, `POST /agenda/states` avec `bank_transaction_id`) reste possible, y compris pour une échéance suivie par Lyvre ;
> - `app/services/agenda_checks.py` : détections § 6.2 (TVA de l'exercice non paramétrée au RSA ou au réel, crédit de TVA au-dessus du minimum de remboursement, RFA → RSA, attestations RFA manquantes, sortie du micro-BA, renonciation à une option à J-60, transactions non rapprochées de plus de 30 jours, dates à confirmer à 90 jours, Certiphyto à 6 mois, fin du plan JA à 6 mois, fermage à J-15) ; une détection en échec est journalisée et omise ;
> - écran : bloc « À vérifier » en tête de l'échéancier ; dans la fiche, paiement reconnu (date, libellé, montant, lien vers le relevé, « Détacher le paiement ») ou débits proposés avec « Rattacher ».
>
> Écarts :
> - l'**acompte mensuel du prélèvement à la source** n'est pas rapproché : sans montant, tout débit DGFiP autour du 15 lui serait attribué, et il est souvent prélevé sur le compte personnel ;
> - les seuils RFA et micro-BA se lisent sur l'**année écoulée** : la détection arrive après le 1er janvier où le changement s'applique ;
> - le rapprochement s'exécute à l'ouverture de l'échéancier (et, en AG9a.d, avant le résumé du lundi), pas à l'import des relevés ;
> - minimum de remboursement : 760 € pour la dernière CA3, 150 € pour la dernière CA12A (paramètres `vat.rsa.refund_min_*`), sans distinguer la CA3 de décembre.
>
> Tests : `tests/api/test_agenda_payments.py` (9 tests, dont la recette : prélèvement DGFiP du 05/11 de 1 001 € → acompte fait), `frontend/src/features/agenda/agenda.test.tsx` (3 tests).
>
> **AG9a.d réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/agenda_summary.py` : `weekly_summary(jour)`, quatre blocs (en retard avec les pénalités de la fiche, cette semaine avec le montant et l'action, à préparer avec ce qui manque, à vérifier) après le rattachement des paiements ; les événements discrets n'apparaissent que dans « cette semaine » ;
> - table `agenda_subscriptions` (migration `c9d1f3b5e7a8`, base de l'instance) : abonnement, semaine du dernier envoi, jeton iCal réservé à AG9a.e ;
> - destinataires (Q-E4) : administrateurs et trésoriers de l'instance, abonnés par défaut ; administrateur global sans rôle sur l'instance seulement s'il s'abonne ; jamais l'expert-comptable ;
> - `flask agenda send-weekly [--date] [--dry-run]` (`app/commands.py`) : instances agricoles actives, une notification par semaine dans l'application, un e-mail texte par abonné par le SMTP du serveur (Q-E1), une ligne de journal par envoi, idempotent par semaine ISO, code de sortie 1 en cas d'échec ; un échec n'est pas noté envoyé et se retente ;
> - désabonnement : lien signé dans l'e-mail (`/agenda/unsubscribe`, hors connexion, confirmation par POST pour résister aux aperçus de lien), interrupteur « Résumé du lundi par e-mail » dans l'échéancier ;
> - API `GET /agenda/summary`, `GET`/`PUT /agenda/subscription` ; carte « Échéancier — semaine du … » en tête du tableau de bord des exploitations ;
> - `doc/agenda.md` : configuration du relais Brevo (`MAIL_*`, `APP_BASE_URL`), timer systemd (lundi 7 h, `Persistent=true`) ou cron, lignes de journal.
>
> Écarts :
> - l'abonnement se règle dans **l'échéancier**, pas dans le profil utilisateur : Lyvre n'a pas d'écran de profil, et l'abonnement est propre à chaque instance ;
> - une instance sans rien à signaler ne reçoit pas d'e-mail (la notification est créée quand même) ;
> - la pénalité est le **texte** de la fiche, pas un montant estimé ;
> - l'objet et le texte portent le nom de l'exploitation (Organisation), à défaut le libellé de l'instance.
>
> Tests : `tests/api/test_agenda_summary.py` (8 tests, dont l'exploitation fictive A au lundi 02/11/2026 : TFNB et appel MSA du 15/10 en retard, appel MSA du 10/12 à confirmer), `frontend/src/features/agenda/agendaWeekCard.test.tsx` (2 tests).
>
> **AG9a.e réalisé (04/11/2026, non commité)**. Contenu :
> - `app/services/agenda_ical.py` : jeton aléatoire de 256 bits par utilisateur et par instance (`agenda_subscriptions.ical_token`), régénérable et révocable ; calendrier RFC 5545 écrit à la main (CRLF, pliage à 75 octets sans couper un caractère UTF-8, échappement), un événement « journée entière » par occurrence de J-30 à J+400, UID stable, `STATUS:TENTATIVE` pour une date à confirmer, alarme au premier rappel de la fiche, lien vers Lyvre, rafraîchissement suggéré toutes les 12 h ;
> - URL publique `/agenda/ical/<instance>/<jeton>.ics` (au lieu de `/agenda/<jeton>.ics` : le jeton vit dans la base de l'instance, qui doit être désignée), 404 identique pour une instance inconnue, un jeton faux ou révoqué et un accès retiré ; lecture seule (pas de rattachement de paiement) ;
> - API `GET`/`POST`/`DELETE /agenda/ical` ; bouton « Agenda (iCal) » de l'échéancier : adresse à copier, régénérer, révoquer.
>
> Tests : `tests/api/test_agenda_ical.py` (4 tests, validateur RFC 5545 : imbrication, propriétés obligatoires, lignes ≤ 75 octets, CRLF, UID uniques et stables) ; fichier également relu sans erreur par la bibliothèque `icalendar` (hors dépendances du projet) ; `agendaWeekCard.test.tsx` (adresse iCal).
>
> **AG9a terminé (a à e).**

---

## 1. Ce que le lot doit produire

Le lundi 2 novembre 2026, une exploitante en EARL au réel simplifié et au RSA reçoit un résumé (US-A2) :
- l'acompte de TVA du 5/11, avec le montant calculé par Lyvre (1/5 de la TVA due en 2025) et un bouton « préparer le 3525 bis » ;
- le fermage de la Saint-Martin (11/11) ;
- le solde MSA de sa caisse, avec la mention « date à confirmer » si le calendrier de la caisse n'est pas saisi.

Elle retrouve les mêmes informations dans **Compta › Échéancier**, en liste ou en calendrier. Elle coche une échéance comme faite, à moins que Lyvre ne l'ait déjà fait : déclaration validée dans Lyvre, ou prélèvement de la DGFiP ou de la MSA reconnu sur le relevé.

## 2. Ce qui existe déjà

| Brique | Où | Usage dans AG9a |
|---|---|---|
| Calendrier des jours ouvrés et fériés (dont le lundi de Pentecôte) | `app/services/fr_calendar.py` | Toutes les dates calculées |
| Paramètres réglementaires datés, avec fiabilité et surcharge | `data/regulatory/*.json`, `reg_params` | Dates annuelles (PAC, MSA par caisse) et règles |
| Profil fiscal daté et options (date limite de renonciation) | `tax_profile` (`current_value`, `renounce_by`) | Applicabilité des fiches, détection des options |
| Échéances calculées de la TVA | `vat_return.periods`, `vat_installments.schedule`, `rfa.compute` | Occurrences TVA **lues** dans le moteur, avec leur statut |
| Micro-BA : moyenne triennale et seuil | `micro_ba.summary` | Détection micro → réel |
| Transactions bancaires (libellé, date, montant, rapprochement) | `bank_transactions` | Rapprochement des paiements |
| Notifications de l'application | `notifications` | Résumé du lundi dans l'application |
| Envoi d'e-mails | SMTP du serveur (`password_reset.deliver`, `MAIL_*`) ; Brevo ne fait aujourd'hui que la synchronisation de contacts | Résumé par e-mail (Q-E1) |
| Tâche planifiée | **aucune** (`doc/backups.md` : pas de cron intégré) | Commande à lancer par le serveur (§ 7) |

## 3. Choix structurants

| # | Choix | Raison |
|---|---|---|
| E1 | **Base d'échéances en YAML versionné** : `data/deadlines/<domaine>.yml` (tva, fiscal, social, pac, filieres, divers), une fiche par échéance, validée par un schéma dans les tests | Relue par l'expert-comptable, citée par l'assistant (AG9b) ; même esprit que `doc/base_documentaire` |
| E2 | **Règles déclaratives, sans expression évaluée** : l'applicabilité est une liste de conditions typées (`vat_regime: [rsa_installments]`, `flag: employer`), la date une règle d'un type connu (§ 4.2) | Aucune `eval` ; chaque règle se teste et s'explique |
| E3 | **Occurrences calculées à la volée** pour une fenêtre (de J-90 à J+400). Seul l'**état** d'une occurrence se stocke (faite, ignorée, par qui, comment), dans `deadline_states` | Rien à régénérer quand le profil ou un paramètre change |
| E4 | **TVA et 3520 lus dans le moteur d'AG2**, pas recopiés : la fiche porte le texte, le moteur fournit les dates, les montants et le statut (déposée → faite) | Une seule source de vérité pour les échéances que Lyvre prépare |
| E5 | **Profil des démarches** : les drapeaux hors fiscalité (caisse MSA, demandeur PAC, employeur, productions, irrigant, zone vulnérable, phyto, JA, baux) dans une colonne JSON `organization.agri_profile`, au schéma défini dans le code | Données peu nombreuses, non datées, propres aux exploitations ; pas de nouvelle table |
| E6 | **Démarches hors comptabilité : rappels seulement** (AGD9) : date, organisme, lien, pas de donnée produite | Conforme à AGD9 |

## 4. Base d'échéances (AG9.1, AG9.2)

### 4.1 Fiche

```yaml
- id: TVA-02
  title: Acomptes trimestriels de TVA (3525 bis)
  domain: tva                       # tva | fiscal | social | pac | filieres | divers
  organism: SIE
  applies:                          # toutes les conditions (ET) ; une liste de valeurs vaut OU
    vat_regime: [rsa_installments]
  dates:
    source: lyvre.vat_installments  # occurrences fournies par le moteur de TVA
  reminders: [15, 5]                # jours avant l'échéance
  action: {label: Préparer le 3525 bis, route: /vat-returns/}
  prepare: [TVA due de l'année précédente (ligne 23), TVA estimée de l'année]
  penalties: Intérêt de retard de 0,20 % par mois (CGI art. 1727) ; majoration de 10 % si la TVA de l'année dépasse les acomptes de plus de 30 % (art. 1731).
  link: https://bofip.impots.gouv.fr/node/10637
  reliability: R
  sources: [audit_calendrier.md TVA-02]
```

Les liens sont ceux de l'audit, sans ajout : aucun identifiant de source n'est inventé.

### 4.2 Règles de date

| Type | Paramètres | Exemple |
|---|---|---|
| `fixed` | `days: [MM-JJ…]`, `shift: next_working_day \| none` | TFNB le 15/10 ; Saint-Martin le 11/11 sans report |
| `nth_working_day_after` | `day: MM-JJ`, `n` | Liasse BA au 31/12 : 2e jour ouvré après le 1er mai |
| `after_close` | `months`, `day` (`end` ou un jour), `edi_days`, `shift` | Liasse : C + 3 mois (+15 j en EDI) ; AG : C + 6 mois ; solde d'IS : le 15 du 4e mois |
| `annual_param` | `key` (paramètre réglementaire de l'année), `fallback` (une règle ci-dessus) | Date limite PAC (`pac.deadline`) ; appels MSA (`msa.<caisse>.calls`) |
| `profile` | `field` du profil des démarches | Fin de validité du Certiphyto ; dates de fermage des baux |
| `lyvre.*` | `vat_returns`, `vat_installments`, `rfa` | Occurrences calculées par le moteur de TVA |

Une règle `annual_param` dont le paramètre de l'année manque utilise son repli et affiche **« date à confirmer »** (AG9.2). Une clôture au 31/12 et une clôture décalée suivent la table § 3.4 de l'audit, encodée par `after_close`, puis vérifiée sur ses six lignes dans les tests.

### 4.3 Conditions d'applicabilité

Un nom connu par condition, lu sur le profil à la date de l'occurrence :

| Condition | Lue dans |
|---|---|
| `legal_form`, `income_tax`, `ba_regime`, `vat_regime` | profil fiscal daté (AG1.a) |
| `option` | option datée active (`rsa_fiscal_year`, `vat_quarterly`…) |
| `close` : `civil` ou `offset` | exercice en cours |
| `flag` : `pac`, `employer`, `irrigant`, `vulnerable_zone`, `phyto`, `bonded_warehouse`, `ja`, `msa_monthly`, `livestock`, `viticulture` | profil des démarches |
| `bookkeeping` : `simple` ou `double` | instance |

Une fiche dont une condition porte sur un drapeau **non renseigné** est montrée une fois, avec la question « Êtes-vous concerné ? » : la réponse renseigne le profil.

### 4.4 Contenu initial

Les 38 fiches de l'audit, de TVA-01 à DIV-05, et les échéances récurrentes (DSN, acompte du PAS, DRM). Les fiches marquées [I] dans l'audit gardent la fiabilité I : leur date porte « à confirmer » et elles ne déclenchent pas de pénalité estimée. **L'expert-comptable relit la base** (AGD5) avant la mise en production.

## 5. Échéancier (AG9.3)

### 5.1 Occurrence et statut

Une occurrence = (fiche, date, période concernée), avec le montant estimé quand Lyvre le connaît (acompte, CA12A, 3520).

| Statut | Règle |
|---|---|
| **faite** | état enregistré (manuel ou automatique), ou déclaration Lyvre déposée |
| **prête** | déclaration Lyvre validée, pas encore déposée |
| **en retard** | date passée, pas faite |
| **cette semaine** | de J à J+7 |
| **à préparer** | de J+8 à J+45 |
| **à venir** | au-delà |

Une occurrence peut être **ignorée** (« non concerné cette année »), avec un motif.

### 5.2 État enregistré

Table `deadline_states` : `deadline_id`, `occurs_on`, `period` (texte, ex. « 2026-T3 »), `status` (`done` ou `skipped`), `done_on`, `origin` (`manual`, `vat_return`, `bank`), `bank_transaction_id`, `note`, `user_id`, unique (`deadline_id`, `occurs_on`).

### 5.3 Écran

**Compta › Échéancier**, pour le plan agricole, en partie double comme en comptabilité simplifiée :
- **liste** groupée par bloc (en retard, cette semaine, à préparer, à venir), avec des filtres par domaine ;
- **calendrier** mensuel : grille des jours, pastilles par domaine ;
- **fiche en tiroir** : organisme, ce qu'il faut préparer, pénalités, lien officiel, fiabilité, « date à confirmer », et les boutons « faite », « ignorer » et l'action Lyvre.

Le profil des démarches se renseigne dans **Organisation › Profil fiscal**, bloc « Activités et démarches ».

## 6. Rapprochement des paiements et détections (AG9.3, AG9.5)

### 6.1 Paiements reconnus

Un débit bancaire est rattaché à une occurrence si les trois conditions suivantes sont réunies :
- son **libellé** correspond à l'organisme : motifs par organisme dans `data/deadlines/payees.yml` (`DGFIP`, `IMPOT`, `SIE`, `MSA`, `TRESOR PUBLIC`…) ;
- sa **date** tombe entre J-10 et J+10 de l'échéance ;
- son **montant**, si Lyvre l'estime, est égal à 5 % près.

L'occurrence passe à « faite » (`origin = bank`), avec le lien vers la transaction (Q-E2). Un rattachement se défait.

### 6.2 Détections de AG9a

| Détection | Source |
|---|---|
| RFA → RSA : moyenne des recettes sur 2 ans au-delà de 46 000 € (× associés d'un GAEC) | `rfa.compute` |
| Micro-BA → réel : moyenne triennale au-delà du seuil | `micro_ba.summary` |
| Crédit de TVA remboursable (CA3 : 760 € ; CA12A : 150 €) | moteur de TVA |
| Date limite de renonciation à une option, à J-60 | `tax_profile.renounce_by` |
| Attestations RFA manquantes | `rfa.compute` |
| Relevés non rapprochés : transactions non rapprochées de plus de 30 jours | `bank_transactions` |
| Paramètres annuels non confirmés pour l'année (fiabilité A sans valeur de l'année, ou I) | `reg_params` |
| Certiphyto à moins de 6 mois de sa fin, fin de la période JA, fermage à indexer au 1/10 et avis J-15 (Saint-Michel, Saint-Martin) | profil des démarches |

Elles **viennent après** les lots dont elles dépendent : virement ASP non rattaché (AG3), BA estimé contre base du PAS (AG5), DEP (AG6).

## 7. Résumé du lundi (AG9.4)

Un service, `agenda.weekly_summary(jour)`, produit les 4 blocs : en retard, avec la pénalité estimée ; cette semaine, avec le montant et le bouton d'action ; à préparer, avec les données manquantes détectées ; à vérifier cette année.

**Dans l'application** :
- en tête du tableau de bord d'une exploitation ;
- une notification le lundi.

**Par e-mail** :
- commande `flask agenda send-weekly`, qui parcourt les instances agricoles et leurs utilisateurs abonnés, puis écrit une ligne de journal par envoi ;
- elle est lancée chaque lundi à 7 h par un timer systemd (ou un cron) du serveur, documenté dans `doc/agenda.md`, car Lyvre n'a pas de planificateur ;
- elle est idempotente : un seul envoi par utilisateur et par semaine, enregistré ;
- canal d'envoi : Q-E1 ; destinataires : Q-E4.

Chaque utilisateur se désabonne depuis son profil. Le lien de désabonnement figure dans l'e-mail.

## 8. Export iCal (option, AG9.3)

URL secrète par utilisateur et par instance (`/agenda/<jeton>.ics`), révocable, qui donne les occurrences de J-30 à J+400 avec leur lien vers Lyvre (Q-E3).

## 9. Données, API, écrans

| Élément | Contenu |
|---|---|
| Migration | `organization.agri_profile` (JSON) ; tables `deadline_states`, `agenda_subscriptions` (utilisateur, abonné, dernier envoi, jeton iCal) |
| Données | `data/deadlines/{tva,fiscal,social,pac,filieres,divers}.yml`, `data/deadlines/payees.yml` ; paramètres annuels ajoutés à `data/regulatory/agenda.json` (date limite PAC, appels MSA par caisse : **saisie** chaque année, fiabilité A) |
| Services | `app/services/deadlines.py` (chargement, schéma, règles, applicabilité) ; `app/services/agenda.py` (occurrences, statuts, rapprochement, détections, résumé) |
| API | `GET /agenda?from=&to=` ; `GET /agenda/summary` ; `POST /agenda/states` / `DELETE /agenda/states/<id>` ; `GET`/`PUT /organization/agri-profile` ; `GET`/`PUT /agenda/subscription` ; `/agenda/<jeton>.ics` |
| Écrans | Compta › Échéancier (liste, calendrier, fiche) ; bloc du tableau de bord ; bloc « Activités et démarches » du profil fiscal ; abonnement dans le profil utilisateur |

## 10. Sous-lots

| Sous-lot | Contenu | Recette |
|---|---|---|
| **AG9a.a** Base et règles | Schéma YAML, 38 fiches de l'audit, règles de date, applicabilité, profil des démarches | Table § 3.4 de l'audit sur 6 clôtures ; Pentecôte ; repli « date à confirmer » |
| **AG9a.b** Échéancier | Occurrences, statuts, états, TVA et 3520 lus dans le moteur, écran liste, calendrier, fiche | Exploitation A au 02/11/2026 : acompte du 5/11 avec son montant |
| **AG9a.c** Paiements et détections | Rapprochement bancaire, détections § 6.2 | Un prélèvement DGFiP du 05/11 coche l'acompte |
| **AG9a.d** Résumé du lundi | Service, tableau de bord, notification, e-mail, commande, abonnement | US-A2 sur le jeu d'essai, à la date du 02/11/2026 |
| **AG9a.e** iCal | Jeton, export | Fichier valide (RFC 5545) |

Ordre : a → b → c → d → e.

## 11. Questions (tranchées le 04/11/2026, voir le statut)

- **Q-E1 Canal des e-mails** : le **SMTP du serveur** (`MAIL_*`, comme la réinitialisation du mot de passe), réglé sur le relais SMTP de Brevo, ce qui respecte AGD3 sans code propre à Brevo (proposition) ; ou l'API transactionnelle de Brevo avec une clé du serveur ; ou la clé Brevo de chaque instance ?
- **Q-E2 Paiement reconnu** : l'occurrence passe **automatiquement** à « faite », et le rattachement se défait (proposition) ; ou Lyvre **propose** le rattachement, qui reste à confirmer ?
- **Q-E3 iCal** : dans AG9a (sous-lot e), ou plus tard ?
- **Q-E4 Destinataires du résumé** : tous les utilisateurs de l'instance qui peuvent écrire, abonnés par défaut, qui peuvent se désabonner (proposition) ; ou seulement sur inscription ; l'expert-comptable (lecture seule) compris ?
