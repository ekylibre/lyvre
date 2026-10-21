# Factures d'achat

Les factures fournisseurs reçues dans **Qonto** (facture électronique, transfert par e-mail, dépôt)
arrivent dans l'application, y sont **comptabilisées en engagement** et **réglées** à partir des
paiements Qonto. Qonto reste maître de ces factures : l'application ne les modifie jamais côté Qonto.
Les autres factures se **saisissent** dans l'application à partir de leur fichier (voir
[Saisir une facture](#saisir-une-facture)).

Menu **Factures d'achat** (`/purchases/`). Prérequis : intégration Qonto configurée
(Configuration › Intégrations › Qonto) et compte Qonto rattaché à un compte bancaire pour les
règlements (voir [Imports › Synchronisation Qonto](imports.md#synchronisation-qonto)).

## Mise en place

1. **Exercice et TVA** — Compta › Exercices : cochez **Soumis à la TVA** si l'organisation récupère la
   TVA sur l'exercice. Soumis : HT en charge, TVA en `44566` (à défaut `4456`). Non soumis (défaut) :
   charge TTC. Le changement ne vaut que pour les comptabilisations suivantes.
2. **Catalogue** — Compta › Catalogue : un produit ou service porte son compte de charge (6…), de
   produit (7…) et son taux de TVA par défaut (ex. « Électricité », 6061, 20 %). Un produit utilisé
   ne se supprime pas : archivez-le. « Achats divers » (6068 en association, 628 en SCI) est créé
   automatiquement et sert à défaut.
3. **Fournisseurs** — Tiers › Entités : sur la fiche, choisissez le **produit par défaut** ; il est
   repris sur les lignes de chaque nouvelle facture. L'identifiant Qonto, le n° de TVA, le SIRET,
   l'IBAN puis le nom servent, dans cet ordre, à reconnaître le fournisseur d'une facture.
4. **Date de début** (administrateur) — sur la page Factures d'achat, avant la première
   synchronisation ; défaut : début de l'exercice ouvert. La reculer plus tard relit tout depuis
   cette date, sans doublon.

## Au quotidien

**Synchroniser les factures Qonto** : la synchronisation tourne en arrière-plan ; le résumé indique
les factures nouvelles, mises à jour, comptabilisées, les règlements passés, les factures masquées
et celles à compléter.

| État | Signification |
|------|---------------|
| **À compléter** | Il manque quelque chose : fournisseur à rattacher, taux de TVA à confirmer (exercice soumis), ligne sans compte, total des lignes ≠ TTC, exercice absent ou clôturé… (motifs en infobulle et sur la fiche) |
| **Prête** | Complète : comptabilisée automatiquement (bouton de rattrapage « Comptabiliser les factures prêtes ») |
| **Comptabilisée** | Écriture d'achat passée au journal AC |
| **Masquée** | Rejetée ou écartée dans Qonto, ou document non financier : jamais comptabilisée (case « Masquées ») |

### Lignes

Qonto ne donne pas de lignes de facture : l'application en crée **une par taux de TVA** (ou une seule
si Qonto n'a pas de ventilation), avec le produit par défaut du fournisseur. Sur la fiche d'une
facture, modifiez le produit (il préremplit compte et taux), le compte, le libellé, le HT et le taux ;
la TVA laissée vide est calculée. Le total doit égaler le TTC de Qonto. Une fois enregistrées, les
lignes ne sont plus touchées par la synchronisation, et la facture est comptabilisée dès qu'elle est
complète.

### Écriture d'achat (journal AC, à la date de la facture)

| Compte | Débit | Crédit |
|--------|-------|--------|
| compte de chaque ligne (6…) | HT (soumis) ou TTC (non soumis) | |
| 44566 (soumis) | TVA | |
| compte du fournisseur 401NNN | | TTC |

Un **avoir** produit l'écriture inverse. Le compte du fournisseur est celui de sa fiche (convention
`401NNN`, ex. `401001`) ; il est créé dans le plan comptable s'il n'existe pas, et un fournisseur sans
code reçoit le numéro suivant libre.

**Annuler la comptabilisation** (fiche de la facture) supprime l'écriture d'achat et reprend les
dernières données de Qonto ; c'est la marche à suivre pour une facture signalée **à revoir** (modifiée
dans Qonto après comptabilisation : l'écriture n'est jamais corrigée d'office).

### Fournisseurs inconnus

Une facture dont le fournisseur n'est reconnu ni par son identifiant Qonto, ni par son n° de TVA,
son SIRET, son IBAN ou son nom est **à compléter**. Le lien « N fournisseur(s) à valider » ouvre
`/purchases/suppliers` : **Créer** le fournisseur (n° de TVA, IBAN et identifiant Qonto repris),
**Rattacher** à un tiers existant (noms ou IBAN proches suggérés) ou **Ignorer**. Le choix vaut pour
toutes ses factures et ses transactions bancaires de même nom ; les factures devenues complètes sont
aussitôt comptabilisées et réglées.

## Saisir une facture

**+ Nouvelle facture** (page Factures d'achat) : déposez le fichier (PDF, JPEG ou PNG, 10 Mo maximum)
puis **Lire la facture**. L'application lit, dans cet ordre, la facture électronique **Factur-X**
jointe au PDF (valeurs exactes), le texte du PDF, ou l'image par **OCR** (scan, photo : quelques
secondes, 3 premières pages). Le formulaire s'ouvre prérempli, la pièce affichée à côté ; les champs
**à vérifier** (lus par OCR, devinés ou incohérents : HT + TVA ≠ TTC) sont encadrés. Rien n'est
enregistré avant **Enregistrer la facture**. **Saisir sans fichier** ouvre un formulaire vide.

- **Fournisseur** : reconnu par son n° de TVA, son SIRET, son IBAN ou son nom ; sinon « Créer un
  fournisseur » est proposé avec le nom lu (modifiable). Les identifiants lus complètent la fiche.
- **Lignes** : une par taux de TVA, avec le produit par défaut du fournisseur ; modifiables comme sur
  la fiche. Le total des lignes doit égaler le TTC.
- **Remise après le total** (points fidélité d'un ticket de caisse) : déduite du TTC, qui devient le
  montant payé, et portée en ligne négative au compte de rabais obtenus (6098, à défaut 609).
- **Doublon** : même fournisseur et même n° (ou, sans n°, même date et même TTC) → avertissement ;
  cochez « Ce n'est pas un doublon » pour enregistrer quand même.

**Envoyer à Qonto** (instances où l'intégration Qonto est disponible, case cochée par défaut, fichier
obligatoire) : la pièce est déposée dans Qonto à l'enregistrement. Décochez-la pour une facture payée
par un autre compte. En cas d'échec, la facture reste enregistrée, marquée « envoi en échec » (motif
sur la fiche, badge dans la liste) : **Renvoyer à Qonto** recommence sans risque de doublon (même clé
d'idempotence). Quand Qonto renvoie la facture à la synchronisation, elle n'est pas recréée et **la
saisie l'emporte** : fournisseur, n°, dates, montants et lignes sont gardés ; Qonto complète les champs
vides et met à jour statut, date de paiement et transactions de paiement (règlement comme au lot 2a).
Une pièce envoyée ne se remplace plus.

La facture complète est comptabilisée aussitôt (journal AC). Tant qu'elle ne l'est pas, **Modifier
l'en-tête** (fiche) permet de corriger fournisseur, n°, dates, montants et de remplacer la pièce. La
pièce se consulte et se télécharge depuis la fiche ; elle est rangée dans le dossier de l'instance
(`instance/uploads/<instance>/achats/AAAA/MM/`). Filtre **Origine** de la liste : Qonto ou saisies.

## Règlements

Qonto indique les transactions qui ont payé chaque facture. Quand la transaction est importée dans le
compte bancaire et que la facture est comptabilisée, l'application passe le **règlement** au journal
BQ — débit 401NNN du fournisseur, crédit banque (sens inverse pour un remboursement d'avoir) — et le
**rapproche**, quel que soit l'ordre d'arrivée de la facture et du paiement. Les **règles de
catégorisation ignorent** ces transactions : la charge est dans l'écriture d'achat, pas dans le
paiement.

La fiche de la facture montre chaque paiement : réglé, en attente de comptabilisation, pas encore
importé, annulé par la banque, ou passé par une autre écriture. Dans le compte bancaire, une
transaction liée porte un badge « Facture n° … » et le filtre **Débit sans facture** liste les
paiements sans justificatif comptable.

### Factures payées hors Qonto (relevé OFX)

Une facture **saisie** et comptabilisée attend son paiement : l'application cherche, sur les comptes
bancaires non rattachés à Qonto, un débit du montant TTC entre la date de facture − 5 jours et
l'échéance (à défaut la date) + 60 jours. **Un seul débit possible** (et propre à cette facture) :
le règlement 401 / banque est passé et rapproché automatiquement, à la comptabilisation de la facture
ou à l'import du relevé OFX qui le contient (message après l'import). **Plusieurs** : la fiche les
propose, même fournisseur en premier — **Régler avec cette transaction**. Un règlement hors Qonto se
**défait** depuis la fiche (écriture supprimée, transaction de nouveau à rapprocher). Un débit déjà
passé par une règle peut être choisi : il rejoint les règlements à remplacer ci-dessous.

### Règlements à remplacer

Une transaction passée en charge par une règle (6xx / banque) **avant** l'arrivée de sa facture
compterait la charge deux fois. Le bandeau rouge de la liste mène à `/purchases/settlements` :
**Remplacer la sélection** supprime ces écritures de règle et passe à la place les règlements
fournisseur, rapprochés. Un rapprochement saisi à la main n'est jamais remplacé : il est seulement
listé pour vérification.
