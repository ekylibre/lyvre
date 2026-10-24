# Immobilisations et amortissements

Écran : **Compta › Immobilisations**. Méthodes reprises d'Ekylibre (`FixedAsset`).

## Fiche

- **Compte** (classe 2 ; 23x : immobilisation en cours), **acquisition**, **mise en service**,
  **valeur d'origine** (HT si l'exercice est soumis à la TVA, sinon TTC), valeur résiduelle.
- **Méthode** : linéaire, dégressif (coefficient fiscal proposé : 1,25 jusqu'à 4 ans, 1,75 jusqu'à
  6 ans, 2,25 au-delà), non amortissable (terrain…) ; **durée** en mois (taux affiché).
- **Reprise** d'un tableau existant : cumul déjà amorti à une date.
- **Projet** : les dotations lui sont affectées.
- **Composants** (« Ajouter un composant ») : un bien (immeuble de la SCI) découpé en terrain non
  amortissable, gros œuvre, toiture, installations…, chacun avec sa méthode et sa durée.
- Depuis une **facture d'achat** comptabilisée : « Créer l'immobilisation » sur une ligne au compte
  2x (fiche préremplie, durée de 5 ans à vérifier).

## Calcul

- **Année de 360 jours** : chaque mois compte 30 jours (un 31 ou un dernier jour de mois compte
  pour 30). Une mise en service le 15/03 donne 286 jours la première année civile.
- **Linéaire** : à partir de la mise en service ; chaque exercice reçoit le reste à amortir ×
  jours de l'exercice / jours restants du plan ; la dernière année solde exactement.
- **Dégressif** : à partir du 1er jour du mois d'acquisition ; reste × taux dégressif (ou taux
  linéaire sur les années restantes s'il est plus fort) × jours / 360.
- Les dotations **passées** sont figées : modifier la valeur ou la durée ne recalcule que la suite.
- **Tableau d'amortissement** sur la fiche : exercice, période, jours, dotation, cumul, valeur nette.

## Écritures

- **Mise en service** d'une immobilisation en cours : 2x au débit, 23x au crédit.
- **Dotations** : assistant de clôture, étape 2 (« Dotations aux amortissements ») : une écriture OD
  au dernier jour de l'exercice (6811 / 28x, une ligne par immobilisation), « Recalculer » tant que
  l'exercice est ouvert.
- **Sortie** (« Sortir de l'actif… ») : cession ou mise au rebut à une date : dotation
  complémentaire jusqu'à la date, puis 28x (cumul) et 675 (valeur nette) au débit, 2x au crédit ;
  prix de cession sans facture de vente : 462 / 775.
- Comptes par défaut : **Configuration › Comptes par défaut** (à valider par l'expert-comptable).

## Structures

- **SCI à l'IR** : amortissements non comptabilisés par défaut (registre et tableaux seulement), à
  décider avec l'expert-comptable (`organization.depreciation_enabled`).
- **Comptabilité simplifiée** : registre seulement.

## États

- Registre (valeur d'origine, amortissements, valeur nette, état).
- Tableau de l'annexe par compte (`GET /api/v1/fiscal-years/<id>/assets/annex`) : valeurs brutes et
  amortissements au début, augmentations, diminutions, fin.
