# Besoins — écarts retenus du comparatif des logiciels open source

> Statut : expression de besoins (`/sc:brainstorm`, 23/10/2026), **à valider**. Pas de conception ni de code.
> Origine : `doc/ref_compta/comparatif_oss_compta.md` (synthèse, § 3 écarts E1…E49) et rapports
> `doc/ref_compta/comparatif_oss/*.md` (Invoice Ninja, Diacamma, enDI, Dokos, Frappe Books, Tryton).
> Étape suivante : réponses au § 8, puis `/sc:design` par lot.

## 1. Décisions déjà prises (23/10/2026)

| # | Sujet | Décision |
|---|---|---|
| CO1 | Familles retenues | **Fiabilité comptable** (E1, E2, E3, E5, E8, E9), **échéances réglementaires** (E7, E29, E30), **vie associative et SCI** (E10, E35, E36, E41) |
| CO2 | Familles écartées pour l'instant | Encaissements associatifs (remises de chèques E14, notes de frais E32, SEPA E18/E19, paiement en ligne E20, relances auto E21, balance âgée E22) et plateforme (E43–E49) |
| CO3 | Invoice Ninja | Dans le tableau « Lyvre et les autres logiciels open source », avec la mention « code source disponible, licence non libre (Elastic License 2.0) » |
| CO4 | TVA | **Ni Seconde Nature ni la SCI ne sont assujetties** : E7, E29, E30 servent d'abord les **autres structures** visées par Lyvre ; ils ne sont pas urgents pour les deux instances actuelles |

## 2. Principes communs (exigences non fonctionnelles)

- **N1** Montants en centimes entiers ; calculs déterministes ; aucun arrondi caché (écart d'arrondi
  porté sur une ligne explicite).
- **N2** Les deux référentiels (`asso`, `sci`) et, quand c'est pertinent, le **mode simplifié** :
  chaque besoin dit s'il s'applique au mode simplifié (par défaut : non, masqué).
- **N3** Rôles existants : l'expert-comptable (`accountant`) voit tout en lecture ; les actions
  sensibles (déverrouiller, dévalider, importer en masse) sont réservées à l'administrateur de la
  structure, motif obligatoire, tracées dans un journal d'événements (comme `closing_events`).
- **N4** Une migration Alembic par lot ; bases réelles migrées seulement avec accord (règle en vigueur).
- **N5** Comptes cités selon le **référentiel** de l'instance (base documentaire `doc/base_documentaire/`) :
  aucun numéro de compte codé en dur hors des tables de paramétrage.
- **N6** Tests API pytest + Vitest + un parcours E2E par lot ; documentation utilisateur dans `doc/`.
- **N7** Interface React + Mantine, mêmes conventions que l'existant (DataGrid, fenêtres, raccourcis).

---

## 3. Fiabilité comptable

### E2 — Validation des écritures et intangibilité

**Objectif.** Une écriture validée ne se modifie plus ; on la corrige par contrepassation. Les
modifications avant validation sont tracées. C'est l'attente de l'expert-comptable et la condition pour
diffuser Lyvre à d'autres structures.

**Existant.** `journal_entries.validation_number` / `validated_at` remplis à la **clôture provisoire**
(numérotation FEC) ; `reverses_entry_id` existe ; sources gérées protégées (`MANAGED_SOURCES`).
Avant la clôture, toute écriture est modifiable et supprimable.

**Exigences.**
- E2.1 État d'une écriture : **brouillard** puis **validée**. La validation attribue le numéro
  définitif continu (même séquence que le FEC aujourd'hui) et la date de validation.
- E2.2 Validation **à la demande** : une écriture, une sélection, ou « tout jusqu'au JJ/MM/AAAA ».
  La clôture provisoire valide ce qui reste (comportement actuel conservé).
- E2.3 Écriture validée : ni modification, ni suppression. Action **Contrepasser** : écriture inverse
  datée du jour (ou d'une date choisie dans un exercice ouvert), liée par `reverses_entry_id`,
  rapprochements et lettrages défaits proprement.
- E2.4 Les pièces émises (factures de vente numérotées, reçus fiscaux, quittances) génèrent des
  écritures **validées d'office** (option à confirmer, Q2-1).
- E2.5 **Historique** des écritures en brouillard : création, modification (avant / après), suppression,
  par qui et quand ; consultable depuis la fiche de l'écriture et par l'expert-comptable.
- E2.6 Contrôles de clôture : nombre d'écritures en brouillard affiché, validation proposée.
- E2.7 Rapprochement bancaire et règles : inchangés pour l'utilisateur ; une écriture validée reste
  rapprochable et délettrable.

**Critères d'acceptation.**
- Modifier ou supprimer une écriture validée par l'API renvoie un refus explicite (409).
- La contrepassation d'une écriture rapprochée laisse un relevé bancaire cohérent (aucun orphelin).
- Le FEC de l'exercice garde des numéros continus, identiques avant / après la clôture provisoire.

### E3 — Verrouillage des périodes

**Objectif.** Figer les mois déjà rapprochés ou transmis à l'expert-comptable.

**Existant.** Statut d'exercice ouvert / provisoire / clos ; aucun verrou infra-annuel.

**Exigences.**
- E3.1 **Date de verrouillage** par exercice : aucune écriture créée, modifiée, validée ou supprimée
  à une date antérieure ou égale. S'applique à toutes les sources (saisie, règles, ventes, achats,
  rapprochement qui créerait une écriture, imports).
- E3.2 Avancer la date : trésorier ou administrateur. **Reculer** la date : administrateur, motif
  obligatoire, journalisé.
- E3.3 Verrouiller une période **valide** les écritures en brouillard de cette période (lien E2), après
  confirmation listant ce qui sera validé.
- E3.4 Les écrans de saisie proposent la première date libre ; message clair si une pièce (facture
  d'achat, encaissement) tombe dans une période verrouillée : proposer la date du jour.

**Critères d'acceptation.** Une facture d'achat Qonto datée d'un mois verrouillé est comptabilisée à
la première date ouverte avec mention dans le libellé, ou bloquée selon Q3-1.

### E1 — Lettrage des comptes de tiers

**Objectif.** Savoir, depuis la comptabilité elle-même, ce qui reste dû par chaque tiers (locataires,
clients, fournisseurs, associés, financeurs).

**Existant.** Factures d'achat / vente reliées à leurs règlements (`purchase_payments`,
`sale_payments`, statut payé) ; sous-comptes 401 / 411 par tiers ; comptes courants d'associés 455.
Aucun lettrage au niveau des lignes d'écriture.

**Exigences.**
- E1.1 Comptes lettrables : classe 40, 41, 42–45 (dont 455), 467, 468 et tout compte marqué
  « lettrable » dans le plan (paramètre par compte).
- E1.2 Un **lettrage** = un code (AA, AB…) par compte, sur des lignes dont le solde est nul ;
  **lettrage partiel** possible (solde non nul, marqué partiel) ; **délettrage**.
- E1.3 **Lettrage automatique** : à l'encaissement / au règlement d'une facture dans Lyvre (ventes,
  achats, quittances), et proposition sur un compte (même montant, même référence de pièce, puis
  combinaisons de montants).
- E1.4 **Écart** de faible montant (seuil paramétrable, par défaut 1 €) : lettrage avec écriture d'écart
  en charge / produit divers de gestion selon le référentiel.
- E1.5 **Inter-exercices** : les à-nouveaux reprennent les lignes **non lettrées** une par une pour les
  comptes lettrables (au lieu d'un solde global), pour pouvoir les lettrer l'année suivante.
- E1.6 Écran par compte de tiers : lignes non lettrées / lettrées / toutes, totaux, lettrer au clavier
  (dans l'esprit du rapprochement bancaire).
- E1.7 La fiche d'un tiers affiche son solde non lettré. Le FEC remplit `EcritureLet` et `DateLet`.
- E1.8 **Reprise** : lettrage automatique initial des pièces déjà payées dans Lyvre (ventes, achats).

**Critères d'acceptation.**
- Une facture de loyer encaissée par un virement rapproché est lettrée sans action.
- Après clôture et à-nouveaux, une facture impayée de décembre se lettre avec son encaissement de janvier.
- Le FEC produit passe le contrôle « Test Compta Demat » avec les colonnes de lettrage remplies.

### E8 — Immobilisations et amortissements

**Objectif.** Tenir le registre des immobilisations et passer les dotations sans calcul manuel ;
amortir l'immeuble de la SCI par composants.

**Existant.** Comptes 2x / 28x dans les deux plans, aucun suivi ; assistant de clôture avec étape
d'inventaire (486 / 487) ; lignes d'achat liées au catalogue.

**Exigences.**
- E8.1 **Fiche immobilisation** : libellé, compte (2x), date de mise en service, valeur d'origine,
  valeur résiduelle, mode (**linéaire** ; dégressif : Q8-1), durée, prorata temporis au jour, projet,
  pièce d'origine, état (en cours, amortie, cédée, mise au rebut).
- E8.2 **Composants** : une immobilisation peut être découpée (terrain non amortissable, gros œuvre,
  toiture, installations…) avec durée propre.
- E8.3 Création **depuis une ligne de facture d'achat** au compte 2x (proposée), ou à la main, ou par
  **reprise** d'un tableau existant (valeur, cumul déjà amorti à une date).
- E8.4 **Tableau d'amortissement** prévisionnel par immobilisation ; **dotations** générées par
  l'assistant de clôture (nouvelle sous-étape de l'inventaire), écritures gérées (source protégée).
- E8.5 **Cession / mise au rebut** : date, prix, écritures de sortie (valeur nette comptable,
  produit de cession), selon le référentiel en vigueur.
- E8.6 **États** : registre des immobilisations, tableau des immobilisations et des amortissements
  pour l'annexe (mouvements de l'exercice), exports tableur.
- E8.7 Association : **subventions d'investissement** (13x) et leur quote-part virée au résultat au
  rythme de l'amortissement du bien financé (Q8-2).
- E8.8 Mode simplifié : registre seulement, sans écritures (Q8-3).

**Critères d'acceptation.** Une immobilisation acquise le 15/03 sur 5 ans donne la bonne dotation
prorata temporis la première année, et la somme des dotations égale la base amortissable.

### E9 — Charges et produits constatés d'avance depuis la pièce

**Objectif.** Ne plus calculer à la main les 486 / 487 à la clôture pour les assurances, abonnements,
cotisations à cheval sur deux exercices.

**Existant.** Étape « inventaire » de l'assistant (écritures 486 / 487 saisies, extourne automatique).

**Exigences.**
- E9.1 **Période de service** (du / au) facultative sur une ligne de facture d'achat, de vente, de
  quittance, ou une ligne d'écriture de charge / produit.
- E9.2 À la clôture, l'étape inventaire **propose** les écritures 486 / 487 calculées au prorata des
  jours hors exercice, pièce par pièce, modifiables avant validation ; l'extourne existante s'applique.
- E9.3 Proposition des abonnements d'achat (module en cours) avec leur périodicité.
- E9.4 Pas d'étalement mensuel (Lyvre n'a pas de périodes comptables mensuelles).

**Critères d'acceptation.** Une assurance annuelle du 01/07 au 30/06 payée en juillet donne une charge
constatée d'avance de 181/365 de son montant à la clôture au 31/12.

### E5 — Reprise d'historique (import FEC et tableur)

**Objectif.** Permettre à une nouvelle structure d'arriver avec son historique ou ses soldes.

**Existant.** Imports OFX, CSV Odoo, associés (analyse puis tout-ou-rien), seed des plans.

**Exigences.**
- E5.1 **Import FEC** (tabulation ou barre verticale, encodages courants) d'un exercice : analyse
  préalable (comptes inconnus, journaux, déséquilibres, tiers par `CompAuxNum`), puis import
  **tout-ou-rien**.
- E5.2 Deux usages : **historique complet** (exercice clos importé tel quel, validé et verrouillé) ou
  **soldes d'ouverture** seulement (à-nouveaux de l'exercice de démarrage, détail par tiers non lettré).
- E5.3 **Import tableur** d'écritures (CSV / XLSX) avec correspondance de colonnes mémorisée.
- E5.4 Correspondance des comptes : création des comptes absents rattachés à leur classe, ou
  correspondance vers un compte existant (table mémorisée).
- E5.5 Lettrage repris si présent dans le FEC (E1).

**Critères d'acceptation.** Le FEC exporté par Lyvre, réimporté dans une base vide, redonne la même
balance et les mêmes états.

---

## 4. Échéances réglementaires (pour les structures assujetties)

> Rappel CO4 : ni Seconde Nature ni la SCI ne sont assujetties. Ces besoins sont **activés par
> structure** selon le régime de TVA (`fiscal_years.vat_liable`) et restent invisibles sinon.

### E29 — Facture électronique via une plateforme agréée

**Objectif.** Recevoir (et plus tard émettre) les factures électroniques par une plateforme agréée,
comme l'impose la réforme aux assujettis.

**Existant.** Lecture Factur-X / PDF / OCR des factures d'achat ; Factur-X produit en vente ; émission
optionnelle via Qonto ; écran Intégrations avec sondes.

**Exigences.**
- E29.1 Nouvelle intégration « plateforme agréée » (une à la fois par structure) dans l'écran
  Intégrations, avec sonde et description.
- E29.2 **Réception** : les factures reçues arrivent dans le circuit des factures d'achat existant
  (fournisseur retrouvé par SIREN / TVA, lignes lues depuis le XML structuré, pas d'OCR).
- E29.3 **Statuts de cycle de vie** renvoyés à la plateforme : refusée, approuvée, payée (à partir du
  règlement rapproché).
- E29.4 **Émission** (deuxième temps) : envoi des factures de vente Factur-X par la plateforme ;
  coexistence avec l'émission par Qonto.
- E29.5 Recherche dans l'**annuaire** à la création d'un client / fournisseur (SIREN, adresse de
  facturation électronique).
- E29.6 E-reporting : hors périmètre (pas de ventes B2C à l'international ni B2C assujetties dans la
  cible actuelle), à revoir.

### E7 — Déclaration de TVA préparée

**Exigences.**
- E7.1 Table de **codes de déclaration** par régime (CA3 mensuelle / trimestrielle, CA12 annuelle) :
  chaque case = formule sur des comptes de TVA et des bases (comptes 44x, 70x…), fournie par le
  référentiel (base documentaire), modifiable par l'administrateur.
- E7.2 **État de TVA** d'une période : montants par case, détail par écriture, export tableur et PDF
  de travail (pas de télédéclaration).
- E7.3 TVA à l'encaissement (déjà gérée en vente) prise en compte ; écriture de liquidation
  (44551 / 44567…) proposée et période **verrouillée** après déclaration (lien E3).

### E30 — Chorus Pro

**Exigences.**
- E30.1 Option « client public » sur un tiers (SIRET du service, code service, numéro d'engagement).
- E30.2 Dépôt de la facture de vente sur Chorus Pro (API) et suivi du statut ; ou consigne de dépôt
  manuel avec le PDF Factur-X si l'API n'est pas configurée.

---

## 5. Vie associative et SCI

### E41 — Régularisation annuelle des charges locatives (SCI)

**Objectif.** Comparer chaque année les provisions sur charges appelées aux charges réelles
récupérables, et produire le décompte et la régularisation de chaque locataire.

**Existant.** Bail simple (`leases` : loyer, provisions sur charges, compte de charges, dépôt de
garantie), factures récurrentes, quittances distinguant loyer et charges.

**Exigences.**
- E41.1 **Charges récupérables** : comptes de charges marqués récupérables (eau, entretien, taxe
  d'enlèvement des ordures ménagères…), sur une période de régularisation (par défaut l'année civile).
- E41.2 **Clé de répartition** par lot / bail : tantièmes, surface ou pourcentage ; prorata de la
  durée d'occupation en cas d'entrée ou de sortie en cours d'année.
- E41.3 **Décompte** par locataire : charges par nature, quote-part, provisions appelées (depuis les
  factures du bail), solde ; PDF envoyé par courriel (comme les quittances).
- E41.4 Le solde génère une **facture** complémentaire ou un **avoir** au locataire ; option
  d'ajuster la provision mensuelle du bail pour l'année suivante.
- E41.5 Justificatifs : liste des factures d'achat retenues, jointe au décompte sur demande.

**Critères d'acceptation.** Pour un locataire entré le 01/04 avec 50 % des tantièmes, la quote-part
égale 50 % × 275/365 des charges récupérables, et le solde = quote-part − provisions encaissées.

### E35 — Adhésions gérées dans Lyvre (sans HelloAsso)

**Objectif.** Permettre aux associations qui n'utilisent pas HelloAsso de gérer leurs adhésions et
cotisations dans Lyvre, et à celles qui l'utilisent de compléter (chèque, espèces, virement).

**Existant.** `entities.is_member`, synchro HelloAsso (items `Membership`), statut d'adhésion
(anniversaire, expire bientôt / expirée), relances d'adhésion par courriel, liste des adhérents.

**Exigences.**
- E35.1 **Types de cotisation** : libellé, montant (ou montant libre), durée (année civile, saison
  du JJ/MM au JJ/MM, ou date anniversaire), compte de produit (756 selon le référentiel), statut
  donnant droit à un reçu fiscal ou non.
- E35.2 **Adhésion** : adhérent, type, période couverte, montant, mode de paiement (chèque, espèces,
  virement, HelloAsso) ; les adhésions HelloAsso deviennent des adhésions de ce modèle (une seule
  source de vérité pour le statut).
- E35.3 Encaissement : écriture de produit en partie double (caisse 53x, banque, ou chèque à
  encaisser) ou recette en mode simplifié ; rapprochable.
- E35.4 **Renouvellement en masse** d'une saison à l'autre (sélection, même type, courriel d'appel).
- E35.5 **Familles** (adhésion familiale rattachant plusieurs personnes) et **activités** facultatives
  (Q35-1).
- E35.6 Statistiques simples : nombre d'adhérents par saison, par type, nouveaux / renouvelés.

**Critères d'acceptation.** Une adhésion payée par chèque met l'adhérent « à jour » avec la même règle
que pour HelloAsso, et la relance d'expiration fonctionne sans HelloAsso.

### E36 — Espace adhérent / locataire / client

**Objectif.** Les tiers consultent et téléchargent eux-mêmes leurs documents, ce qui fait moins de
demandes au trésorier.

**Exigences.**
- E36.1 Accès par **lien de connexion envoyé par courriel** (sans mot de passe), à l'adresse connue
  du tiers ; lien à durée limitée ; aucun accès aux écrans de gestion.
- E36.2 Contenu selon le tiers : **adhésion** (statut, échéance), **reçus fiscaux**, **factures** et
  **avoirs**, **quittances** et **décomptes de charges** (E41), **relevé** de ce qui reste dû (lettrage E1).
- E36.3 Mise à jour de ses coordonnées (adresse, courriel) soumise à validation.
- E36.4 Activation par structure et par type de document ; page aux couleurs de la structure.
- E36.5 Paiement en ligne : **hors périmètre** (E20 écarté) ; lien HelloAsso possible pour l'adhésion.
- E36.6 Sécurité : jeton à usage limité, journal des accès, aucune donnée d'un autre tiers ;
  désactivation immédiate par l'administrateur.

### E10 — Analytique multi-axes

**Objectif.** Ventiler à la fois par projet, par financeur et par site ; répartir les frais de
structure ; produire les comptes rendus demandés par chaque financeur.

**Existant.** Un axe « projets » (`project_id` sur lignes d'écriture, d'achat, règles), ventilation
d'une ligne, compte de résultat d'un projet, budget par projet, fonds dédiés liés aux projets.

**Exigences.**
- E10.1 **Axes** paramétrables (le premier = projets existants, repris sans perte), chacun avec ses
  valeurs ; une ligne porte **au plus une valeur par axe**.
- E10.2 **Clés de répartition** en pourcentage (frais de structure répartis entre projets), appliquées
  à la saisie ou à la clôture (Q10-1).
- E10.3 **Règles d'affectation** automatiques par compte, tiers ou journal ; les règles bancaires
  existantes acceptent une valeur par axe.
- E10.4 Axe **obligatoire** pour certains comptes (contrôle à la saisie et à la clôture).
- E10.5 États par valeur d'axe : compte de résultat (existant, généralisé), balance et grand livre
  analytiques, croisement de deux axes (projet × financeur).
- E10.6 Budget : par valeur du **premier axe** comme aujourd'hui ; extension aux autres axes en Q10-2.

**Critères d'acceptation.** Une charge de loyer de structure ventilée par la clé 60 / 40 apparaît pour
60 % et 40 % dans les comptes de résultat des deux projets, et le total analytique égale le total général.

---

## 6. User stories

| # | En tant que… | je veux… | afin de… |
|---|---|---|---|
| US1 | expert-comptable | que les écritures validées soient intangibles et l'historique visible | certifier la tenue sans revue ligne à ligne |
| US2 | trésorier | verrouiller les mois rapprochés | ne pas les modifier par erreur |
| US3 | gérant de SCI | voir ce que chaque locataire doit, depuis la compta | relancer à bon escient |
| US4 | gérant de SCI | amortir l'immeuble par composants | tenir des comptes justes (et préparer un passage à l'IS) |
| US5 | trésorier | que les charges constatées d'avance soient proposées à la clôture | ne plus les calculer |
| US6 | nouvelle association | importer le FEC de son ancien logiciel | démarrer sans ressaisie |
| US7 | gérant de SCI | produire le décompte annuel de charges de chaque locataire | respecter le bail et récupérer les charges |
| US8 | trésorier d'un club | enregistrer les adhésions payées par chèque | avoir un fichier d'adhérents à jour sans HelloAsso |
| US9 | adhérent / locataire | télécharger mes reçus, factures, quittances | ne plus les demander |
| US10 | trésorier | ventiler par projet et par financeur | produire le compte rendu de chaque subvention |
| US11 | structure assujettie | recevoir mes factures par la plateforme agréée | respecter la réforme |
| US12 | structure assujettie | obtenir les montants de ma CA3 / CA12 | déclarer sans tableur |

## 7. Ordre proposé

1. **Lot F (fiabilité)** : E2 → E3 → E1 → E9 → E8 → E5. E2 et E3 d'abord (socle d'intangibilité),
   E1 ensuite (dont dépendent E36 relevé et E41 soldes), E5 en dernier (réutilise E1 et E2).
2. **Lot V (vie associative et SCI)** : E41 → E35 → E10 → E36 (l'espace tiers réunit les documents
   produits par les autres).
3. **Lot R (réglementaire)** : E7 → E29 → E30, quand une structure assujettie sera accueillie (CO4).

## 8. Questions ouvertes

| # | Question |
|---|---|
| Q2-1 | Pièces émises (factures de vente, reçus, quittances) : écritures **validées d'office**, ou en brouillard comme les autres ? |
| Q2-2 | Validation : faut-il **imposer** une validation périodique (ex. mensuelle) ou la laisser libre jusqu'à la clôture ? |
| Q3-1 | Pièce reçue datée d'une période verrouillée : **comptabiliser à la première date ouverte** ou **bloquer** jusqu'au déverrouillage ? |
| Q1-1 | Seuil d'écart de lettrage par défaut : 1 € ? Comptes d'écart à confirmer avec l'expert-comptable. |
| Q1-2 | À-nouveaux détaillés (lignes non lettrées) : pour tous les comptes lettrables, ou seulement 411 / 401 ? |
| Q8-1 | Amortissement dégressif utile (association fiscalisée) ou linéaire seul ? |
| Q8-2 | Subventions d'investissement (E8.7) : dans ce lot ou plus tard ? |
| Q8-3 | Mode simplifié : registre des immobilisations sans écritures, ou rien ? |
| Q8-4 | SCI à l'IR : amortissement comptable tenu malgré tout (pas déductible au 2072) ? Point à valider avec l'expert-comptable. |
| Q41-1 | Taxe foncière : la part TEOM seulement est récupérable (habitation) ; d'autres règles pour les baux commerciaux de la SCI ? |
| Q35-1 | Familles, activités, licences fédérales : utiles à Seconde Nature, ou seulement à d'autres associations (alors plus tard) ? |
| Q35-2 | Adhésions HelloAsso existantes : conversion automatique dans le nouveau modèle à la migration ? |
| Q36-1 | Espace tiers : un seul espace pour tous les types de tiers, ou espaces distincts (adhérent, locataire, client) ? |
| Q10-1 | Clés de répartition appliquées **à la saisie** (lignes ventilées tout de suite) ou **à la clôture** (écritures de répartition) ? |
| Q10-2 | Budget par axe autre que projet : nécessaire ? |
| Q29-1 | Plateforme agréée : laquelle (Qonto est-il immatriculé et son API couvre-t-elle la réception ? sinon SuperPDP, utilisé par Diacamma et enDI) ? À vérifier avant le design. |
| Q29-2 | Une SCI qui ne loue que des logements nus (exonérés) est-elle tenue de recevoir par plateforme ? À vérifier (le champ exact de l'obligation pour les assujettis exonérés). |
