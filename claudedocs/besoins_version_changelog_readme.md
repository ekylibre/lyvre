# Besoins — numéro de version, changelog, README

Brainstorm du 26/10/2026.

## Constat

- Aucune version : `frontend/package.json` est en `0.0.0`, pas de tag git, rien n'est affiché dans
  l'application.
- Historique : 170 commits du 28/04/2026 au 26/10/2026, dont 158 en octobre (jusqu'à 57 le 23/10),
  organisés en lots nommés dans les messages (S1–S6 ventes, D comptabilité simplifiée, F1–F6
  fiabilité comptable, K1–K4 reprise Ekylibre, L1–L5 baux, G1–G5 Sirene, B1–B3 Brevo…). Mise en
  production sur Lyvre le 25/10/2026 (bascule depuis l'ancien service).
- README déjà soigné (logo, badges, 6 captures, tableau des fonctionnalités, démarrage), mais muet
  sur les baux et leur signature, la carte, la révision des loyers, les immobilisations, le
  lettrage, la reprise Ekylibre, Sirene et Brevo. Les captures viennent de
  `scripts/readme_screenshots.mjs` (`doc/images/`).

## Décisions de l'utilisateur

- **V1 — Schéma calendaire** `AAAA.MM.N` : année, mois, puis numéro d'ordre dans le mois, à partir
  de 1 (`2026.10.1`, `2026.10.2`…). Le premier publié en novembre sera `2026.11.1`.
- **V2 — Deux lectures du changelog** : une page « Nouveautés » dans l'application, pour les
  utilisateurs connectés, et `CHANGELOG.md` dans le dépôt, pour les développeurs et l'hébergeur.
- **V3 — Historique reconstitué** : versions rétroactives regroupées par lot, datées (sans tag :
  voir V8).
- **V4 — README** : contenu à jour, nouvelles captures sur des données de démonstration, mise en
  page plus visuelle (sections par public, démarrage rapide). Pas de version anglaise.

## Exigences — version

- **V-R1** — Une seule source pour le numéro, lue par le serveur et par l'interface (pas de
  numéro recopié à la main à deux endroits). `package.json` suit la même valeur (au format SemVer
  qu'il impose, par exemple `2026.10.3`).
- **V-R2** — Affichage : dans le menu de l'utilisateur, sur la page `/about` et dans la réponse de
  session (un administrateur voit quelle version tourne). Le commit déployé est indiqué à côté
  quand il est connu (image Docker).
- **V-R3** — Publier une version : incrémenter le numéro, compléter le changelog, poser le tag
  `v2026.10.N`. La procédure tient en une commande ou un court paragraphe documenté.

## Exigences — changelog

- **C-R1** — Une seule source de contenu pour les deux lectures (V2) : chaque version a une date,
  un numéro, un titre court, et des entrées classées (Nouveautés, Améliorations, Corrections,
  Action requise à la mise à jour).
- **C-R2** — Deux registres d'écriture : pour la page « Nouveautés », phrases pour un trésorier
  (ce qui change à l'écran) ; pour `CHANGELOG.md`, la même entrée peut porter une précision
  technique (migration, variable d'environnement, lot).
- **C-R3** — « Action requise » mise en évidence : migration manuelle, variable à ajouter
  (`SIRENE_API_KEY`), IP à autoriser (Brevo), réglage à faire après mise à jour.
- **C-R4** — Page « Nouveautés » : versions les plus récentes en tête ; un **repère « nouveau »**
  (pastille dans le menu) tant que l'utilisateur n'a pas ouvert la page depuis la dernière version,
  mémorisé par utilisateur.
- **C-R5** — Fonctions propres à une structure : une nouveauté réservée aux associations (Brevo) ou
  aux SCI (baux) est signalée comme telle, ou masquée pour l'autre structure (à trancher, Q3).
- **C-R6** — Historique rétroactif (V3) : de `2026.04.1` (import initial) à la version courante, en
  versions par lot ; la bascule de production du 25/10 est une version à part, repérable.

## Exigences — README

- **R-R1** — Accroche, valeur en une phrase, badges (licence, auto-hébergé, **version**, stack),
  capture principale.
- **R-R2** — Sections par public : association, SCI, expert-comptable, hébergeur (installation,
  sauvegardes, intégrations, variables).
- **R-R3** — Fonctionnalités à jour, cohérentes avec la page `/about` (même périmètre, sans
  copier-coller).
- **R-R4** — Nouvelles captures, toutes sur des **données de démonstration** (aucune donnée réelle
  d'une association, d'un adhérent ou d'un locataire) : carte des parcelles d'un bail, signature,
  revue Sirene, rapport Brevo, en plus des existantes rafraîchies. Thème clair et sombre.
- **R-R5** — Démarrage rapide en quelques commandes (Docker), lien vers la documentation détaillée
  et vers le changelog.
- **R-R6** — Rendu correct sur GitHub (clair et sombre), sans dépendance externe autre que les
  badges.

## Critères d'acceptation

- Le même numéro apparaît dans le menu utilisateur, sur `/about`, dans la session et dans le
  README ; il n'est écrit qu'à un endroit.
- Les versions rétroactives figurent dans le changelog (date, lot) ; `git tag` ne contient que les
  versions publiées à partir de maintenant.
- Après le déploiement d'une nouvelle version, un utilisateur voit la pastille « nouveau » ; elle
  disparaît une fois la page « Nouveautés » ouverte.
- `CHANGELOG.md` et la page « Nouveautés » montrent les mêmes versions et les mêmes entrées.
- Aucune capture du README ne montre de donnée réelle.

## Décisions complémentaires (26/10/2026)

- **V5 — Découpage rétroactif** : accepté sur le principe ; la liste des versions (numéro, date,
  lot) est proposée en conception et validée avant d'écrire le changelog.
- **V6 — Données de démonstration** : choix laissé à la conception → **script de démonstration**
  qui crée une instance association et une instance SCI fabriquées (aucune donnée réelle),
  relançable pour refaire les captures.
- **V7 — Nouveautés par structure** : affichées pour tous, avec une **étiquette** « Associations »
  ou « SCI » sur les entrées propres à une structure.
- **V8 — Tags** : **pas de tags rétroactifs**. Les versions passées n'existent que dans le
  changelog (date et lot) ; le premier tag `v2026.10.N` est posé à la prochaine publication.

## Questions ouvertes (pour la conception) — traitées ci-dessus

1. **Découpage rétroactif** : regroupement proposé à partir des messages de commit (une version par
   lot ou par journée chargée). Je proposerai la liste des versions en conception, à valider.
2. **Données de démonstration** pour les captures : jeu fabriqué existant des tests de bout en bout,
   ou nouvelle instance de démonstration (association + SCI) créée par un script ?
3. **Nouveautés par structure** (C-R5) : masquer pour l'autre structure, ou afficher avec une
   étiquette « Associations » / « SCI » ?
4. **Tags rétroactifs** : les poser sur l'historique publié et les pousser sur GitHub (visible de
   tous les clones), ou seulement à partir de la prochaine version ?
