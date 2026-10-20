# Besoins — Front réactif

> Statut : besoins validés (brainstorm du 2026-10-20). Étape suivante : `/sc:design` pour choisir
> l'architecture (React/Vite, HTMX + Alpine, ou hybride), puis `/sc:workflow` pour le plan.

## 1. Contexte

| Constat (état au commit `3de8b09`) | Valeur |
|------------------------------------|--------|
| Templates Jinja | 70 (~5 700 lignes), 23 blueprints |
| Écrans utilisant HTMX | 6 (sync Stancer, suggestions de rapprochement, lignes d'écriture…) |
| Routes JSON | 1 |
| JavaScript applicatif | `app.js`, 28 lignes |
| Filtres déclenchant un rechargement complet (`onchange="this.form.submit()"`) | 10 écrans |

Le manque de réactivité vient surtout du modèle « une action = une page HTML complète » :
rechargement, perte du scroll et de la sélection, aucun retour avant la réponse du serveur.

## 2. Objectifs

- **O1 — Tous les écrans réactifs** : plus aucun rechargement complet de page pour les actions courantes
  (filtres, tri, changement d'exercice/mois, pagination, actions sur une ligne, formulaires).
- **O2 — Saisie et rapprochement efficaces** pour un usage intensif au clavier.
- **O3 — Maintenance soutenable par une seule personne** : limiter le volume de code à porter et
  le nombre de technologies à maîtriser.

## 3. Utilisateurs

| Profil | Usage | Attentes |
|--------|-------|----------|
| Trésorier / comptable | Intensif, ordinateur : saisie, imports, rapprochement, états | Rapidité, clavier, traitement en masse, aucune perte de contexte |
| Bénévoles occasionnels | Ponctuel : temps de travaux, adhérents, consultation | Simplicité, retours clairs, pas de formation nécessaire |

L'usage mobile n'est pas une priorité (affichage correct seulement, pas d'optimisation dédiée).

## 4. Besoins fonctionnels

### F1 — Navigation et listes (tous les écrans)
- F1.1 Filtres, tri, recherche, changement d'exercice / mois **sans rechargement**, avec mise à jour
  de l'URL (lien partageable, bouton Précédent fonctionnel, rafraîchissement F5 conservé).
- F1.2 Conservation du scroll, de la sélection et des filtres après une action.
- F1.3 Indicateur de chargement visible pour toute action de plus de ~300 ms.
- F1.4 Actions sur une ligne (supprimer, marquer, synchroniser) mises à jour **en place**.

### F2 — Saisie d'écritures
- F2.1 **Clavier d'abord** : Tab / Entrée pour enchaîner champs et lignes, ajout de ligne au clavier,
  raccourci pour enregistrer et enchaîner sur une nouvelle écriture.
- F2.2 **Autocomplétion** des comptes (code ou libellé) et des tiers.
- F2.3 **Validation immédiate** : équilibre débit/crédit en direct, compte inexistant ou d'en-tête,
  exercice clôturé, date hors exercice — signalés pendant la saisie, avant envoi.
- F2.4 Après enregistrement : retour visuel, formulaire réinitialisé, journal / date conservés.

### F3 — Rapprochement bancaire et imports
- F3.1 Suggestions affichées sans quitter la liste ; rapprocher / annuler **en place** avec mise à
  jour des compteurs (non rapprochées, soldes).
- F3.2 **Traitement en masse** : sélection multiple (y compris au clavier), rapprochement /
  catégorisation groupés, application de règles à une sélection.
- F3.3 **Annulation** d'une action groupée ou unitaire juste après l'avoir faite.
- F3.4 Imports (OFX, CSV Odoo, xlsx) : progression visible, puis récapitulatif
  (importées / doublons / erreurs) sans rechargement.
- F3.5 Détection et signalement des doublons pendant l'import et la saisie.

### F4 — Autres écrans
- F4.1 Tableaux de bord, états financiers, listes de tiers, temps de travaux, synchronisations
  (Stancer, Odoo, HelloAsso) : même niveau de réactivité que F1.
- F4.2 Les spécificités existantes sont conservées : menus par plan comptable (`asso` / `sci`),
  droits admin, multi-instance, impression / exports (PDF, CSV, ODS, DOCX/ODT).

## 5. Besoins non fonctionnels

| # | Exigence |
|---|----------|
| NF1 | **Toolchain** : Node accepté **en développement et en CI uniquement** ; l'image Docker de production reste Python (le front compilé est servi par Flask) |
| NF2 | **Même dépôt** (pas de dépôt front séparé) |
| NF3 | **Migration progressive** : l'application reste utilisable à chaque étape, écran par écran ; ancien et nouveau front cohabitent |
| NF4 | **Effort limité / maintenance solo** : minimiser le code dupliqué entre Python et JS (règles de validation, libellés, logique comptable restent côté serveur, source de vérité) |
| NF5 | **Sécurité inchangée** : session Flask-Login, protection CSRF, isolement des instances (tenant) et droits admin appliqués à toute nouvelle route |
| NF6 | **Performance perçue** : retour visuel < 100 ms sur interaction locale ; réponse d'action courante < 500 ms sur une base d'association typique |
| NF7 | **Tests** : la suite pytest actuelle (133 tests) reste verte ; les nouveaux échanges serveur sont testés |
| NF8 | **Accessibilité** : navigation clavier complète, focus visible, messages d'erreur liés aux champs |
| NF9 | Montants toujours en centimes entiers côté serveur ; formatage euros cohérent entre écrans |

## 6. Récits utilisateur et critères d'acceptation

**US1 — Filtrer sans perdre sa place**
En tant que trésorier, je change le mois dans la liste des écritures sans que la page se recharge.
- La liste se met à jour, l'URL contient `month=YYYY-MM`, F5 réaffiche le même état.
- Le bouton Précédent revient au filtre antérieur.

**US2 — Saisir une série d'écritures au clavier**
En tant que trésorier, je saisis 10 écritures à la suite sans toucher la souris.
- Tab / Entrée enchaînent les champs et les lignes ; l'autocomplétion des comptes répond à la frappe.
- Le bouton Enregistrer reste inactif tant que débit ≠ crédit, avec l'écart affiché.
- Après enregistrement, une nouvelle écriture est prête, journal et date conservés.

**US3 — Rapprocher un relevé en masse**
En tant que trésorier, je sélectionne 20 transactions et je les rapproche en une action.
- Chaque ligne traitée change d'état en place ; les compteurs se mettent à jour.
- Je peux annuler l'opération juste après ; les lignes reviennent à l'état « non rapprochée ».

**US4 — Importer un relevé**
En tant que trésorier, j'importe un fichier OFX et je vois la progression puis le récapitulatif
(importées, doublons ignorés, erreurs) sans quitter l'écran.

**US5 — Bénévole occasionnel**
En tant que bénévole, je saisis mes temps de travaux ; les erreurs (type manquant, heures
invalides) s'affichent à côté du champ concerné, avant l'envoi.

## 7. Hors périmètre
- Application mobile dédiée, mode hors ligne.
- Collaboration temps réel entre plusieurs utilisateurs sur le même écran.
- Changement de stack backend (Flask, SQLAlchemy, SQLite restent en place).
- Refonte graphique (identité visuelle actuelle Bootstrap conservée, sauf besoin d'ergonomie).

## 8. Questions ouvertes (à trancher en `/sc:design`)

1. **Technologie** : la demande initiale cite React. Les besoins F1 à F4 peuvent aussi être couverts
   par un rendu serveur partiel (HTMX + un peu d'Alpine.js), plus léger à maintenir seul (NF4).
   Une option hybride est possible : îlots React (ou équivalent) pour la saisie et le rapprochement,
   HTMX pour les listes. Critères de choix : volume de code à porter, duplication de la
   validation (NF4), cohabitation pendant la migration (NF3), expérience clavier (F2/F3).
2. **API** : si React est retenu, faut-il une API JSON générale, ou seulement des routes JSON
   pour les écrans réécrits ?
3. **Ordre de migration** : proposition à valider — (1) saisie d'écritures, (2) rapprochement et
   imports, (3) listes avec filtres (les 10 écrans en `onchange=submit`), (4) le reste.
4. **Annulation (F3.3)** : simple « annuler la dernière action » à l'écran, ou historique conservé ?
5. **Exports et impression** : restent des pages serveur dédiées (recommandé) ou s'intègrent au nouveau front ?
