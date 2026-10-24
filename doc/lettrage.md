# Lettrage des comptes de tiers

Le lettrage relie, sur un compte de tiers (client 411…, fournisseur 401…, associé 455…), les lignes
qui se soldent : une facture et son règlement, un avoir, des acomptes. Il dit, depuis la
comptabilité elle-même, ce que chaque tiers doit encore. Écran : **Compta › Lettrage**.

## Comptes lettrables

Par défaut, les comptes de tiers : `40`, `41`, `42`, `43`, `441`, `45`, `467`, `468` (les comptes de
TVA `445` ne le sont pas). Un compte se rend lettrable ou non dans **Compta › Plan comptable**
(fiche du compte, case « Lettrable »). Les comptes 401NNN / 411NNN créés par Lyvre le sont d'office.

## Lettrage automatique

- **Factures de vente** : à chaque encaissement (transaction bancaire, chèque, espèces), à chaque
  avoir, la ligne client de la facture est lettrée avec celles de ses encaissements et avoirs —
  complet si la facture est soldée, **partiel** sinon (code en minuscules). Défaire un encaissement
  défait le lettrage.
- **Factures d'achat** : même chose avec les règlements (Qonto, relevé OFX, rapprochement).
- **Contrepassation** : l'écriture contrepassée est lettrée avec sa contrepassation.
- Un lettrage posé à la main sur ces lignes est respecté.
- **Pièces déjà payées** avant la mise à jour : bouton « Lettrer les pièces déjà payées »
  (administrateur), ou `scripts/lettering_reprise.py`.

## Lettrer à la main

1. Choisir le compte (la liste indique le nombre de lignes ouvertes) ; onglets **Non lettrées**,
   **Lettrées**, **Toutes**.
2. Sélectionner les lignes : clic, ou au clavier **Espace** (↑ ↓ pour se déplacer). Le total
   sélectionné (débit, crédit, solde) s'affiche en bas.
3. **Entrée** ou « Lettrer » : solde nul → lettrage complet (A, B… Z, AA…) ; sinon « Lettrer en
   partiel ». Ajouter une ligne à un lettrage partiel le complète.
4. **Écart** : si le reste est inférieur au seuil (1 € par défaut), « Lettrer avec écart » passe une
   écriture OD qui solde le reste en charge ou en produit divers, et le lettrage est complet.
5. **Propositions** : paires de montants opposés (même tiers, dates proches), puis combinaisons de 2
   ou 3 lignes ; « Accepter » ou « Tout accepter ».
6. **Délettrer** : sur une ligne lettrée ; l'écriture d'écart est retirée (contrepassée si validée).

Le lettrage ne modifie pas l'écriture : une ligne validée ou d'une période verrouillée se lettre et
se délettre.

## D'un exercice à l'autre

À l'ouverture de l'exercice suivant (assistant de clôture, étape 7), les comptes lettrables ne sont
pas repris en un solde : **chaque ligne non lettrée** (ou d'un lettrage partiel) devient une ligne
d'à-nouveau, avec sa référence et sa date. Une facture de décembre impayée se lettre ainsi avec son
encaissement de janvier.

## Où le retrouver

- **Fiche d'un tiers** : solde non lettré client / fournisseur, lien vers son lettrage.
- **FEC** : colonnes `EcritureLet` (code ; minuscules : partiel) et `DateLet`.

## Réglages

**Configuration › Comptes par défaut** (administrateur) : comptes de l'écart de lettrage (par défaut
6588 / 758 pour une association, 671 / 7718 pour une SCI — à faire valider par l'expert-comptable)
et seuil de l'écart.
