# Saisie d'écritures et rapprochement bancaire

Deux écrans sont des **îlots React** utilisables entièrement au clavier : la saisie d'écriture
(`/entries/new`, `/entries/<id>/edit`) et l'espace de rapprochement (`/reconciliation/`). Ils
enregistrent via l'API JSON `/api/v1` ([routes.md](routes.md#api-json-apiv1)) ; la validation
comptable reste faite par le serveur, qui fait foi.

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

Impossible si l'exercice est clôturé ou si une ligne est rapprochée (annuler d'abord le
rapprochement). La référence d'origine est conservée.

---

## Espace de rapprochement

### Écran

- **À gauche** : les transactions non rapprochées du compte bancaire et du mois choisis (filtres
  repris dans l'URL). `★` = la transaction a une suggestion unique.
- **À droite** : les écritures candidates pour la transaction active, numérotées `1`…`9`.
  Candidates = lignes sur le **compte comptable du compte bancaire**, de **même montant et même
  sens**, non rapprochées, datées à ±3 jours ; la meilleure (`★`) est celle de même date si elle
  est seule à ce score.
- **Barre d'actions** sur la sélection : rapprocher les suggestions `★`, appliquer les règles,
  rapprochement automatique.

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
