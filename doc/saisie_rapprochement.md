# Saisie d'écritures et rapprochement bancaire

Deux écrans de la SPA (React + Mantine) s'utilisent entièrement au clavier : la saisie d'écriture
(`/entries/new`, `/entries/<id>/edit`) et l'espace de rapprochement (`/reconciliation/`, saisie
dans un panneau latéral avec la même logique). Ils enregistrent via l'API JSON `/api/v1`
([routes.md](routes.md#api-json-apiv1)) ; la validation comptable reste faite par le serveur, qui
fait foi.

---

## Saisie d'une écriture

### Déroulé

1. **En-tête** : exercice (exercices ouverts uniquement), journal, date, description. Une date hors
   de l'exercice choisi est signalée immédiatement.
2. **Lignes** : compte (autocomplétion par début de code ou mots du libellé, sans tenir compte des
   accents), libellé (par défaut, la description de l'écriture), débit **ou** crédit en euros
   (`84,50`, `1 234,56`).
3. L'**écart** débit − crédit s'affiche en direct ; le bouton **Enregistrer** reste désactivé tant
   que l'écriture n'est pas équilibrée ou qu'une erreur est signalée.
4. 400 ms après la dernière modification, le serveur valide l'écriture à blanc : ses erreurs
   s'affichent sous la cellule concernée (compte de regroupement, exercice clôturé…).

Les 20 derniers comptes utilisés sont proposés quand le champ compte est vide (mémorisés dans le
navigateur, par instance).

### Raccourcis

| Touche | Action |
|--------|--------|
| `Tab` / `Maj+Tab` | Champ suivant / précédent |
| `Entrée` dans la description | Aller au compte de la première ligne |
| `Entrée` dans un montant de la **dernière** ligne | Nouvelle ligne **préremplie avec l'écart**, focus sur son compte |
| `=` dans un montant | Mettre le montant qui équilibre l'écriture |
| `Alt+↓` / `Échap` | Ouvrir / fermer la liste des comptes ; `↑` `↓` puis `Entrée` (ou `Tab`) pour choisir |
| `Ctrl+Suppr` | Supprimer la ligne courante |
| `Ctrl+Entrée` | Enregistrer **et saisir la suivante** (exercice, journal et date conservés) |
| `Ctrl+Maj+Entrée` | Enregistrer et ouvrir l'écriture |

### Depuis une transaction bancaire

`/entries/new?bt_id=<id>` (bouton « Créer l'écriture » ou touche `N` du rapprochement) préremplit
la date, le journal `BQ`, l'exercice et la **ligne banque** (compte du compte bancaire, au débit pour
une entrée d'argent, au crédit pour une sortie). À l'enregistrement, l'écriture est créée **et**
rapprochée dans la même transaction : si l'écriture ne contient pas de ligne sur le compte bancaire
du même montant et du même sens, rien n'est enregistré.

### Modification

Impossible si l'exercice est clôturé, si l'écriture est **validée** ou dans une **période verrouillée**, ou si une ligne est rapprochée
(annuler d'abord le rapprochement). La référence d'origine est conservée.

### Validation et contrepassation

Une écriture est d'abord en **brouillard** (modifiable, supprimable), puis **validée** : elle reçoit
son numéro définitif, continu par journal et par exercice (celui du FEC), et ne se modifie plus.

- **Valider** : depuis la fiche, une sélection dans la liste (« Valider (n) »), ou « Valider
  jusqu'au… » (liste des écritures, Exercices › Lots). Chaque validation forme un **lot** ; les
  numéros sont attribués à la suite des numéros existants et ne changent plus. Une écriture
  déséquilibrée ou datée hors de l'exercice n'est pas validée (liste affichée).
- **Validées d'office** : les écritures des factures et avoirs de vente émis (elles se corrigent par
  un avoir). Les encaissements restent en brouillard tant qu'on ne les valide pas.
- **Contrepasser** (fiche d'une écriture validée) : date et motif ; une écriture inverse est passée au
  même journal. Un rapprochement bancaire est défait (la transaction redevient à rapprocher ;
  l'écriture contrepassée et sa contrepassation ne sont plus proposées). Une facture d'achat ou un
  règlement adossés redeviennent à comptabiliser.
- Quand Lyvre refait l'écriture d'une pièce (facture d'achat modifiée ou décomptabilisée,
  encaissement défait, écriture de règle remplacée par un règlement, intérêts d'associés recalculés)
  et que l'écriture est validée, il la **contrepasse** au lieu de la supprimer.
- **Projets** : une ligne validée s'affecte entière à un projet ; la ventilation se fait avant la
  validation.
- **Annuler le dernier lot** (administrateur, motif) : Exercices › Lots ; seul le dernier lot de
  l'exercice s'annule, pour garder une numérotation continue.
- **Historique** (fiche) : création, modifications (avant / après), validation, contrepassation,
  suppression, avec l'auteur ; visible par l'expert-comptable.
- Le tableau de bord signale les écritures en brouillard depuis plus de 3 mois.
- Comptabilité simplifiée : pas de validation (pas de FEC).

### Verrouillage des périodes

Exercices › colonne **Verrouillage** : « Verrouiller jusqu'au… » fige les mois déjà rapprochés ou
transmis à l'expert-comptable.

- Jusqu'à cette date, plus aucune écriture ne se saisit, ne se modifie ni ne se supprime (quel que
  soit l'écran : saisie, encaissement, règlement, règle…) ; le message donne la première date
  ouverte. Les écritures de l'assistant de clôture ne sont pas concernées.
- Verrouiller **valide** les écritures en brouillard de la période (aperçu avant de confirmer) ;
  une écriture déséquilibrée empêche le verrouillage.
- **Pièces reçues** après coup (factures d'achat Qonto ou saisies, règlements, transactions
  catégorisées par une règle, encaissements rapprochés) : passées à la **première date ouverte**,
  libellé préfixé « [pièce du JJ/MM/AAAA] » ; dans l'exercice suivant si celui-ci est entièrement
  verrouillé.
- **Déverrouiller…** (administrateur, motif) : recule la date ou retire le verrou ; rien n'est
  dévalidé ; tracé dans l'historique de la clôture.
- La clôture provisoire verrouille l'exercice entier ; la réouverture rétablit la date d'avant.

---

## Liste des transactions d'un compte

**Banque › Transactions** (un compte) : chaque ligne porte un **feu**, une icône de **type** et une
icône de **pièce** ; l'infobulle de chacun donne son libellé.

| Feu | Libellé | Quand |
|---|---|---|
| Vert | À jour | rapprochée avec son justificatif (ou sans justificatif exigé), **ou** facture liée et écriture passée (la facture tient lieu de justificatif), **ou** annulée par la banque et non rapprochée |
| Orange | À traiter | à rapprocher, justificatif manquant, ou passée par une règle avec le tiers par défaut |
| Rouge | Anomalie | annulée par la banque mais encore rapprochée, ou justificatif perdu |

- **Légende des feux** au-dessus du tableau : nombre de lignes par couleur ; un clic filtre le tableau,
  un second clic retire le filtre. Autre filtre : « Débit sans facture ».
- **Type** : carte, prélèvement, virement émis ou reçu, frais bancaires, chèque, retrait d'espèces
  (codes Qonto et OFX). **Pièce** : trombone (justificatif présent), fichier barré (manquant), point
  d'interrogation (perdu), rien pour un relevé OFX.
- **Catégorie** : celle de la règle de Lyvre, sinon celle de Qonto (en gris, infobulle « Catégorie Qonto »).
- **Actions** : la première est visible, les autres dans le menu « … » — Encaisser F-… (facture de vente
  ouverte de même montant), Créer la facture (justificatif Qonto), Attribuer / Changer le tiers,
  Nouvelle écriture, Rapprocher. Aucune pour le comptable.

## Espace de rapprochement

### Écran

- **À gauche** : les transactions non rapprochées du compte bancaire et du mois choisis (filtres
  repris dans l'URL), avec leur feu, leur type et leur pièce comme dans la
  [liste des transactions](#liste-des-transactions-dun-compte). `★` = la transaction a une suggestion unique.
- **À droite** : les écritures candidates pour la transaction active, numérotées `1`…`9`.
  Candidates = lignes sur le **compte comptable du compte bancaire**, de **même montant et même
  sens**, non rapprochées, datées à ±3 jours ; la meilleure (`★`) est celle de même date si elle
  est seule à ce score.
- **Barre d'actions** sur la sélection : rapprocher les suggestions `★`, appliquer les règles,
  rapprochement automatique.

### Règles de catégorisation et comptes de tiers

En **partie double**, une règle ne passe jamais la charge ou le produit directement contre la banque :
elle passe une **pièce** (journal AC : charge / tiers ; journal VE : tiers / produit) et un
**règlement** tiers / banque rapproché de la transaction, lettrés entre eux. Le tiers est celui de la
règle s'il a un compte, sinon le tiers par défaut **401000 « Fournisseurs divers »** ou
**411000 « Clients divers »**. Ensuite :

- la **facture** qui arrive (achat comptabilisé lié à la transaction, ou facture de vente encaissée
  par elle) **remplace automatiquement** les deux écritures par le règlement du vrai tiers ;
- sans facture, **Banque › Transactions › Attribuer le tiers** (actions de la ligne) repasse les deux écritures
  sur le compte du tiers choisi (créé au besoin) ; validées, elles sont contrepassées.

En comptabilité **simplifiée** (trésorerie), la règle passe une seule écriture banque / 6… ou 7….

### Raccourcis

| Touche | Action |
|--------|--------|
| `↑` `↓` (ou `k` `j`) | Transaction précédente / suivante (suggestions chargées à l'avance) |
| `Entrée` | Rapprocher la transaction active avec la suggestion `★` |
| `1` … `9` | Rapprocher avec la suggestion n° |
| `Espace` | Sélectionner / désélectionner la transaction active |
| `Maj+↑` `Maj+↓` | Étendre la sélection |
| `Ctrl+A` / `Échap` | Tout sélectionner / tout désélectionner |
| `N` | Créer l'écriture de la transaction dans un panneau (créée + rapprochée) |
| `R` | Appliquer les règles de catégorisation à la sélection (ou à la transaction active) |
| `Ctrl+Z` | Annuler la dernière action |

### Contrôles

Un rapprochement est refusé (et signalé) si la transaction ou la ligne est déjà rapprochée, si la
ligne n'est pas sur le compte comptable du compte bancaire ou si les montants diffèrent. Dans une
action groupée, chaque transaction est traitée séparément : les refus n'empêchent pas les autres.

Le **rapprochement automatique** ne retient que les cas sans ambiguïté : une seule ligne candidate
**de même date**, qui n'est candidate pour aucune autre transaction. Il porte sur la sélection si
elle existe, sinon sur tout le compte.

### Annulation

Après chaque action, un bandeau « Annuler (Ctrl+Z) » reste affiché 10 secondes. L'annulation
rejoue l'opération inverse renvoyée par le serveur :

| Action | Annulation |
|--------|------------|
| Rapprocher | Défait les rapprochements réussis |
| Appliquer les règles | Supprime les écritures générées (et leurs rapprochements) ; la **catégorie et le tiers** affectés aux transactions sont conservés |

Rien n'est mémorisé côté serveur : recharger la page fait perdre la possibilité d'annuler (l'action
reste réversible à la main).

---

## Accessibilité

- Navigation complète au clavier, focus visible, aide des raccourcis sous chaque écran.
- Autocomplétion des comptes au motif ARIA « combobox » ; erreurs liées aux champs
  (`aria-describedby`, `aria-invalid`).
- Écart, compteurs et transaction active annoncés aux lecteurs d'écran (`aria-live`).
- Le panneau de saisie du rapprochement est une fenêtre modale : le focus y reste (`Tab` boucle),
  `Échap` la ferme et rend le focus à la liste.
